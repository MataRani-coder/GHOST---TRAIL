from database import IdentityDatabase
import numpy as np

db = IdentityDatabase("tracker.db")
ids = db.load_registered_identities()
for gid, info in ids.items():
    name = info["name"]
    body_shape = info["embedding"].shape
    face = info.get("face_embedding")
    face_info = f"shape={face.shape}" if face is not None else "NONE"
    print(f"ID={gid}, name={name}, body={body_shape}, face={face_info}")
db.close()
