"""
calibrate_threshold.py
======================
Run this script ONCE while standing in front of the camera (or use your
registered images) to measure the ACTUAL face similarity scores the system
produces for Ganesh and Lakshay.

Usage:
  python calibrate_threshold.py

Output: shows similarity scores so you know what threshold to set.
"""
from __future__ import annotations

import cv2
import numpy as np
import yaml

from database import IdentityDatabase
from face_recognizer import FaceRecognizer


def load_config(path: str = "config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    cfg = load_config()
    face_cfg = cfg.get("face_recognition", {})

    db = IdentityDatabase(cfg["database"]["db_path"])
    registered = db.load_registered_identities()
    db.close()

    # Only keep entries that have a face embedding
    gallery = {
        gid: {"name": info["name"], "emb": np.asarray(info["face_embedding"], dtype=np.float32)}
        for gid, info in registered.items()
        if info.get("face_embedding") is not None
    }

    if not gallery:
        print("[ERROR] No face embeddings found in DB. Re-run register_identity.py first.")
        return

    fr = FaceRecognizer(
        model_name=face_cfg.get("model_name", "buffalo_l"),
        device=face_cfg.get("device", "cpu"),
        det_size=tuple(face_cfg.get("det_size", [320, 320])),
    )

    if not fr.available:
        print("[ERROR] FaceRecognizer not available.")
        return

    print("\n" + "=" * 60)
    print("FACE THRESHOLD CALIBRATION")
    print("=" * 60)
    print(f"Registered people: {[v['name'] for v in gallery.values()]}")
    print(f"Current face_threshold in config: {face_cfg.get('face_threshold', '?')}")
    print("\nPress SPACE to capture a measurement, Q to quit.")
    print("Tip: stand in front of the camera and press SPACE.\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Cannot open camera.")
        return

    measurements = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]
        full_box = np.array([0, 0, w, h], dtype=float)
        face_emb = fr.get_face_embedding_from_frame(frame, full_box)

        display = frame.copy()
        if face_emb is not None:
            scores = {}
            for gid, info in gallery.items():
                score = float(np.dot(face_emb, info["emb"]))
                scores[info["name"]] = score

            y = 30
            for name, score in scores.items():
                color = (0, 220, 0) if score >= face_cfg.get("face_threshold", 0.52) else (0, 80, 220)
                cv2.putText(display, f"{name}: {score:.4f}", (10, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                y += 35

            cv2.putText(display, "FACE DETECTED", (10, y + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 0), 2)
        else:
            cv2.putText(display, "No face detected", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 220), 2)

        cv2.putText(display, "SPACE=capture  Q=quit", (10, display.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
        cv2.imshow("Threshold Calibration", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord(" ") and face_emb is not None:
            print("\n--- Captured measurement ---")
            for name, score in scores.items():
                flag = " ← above threshold" if score >= face_cfg.get("face_threshold", 0.52) else ""
                print(f"  {name}: {score:.4f}{flag}")
            measurements.append(scores)

    cap.release()
    cv2.destroyAllWindows()

    if measurements:
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        for name in gallery.values():
            name = name["name"]
            vals = [m[name] for m in measurements if name in m]
            if vals:
                print(f"  {name}: min={min(vals):.4f}  max={max(vals):.4f}  avg={sum(vals)/len(vals):.4f}")
        threshold = face_cfg.get("face_threshold", 0.52)
        print(f"\nCurrent threshold: {threshold}")
        print("Recommendation: set face_threshold to ~85% of the LOWEST score you see")
        print("for the correct person. Example: if Ganesh min score = 0.60, set threshold = 0.51")


if __name__ == "__main__":
    main()
