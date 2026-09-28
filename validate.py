"""Validation: check face separation between Ganesh and Lakshay embeddings."""
import numpy as np
import yaml
from database import IdentityDatabase
from face_recognizer import FaceRecognizer
from identity_manager import GlobalIdentityManager

cfg = yaml.safe_load(open("config.yaml"))
face_cfg = cfg.get("face_recognition", {})
threshold = face_cfg.get("face_threshold", 0.52)

db = IdentityDatabase(cfg["database"]["db_path"])
ids = db.load_registered_identities()
db.close()

names = {
    v["name"]: np.asarray(v["face_embedding"], dtype="float32")
    for v in ids.values()
    if v.get("face_embedding") is not None
}

print("=== Face Embedding Validation ===")
print(f"Registered with face embeddings: {list(names.keys())}")
print(f"Current face_threshold in config: {threshold}")

n = list(names.keys())
if len(n) >= 2:
    sim = float(np.dot(names[n[0]], names[n[1]]))
    print(f"\nFace similarity {n[0]} vs {n[1]}: {sim:.4f}")
    margin = threshold - sim
    if margin > 0.05:
        print(f"GOOD: Threshold {threshold} is {margin:.4f} above their similarity — clear separation.")
    else:
        print(f"WARNING: Threshold {threshold} is only {margin:.4f} above their similarity. Consider raising threshold.")

fr = FaceRecognizer(model_name=face_cfg.get("model_name", "buffalo_l"), device="cpu")
print(f"\nFaceRecognizer available: {fr.available}")
print("Validation complete.")
