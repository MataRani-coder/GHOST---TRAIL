"""
sentinel_server.py
==================
Internal FastAPI server embedded inside sentinel.exe.
- Serves the built React dashboard (static files from dashboard/dist/)
- Provides REST endpoints for camera info, persons, alerts, settings
- Streams live MJPEG camera frames via /api/stream/<camera_id>
- Broadcasts real-time detections/alerts over WebSocket /api/ws
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import cv2
import numpy as np
import uvicorn
import yaml
import subprocess
import shutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


# ──────────────────────────────────────────────────────────────────────────────
# Helpers to resolve bundled asset paths (works both in .py and PyInstaller .exe)
# ──────────────────────────────────────────────────────────────────────────────

def _base_dir() -> Path:
    """Return the base directory of the bundled executable or the script directory."""
    if getattr(sys, "frozen", False):
        # Running inside PyInstaller bundle
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).parent


BASE_DIR = _base_dir()
STATIC_DIR = BASE_DIR / "dashboard" / "dist"

def _safe_gallery_stem(name: str) -> str:
    """Canonical filename stem used for enrolled face images."""
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name)).strip("._")
    return stem or "person"

CONFIG_PATH = BASE_DIR / "config.yaml"


# ──────────────────────────────────────────────────────────────────────────────
# Shared state (written by tracker thread, read by API)
# ──────────────────────────────────────────────────────────────────────────────

class _SharedState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        # Latest rendered frame per camera_id  (numpy BGR)
        self.frames: Dict[str, np.ndarray] = {}
        # Active alerts list (dicts)
        self.alerts: List[Dict[str, Any]] = []
        # Detection telemetry: {camera_id: {track_id: {name, bbox, conf}}}
        self.detections: Dict[str, Dict[int, Dict[str, Any]]] = {}
        # System status
        self.status: str = "starting"   # starting | running | stopped | error
        self.fps: float = 0.0
        self.camera_ids: List[str] = []
        # Log of recent events for frontend alerts page
        self.alert_log: List[Dict[str, Any]] = []
        
        # Queue for WebSocket to broadcast instantly
        self.pending_ws_alerts: List[Dict[str, Any]] = []
        
        # Daily unknown detection counter — resets each day
        import datetime as _dt
        self.today_unknown_count: int = 0
        self._today_date: str = _dt.date.today().isoformat()

    def push_frame(self, camera_id: str, frame: np.ndarray) -> None:
        with self.lock:
            self.frames[camera_id] = frame

    def push_detections(self, camera_id: str, detections: Dict[int, Dict[str, Any]]) -> None:
        with self.lock:
            self.detections[camera_id] = detections

    def _check_daily_reset(self) -> None:
        """Reset daily counters and alert logs when a new day starts."""
        import datetime as _dt
        today = _dt.date.today().isoformat()
        if today != self._today_date:
            print(f"[SHARED] New day detected ({self._today_date} → {today}) — resetting daily stats")
            self._today_date = today
            self.today_unknown_count = 0
            self.alerts.clear()
            self.alert_log.clear()

    def push_alert(self, alert: Dict[str, Any]) -> None:
        with self.lock:
            self._check_daily_reset()
            # Increment counter for unknown person alerts
            if alert.get("type") == "unknown_person":
                self.today_unknown_count += 1
            self.alerts.append(alert)
            # Add to historical log too
            self.alert_log.insert(0, alert)
            self.pending_ws_alerts.append(alert)
            if len(self.alert_log) > 200:
                self.alert_log = self.alert_log[:200]

    def expire_alerts(self) -> None:
        now = time.time()
        with self.lock:
            self._check_daily_reset()
            self.alerts = [a for a in self.alerts if now - a.get("timestamp", 0) < a.get("duration_sec", 30.0)]

    def get_frame(self, camera_id: str) -> Optional[np.ndarray]:
        with self.lock:
            return self.frames.get(camera_id)


SHARED = _SharedState()


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket connection manager
# ──────────────────────────────────────────────────────────────────────────────

class _WsManager:
    def __init__(self) -> None:
        self.clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self.clients.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        data = json.dumps(payload)
        dead: List[WebSocket] = []
        async with self._lock:
            clients = list(self.clients)
        for ws in clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        async with self._lock:
            for ws in dead:
                self.clients.discard(ws)


WS_MANAGER = _WsManager()


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI application
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Sentinel AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Config helpers ──────────────────────────────────────────────────────────

def _load_config() -> Dict[str, Any]:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _save_config(cfg: Dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False)


# ── REST endpoints ──────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    with SHARED.lock:
        return {
            "status": SHARED.status,
            "fps": round(SHARED.fps, 1),
            "cameras": SHARED.camera_ids,
            "active_alerts": len(SHARED.alerts),
        }


@app.get("/api/cameras")
async def get_cameras():
    cfg = _load_config()
    cams = cfg.get("cameras", [])
    result = []
    for c in cams:
        cid = str(c.get("camera_id", ""))
        with SHARED.lock:
            online = cid in SHARED.frames
        result.append({
            "camera_id": cid,
            "name": str(c.get("name", f"Camera {cid}")),
            "source": str(c.get("source", "")),
            "enabled": bool(c.get("enabled", True)),
            "online": online,
        })
    return result


def _mjpeg_stream(camera_id: str):
    """Yield the latest annotated frame for a camera as an MJPEG stream."""
    camera_id = str(camera_id)
    while True:
        frame = SHARED.get_frame(camera_id)
        if frame is None:
            # Keep the browser connection alive while the tracker is still
            # waiting for its first frame.  Once a frame arrives, the real
            # annotated camera image is streamed below.
            time.sleep(0.05)
            continue

        try:
            ok, encoded = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82]
            )
            if not ok:
                time.sleep(0.02)
                continue
            payload = encoded.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
                + payload
                + b"\r\n"
            )
        except Exception as exc:
            print(f"[WARN] MJPEG stream {camera_id} failed: {exc}")
            time.sleep(0.05)


@app.get("/api/stream/{camera_id}")
def stream_camera(camera_id: str):
    # Only expose cameras that are actually configured.
    cfg = _load_config()
    configured = {str(c.get("camera_id")) for c in cfg.get("cameras", [])}
    if str(camera_id) not in configured:
        return JSONResponse(status_code=404, content={"detail": "Camera not found"})

    return StreamingResponse(
        _mjpeg_stream(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
        },
    )

class CameraAdd(BaseModel):
    camera_id: str
    name: str
    source: str

@app.post("/api/cameras")
def add_camera(body: CameraAdd):
    cfg = _load_config()
    cams = cfg.setdefault("cameras", [])
    for c in cams:
        if str(c.get("camera_id")) == body.camera_id:
            c["name"] = body.name
            c["source"] = body.source
            c["enabled"] = True
            break
    else:
        cams.append({
            "camera_id": body.camera_id,
            "name": body.name,
            "source": body.source,
            "enabled": True
        })
    _save_config(cfg)
    # Restart tracker so new camera takes effect
    if hasattr(SHARED, "tracker") and SHARED.tracker:
        SHARED.tracker.stop()
        SHARED.tracker.start()
    return {"success": True, "camera": body.dict()}

class CameraToggle(BaseModel):
    enabled: bool

@app.post("/api/cameras/{camera_id}/toggle")
def toggle_camera(camera_id: str, body: CameraToggle):
    cfg = _load_config()
    cams = cfg.get("cameras", [])
    for c in cams:
        if str(c.get("camera_id")) == camera_id:
            c["enabled"] = body.enabled
    _save_config(cfg)
    if hasattr(SHARED, "tracker") and SHARED.tracker:
        SHARED.tracker.stop()
        SHARED.tracker.start()
    return {"success": True}

@app.delete("/api/cameras/{camera_id}")
def remove_camera(camera_id: str):
    cfg = _load_config()
    cams = cfg.get("cameras", [])
    cfg["cameras"] = [c for c in cams if str(c.get("camera_id")) != camera_id]
    _save_config(cfg)
    if hasattr(SHARED, "tracker") and SHARED.tracker:
        SHARED.tracker.stop()
        SHARED.tracker.start()
    return {"success": True}


import sqlite3

class PersonUpdateRequest(BaseModel):
    name: str
    badge_id: str = ""
    role: str = ""
    clearance: str = "Level 2 (Personnel)"
    profile_note: str = ""

@app.get("/api/persons")
def get_persons():
    persons = []
    with SHARED.lock:
        tracker = getattr(SHARED, "tracker", None)
        manager = getattr(tracker, "identity_manager", None) if tracker else None
        if manager is None:
            return []
        try:
            for pid, identity in manager.identities.items():
                if not identity.is_registered:
                    continue
                details = manager.db.get_identity_details(int(pid))
                status = str(details.get("face_review_status") or identity.face_review_status or "pending")
                last_seen = "Unknown"
                last_camera = "-"
                try:
                    with manager.db._connect() as conn:
                        row = conn.execute(
                            "SELECT timestamp, camera_id FROM sighting_logs WHERE global_track_id = ? ORDER BY timestamp DESC LIMIT 1",
                            (int(pid),),
                        ).fetchone()
                    if row is not None:
                        last_seen = float(row["timestamp"])
                        last_camera = str(row["camera_id"])
                except Exception:
                    pass
                last_seen_ms = int(last_seen * 1000) if isinstance(last_seen, (int, float)) else last_seen
                persons.append({
                    "id": int(pid),
                    "name": identity.name,
                    "status": "High Risk" if status == "denied" else "Active",
                    "face_review_status": status,
                    "face_reviewed_ts": details.get("face_reviewed_ts"),
                    "face_review_note": details.get("face_review_note"),
                    "risk_tier": "high_risk" if status == "denied" else None,
                    "badge_id": details.get("badge_id") or "",
                    "role": details.get("role") or "",
                    "clearance": details.get("clearance") or "Level 2 (Personnel)",
                    "profile_note": details.get("profile_note") or "",
                    "last_seen": last_seen_ms,
                    "camera": last_camera,
                    "thumbnail": f"/api/persons/{pid}/thumbnail"
                })
            persons.sort(key=lambda x: x["id"], reverse=True)
        except Exception as exc:
            print(f"[ERROR] /api/persons: {exc}")
    return persons

@app.put("/api/persons/{person_id}")
def update_person(person_id: int, body: PersonUpdateRequest):
    name = body.name.strip()
    if not name:
        return JSONResponse(status_code=400, content={"success": False, "error": "Name cannot be empty"})
    db = _get_db()
    if db is None:
        return JSONResponse(status_code=503, content={"success": False, "error": "Tracker not running"})
    existing = db.get_identity_details(person_id)
    if not existing:
        return JSONResponse(status_code=404, content={"success": False, "error": "Person not found"})
    old_name = str(existing.get("name") or "")
    tracker = getattr(SHARED, "tracker", None)
    manager = getattr(tracker, "identity_manager", None) if tracker else None
    if manager is not None:
        ok = manager.update_identity_details(person_id, name, body.badge_id, body.role, body.clearance, body.profile_note)
    else:
        ok = db.update_identity_details(person_id, name, body.badge_id, body.role, body.clearance, body.profile_note)
    if not ok:
        return JSONResponse(status_code=404, content={"success": False, "error": "Person not found"})

    # Keep the gallery thumbnail in sync when an accepted Guest is renamed.
    # The filename is derived from the profile name for enrolled faces.
    try:
        faces_dir = BASE_DIR / "Faces"
        old_file = faces_dir / f"{_safe_gallery_stem(old_name)}.jpg"
        new_file = faces_dir / f"{_safe_gallery_stem(name)}.jpg"
        if old_file.exists() and old_file.resolve() != new_file.resolve():
            new_file.parent.mkdir(parents=True, exist_ok=True)
            old_file.replace(new_file)
    except Exception as exc:
        print(f"[WARN] Could not rename face gallery image: {exc}")

    # Keep historical pending captures readable under the edited profile name.
    try:
        with sqlite3.connect(db.db_path, timeout=5.0) as conn:
            conn.execute("UPDATE flagged_persons SET guest_label = ? WHERE global_track_id = ?", (name, int(person_id)))
            conn.commit()
    except Exception:
        pass

    return {"success": True, "id": person_id, "name": name}

@app.get("/api/persons/{person_id}/thumbnail")
def get_person_thumbnail(person_id: int):
    cfg = _load_config()
    db_path = cfg.get("database", {}).get("db_path", "tracker.db")
    if not os.path.isabs(db_path):
        db_path = str(BASE_DIR / db_path)
    
    name = None
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM registered_identities WHERE id = ?", (person_id,))
        row = cursor.fetchone()
        if row:
            name = row[0]
        conn.close()
    except Exception:
        pass
        
    if name:
        faces_dir = BASE_DIR / "Faces"
        img_path = faces_dir / f"{_safe_gallery_stem(name)}.jpg"
        if img_path.exists():
            return FileResponse(str(img_path))
            
    return RedirectResponse("/assets/placeholder.jpg")

@app.post("/api/persons")
def register_person(name: str = Form(...), image: UploadFile = File(None), force: str = Form("false"), update_id: str = Form(None)):
    if not image:
        return {"success": False, "error": "Image required"}
    
    faces_dir = Path("Faces")
    faces_dir.mkdir(exist_ok=True)
    img_path = faces_dir / f"{_safe_gallery_stem(name)}.jpg"
    
    with open(img_path, "wb") as f:
        shutil.copyfileobj(image.file, f)
        
    cmd = [sys.executable, "register_identity.py", "--name", name, "--input", str(img_path)]
    if force.lower() == "true":
        cmd.append("--force")
    if update_id and update_id.strip() != "null":
        cmd.append("--update-id")
        cmd.append(update_id.strip())
        
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 2:
        import json
        for line in result.stdout.splitlines():
            if '{"conflict":' in line:
                try:
                    conflict_data = json.loads(line)
                    conflict_data["thumbnail"] = f"/api/persons/{conflict_data['id']}/thumbnail"
                    return {"success": False, "conflict": conflict_data}
                except Exception:
                    pass
        return {"success": False, "error": "Similarity conflict detected but failed to parse details."}
    elif result.returncode != 0:
        return {"success": False, "error": f"Registration failed: {result.stderr}"}
        
    with SHARED.lock:
        if hasattr(SHARED, "tracker") and SHARED.tracker and hasattr(SHARED.tracker, "identity_manager") and SHARED.tracker.identity_manager:
            SHARED.tracker.identity_manager._load_from_db()
            
    return {"success": True, "person": {"id": -1, "name": name}}

@app.delete("/api/persons/{person_id}")
def delete_person(person_id: int):
    cfg = _load_config()
    db_path = cfg.get("database", {}).get("db_path", "tracker.db")
    if not os.path.isabs(db_path):
        db_path = str(BASE_DIR / db_path)
    
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM registered_identities WHERE id = ?", (person_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        return {"success": False, "error": str(e)}

    # Immediately remove from in-memory identity manager
    with SHARED.lock:
        if hasattr(SHARED, "tracker") and SHARED.tracker and hasattr(SHARED.tracker, "identity_manager") and SHARED.tracker.identity_manager:
            SHARED.tracker.identity_manager.remove_identity(person_id)
    return {"success": True}


@app.post("/api/persons/{person_id}/unenroll")
def unenroll_person(person_id: int):
    """Remove a profile from the active enrolled face database and gallery."""
    db = _get_db()
    if db is None:
        return {"success": False, "error": "Tracker not running"}

    review = db.get_face_review(person_id)
    if not review:
        return JSONResponse(status_code=404, content={"success": False, "error": "Person not found"})

    name = str(review.get("name") or f"person_{person_id}")
    removed = db.delete_identity(person_id)
    if not removed:
        return {"success": False, "error": "Person could not be removed"}

    gallery_path = BASE_DIR / "Faces" / f"{_safe_gallery_stem(name)}.jpg"
    try:
        if gallery_path.exists():
            gallery_path.unlink()
    except Exception as exc:
        print(f"[WARN] Could not remove enrolled face image for {name}: {exc}")

    with SHARED.lock:
        tracker = getattr(SHARED, "tracker", None)
        manager = getattr(tracker, "identity_manager", None) if tracker else None
        if manager is not None:
            manager.remove_identity(person_id)

    return {"success": True, "id": person_id, "name": name, "status": "unenrolled"}


class FaceReviewRequest(BaseModel):
    status: str
    note: Optional[str] = None


@app.post("/api/persons/{person_id}/face-review")
def review_person_face(person_id: int, body: FaceReviewRequest):
    """Record a human face verification decision for an enrolled person.

    Confirmed -> verified/authorized for face-review purposes.
    Denied -> High Risk incident is created in the Security Incidents feed.
    """
    status = str(body.status).strip().lower()
    if status not in {"confirmed", "denied"}:
        return JSONResponse(status_code=400, content={
            "success": False,
            "error": "status must be 'confirmed' or 'denied'"
        })

    db = _get_db()
    if db is None:
        return {"success": False, "error": "Tracker not running"}

    person = db.get_face_review(person_id)
    if not person:
        return JSONResponse(status_code=404, content={
            "success": False,
            "error": "Person not found"
        })

    reviewed_ts = time.time()
    note = body.note.strip() if body.note else None

    if status == "confirmed":
        db.set_face_review(person_id, "confirmed", reviewed_ts, note)
        db.resolve_active_incidents_for_person(person_id, reviewed_ts)
        with SHARED.lock:
            tracker = getattr(SHARED, "tracker", None)
            manager = getattr(tracker, "identity_manager", None) if tracker else None
            if manager is not None:
                manager.set_face_review_status(person_id, "confirmed")
        _resolve_person_runtime_alerts(person_id, str(person["name"]))
        # Record the acceptance so the operator can audit the change.
        incident = db.create_face_acceptance_incident(person_id, str(person["name"]), reviewed_ts)
        alert = _incident_to_alert(incident)
        return {
            "success": True,
            "person_id": person_id,
            "status": "confirmed",
            "reviewed_ts": reviewed_ts,
            "message": "face has been accepted, person has been added to the database",
            "incident": alert,
        }

    db.set_face_review(person_id, "denied", reviewed_ts, note)
    # Replace older person-specific active alarms with the single authoritative
    # face-denial incident created below.
    db.resolve_active_incidents_for_person(person_id, reviewed_ts)
    with SHARED.lock:
        tracker = getattr(SHARED, "tracker", None)
        manager = getattr(tracker, "identity_manager", None) if tracker else None
        if manager is not None:
            manager.set_face_review_status(person_id, "denied")
    incident = db.create_face_denial_incident(person_id, str(person["name"]), reviewed_ts)

    # Do not add the same persistent incident to the live feed repeatedly if
    # an operator clicks Deny more than once.
    with SHARED.lock:
        already_live = any(
            int(a.get("incident_id")) == int(incident["id"])
            for a in SHARED.alert_log
            if a.get("incident_id") is not None
        )

    alert = {
        "id": f"face-denied-{incident['id']}",
        "incident_id": int(incident["id"]),
        "source": "manual_face_review",
        "type": "face_verification_denied",
        "alert_type": "face_verification_denied",
        "person_id": person_id,
        "person_name": str(person["name"]),
        "camera_id": incident.get("camera_id") or "PERSONS_DB",
        "message": incident["message"],
        "detail": incident["detail"],
        "risk_tier": "high_risk",
        "severity": "critical",
        "timestamp": reviewed_ts,
        "status": "active",
        "duration_sec": 86400.0,
    }
    if not already_live:
        SHARED.push_alert(alert)
    return {
        "success": True,
        "person_id": person_id,
        "status": "denied",
        "reviewed_ts": reviewed_ts,
        "risk_tier": "high_risk",
        "incident": alert,
    }


def _incident_to_alert(row: Dict[str, Any]) -> Dict[str, Any]:
    incident_type = str(row.get("incident_type") or "security_incident")
    prefix = "face-accepted" if incident_type == "face_verification_accepted" else "face-denied"
    return {
        "id": f"{prefix}-{int(row['id'])}",
        "incident_id": int(row["id"]),
        "source": str(row.get("source") or "manual_face_review"),
        "type": str(row.get("incident_type") or "security_incident"),
        "alert_type": str(row.get("incident_type") or "security_incident"),
        "person_id": row.get("person_id"),
        "person_name": row.get("person_name"),
        "camera_id": row.get("camera_id") or "PERSONS_DB",
        "message": row.get("message"),
        "detail": row.get("detail"),
        "risk_tier": row.get("risk_tier"),
        "severity": "critical" if row.get("risk_tier") == "high_risk" else ("info" if row.get("risk_tier") == "verified" else "warning"),
        "timestamp": row.get("timestamp"),
        "status": row.get("status", "active"),
        "duration_sec": 86400.0,
    }


def _get_db():
    """Return the running tracker's IdentityDatabase, or None if not up yet."""
    with SHARED.lock:
        if hasattr(SHARED, "tracker") and SHARED.tracker and getattr(SHARED.tracker, "identity_manager", None):
            return SHARED.tracker.identity_manager.db
    return None


