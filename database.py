from __future__ import annotations

import json
import queue
import sqlite3
import threading
from typing import Dict, List, Optional, Tuple

import numpy as np


class IdentityDatabase:
    """
    SQLite-backed persistence for identity embeddings and sighting logs.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._task_queue: "queue.Queue[Tuple[float, str, int, str, Optional[float]]]" = queue.Queue(maxsize=10000)
        self._max_write_batch_size = 100
        self._init_db()
        self._worker = threading.Thread(target=self._writer_loop, name="sqlite-writer", daemon=True)
        self._worker.start()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS registered_identities (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    face_embedding TEXT,
                    face_review_status TEXT NOT NULL DEFAULT 'pending',
                    face_reviewed_ts REAL,
                    face_review_note TEXT,
                    badge_id TEXT DEFAULT '',
                    role TEXT DEFAULT '',
                    clearance TEXT DEFAULT 'Level 2 (Personnel)',
                    profile_note TEXT DEFAULT ''
                )
                """
            )
            # Migrations: add newly introduced review columns when upgrading
            # an existing tracker.db. SQLite raises if the column already exists,
            # so each migration is intentionally best-effort.
            for migration in (
                "ALTER TABLE registered_identities ADD COLUMN face_embedding TEXT",
                "ALTER TABLE registered_identities ADD COLUMN face_review_status TEXT NOT NULL DEFAULT 'pending'",
                "ALTER TABLE registered_identities ADD COLUMN face_reviewed_ts REAL",
                "ALTER TABLE registered_identities ADD COLUMN face_review_note TEXT",
                "ALTER TABLE registered_identities ADD COLUMN badge_id TEXT DEFAULT ''",
                "ALTER TABLE registered_identities ADD COLUMN role TEXT DEFAULT ''",
                "ALTER TABLE registered_identities ADD COLUMN clearance TEXT DEFAULT 'Level 2 (Personnel)'",
                "ALTER TABLE registered_identities ADD COLUMN profile_note TEXT DEFAULT ''",
            ):
                try:
                    conn.execute(migration)
                except Exception:
                    pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sighting_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    camera_id TEXT NOT NULL,
                    global_track_id INTEGER NOT NULL,
                    bounding_box_coords TEXT NOT NULL,
                    match_confidence REAL DEFAULT NULL
                )
                """
            )
            try:
                conn.execute("ALTER TABLE sighting_logs ADD COLUMN match_confidence REAL DEFAULT NULL")
            except Exception:
                pass

            # Flagged (pending-review) captures: a face image saved ONLY when a
            # track's behavior crosses the Suspicious/High-Risk line. Nothing
            # here is final — a human must confirm or dismiss every row via the
            # dashboard before it's treated as an actual "suspicious" tag.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS flagged_persons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    global_track_id INTEGER NOT NULL,
                    guest_label TEXT NOT NULL,
                    risk_tier TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    image_path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending_review',
                    reviewed_ts REAL
                )
                """
            )
            # Persistent security incidents created by manual face review.
            # Unlike transient AI alerts, these remain visible until explicitly
            # acknowledged/resolved and survive an application restart.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS security_incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_type TEXT NOT NULL,
                    person_id INTEGER,
                    person_name TEXT NOT NULL,
                    risk_tier TEXT NOT NULL,
                    message TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    camera_id TEXT,
                    timestamp REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    source TEXT NOT NULL DEFAULT 'manual_face_review',
                    reviewed_ts REAL
                )
                """
            )
            # Reconcile records created by earlier versions: once a face was
            # already accepted/denied, any duplicate pending-review cards for
            # the same global identity are no longer actionable. Accepted
            # review events are informational history, not active alarms.
            conn.execute("""
                UPDATE flagged_persons
                SET status = ri.face_review_status, reviewed_ts = COALESCE(reviewed_ts, ri.face_reviewed_ts)
                FROM registered_identities ri
                WHERE flagged_persons.global_track_id = ri.id
                  AND flagged_persons.status = 'pending_review'
                  AND ri.face_review_status IN ('confirmed','denied')
            """)
            conn.execute("""
                UPDATE security_incidents
                SET status = 'resolved'
                WHERE incident_type = 'face_verification_accepted' AND status = 'active'
            """)
            conn.commit()

    def _writer_loop(self) -> None:
        # Dedicated writer thread keeps one connection for efficient sequential inserts.
        conn = sqlite3.connect(self.db_path, check_same_thread=True)
        try:
            while True:
                if self._stop_event.is_set() and self._task_queue.empty():
                    break
                try:
                    first_payload = self._task_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                batch = [first_payload]
                # Drain additional tasks quickly to form one DB transaction batch.
                while len(batch) < self._max_write_batch_size:
                    try:
                        batch.append(self._task_queue.get_nowait())
                    except queue.Empty:
                        break

                try:
                    conn.execute("BEGIN")
                    conn.executemany(
                        """
                        INSERT INTO sighting_logs(timestamp, camera_id, global_track_id, bounding_box_coords, match_confidence)
                        VALUES(?, ?, ?, ?, ?)
                        """,
                        batch,
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    for _ in batch:
                        self._task_queue.task_done()
        finally:
            conn.close()

    def load_registered_identities(self, active_only: bool = False) -> Dict[int, Dict[str, object]]:
        """Load identity records.

        active_only=True is used by the live identity stitcher: pending/denied
        anonymous Guests remain persisted for review/audit but must not be
        treated as fresh, recently-seen runtime identities after a restart.
        """
        query = """
            SELECT id, name, embedding, face_embedding,
                   face_review_status, face_reviewed_ts, face_review_note,
                   badge_id, role, clearance, profile_note
            FROM registered_identities
        """
        params = ()
        if active_only:
            query += " WHERE name NOT LIKE 'Guest %' OR face_review_status IN ('confirmed', 'denied')"

        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        identities: Dict[int, Dict[str, object]] = {}
        for row in rows:
            body_arr = np.asarray(json.loads(row["embedding"]), dtype=np.float32)
            face_arr = (
                np.asarray(json.loads(row["face_embedding"]), dtype=np.float32)
                if row["face_embedding"] else None
            )
            identities[int(row["id"])] = {
                "name": str(row["name"]),
                "embedding": body_arr,
                "face_embedding": face_arr,
                "face_review_status": str(row["face_review_status"] or "pending"),
                "face_reviewed_ts": row["face_reviewed_ts"],
                "face_review_note": row["face_review_note"],
                "badge_id": row["badge_id"] or "",
                "role": row["role"] or "",
                "clearance": row["clearance"] or "Level 2 (Personnel)",
                "profile_note": row["profile_note"] or "",
            }
        return identities

    def upsert_identity(
        self,
        identity_id: int,
        name: str,
        embedding: np.ndarray,
        face_embedding: Optional[np.ndarray] = None,
    ) -> None:
        emb_json = json.dumps(embedding.astype(float).tolist())
        face_json = json.dumps(face_embedding.astype(float).tolist()) if face_embedding is not None else None
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO registered_identities(
                    id, name, embedding, face_embedding, face_review_status, face_reviewed_ts, face_review_note,
                    badge_id, role, clearance, profile_note
                )
                VALUES(?, ?, ?, ?, 'pending', NULL, NULL, '', '', 'Level 2 (Personnel)', '')
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    embedding = excluded.embedding,
                    face_embedding = COALESCE(excluded.face_embedding, registered_identities.face_embedding),
                    -- Keep the human review decision when the live tracker
                    -- refreshes an embedding. A detection/update must never
                    -- silently turn a confirmed face back into "pending".
                    face_review_status = registered_identities.face_review_status,
                    face_reviewed_ts = registered_identities.face_reviewed_ts,
                    face_review_note = registered_identities.face_review_note
                """,
                (identity_id, name, emb_json, face_json),
            )
            conn.commit()

    def log_sighting(
        self,
        timestamp: float,
        camera_id: str,
        global_track_id: int,
        bbox_coords: List[int],
        match_confidence: Optional[float] = None,
    ) -> None:
        bbox_json = json.dumps([int(v) for v in bbox_coords])
        payload = (float(timestamp), str(camera_id), int(global_track_id), bbox_json,
                   None if match_confidence is None else float(match_confidence))
        # Non-blocking-ish enqueue; fall back to blocking put only if queue is saturated.
        try:
            self._task_queue.put_nowait(payload)
        except queue.Full:
            self._task_queue.put(payload)

    def get_max_guest_number(self) -> int:
        """Return the largest numeric Guest N label persisted in SQLite."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM registered_identities WHERE name LIKE 'Guest %'"
            ).fetchall()
        best = 0
        for row in rows:
            try:
                suffix = str(row["name"]).rsplit(" ", 1)[-1]
                best = max(best, int(suffix))
            except (ValueError, TypeError):
                continue
        return best

    def get_max_identity_id(self) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM registered_identities").fetchone()
        return int(row["max_id"]) if row is not None else 0

    def get_identity_details(self, identity_id: int) -> Dict[str, object]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, name, badge_id, role, clearance, profile_note,
                       face_review_status, face_reviewed_ts, face_review_note
                FROM registered_identities WHERE id = ?
                """,
                (int(identity_id),),
            ).fetchone()
        return dict(row) if row is not None else {}

    def update_identity_details(self, identity_id: int, name: str, badge_id: str = "",
                               role: str = "", clearance: str = "Level 2 (Personnel)",
                               profile_note: str = "") -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """UPDATE registered_identities
                   SET name = ?, badge_id = ?, role = ?, clearance = ?, profile_note = ?
                   WHERE id = ?""",
                (str(name).strip(), str(badge_id).strip(), str(role).strip(),
                 str(clearance).strip(), str(profile_note).strip(), int(identity_id)),
            )
            conn.commit()
        return cur.rowcount > 0

    def get_identity_id_by_name(self, name: str) -> Optional[int]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM registered_identities WHERE name = ? LIMIT 1",
                (str(name),),
            ).fetchone()
        return int(row["id"]) if row is not None else None

    # ------------------------------------------------------------------
    # Flagged persons — capture-on-anomaly, pending human review
    # ------------------------------------------------------------------
    def insert_flagged_person(
        self,
        global_track_id: int,
        guest_label: str,
        risk_tier: str,
        reason: str,
        camera_id: str,
        timestamp: float,
        image_path: str,
    ) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO flagged_persons
                    (global_track_id, guest_label, risk_tier, reason, camera_id, timestamp, image_path, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_review')
                """,
                (int(global_track_id), str(guest_label), str(risk_tier), str(reason),
                 str(camera_id), float(timestamp), str(image_path)),
            )
            conn.commit()
            return int(cur.lastrowid)

    def has_recent_flag(self, global_track_id: int, since_ts: float) -> bool:
        """True if this track already has a flag newer than since_ts —
        used to avoid re-capturing/re-flagging the same person every frame."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM flagged_persons WHERE global_track_id = ? AND timestamp >= ? LIMIT 1",
                (int(global_track_id), float(since_ts)),
            ).fetchone()
        return row is not None

    def list_flagged_persons(self, status: Optional[str] = None) -> List[Dict[str, object]]:
        query = "SELECT * FROM flagged_persons"
        params: Tuple = ()
        if status:
            query += " WHERE status = ?"
            params = (str(status),)
        query += " ORDER BY timestamp DESC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_flagged_person(self, flag_id: int) -> Optional[Dict[str, object]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM flagged_persons WHERE id = ?", (int(flag_id),)
            ).fetchone()
        return dict(row) if row is not None else None

    def set_flagged_status(self, flag_id: int, status: str, reviewed_ts: float) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE flagged_persons SET status = ?, reviewed_ts = ? WHERE id = ?",
                (str(status), float(reviewed_ts), int(flag_id)),
            )
            conn.commit()

    def set_flagged_status_for_identity(self, global_track_id: int, status: str, reviewed_ts: float) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE flagged_persons SET status = ?, reviewed_ts = ? WHERE global_track_id = ? AND status = 'pending_review'",
                (str(status), float(reviewed_ts), int(global_track_id)),
            )
            conn.commit()

    def delete_flagged_person(self, flag_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM flagged_persons WHERE id = ?", (int(flag_id),))
            conn.commit()

    def create_face_acceptance_incident(self, person_id: int, person_name: str, reviewed_ts: float) -> Dict[str, object]:
        """Persist an informational acceptance event as resolved, not an alarm."""
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                """SELECT * FROM security_incidents
                   WHERE person_id = ? AND incident_type = 'face_verification_accepted'
                   ORDER BY timestamp DESC LIMIT 1""", (int(person_id),)
            ).fetchone()
            message = "face has been accepted, person has been added to the database"
            detail = (f"Face verification was accepted for {person_name} (ID #{int(person_id)}). "
                      "The person has been promoted to the enrolled face database.")
            if existing is not None:
                conn.execute(
                    """UPDATE security_incidents SET person_name=?, message=?, detail=?, risk_tier='verified',
                       status='resolved', reviewed_ts=? WHERE id=?""",
                    (str(person_name), message, detail, float(reviewed_ts), int(existing['id']))
                )
                conn.commit()
                row=conn.execute("SELECT * FROM security_incidents WHERE id=?",(int(existing['id']),)).fetchone()
                return dict(row) if row else {}
            cur=conn.execute(
                """INSERT INTO security_incidents(
                    incident_type, person_id, person_name, risk_tier, message, detail, camera_id, timestamp, status, source, reviewed_ts
                ) VALUES(?,?,?,?,?,?,?,?,'resolved','manual_face_review',?)""",
                ('face_verification_accepted',int(person_id),str(person_name),'verified',message,detail,'PERSONS_DB',float(reviewed_ts),float(reviewed_ts))
            )
            conn.commit()
            row=conn.execute("SELECT * FROM security_incidents WHERE id=?",(int(cur.lastrowid),)).fetchone()
            return dict(row) if row else {}

    def deny_flagged_person(self, flag_id: int, reviewed_ts: float) -> Dict[str, object]:
        """Deny a flagged person, retain the profile, and create one High Risk incident."""
        with self._lock, self._connect() as conn:
            row=conn.execute("SELECT * FROM flagged_persons WHERE id=?",(int(flag_id),)).fetchone()
            if row is None: return {}
            flagged=dict(row); gid=int(flagged['global_track_id']); guest_label=str(flagged['guest_label'])
            conn.execute("""UPDATE registered_identities SET face_review_status='denied', face_reviewed_ts=?, face_review_note=? WHERE id=?""",
                         (float(reviewed_ts),'Face denied by operator; categorized as High Risk.',gid))
            conn.execute("""UPDATE flagged_persons SET status='denied', risk_tier='high_risk', reviewed_ts=? WHERE global_track_id=? AND status='pending_review'""",
                         (float(reviewed_ts),gid))
            existing=conn.execute("""SELECT * FROM security_incidents WHERE person_id=? AND incident_type='face_verification_denied' AND status='active' ORDER BY timestamp DESC LIMIT 1""",(gid,)).fetchone()
            if existing is not None:
                conn.commit(); return dict(existing)
            message='Face Verification Denied — High Risk Person'
            detail=f"Manual face verification was denied for {guest_label} (ID #{gid}). The profile has been categorized as High Risk for security review."
            cur=conn.execute("""INSERT INTO security_incidents(
                incident_type,person_id,person_name,risk_tier,message,detail,camera_id,timestamp,status,source,reviewed_ts
            ) VALUES(?,?,?,?,?,?,?,?, 'active','manual_face_review',?)""",
            ('face_verification_denied',gid,guest_label,'high_risk',message,detail,str(flagged['camera_id']),float(reviewed_ts),float(reviewed_ts)))
            conn.commit()
            created=conn.execute("SELECT * FROM security_incidents WHERE id=?",(int(cur.lastrowid),)).fetchone()
            return dict(created) if created else {}

    # ------------------------------------------------------------------
    # Face verification review + persistent security incidents
    # ------------------------------------------------------------------
    def get_face_review(self, person_id: int) -> Dict[str, object]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, name, face_review_status, face_reviewed_ts, face_review_note
                FROM registered_identities
                WHERE id = ?
                """,
                (int(person_id),),
            ).fetchone()
        if row is None:
            return {}
        return dict(row)

    def set_face_review(self, person_id: int, status: str, reviewed_ts: float, note: Optional[str] = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE registered_identities
                SET face_review_status = ?, face_reviewed_ts = ?, face_review_note = ?
                WHERE id = ?
                """,
                (str(status), float(reviewed_ts), note, int(person_id)),
            )
            conn.commit()

    def create_face_denial_incident(self, person_id: int, person_name: str, reviewed_ts: float) -> Dict[str, object]:
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM security_incidents
                WHERE person_id = ?
                  AND incident_type = 'face_verification_denied'
                  AND status = 'active'
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (int(person_id),),
            ).fetchone()
            if existing is not None:
                return dict(existing)

            message = "Face Verification Denied — High Risk Person"
            detail = (
                f"Manual face verification was denied for enrolled profile {person_name} "
                f"(ID #{int(person_id)}). The profile has been escalated to the High Risk category "
                "for security review."
            )
            cur = conn.execute(
                """
                INSERT INTO security_incidents(
                    incident_type, person_id, person_name, risk_tier, message, detail,
                    camera_id, timestamp, status, source
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'active', 'manual_face_review')
                """,
                (
                    'face_verification_denied', int(person_id), str(person_name),
                    'high_risk', message, detail, 'PERSONS_DB', float(reviewed_ts),
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM security_incidents WHERE id = ?", (int(cur.lastrowid),)
            ).fetchone()
        return dict(row)

    def delete_identity(self, person_id: int) -> bool:
        """Remove an identity from the enrolled/reviewed face database."""
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM registered_identities WHERE id = ?", (int(person_id),))
            conn.commit()
        return cur.rowcount > 0

    def list_security_incidents(self, limit: int = 200) -> List[Dict[str, object]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM security_incidents ORDER BY timestamp DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_active_security_incidents(self) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM security_incidents WHERE status = 'active'"
            ).fetchone()
        return int(row["n"]) if row else 0

    def resolve_active_incidents_for_person(self, person_id: int, reviewed_ts: float) -> int:
        """Resolve all active person-specific incidents after an operator
        confirms that the face belongs to an accepted/enrolled person.

        The acceptance event itself is recorded separately as a resolved
        audit record, so confirming a face does not create a new active error.
        """
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE security_incidents
                SET status = 'resolved', reviewed_ts = ?
                WHERE person_id = ?
                  AND status = 'active'
                  AND incident_type != 'face_verification_accepted'
                """,
                (float(reviewed_ts), int(person_id)),
            )
            conn.commit()
            return int(cur.rowcount or 0)

    def resolve_security_incidents_for_person(self, person_id: int, reviewed_ts: float) -> None:
        """Backward-compatible alias used by older callers."""
        self.resolve_active_incidents_for_person(person_id, reviewed_ts)

    def set_security_incident_status(self, incident_id: int, status: str, reviewed_ts: float) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE security_incidents SET status = ?, reviewed_ts = ? WHERE id = ?",
                (str(status), float(reviewed_ts), int(incident_id)),
            )
            conn.commit()

    def clear_security_incidents(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM security_incidents")
            conn.commit()

    def close(self) -> None:
        self._stop_event.set()
        self._task_queue.join()
        if self._worker.is_alive():
            self._worker.join(timeout=2.0)
