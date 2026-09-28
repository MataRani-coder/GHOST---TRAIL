"""
sentinel_tracker.py
===================
Background pipeline controller that wraps the main tracking loop.
Writes rendered frames + alerts into sentinel_server.SHARED so the
FastAPI server can pick them up and serve them to the browser.
"""

from __future__ import annotations

import sys
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

import cv2
import numpy as np
import yaml


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).parent


BASE_DIR = _base_dir()

# Where pending-review captures are written. Separate from Faces/<name>.jpg
# (which holds enrolled/registered people) so flagged, unreviewed crops never
# get confused with confirmed identities.
FLAGGED_DIR = BASE_DIR / "Faces" / "flagged"

# Don't re-capture/re-flag the same track more than once in this window, even
# if it keeps re-triggering alerts (e.g. it re-enters after a gap).
FLAG_RECAPTURE_COOLDOWN_SEC = 300.0


def _parse_source(raw: Any) -> Any:
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return raw


class SentinelTracker:
    """
    Runs the full Sentinel AI pipeline in a background daemon thread.
    Call start() to launch, stop() to shut down cleanly.
    """

    def __init__(self) -> None:
        from sentinel_server import SHARED
        SHARED.tracker = self
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.alerted_guests = set()
        self.alerted_watchlist = set()
        # Per-guest frame counter — must be seen for this many frames before alert fires
        # At ~9 FPS this is ~3 seconds of sustained presence
        self.guest_sighting_counts: dict = {}
        self.local_face_boxes: dict[str, dict[int, np.ndarray]] = {}
        self.face_probe_attempts: dict[tuple[str, int], int] = {}
        self.GUEST_CONFIRM_FRAMES = 2

    # ──────────────────────────────────────────────────────────────────
    def _capture_flag(
        self,
        frame: np.ndarray,
        xyxy: np.ndarray,
        camera_id: str,
        gid: int,
        gname: str,
        tier: str,
        reason: str,
        timestamp: float,
    ) -> None:
        """
        Save a face/body crop for a track whose behavior just crossed the
        Suspicious/High-Risk line, and log it to flagged_persons as
        'pending_review'. This is a CAPTURE, not a verdict — nothing here
        is treated as confirmed until a human reviews it via the dashboard
        (Persons > Flagged: confirm keeps the tag, dismiss deletes the row
        and the image).
        """
        try:
            db = self.identity_manager.db
            if db.has_recent_flag(gid, timestamp - FLAG_RECAPTURE_COOLDOWN_SEC):
                return

            h, w = frame.shape[:2]
            x1, y1, x2, y2 = xyxy.astype(int)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                return
            crop = frame[y1:y2, x1:x2]

            FLAGGED_DIR.mkdir(parents=True, exist_ok=True)
            image_name = f"{int(timestamp)}_{gid}_{uuid.uuid4().hex[:8]}.jpg"
            image_path = FLAGGED_DIR / image_name
            cv2.imwrite(str(image_path), crop)

            db.insert_flagged_person(
                global_track_id=gid,
                guest_label=gname,
                risk_tier=tier,
                reason=reason,
                camera_id=camera_id,
                timestamp=timestamp,
                image_path=str(image_path.relative_to(BASE_DIR)),
            )
            print(f"[FLAG] Captured {gname} ({tier}) on {camera_id} -> {image_name} [pending review]")
        except Exception as exc:
            print(f"[WARN] Flag capture failed for {gname}: {exc}")

    # ──────────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="sentinel-tracker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ──────────────────────────────────────────────────────────────────
    def _run(self) -> None:
        """Full pipeline — mirrors main.py logic but writes to SHARED."""
        # Lazy import so PyInstaller hooks work correctly
        from sentinel_server import SHARED

        # ── Load config ────────────────────────────────────────────────
        cfg_path = BASE_DIR / "config.yaml"
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
        except Exception as exc:
            SHARED.status = "error"
            print(f"[ERROR] Cannot load config: {exc}")
            return

        camera_configs: List[Dict[str, Any]] = cfg.get("cameras", [])
        for cam_cfg in camera_configs:
            cam_cfg["source"] = _parse_source(cam_cfg.get("source", 0))

        all_camera_ids = [str(c["camera_id"]) for c in camera_configs]
        SHARED.camera_ids = all_camera_ids
        SHARED.status = "starting"

        # ── Import AI modules ──────────────────────────────────────────
        try:
            from alert_manager import (
                AlertManager,
                ALERT_THREAT_OBJECT,
                ALERT_ANOMALOUS_BEHAVIOR,
                ALERT_WATCHLIST_MATCH,
            )
            from behavior_analyzer import BehaviorAnalyzer, RISK_LABELS, RISK_HIGH, RISK_SUSPICIOUS
            from database import IdentityDatabase
            from detector import YoloDetector
            from face_recognizer import FaceRecognizer
            from identity_manager import GlobalIdentityManager
            from stream_manager import StreamManager
            from tracker import (
                DeepReIDExtractor,
                ReIDCandidate,
                ReIDMicroBatcher,
                SingleCameraTracker,
                annotate_tracked_objects,
                make_grid_with_offline,
            )
        except Exception as exc:
            SHARED.status = "error"
            print(f"[ERROR] Import failure: {exc}")
            return

        # ── Build AI components ────────────────────────────────────────
        try:
            # Change working dir so relative paths (yolov8n.pt, tracker.db) work
            import os
            os.chdir(str(BASE_DIR))

            detector = YoloDetector(
                weights=str(BASE_DIR / cfg["model"]["weights"]),
                device=cfg["model"].get("device", "cpu"),
                conf_thres=cfg["model"].get("conf_thres", 0.40),
                iou_thres=cfg["model"].get("iou_thres", 0.45),
                classes=cfg["model"].get("classes"),
                imgsz=cfg["model"].get("imgsz", 320),
            )
            class_map = detector.class_name_map()

            stream_manager = StreamManager(
                camera_configs=camera_configs,
                stream_cfg=cfg["stream"],
            )
            trackers = {
                cam["camera_id"]: SingleCameraTracker(**cfg["tracker"])
                for cam in camera_configs
            }

            db = IdentityDatabase(str(BASE_DIR / cfg["database"]["db_path"]))

            feature_encoder = DeepReIDExtractor(
                model_name=cfg["reid"].get("model_name", "osnet_x1_0"),
                model_weights=cfg["reid"].get("reid_model_weights") or None,
                device=cfg["reid"].get("device", "cpu"),
                input_size=tuple(cfg["reid"].get("input_size", [256, 128])),
            )

            face_cfg = cfg.get("face_recognition", {})
            face_recognizer = FaceRecognizer(
                model_name=face_cfg.get("model_name", "buffalo_sc"),
                device=face_cfg.get("device", "cpu"),
                det_size=tuple(face_cfg.get("det_size", [320, 320])),
                face_sim_threshold=face_cfg.get("face_sim_threshold", 0.40),
            )

            global_manager = GlobalIdentityManager(
                db=db,
                face_recognizer=face_recognizer,
                face_threshold=face_cfg.get("face_threshold", 0.72),
                confirm_frames=cfg["reid"].get("confirm_frames", 15),
                body_registered_threshold=cfg["reid"].get("body_registered_threshold", 0.90),
                body_guest_threshold=cfg["reid"].get("body_guest_threshold", 0.50),
                max_time_gap_sec=cfg["reid"].get("max_time_gap_sec", 30.0),
                guest_handoff_grace_sec=cfg["reid"].get("guest_handoff_grace_sec", 0.75),
                max_gallery_size=cfg["reid"].get("max_gallery_size", 2000),
                guest_face_threshold=cfg["reid"].get("guest_face_threshold", 0.55),
                registered_face_stitch_threshold=cfg["reid"].get("registered_face_stitch_threshold", 0.60),
                camera_handoff_max_gap_sec=cfg["reid"].get("camera_handoff_max_gap_sec", 8.0),
            )
            self.identity_manager = global_manager

            reid_batcher = ReIDMicroBatcher(
                max_wait_ms=cfg["reid"].get("micro_batch_max_wait_ms", 15.0),
                max_batch_size=cfg["reid"].get("micro_batch_max_size", 64),
            )

            alert_cfg = cfg.get("alerts", {})
            alert_manager = AlertManager(cooldown_sec=alert_cfg.get("cooldown_sec", 5.0))

            behavior_cfg = cfg.get("behavior", {})
            behavior_analyzer = BehaviorAnalyzer(
                watch_dwell_sec=behavior_cfg.get("watch_dwell_sec", 8.0),
                suspicious_dwell_sec=behavior_cfg.get("suspicious_dwell_sec", 20.0),
                high_risk_dwell_sec=behavior_cfg.get("high_risk_dwell_sec", 45.0),
                off_hours_start=behavior_cfg.get("off_hours_start", 22),
                off_hours_end=behavior_cfg.get("off_hours_end", 6),
                reentry_high_risk=behavior_cfg.get("reentry_high_risk", 3),
                zone_hop_window_sec=behavior_cfg.get("zone_hop_window_sec", 90.0),
            )
            self.behavior_analyzer = behavior_analyzer

            threat_class_ids = set(int(c) for c in cfg.get("threat_classes", []))
            reid_enabled = bool(cfg.get("reid", {}).get("enabled", True))
            person_class_id = cfg["reid"].get("person_class_id", 0)

        except Exception as exc:
            SHARED.status = "error"
            print(f"[ERROR] Component init failure: {exc}")
            return

        # ── Start streaming ────────────────────────────────────────────
        stream_manager.start_all()
        SHARED.status = "running"
        print("[INFO] Sentinel tracker started.")

        local_global_map: Dict[str, Dict[int, int]] = defaultdict(dict)
        local_name_map: Dict[str, Dict[int, str]] = defaultdict(dict)
        local_face_boxes: Dict[str, Dict[int, np.ndarray]] = defaultdict(dict)
        last_fps_time = time.time()
        frame_counter = 0
        reid_frame_counter = 0
        reid_interval = cfg.get("reid", {}).get("reid_interval", 3)  # Run Re-ID every N frames

        try:
            while not self._stop_event.is_set():
                latest_packets = stream_manager.get_latest_frames()
                if not latest_packets:
                    time.sleep(0.005)
                    continue

                tracked_by_camera: Dict[str, Any] = {}
                frame_by_camera: Dict[str, np.ndarray] = {}
                ready_batches: List[List[ReIDCandidate]] = []

                alert_manager.tick()

                # Phase 1: detect + track
                for camera_id, packet in latest_packets.items():
                    frame = packet.frame
                    # Downscale large frames for faster YOLO pre-processing
                    h, w = frame.shape[:2]
                    if w > 720:
                        scale = 640.0 / w
                        frame = cv2.resize(frame, (640, int(h * scale)), interpolation=cv2.INTER_LINEAR)
                    detections = detector.infer(frame)
                    tracked = trackers[camera_id].update(detections)
                    tracked_by_camera[camera_id] = tracked
                    frame_by_camera[camera_id] = frame

                    track_ids = tracked.tracker_id if tracked.tracker_id is not None else np.array([], dtype=int)
                    class_ids = tracked.class_id if tracked.class_id is not None else np.array([], dtype=int)

                    # Purge lost tracks from identity manager so they release their exclusive locks
                    self.identity_manager.cleanup_camera_tracks(camera_id, track_ids.tolist())
                    behavior_analyzer.cleanup_local(camera_id, track_ids.tolist())
                    active_tids = {int(t) for t in track_ids.tolist()}
                    for old_tid in list(local_face_boxes[camera_id].keys()):
                        if old_tid not in active_tids:
                            local_face_boxes[camera_id].pop(old_tid, None)
                    for old_key in list(self.face_probe_attempts.keys()):
                        if old_key[0] == camera_id and old_key[1] not in active_tids:
                            self.face_probe_attempts.pop(old_key, None)

                    # Threat object alerts
                    if threat_class_ids:
                        for cls in set(class_ids):
                            if int(cls) in threat_class_ids:
                                cls_name = class_map.get(int(cls), f"class_{int(cls)}")
                                if alert_manager.trigger(
                                    alert_type=ALERT_THREAT_OBJECT,
                                    camera_id=camera_id,
                                    message=f"Suspicious Object: {cls_name.upper()}",
                                    detail=f"A {cls_name} was detected in the surveillance area.",
                                ):
                                    SHARED.push_alert({
                                        "id": str(uuid.uuid4()),
                                        "type": ALERT_THREAT_OBJECT,
                                        "camera_id": camera_id,
                                        "message": f"Suspicious Object: {cls_name.upper()}",
                                        "detail": f"A {cls_name} was detected in the surveillance area.",
                                        "timestamp": time.time(),
                                        "duration_sec": 4.0,
                                    })

                    for i in range(len(tracked)):
                        tid = int(track_ids[i]) if i < len(track_ids) else -1
                        cls = int(class_ids[i]) if i < len(class_ids) else -1
                        if tid < 0 or cls < 0:
                            continue

                        xyxy = tracked.xyxy[i]
                        x1, y1, x2, y2 = xyxy.astype(int)
                        area = max(0, (x2 - x1)) * max(0, (y2 - y1))
                        if area < cfg["reid"].get("min_box_area", 2000):
                            continue

                        if reid_enabled and cls == person_class_id:
                            # Only run Re-ID every N frames for performance
                            if reid_frame_counter % reid_interval == 0:
                                maybe_ready = reid_batcher.add(
                                    (camera_id, tid, xyxy, frame, packet.timestamp)
                                )
                                if maybe_ready:
                                    ready_batches.append(maybe_ready)
                        else:
                            gid = int(f"{abs(hash(camera_id)) % 9999}{tid}")
                            local_global_map[camera_id][tid] = gid
                            local_name_map[camera_id][tid] = class_map.get(cls, "Object")

                if reid_enabled:
                    due_batch = reid_batcher.flush_due()
                    if due_batch:
                        ready_batches.append(due_batch)

                    # Phase 2: batch Re-ID
                    for candidate_batch in ready_batches:
                        batch_inputs = [(fr, xy) for _, _, xy, fr, _ in candidate_batch]
                        try:
                            batch_body_embeddings = feature_encoder.encode_batch(batch_inputs)
                        except Exception as exc:
                            print(f"[WARN] ReID batch failed: {exc}")
                            batch_body_embeddings = [None] * len(candidate_batch)

                        for idx, (camera_id, tid, xyxy, _frame, timestamp) in enumerate(candidate_batch):
                            body_feature = batch_body_embeddings[idx]

                            # ── Ghost Trail escalation gate ──────────────────────────
                            # Anonymous by default: a track only gets run through face
                            # recognition once ITS OWN local behavior already earns
                            # suspicion (or it was already a confirmed/registered
                            # identity on a previous frame). Everyone else stays a
                            # body-embedding-only Guest — no face ever touched.
                            prev_gid = local_global_map[camera_id].get(tid)
                            already_reviewed = (
                                prev_gid is not None
                                and global_manager.get_face_review_status(int(prev_gid)) in {"confirmed", "denied"}
                            )
                            is_new_track = tid not in local_name_map[camera_id]
                            probe_key = (camera_id, tid)
                            probe_attempt = self.face_probe_attempts.get(probe_key, 0)
                            # Retry face extraction for the first few Re-ID passes.
                            # A handoff should not depend on catching the face in
                            # the very first frame of a new local track.
                            retry_face = probe_attempt < 5 or (probe_attempt % 10 == 0)
                            escalate = (
                                is_new_track
                                or already_reviewed
                                or retry_face
                                or behavior_analyzer.should_escalate_to_face(camera_id, tid, timestamp)
                            )

                            face_feature = None
                            if escalate and face_recognizer.available:
                                self.face_probe_attempts[probe_key] = probe_attempt + 1
                                try:
                                    face_feature, detected_face_box = face_recognizer.get_face_data_from_frame(
                                        _frame, xyxy
                                    )
                                    if detected_face_box is not None:
                                        local_face_boxes[camera_id][tid] = detected_face_box
                                except Exception:
                                    pass

                            gid, gname = global_manager.assign_identity(
                                camera_id=camera_id,
                                local_track_id=tid,
                                body_embedding=body_feature,
                                face_embedding=face_feature,
                                timestamp=timestamp,
                                bbox_xyxy=xyxy,
                            )
                            local_global_map[camera_id][tid] = gid
                            local_name_map[camera_id][tid] = gname

                            # ── Behavior-graph scoring (perimeter-wide) ─────────────
                            tier, reason = behavior_analyzer.update_global(gid, camera_id, timestamp)

                            review_status = global_manager.get_face_review_status(gid)
                            registered = global_manager.is_registered(gid)

                            if not registered:
                                # Anonymous guest: alert only when behavior crosses the
                                # Suspicious/High-Risk line, then ask for human review.
                                if behavior_analyzer.should_alert(gid, tier):
                                    risk_label = RISK_LABELS.get(tier, tier)
                                    message = f"Anomalous Behavior — {risk_label}"
                                    detail = f"{gname} on {camera_id}: {reason}"
                                    print(f"[ALERT] {message} | {detail}")
                                    if tier in (RISK_SUSPICIOUS, RISK_HIGH):
                                        self._capture_flag(_frame, xyxy, camera_id, gid, gname, tier, reason, timestamp)
                                    alert_manager.trigger(
                                        alert_type=ALERT_ANOMALOUS_BEHAVIOR,
                                        camera_id=camera_id, message=message, detail=detail, entity_id=gname,
                                    )
                                    SHARED.push_alert({
                                        "id": str(uuid.uuid4()),
                                        "type": ALERT_ANOMALOUS_BEHAVIOR,
                                        "camera_id": camera_id,
                                        "person_id": gid,
                                        "person_name": gname,
                                        "message": message,
                                        "detail": detail,
                                        "risk_tier": tier,
                                        "timestamp": time.time(),
                                        "duration_sec": 86400.0,
                                        "status": "active",
                                    })
                            elif review_status == "confirmed":
                                # Human-accepted identities are authorized. Their
                                # continued presence must not create another security error.
                                pass
                            elif review_status == "denied":
                                # Denied identities remain security-relevant.
                                if behavior_analyzer.should_alert(gid, tier) and gid not in self.alerted_watchlist:
                                    self.alerted_watchlist.add(gid)
                                    message = "High Risk Face Detected"
                                    detail = f"{gname} detected on {camera_id} after behavior escalation ({reason})"
                                    print(f"[ALERT] {message} | {detail}")
                                    SHARED.push_alert({
                                        "id": str(uuid.uuid4()),
                                        "type": ALERT_WATCHLIST_MATCH,
                                        "camera_id": camera_id,
                                        "person_id": gid,
                                        "person_name": gname,
                                        "message": message,
                                        "detail": detail,
                                        "risk_tier": "high_risk",
                                        "timestamp": time.time(),
                                        "duration_sec": 86400.0,
                                        "status": "active",
                                    })
                            elif gid not in self.alerted_watchlist:
                                # Other enrolled profiles can still produce a watchlist
                                # event when behavior escalation matches them.
                                self.alerted_watchlist.add(gid)
                                message = "Watchlist Match"
                                detail = f"{gname} recognized on {camera_id} after behavior escalation ({reason})"
                                print(f"[ALERT] {message} | {detail}")
                                alert_manager.trigger(
                                    alert_type=ALERT_WATCHLIST_MATCH, camera_id=camera_id,
                                    message=message, detail=detail, entity_id=gname,
                                )
                                SHARED.push_alert({
                                    "id": str(uuid.uuid4()),
                                    "type": ALERT_WATCHLIST_MATCH,
                                    "camera_id": camera_id,
                                    "person_id": gid,
                                    "person_name": gname,
                                    "message": message,
                                    "detail": detail,
                                    "risk_tier": tier,
                                    "timestamp": time.time(),
                                    "duration_sec": 86400.0,
                                    "status": "active",
                                })

                # Phase 3: render + push frames to SHARED
                for camera_id, tracked in tracked_by_camera.items():
                    frame = frame_by_camera[camera_id]

                    rendered = annotate_tracked_objects(
                        frame=frame,
                        detections=tracked,
                        class_name_map=class_map,
                        global_ids=local_global_map[camera_id],
                        global_names=local_name_map[camera_id],
                        camera_id=camera_id,
                        threat_class_ids=threat_class_ids,
                        face_boxes=local_face_boxes[camera_id],
                        face_review_statuses=global_manager.get_review_status_map(),
                        flash_on=False,
                        show_fps=cfg.get("ui", {}).get("show_fps", True),
                        fps=SHARED.fps,
                    )
                    rendered = alert_manager.render_onto(rendered, camera_id)
                    SHARED.push_frame(camera_id, rendered)

                # FPS calculation
                frame_counter += len(tracked_by_camera)
                reid_frame_counter += 1
                now = time.time()
                elapsed = now - last_fps_time
                if elapsed >= 1.0:
                    SHARED.fps = frame_counter / elapsed
                    frame_counter = 0
                    last_fps_time = now

        finally:
            stream_manager.stop_all()
            try:
                db.close()
            except Exception:
                pass
            SHARED.status = "stopped"
            print("[INFO] Sentinel tracker stopped.")