@app.get("/api/persons/flagged")
def list_flagged_persons(status: str = "pending_review"):
    """
    Pending-review queue: faces captured because a track's behavior crossed
    the Suspicious/High-Risk line. Nothing here is a final 'suspicious' tag
    until a human confirms it — pass status='' to see everything, or
    status='confirmed' / 'dismissed' for already-reviewed items.
    """
    db = _get_db()
    if db is None:
        return []
    rows = db.list_flagged_persons(status=status or None)
    for row in rows:
        row["thumbnail"] = f"/api/persons/flagged/{row['id']}/thumbnail"
    return rows


@app.get("/api/persons/flagged/{flag_id}/thumbnail")
def get_flagged_thumbnail(flag_id: int):
    db = _get_db()
    row = db.get_flagged_person(flag_id) if db else None
    if not row:
        return RedirectResponse("/assets/placeholder.jpg")
    img_path = Path(row["image_path"])
    if not img_path.is_absolute():
        img_path = BASE_DIR / img_path
    if img_path.exists():
        return FileResponse(str(img_path))
    return RedirectResponse("/assets/placeholder.jpg")


def _resolve_person_runtime_alerts(person_id: int, person_name: Optional[str] = None) -> None:
    with SHARED.lock:
        for collection in (SHARED.alert_log, SHARED.alerts):
            for alert in collection:
                same_person = alert.get("person_id") == int(person_id)
                same_name = bool(person_name) and alert.get("person_name") == person_name
                if (same_person or same_name) and alert.get("type") in {
                    "face_verification_denied", "anomalous_behavior", "watchlist_match", "unknown_person"
                }:
                    alert["status"] = "resolved"

