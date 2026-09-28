"""
face_recognizer.py
==================
InsightFace-based face recognition module used as the PRIMARY identity verifier
for registered persons (Ganesh, Lakshay, etc.).

Strategy:
  - Uses ArcFace (buffalo_sc or buffalo_l) — state-of-the-art face recognition
  - Extracts a 512-d face embedding from the person crop
  - Much more discriminative than OSNet body Re-ID for same-looking individuals
  - Falls back gracefully if no face is detected in the crop
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


class FaceRecognizer:
    """
    Wrapper around InsightFace ArcFace for face embedding extraction and matching.
    """

    def __init__(
        self,
        model_name: str = "buffalo_sc",   # lightweight; use 'buffalo_l' for higher accuracy
        device: str = "cpu",              # 'cpu' or 'cuda:0'
        det_size: Tuple[int, int] = (320, 320),
        face_sim_threshold: float = 0.40,  # cosine similarity threshold (ArcFace space)
    ) -> None:
        self.face_sim_threshold = face_sim_threshold
        self._available = False

        try:
            import insightface
            from insightface.app import FaceAnalysis

            ctx_id = -1  # CPU
            if device.startswith("cuda"):
                try:
                    gpu_id = int(device.split(":")[-1])
                    ctx_id = gpu_id
                except ValueError:
                    ctx_id = 0

            self._app = FaceAnalysis(
                name=model_name,
                allowed_modules=["detection", "recognition"],
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"] if ctx_id >= 0
                          else ["CPUExecutionProvider"],
            )
            self._app.prepare(ctx_id=ctx_id, det_size=det_size)
            self._available = True
            print(f"[FaceRecognizer] InsightFace '{model_name}' loaded (device={device})")
        except Exception as exc:
            print(f"[FaceRecognizer] WARNING: Could not load InsightFace — {exc}")
            print("[FaceRecognizer] Falling back to OSNet-only mode.")

    @property
    def available(self) -> bool:
        return self._available

    # ------------------------------------------------------------------
    def get_face_embedding(self, person_crop: np.ndarray) -> Optional[np.ndarray]:
        """
        Given a BGR person crop, detect the largest face and return its
        512-d ArcFace embedding (L2-normalised), or None if no face found.
        """
        if not self._available:
            return None
        if person_crop is None or person_crop.size == 0:
            return None

        # InsightFace wants BGR — that's what we already have from OpenCV
        try:
            faces = self._app.get(person_crop)
        except Exception:
            return None

        if not faces:
            return None

        # Pick the largest detected face
        best_face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        emb = best_face.normed_embedding  # already L2-normalised 512-d
        return emb.astype(np.float32) if emb is not None else None

    def get_face_data_from_frame(
        self, frame: np.ndarray, xyxy: np.ndarray
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Return (embedding, absolute_face_bbox) for the largest face in a person box."""
        if not self._available:
            return None, None
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = xyxy.astype(int)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w - 1, x2), min(h - 1, y2)
        if x2 <= x1 or y2 <= y1:
            return None, None
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None, None
        try:
            faces = self._app.get(crop)
        except Exception:
            return None, None
        if not faces:
            return None, None
        best_face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        emb = best_face.normed_embedding
        local_box = np.asarray(best_face.bbox, dtype=float)
        abs_box = local_box + np.asarray([x1, y1, x1, y1], dtype=float)
        return (emb.astype(np.float32) if emb is not None else None), abs_box

    def get_face_embedding_from_frame(
        self, frame: np.ndarray, xyxy: np.ndarray
    ) -> Optional[np.ndarray]:
        """Extract face embedding from a person bounding box in a full frame."""
        emb, _ = self.get_face_data_from_frame(frame, xyxy)
        return emb

    # ------------------------------------------------------------------
    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Dot product of two L2-normalised vectors = cosine similarity."""
        return float(np.dot(a, b))

    def match_against_gallery(
        self,
        query_emb: np.ndarray,
        gallery: Dict[int, np.ndarray],
        threshold: Optional[float] = None,
    ) -> Tuple[Optional[int], float]:
        """
        Find the best matching identity in the gallery.
        Returns (best_id, best_score) or (None, best_score) if below threshold.
        """
        threshold = threshold if threshold is not None else self.face_sim_threshold
        best_id = None
        best_score = -1.0

        for gid, ref_emb in gallery.items():
            score = self.cosine_similarity(query_emb, ref_emb)
            if score > best_score:
                best_score = score
                best_id = gid

        if best_score < threshold:
            return None, best_score
        return best_id, best_score


# ------------------------------------------------------------------
# Standalone registration helper
# ------------------------------------------------------------------
def extract_face_embedding_from_image(
    image_path: str,
    recognizer: FaceRecognizer,
) -> Optional[np.ndarray]:
    """Read an image file and return its face embedding."""
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"[FaceRecognizer] Could not read: {image_path}")
        return None
    h, w = frame.shape[:2]
    full_box = np.array([0, 0, w, h], dtype=float)
    return recognizer.get_face_embedding_from_frame(frame, full_box)
