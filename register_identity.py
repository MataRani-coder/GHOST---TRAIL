from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import yaml

from database import IdentityDatabase
from detector import YoloDetector
from face_recognizer import FaceRecognizer
from tracker import DeepReIDExtractor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register a known identity from image(s).")
    parser.add_argument("--name", required=True, help="Person name to register.")
    parser.add_argument(
        "--input",
        required=True,
        help="Path to an image file or a directory containing images.",
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML.")
    parser.add_argument("--force", action="store_true", help="Force registration even if similar person exists.")
    parser.add_argument("--update-id", type=int, default=None, help="Update an existing identity ID instead of creating a new one.")
    return parser.parse_args()


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_images(path: Path) -> List[Path]:
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted([p for p in path.iterdir() if p.is_file() and p.suffix.lower() in image_exts])
    return []


def pick_person_bbox(detections, person_class_id: int) -> np.ndarray | None:
    if len(detections) == 0 or detections.class_id is None:
        return None
    best_idx = -1
    best_area = -1.0
    for i in range(len(detections)):
        cls_id = int(detections.class_id[i])
        if cls_id != person_class_id:
            continue
        x1, y1, x2, y2 = detections.xyxy[i]
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        if area > best_area:
            best_area = area
            best_idx = i
    if best_idx < 0:
        return None
    return detections.xyxy[best_idx]


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)

    db = IdentityDatabase(cfg["database"]["db_path"])
    detector = YoloDetector(
        weights=cfg["model"]["weights"],
        device=cfg["model"].get("device", "auto"),
        conf_thres=cfg["model"].get("conf_thres", 0.35),
        iou_thres=cfg["model"].get("iou_thres", 0.50),
        classes=cfg["model"].get("classes"),
    )
    body_extractor = DeepReIDExtractor(
        model_name=cfg["reid"].get("model_name", "osnet_x1_0"),
        model_weights=cfg["reid"].get("reid_model_weights"),
        device=cfg["reid"].get("device", cfg["model"].get("device", "cpu")),
        input_size=tuple(cfg["reid"].get("input_size", [256, 128])),
    )

    # Initialize ArcFace face recognizer for registration
    face_cfg = cfg.get("face_recognition", {})
    face_recognizer = FaceRecognizer(
        model_name=face_cfg.get("model_name", "buffalo_sc"),
        device=face_cfg.get("device", cfg["reid"].get("device", "cpu")),
        det_size=tuple(face_cfg.get("det_size", [320, 320])),
    )

    person_class_id = int(cfg["reid"].get("person_class_id", 0))
    input_path = Path(args.input)
    image_paths = list_images(input_path)
    if not image_paths:
        db.close()
        raise SystemExit(f"[ERROR] No valid images found at: {input_path}")

    body_embeddings: List[np.ndarray] = []
    face_embeddings: List[np.ndarray] = []

    for img_path in image_paths:
        frame = cv2.imread(str(img_path))
        if frame is None:
            print(f"[WARN] Could not read image: {img_path}")
            continue

        # ── Body Re-ID embedding (OSNet) ─────────────────────────────
        detections = detector.infer(frame)
        bbox = pick_person_bbox(detections, person_class_id=person_class_id)

        if bbox is not None:
            body_emb = body_extractor.encode(frame, bbox)
            if body_emb is not None:
                body_embeddings.append(body_emb)
                print(f"  [BODY OK] {img_path.name}")
            else:
                print(f"  [BODY FAIL] Re-ID embedding failed for: {img_path.name}")
        else:
            # Try whole-image crop for face-only photos (e.g., portrait shots)
            print(f"  [WARN] No full-body detection in {img_path.name}, trying whole image for face.")

        # ── Face embedding (ArcFace) ─────────────────────────────────
        h, w = frame.shape[:2]
        full_box = np.array([0, 0, w, h], dtype=float)
        face_emb = face_recognizer.get_face_embedding_from_frame(frame, full_box)
        if face_emb is not None:
            face_embeddings.append(face_emb)
            print(f"  [FACE OK] {img_path.name}")
        else:
            print(f"  [FACE NONE] No face detected in: {img_path.name}")

    if not body_embeddings and not face_embeddings:
        db.close()
        raise SystemExit("[ERROR] No usable embeddings extracted. Registration aborted.")

    # ── Average body embeddings ───────────────────────────────────────
    mean_body: Optional[np.ndarray] = None
    if body_embeddings:
        stacked = np.stack(body_embeddings, axis=0)
        mean_body = stacked.mean(axis=0).astype(np.float32)
        norm = np.linalg.norm(mean_body)
        if norm > 1e-8:
            mean_body = mean_body / norm
    else:
        # Fallback zero vector so DB insert doesn't fail
        mean_body = np.zeros((512,), dtype=np.float32)

    # ── Average face embeddings ───────────────────────────────────────
    mean_face: Optional[np.ndarray] = None
    if face_embeddings:
        stacked_face = np.stack(face_embeddings, axis=0)
        mean_face = stacked_face.mean(axis=0).astype(np.float32)
        norm_f = np.linalg.norm(mean_face)
        if norm_f > 1e-8:
            mean_face = mean_face / norm_f
            
        # --- SIMILARITY CHECK ---
        if not args.force:
            identities = db.load_registered_identities()
            best_match_id = None
            best_match_name = None
            best_match_score = -1.0
            for gid, info in identities.items():
                ref_face = info.get("face_embedding")
                if ref_face is not None:
                    score = float(np.dot(mean_face, ref_face))
                    if score > best_match_score:
                        best_match_score = score
                        best_match_id = gid
                        best_match_name = info["name"]
            
            face_threshold = cfg.get("face_recognition", {}).get("face_threshold", 0.45)
            if best_match_score > face_threshold:
                import json
                import sys
                print(json.dumps({
                    "conflict": True,
                    "id": best_match_id,
                    "name": best_match_name,
                    "score": best_match_score
                }))
                db.close()
                sys.exit(2)
                
        print(f"[INFO] Face embeddings averaged from {len(face_embeddings)} images.")
    else:
        print("[WARN] No face embeddings collected — only body Re-ID will be used for this person.")

    if args.update_id is not None:
        identity_id = args.update_id
        existing_id = args.update_id
    else:
        existing_id = db.get_identity_id_by_name(args.name)
        identity_id = existing_id if existing_id is not None else (db.get_max_identity_id() + 1)
    db.upsert_identity(
        identity_id=identity_id,
        name=args.name,
        embedding=mean_body,
        face_embedding=mean_face,
    )
    db.close()

    mode = "updated" if existing_id is not None else "registered"
    print(
        f"[INFO] Identity {mode}: name='{args.name}', id={identity_id}, "
        f"body_samples={len(body_embeddings)}, face_samples={len(face_embeddings)}"
    )


if __name__ == "__main__":
    main()