@app.post("/api/persons/flagged/{flag_id}/confirm")
def confirm_flagged_person(flag_id: int):
    """Accept a flagged face and promote that exact guest identity into the
    enrolled face database. A persistent informational security incident is
    also created so the acceptance is auditable in Security Incidents."""
    db = _get_db()
    if db is None:
        return {"success": False, "error": "Tracker not running"}

    row = db.get_flagged_person(flag_id)
    if not row:
        return {"success": False, "error": "Not found"}

    reviewed_ts = time.time()
    gid = int(row["global_track_id"])
    guest_name = str(row["guest_label"])

    # Persist the acceptance state first. IdentityManager uses this value on
    # startup to keep this profile enrolled even after a restart.
    db.set_face_review(
        gid,
        "confirmed",
        reviewed_ts,
        "face has been accepted, person has been added to the database",
    )
    db.set_flagged_status(flag_id, "confirmed", reviewed_ts)
    db.set_flagged_status_for_identity(gid, "confirmed", reviewed_ts)

    # Copy the reviewed face image into the normal Faces gallery so the same
    # image is used by the Persons Database thumbnail after promotion.
    src = Path(row["image_path"])
    if not src.is_absolute():
        src = BASE_DIR / src
    faces_dir = BASE_DIR / "Faces"
    faces_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_gallery_stem(guest_name) if guest_name else f"person_{gid}"
    gallery_path = faces_dir / f"{safe_name}.jpg"
    try:
        if src.exists():
            shutil.copy2(src, gallery_path)
    except Exception as exc:
        print(f"[WARN] Could not copy accepted face into gallery: {exc}")

    # Promote the same runtime global ID so there is no second identity entry.
    with SHARED.lock:
        tracker = getattr(SHARED, "tracker", None)
        manager = getattr(tracker, "identity_manager", None) if tracker else None

    if manager is not None:
        if not manager.promote_identity(gid):
            # It may have been evicted from RAM; reload the persisted gallery.
            manager._load_from_db()
            manager.promote_identity(gid)

    _resolve_person_runtime_alerts(gid, guest_name)
    db.resolve_active_incidents_for_person(gid, reviewed_ts)

    incident = db.create_face_acceptance_incident(gid, guest_name, reviewed_ts)
    alert = _incident_to_alert(incident)

    with SHARED.lock:
        already_live = any(
            int(a.get("incident_id")) == int(incident["id"])
            for a in SHARED.alert_log
            if a.get("incident_id") is not None
        )
    if not already_live:
        SHARED.push_alert(alert)

    return {
        "success": True,
        "id": flag_id,
        "status": "confirmed",
        "person_id": gid,
        "person_name": guest_name,
        "message": "face has been accepted, person has been added to the database",
        "incident": alert,
    }


@app.post("/api/persons/flagged/{flag_id}/deny")
def deny_flagged_person(flag_id: int):
    """Human denies the captured face; retain the capture, mark it High Risk,
    and create a persistent Security Incident."""
    db = _get_db()
    if db is None:
        return {"success": False, "error": "Tracker not running"}

    row = db.get_flagged_person(flag_id)
    if not row:
        return JSONResponse(status_code=404, content={"success": False, "error": "Not found"})

    reviewed_ts = time.time()
    incident = db.deny_flagged_person(flag_id, reviewed_ts)
    if not incident:
        return JSONResponse(status_code=404, content={"success": False, "error": "Not found"})

    # Update the live identity immediately. The DB update above makes the
    # decision persistent so it is restored on the next application start.
    with SHARED.lock:
        tracker = getattr(SHARED, "tracker", None)
        manager = getattr(tracker, "identity_manager", None) if tracker else None
        if manager is not None:
            manager.set_face_review_status(int(row["global_track_id"]), "denied")

    alert = _incident_to_alert(incident)
    alert["duration_sec"] = 86400.0

    with SHARED.lock:
        already_live = any(
            int(a.get("incident_id")) == int(incident["id"])
            for a in SHARED.alert_log
            if a.get("incident_id") is not None
        )
    if not already_live:
        SHARED.push_alert(alert)

    return {
        "success": True,
        "id": flag_id,
        "status": "denied",
        "risk_tier": "high_risk",
        "incident": alert,
    }


@app.delete("/api/persons/flagged/{flag_id}")
def dismiss_flagged_person(flag_id: int):
    """Human reviews the photo and clears it — deletes the row AND the
    saved image. Use this for false positives (wrong person, bad crop,
    behavior that had an innocent explanation)."""
    db = _get_db()
    if db is None:
        return {"success": False, "error": "Tracker not running"}
    row = db.get_flagged_person(flag_id)
    if not row:
        return {"success": False, "error": "Not found"}

    img_path = Path(row["image_path"])
    if not img_path.is_absolute():
        img_path = BASE_DIR / img_path
    try:
        if img_path.exists():
            img_path.unlink()
    except Exception:
        pass

    db.delete_flagged_person(flag_id)
    return {"success": True, "id": flag_id}


@app.get("/api/alerts")
async def get_alerts():
    """Return runtime alerts plus persistent security incidents.

    Persistent face-verification incidents are merged by incident_id so the
    same review event is never rendered twice when it also exists in SHARED.
    """
    with SHARED.lock:
        runtime_alerts = list(SHARED.alert_log[:100])

    db = _get_db()
    persisted_alerts = []
    if db is not None:
        persisted_alerts = [_incident_to_alert(row) for row in db.list_security_incidents(limit=200)]

    runtime_incident_ids = {
        int(a["incident_id"])
        for a in runtime_alerts
        if a.get("incident_id") is not None
    }
    merged = list(runtime_alerts)
    merged.extend(a for a in persisted_alerts if int(a["incident_id"]) not in runtime_incident_ids)
    merged.sort(key=lambda a: float(a.get("timestamp") or 0), reverse=True)
    return merged[:200]


@app.post("/api/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str):
    db = _get_db()
    # Persistent face-review incident IDs use face-denied-N or face-accepted-N.
    if str(alert_id).startswith(("face-denied-", "face-accepted-")):
        try:
            incident_id = int(str(alert_id).split("-")[-1])
            if db is not None:
                db.set_security_incident_status(incident_id, "resolved", time.time())
            with SHARED.lock:
                for alert in SHARED.alert_log:
                    if str(alert.get("id", "")) == str(alert_id):
                        alert["status"] = "dismissed"
            return {"success": True, "alert_id": alert_id}
        except ValueError:
            pass

    with SHARED.lock:
        for alert in SHARED.alert_log:
            if str(alert.get("id", "")) == str(alert_id) or str(alert.get("timestamp", "")) == str(alert_id):
                alert["status"] = "dismissed"
                break
    return {"success": True, "alert_id": alert_id}


@app.delete("/api/alerts")
async def clear_alerts():
    db = _get_db()
    if db is not None:
        db.clear_security_incidents()
    with SHARED.lock:
        SHARED.alert_log.clear()
        SHARED.alerts.clear()
    return {"ok": True}


@app.get("/api/sightings")
def get_sightings():
    """Return recent sighting logs from the database."""
    cfg = _load_config()
    db_path = cfg.get("database", {}).get("db_path", "tracker.db")
    if not os.path.isabs(db_path):
        db_path = str(BASE_DIR / db_path)
    
    sightings = []
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sl.id, sl.timestamp, sl.camera_id, ri.name, sl.bounding_box_coords,
                   sl.global_track_id, sl.match_confidence, ri.face_review_status
            FROM sighting_logs sl
            LEFT JOIN registered_identities ri ON sl.global_track_id = ri.id
            ORDER BY sl.id DESC
            LIMIT 300
        """)
        for row in cursor.fetchall():
            bbox = [0, 0, 0, 0]
            if row[4]:
                try:
                    import json as _json
                    bbox = _json.loads(row[4])
                except Exception:
                    pass
                    
            name = row[3]
            if not name:
                name = f"Guest_{abs(int(row[5]))}"

            sightings.append({
                "id": row[0],
                "timestamp": int(row[1] * 1000),
                "camera": row[2],
                "name": name,
                "registered": bool(row[7] in ("confirmed", "denied")),
                "face_review_status": row[7] or "pending",
                "confidence": float(row[6]) if row[6] is not None else None,
                "bbox": bbox
            })
    except Exception as e:
        print(f"[ERROR] /api/sightings: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
            
    return sightings

@app.get("/api/dashboard")
def get_dashboard_summary():
    cfg = _load_config()
    db_path = cfg.get("database", {}).get("db_path", "tracker.db")
    if not os.path.isabs(db_path):
        db_path = str(BASE_DIR / db_path)
        


    active_cameras = 0
    if hasattr(SHARED, "tracker") and SHARED.tracker and hasattr(SHARED.tracker, "stream_mgr"):
        active_cameras = sum(1 for cam in SHARED.tracker.stream_mgr.cameras.values() if cam.enabled)

    # Get today's unknown count from in-memory counter (resets daily)
    with SHARED.lock:
        today_unknown = SHARED.today_unknown_count

    db = _get_db()
    active_persistent_incidents = db.count_active_security_incidents() if db is not None else 0
    with SHARED.lock:
        runtime_persistent_ids = {
            int(a["incident_id"])
            for a in SHARED.alerts
            if a.get("incident_id") is not None and a.get("status") != "dismissed"
        }
        runtime_alert_count = sum(
            1 for a in SHARED.alerts
            if a.get("status") != "dismissed" and a.get("incident_id") is None
        )

    # Runtime face-review alerts are already represented in the DB count, so
    # only add runtime alerts that do not have a persistent incident record.
    active_alerts = active_persistent_incidents + runtime_alert_count

    return {
        "activeCameras": active_cameras,
        "totalDetections": today_unknown,
        "activeAlerts": active_alerts,
        "systemHealth": 100
    }

@app.get("/api/stats")
def get_stats():
    """Return full-day tracking analytics from persisted sighting telemetry."""
    cfg = _load_config()
    db_path = cfg.get("database", {}).get("db_path", "tracker.db")
    if not os.path.isabs(db_path):
        db_path = str(BASE_DIR / db_path)
    timeline_data=[]; camera_data=[]
    total=authorized=unknown=high_risk=0; avg_confidence=None
    try:
        conn=sqlite3.connect(db_path, timeout=5.0); conn.row_factory=sqlite3.Row
        today="date(datetime(sl.timestamp, 'unixepoch', 'localtime')) = date('now', 'localtime')"
        row=conn.execute(f"""SELECT COUNT(*) total,
          SUM(CASE WHEN ri.face_review_status='confirmed' THEN 1 ELSE 0 END) authorized,
          SUM(CASE WHEN ri.id IS NULL OR ri.face_review_status NOT IN ('confirmed','denied') THEN 1 ELSE 0 END) unknown,
          SUM(CASE WHEN ri.face_review_status='denied' THEN 1 ELSE 0 END) high_risk,
          AVG(sl.match_confidence) avg_conf
          FROM sighting_logs sl LEFT JOIN registered_identities ri ON sl.global_track_id=ri.id WHERE {today}""").fetchone()
        total=int(row['total'] or 0); authorized=int(row['authorized'] or 0); unknown=int(row['unknown'] or 0); high_risk=int(row['high_risk'] or 0)
        avg_confidence=float(row['avg_conf']) if row['avg_conf'] is not None else None
        rows=conn.execute(f"""SELECT strftime('%H:00', datetime(sl.timestamp,'unixepoch','localtime')) hour,
          COUNT(*) detections,
          SUM(CASE WHEN ri.face_review_status='confirmed' THEN 1 ELSE 0 END) authorized,
          SUM(CASE WHEN ri.id IS NULL OR ri.face_review_status NOT IN ('confirmed','denied') THEN 1 ELSE 0 END) unknown,
          SUM(CASE WHEN ri.face_review_status='denied' THEN 1 ELSE 0 END) high_risk
          FROM sighting_logs sl LEFT JOIN registered_identities ri ON sl.global_track_id=ri.id
          WHERE {today} GROUP BY hour ORDER BY hour""").fetchall()
        timeline_data=[{'hour':r['hour'],'detections':int(r['detections'] or 0),'authorized':int(r['authorized'] or 0),'unknown':int(r['unknown'] or 0),'high_risk':int(r['high_risk'] or 0),'alerts':0} for r in rows]
        rows=conn.execute(f"""SELECT sl.camera_id camera, COUNT(*) detections,
          SUM(CASE WHEN ri.face_review_status='confirmed' THEN 1 ELSE 0 END) authorized,
          SUM(CASE WHEN ri.id IS NULL OR ri.face_review_status NOT IN ('confirmed','denied') THEN 1 ELSE 0 END) unknown,
          SUM(CASE WHEN ri.face_review_status='denied' THEN 1 ELSE 0 END) high_risk
          FROM sighting_logs sl LEFT JOIN registered_identities ri ON sl.global_track_id=ri.id
          WHERE {today} GROUP BY sl.camera_id ORDER BY detections DESC""").fetchall()
        camera_data=[{'camera':r['camera'],'camera_id':r['camera'],'detections':int(r['detections'] or 0),'authorized':int(r['authorized'] or 0),'unknown':int(r['unknown'] or 0),'high_risk':int(r['high_risk'] or 0),'alerts':0} for r in rows]
    except Exception as e:
        print(f"[ERROR] /api/stats: {e}")
    finally:
        if 'conn' in locals(): conn.close()
    return {'timelineData':timeline_data,'cameraData':camera_data,'totalSightings':total,'authorizedDetections':authorized,'unknownGuests':unknown,'highRiskDetections':high_risk,'averageConfidence':round(avg_confidence*100,1) if avg_confidence is not None else None}


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard static serving
#
# sentinel_app.py opens http://127.0.0.1:8765 directly. The v7 server exposed
# only /api/* routes, so the browser correctly received FastAPI's 404 JSON at
# /. Keep all API routes unchanged and serve the existing React build for every
# non-API browser path, including React Router paths such as /dashboard,
# /persons, /tracking, etc.
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_dashboard_root():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return JSONResponse(status_code=500, content={"detail": "Dashboard build not found"})
    return FileResponse(str(index_path), media_type="text/html")


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_dashboard_path(full_path: str):
    # API routes are declared above and take precedence. This fallback is only
    # for dashboard/static browser requests.
    if full_path.startswith("api/") or full_path == "api":
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    # Serve an actual file from dashboard/dist when present.
    requested = (STATIC_DIR / full_path).resolve()
    static_root = STATIC_DIR.resolve()
    try:
        requested.relative_to(static_root)
    except ValueError:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    if requested.is_file():
        return FileResponse(str(requested))

    # React Router uses browser history; unknown frontend paths should resolve
    # to index.html so the client router can render the correct page.
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return JSONResponse(status_code=500, content={"detail": "Dashboard build not found"})


# ──────────────────────────────────────────────────────────────────────────────
# Server launcher (called from sentinel_app.py)
# ──────────────────────────────────────────────────────────────────────────────

def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start uvicorn in the calling thread (blocking).

    SentinelAI launches FastAPI from a background thread, so signal handlers
    must be disabled.
    """
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        timeout_keep_alive=5,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    server.run()
