from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import numpy as np
from scipy.spatial.distance import cosine

from database import IdentityDatabase

if TYPE_CHECKING:
    from face_recognizer import FaceRecognizer


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class RuntimeIdentity:
    identity_id: int
    name: str
    body_embedding: np.ndarray
    face_embedding: Optional[np.ndarray]
    last_seen_ts: float
    last_seen_camera: str
    is_registered: bool = False
    face_review_status: str = "pending"
    last_match_confidence: float = 0.0
    body_history: List[np.ndarray] = field(default_factory=list)
    face_history: List[np.ndarray] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------
class GlobalIdentityManager:
    """
    Dual-model identity assignment — conservative, false-positive-resistant.

    KEY DESIGN PRINCIPLES
    ─────────────────────
    1.  Every NEW track starts as a Guest. No stranger is ever instantly
        labelled as a registered person, no matter how high the score.

    2.  Upgrade from Guest → Registered requires SUSTAINED evidence:
          - Face score >= face_certain_threshold  for  confirm_frames
            consecutive frames (votes must be for the SAME candidate).
          - OR body Re-ID score >= body_registered_threshold for
            confirm_frames frames (only used when face is not visible).

    3.  Once confirmed, the track keeps its registered name and the vote
        buffer is cleared.

    4.  Thresholds are deliberately strict to avoid false positives.
        Only raise them if you are missing true positives (Ganesh/Lakshay
        not being recognised when they should be).
    """

    GUEST_PREFIX = "Guest"

    def __init__(
        self,
        db: IdentityDatabase,
        face_recognizer: Optional["FaceRecognizer"] = None,
        # ── Face thresholds (ArcFace cosine similarity, range roughly -1..1) ──
        # Minimum score to cast a VOTE for a registered identity.
        # Raise this to reduce false positives; lower to catch more true positives.
        face_threshold: float = 0.72,
        # Votes needed before the Guest is promoted to a registered name.
        confirm_frames: int = 15,
        # ── Body Re-ID thresholds (OSNet cosine similarity) ──────────────────
        # ONLY used when no face is visible.  Keep very strict.
        body_registered_threshold: float = 0.88,
        # Threshold for keeping the SAME Guest ID across frames.
        body_guest_threshold: float = 0.55,
        max_time_gap_sec: float = 30.0,
        guest_handoff_grace_sec: float = 0.75,
        max_gallery_size: int = 2000,
        guest_face_threshold: float = 0.55,
        registered_face_stitch_threshold: float = 0.60,
        camera_handoff_max_gap_sec: float = 8.0,
    ) -> None:
        self.db = db
        self.face_recognizer = face_recognizer
        self.face_threshold = face_threshold
        self.confirm_frames = confirm_frames
        self.body_registered_threshold = body_registered_threshold
        self.body_guest_threshold = body_guest_threshold
        self.max_time_gap_sec = max_time_gap_sec
        self.guest_handoff_grace_sec = max(0.25, float(guest_handoff_grace_sec))
        self.max_gallery_size = max_gallery_size
        # Stitching thresholds are intentionally separate from the stricter
        # enrollment/verification threshold. A camera handoff often has a
        # lower-quality face or a different body viewpoint than enrollment.
        self.guest_face_threshold = float(guest_face_threshold)
        self.registered_face_stitch_threshold = float(registered_face_stitch_threshold)
        self.camera_handoff_max_gap_sec = max(1.0, float(camera_handoff_max_gap_sec))
        self.history_size = 5

        self.local_to_global: Dict[Tuple[str, int], int] = {}
        self.identities: Dict[int, RuntimeIdentity] = {}
        self._next_global_id: int = 1
        self._guest_counter: int = 0

        # Per-track vote buffer: track_key → {registered_gid: consecutive_vote_count}
        self._votes: Dict[Tuple[str, int], Dict[int, int]] = {}

        # Exclusive lock: registered_gid → local_key that confirmed it.
        # Only ONE track may hold a confirmed registered identity at a time.
        self._confirmed_by: Dict[int, Tuple[str, int]] = {}

        # Anonymous guest identities are also exclusive while actively tracked.
        # This prevents two live tracks (for example the same frame on two
        # cameras) from being merged into one Guest identity. When the old
        # track disappears, the guest can be re-linked on the next camera.
        self._guest_held_by: Dict[int, Tuple[str, int]] = {}

        self._load_from_db()

    # ------------------------------------------------------------------
    def _load_from_db(self) -> None:
        # Clear existing registered identities so that DB deletions take effect
        stale_gids = [gid for gid, r in self.identities.items() if r.is_registered]
        for gid in stale_gids:
            self.identities.pop(gid, None)

        known = self.db.load_registered_identities(active_only=True)
        now = time.time()
        # Continue Guest numbering across application restarts so labels are
        # stable and never recycle to Guest 1/Guest 2 after a restart.
        try:
            self._guest_counter = max(self._guest_counter, self.db.get_max_guest_number())
        except Exception:
            pass
        for identity_id, payload in known.items():
            name = str(payload["name"])
            body_emb = np.asarray(payload["embedding"], dtype=np.float32)
            face_emb = (
                np.asarray(payload["face_embedding"], dtype=np.float32)
                if payload.get("face_embedding") is not None
                else None
            )
            self.identities[identity_id] = RuntimeIdentity(
                identity_id=identity_id,
                name=name,
                body_embedding=body_emb,
                face_embedding=face_emb,
                last_seen_ts=now,
                last_seen_camera="db_seed",
                # A Guest becomes a real enrolled profile after a human
                # accepts its face. The review state is persisted in SQLite,
                # so this survives application restarts without renaming the
                # profile.
                is_registered=(not name.startswith(self.GUEST_PREFIX))
                or str(payload.get("face_review_status") or "pending") in {"confirmed", "denied"},
                face_review_status=str(payload.get("face_review_status") or "pending"),
                body_history=[body_emb.copy()],
                face_history=[face_emb.copy()] if face_emb is not None else [],
            )
        self._next_global_id = max(self.db.get_max_identity_id() + 1, 1)
        print(f"[IdentityManager] Loaded {len(known)} registered identities from DB.")
        for gid, rec in self.identities.items():
            has_face = rec.face_embedding is not None
            print(f"  ID={gid} name={rec.name} face={'YES' if has_face else 'NO'}")

    def has_face_gallery(self) -> bool:
        """Return True when at least one persisted reviewed profile has a face template."""
        return any(
            record.face_embedding is not None
            and record.face_review_status in {"confirmed", "denied"}
            for record in self.identities.values()
        )

    def get_face_review_status(self, gid: int) -> str:
        record = self.identities.get(int(gid))
        return str(record.face_review_status if record is not None else "pending")

    def set_face_review_status(self, gid: int, status: str) -> bool:
        record = self.identities.get(int(gid))
        if record is None:
            return False
        status = str(status).strip().lower()
        if status not in {"pending", "confirmed", "denied"}:
            return False
        record.face_review_status = status
        # Reviewed identities remain in the security database. A denied face
        # is still a known/reviewed identity, just with a red High-Risk box.
        if status in {"confirmed", "denied"}:
            record.is_registered = True
        else:
            record.is_registered = not record.name.startswith(self.GUEST_PREFIX)
        return True

    def get_review_status_map(self) -> Dict[int, str]:
        return {gid: rec.face_review_status for gid, rec in self.identities.items()}

    def is_registered(self, gid: int) -> bool:
        record = self.identities.get(int(gid))
        return bool(record and record.is_registered)

    def get_identity_details(self, gid: int) -> Dict[str, object]:
        return self.db.get_identity_details(int(gid))

    def update_identity_details(
        self, gid: int, name: str, badge_id: str = "", role: str = "",
        clearance: str = "Level 2 (Personnel)", profile_note: str = ""
    ) -> bool:
        record = self.identities.get(int(gid))
        if record is None:
            return False
        ok = self.db.update_identity_details(int(gid), name, badge_id, role, clearance, profile_note)
        if ok:
            record.name = str(name).strip()
        return ok

    # ------------------------------------------------------------------
    def remove_identity(self, gid: int) -> None:
        """Remove an identity and clean up all references to it."""
        self.identities.pop(gid, None)

        # Clean up local_to_global: remove any local track mappings to this gid
        keys_to_remove = [k for k, v in self.local_to_global.items() if v == gid]
        for k in keys_to_remove:
            del self.local_to_global[k]

        # Clean up _votes: remove any vote entries that were pointing to this gid
        for vote_buf in self._votes.values():
            vote_buf.pop(gid, None)

        # Release the exclusive lock if held
        self._confirmed_by.pop(gid, None)
        self._guest_held_by.pop(gid, None)

        print(f"[IdentityManager] Removed identity {gid}")

    # ------------------------------------------------------------------
    def cleanup_camera_tracks(self, camera_id: str, active_track_ids: List[int]) -> None:
        """
        Called every frame to purge tracks that are no longer active on the given camera.
        Releases any exclusive identity locks held by lost tracks so others can claim them.
        """
        active_keys = {(camera_id, int(tid)) for tid in active_track_ids}
        stale_keys = [k for k in self.local_to_global.keys() if k[0] == camera_id and k not in active_keys]
        
        for k in stale_keys:
            gid = self.local_to_global.pop(k, None)
            self._votes.pop(k, None)
            
            # Release exclusive lock if this lost track was holding it.
            if gid is not None and self._confirmed_by.get(gid) == k:
                self._confirmed_by.pop(gid, None)
                print(f"[IdentityManager] Released exclusive lock on '{self.identities[gid].name}' (track {k} lost)")
            if gid is not None and self._guest_held_by.get(gid) == k:
                self._guest_held_by.pop(gid, None)
                print(f"[IdentityManager] Released guest link for '{self.identities[gid].name}' (track {k} lost)")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def assign_identity(
        self,
        camera_id: str,
        local_track_id: int,
        body_embedding: Optional[np.ndarray],
        face_embedding: Optional[np.ndarray],
        timestamp: float,
        bbox_xyxy: np.ndarray,
    ) -> Tuple[int, str]:
        local_key = (camera_id, int(local_track_id))

        # A fresh local tracker ID must first try to attach to an already-known
        # person, then to a recent anonymous Guest. This is the key global
        # stitching path across cameras.
        is_new_global_identity = False
        if local_key not in self.local_to_global:
            known_gid = self._find_existing_registered(
                body_embedding, face_embedding, timestamp, local_key
            )
            if known_gid is not None:
                self.local_to_global[local_key] = known_gid
                self._confirmed_by[known_gid] = local_key
            else:
                guest_gid = self._find_existing_guest(
                    body_embedding, face_embedding, timestamp, local_key
                )
                if guest_gid is None:
                    guest_gid = self._create_guest(
                        body_embedding, face_embedding, timestamp, camera_id
                    )
                    is_new_global_identity = True
                self.local_to_global[local_key] = guest_gid
                self._guest_held_by[guest_gid] = local_key

        current_gid = self.local_to_global[local_key]
        record = self.identities[current_gid]

        # Calculate similarity BEFORE updating the identity with the current
        # frame. Updating first would make every observation compare against
        # its own just-stored embedding and falsely report ~100% confidence.
        if is_new_global_identity:
            pre_update_confidence: Optional[float] = None
        else:
            pre_face_score = self._best_similarity(
                face_embedding,
                record.face_history or ([record.face_embedding] if record.face_embedding is not None else []),
                face=True,
            )
            pre_body_score = self._best_similarity(
                body_embedding, record.body_history or [record.body_embedding], face=False
            )
            valid_scores = [v for v in (pre_face_score, pre_body_score) if v >= 0.0]
            pre_update_confidence = max(valid_scores) if valid_scores else None

        # Do not force a single global identity to one camera. A real person
        # can legitimately appear in overlapping camera views. Instead, the
        # matcher enforces uniqueness per CAMERA so two simultaneous people in
        # the same camera cannot collapse into one Guest.
        if not record.is_registered:
            confirmed_gid = self._accumulate_votes(
                local_key, face_embedding, body_embedding, timestamp
            )
            if confirmed_gid is not None:
                # Only prevent a collision with another active track on the
                # same camera. Cross-camera observations may share a global ID.
                if not self._same_camera_identity_conflict(confirmed_gid, local_key):
                    self._confirmed_by[confirmed_gid] = local_key
                    self._guest_held_by.pop(confirmed_gid, None)
                    self.local_to_global[local_key] = confirmed_gid
                    current_gid = confirmed_gid
                    record = self.identities[current_gid]
                else:
                    self._votes.pop(local_key, None)
        else:
            self._confirmed_by[current_gid] = local_key
            self._votes.pop(local_key, None)

        self._update_seen(current_gid, body_embedding, face_embedding, timestamp, camera_id)
        # Persist every Re-ID sighting so analytics can distinguish authorized
        # and anonymous traffic rather than inferring status from the name.
        record.last_match_confidence = float(pre_update_confidence or 0.0)
        self.db.log_sighting(
            timestamp, camera_id, current_gid, bbox_xyxy.astype(int).tolist(),
            match_confidence=pre_update_confidence,
        )
        return current_gid, self.identities[current_gid].name

    # ------------------------------------------------------------------
    # Step 1 helper — match persisted enrolled/reviewed identities
    # ------------------------------------------------------------------
    def _find_existing_registered(
        self,
        body_emb: Optional[np.ndarray],
        face_emb: Optional[np.ndarray],
        timestamp: float,
        local_key: Tuple[str, int],
    ) -> Optional[int]:
        """Match a fresh local track against persisted reviewed/enrolled identities."""
        if body_emb is None and face_emb is None:
            return None

        best_gid: Optional[int] = None
        best_score = -1.0
        best_kind = ""

        for gid, record in self.identities.items():
            if not record.is_registered:
                continue
            if self._same_camera_identity_conflict(gid, local_key):
                continue

            gap = timestamp - record.last_seen_ts
            if record.last_seen_camera != "db_seed" and (gap < -0.5 or gap > self.max_time_gap_sec):
                continue

            face_score = self._best_similarity(face_emb, record.face_history or ([record.face_embedding] if record.face_embedding is not None else []), face=True)
            body_score = self._best_similarity(body_emb, record.body_history or [record.body_embedding], face=False)

            # Face is authoritative for reviewed/enrolled profiles. The lower
            # handoff threshold is used only for stitching an already-reviewed
            # identity; enrollment itself remains governed by face_threshold.
            if face_score >= self.registered_face_stitch_threshold:
                score = face_score + 0.02 * max(body_score, 0.0)
                if score > best_score:
                    best_gid, best_score, best_kind = gid, score, f"face={face_score:.3f}"
            elif body_score >= self.body_registered_threshold:
                if body_score > best_score:
                    best_gid, best_score, best_kind = gid, body_score, f"body={body_score:.3f}"

        if best_gid is not None:
            self._confirmed_by[best_gid] = local_key
            print(
                f"[IdentityManager] Matched persisted identity '{self.identities[best_gid].name}' "
                f"for {local_key} via {best_kind}"
            )
        return best_gid

    # ------------------------------------------------------------------
    # Step 1 helper — look for an existing Guest profile to re-use
    # ------------------------------------------------------------------
    def _find_existing_guest(
        self,
        body_emb: Optional[np.ndarray],
        face_emb: Optional[np.ndarray],
        timestamp: float,
        local_key: Tuple[str, int],
        exclude_gid: Optional[int] = None,
    ) -> Optional[int]:
        """
        Stitch a fresh local track onto a recent Guest.

        Important fix from v4: a Guest is no longer blocked merely because a
        different camera is still seeing it. The old one-holder lock made
        camera handoff impossible when both streams were processed in the same
        loop (their timestamps differ by milliseconds). We allow a global Guest
        to be observed by multiple cameras while still preventing two tracks in
        the SAME camera from using that Guest.
        """
        if body_emb is None and face_emb is None:
            return None

        best_gid: Optional[int] = None
        best_score = -1.0
        best_kind = ""

        for gid, record in self.identities.items():
            if exclude_gid is not None and int(gid) == int(exclude_gid):
                continue
            if record.is_registered:
                continue
            if self._same_camera_identity_conflict(gid, local_key):
                continue

            gap = timestamp - record.last_seen_ts
            if gap < -0.5 or gap > self.max_time_gap_sec:
                continue

            face_score = self._best_similarity(
                face_emb,
                record.face_history or ([record.face_embedding] if record.face_embedding is not None else []),
                face=True,
            )
            body_score = self._best_similarity(
                body_emb,
                record.body_history or [record.body_embedding],
                face=False,
            )

            same_camera = record.last_seen_camera == local_key[0]
            camera_change = not same_camera
            recent_handoff = camera_change and gap <= self.camera_handoff_max_gap_sec

            # Prefer face, but use body Re-ID when faces are unavailable. A
            # modest face score is enough for Guest-to-Guest stitching because
            # this is identity continuity, not automatic enrollment.
            if face_score >= self.guest_face_threshold:
                score = 0.72 * face_score + (0.28 * body_score if body_score >= 0 else 0.0)
                if recent_handoff:
                    score += 0.03
                if score > best_score:
                    best_gid, best_score, best_kind = gid, score, f"face={face_score:.3f}, body={body_score:.3f}"
                continue

            # Body fallback is intentionally a little stricter for a cross-
            # camera handoff than for ordinary same-camera re-linking.
            required_body = self.body_guest_threshold
            if recent_handoff:
                required_body = max(required_body, 0.50)
            if body_score >= required_body:
                score = body_score + (0.03 if recent_handoff else 0.0)
                if score > best_score:
                    best_gid, best_score, best_kind = gid, score, f"body={body_score:.3f}"

        if best_gid is not None:
            self._guest_held_by[best_gid] = local_key
            record = self.identities[best_gid]
            print(
                f"[STITCH] Linked {local_key} -> {record.name} via {best_kind}; "
                f"gap={timestamp-record.last_seen_ts:.2f}s, cameras={record.last_seen_camera}->{local_key[0]}"
            )
        return best_gid

    def _same_camera_identity_conflict(self, gid: int, local_key: Tuple[str, int]) -> bool:
        """Return True when another active local track in the same camera owns gid."""
        camera_id, tid = local_key
        for (cam, other_tid), mapped_gid in self.local_to_global.items():
            if cam == camera_id and int(other_tid) != int(tid) and int(mapped_gid) == int(gid):
                return True
        return False

    @staticmethod
    def _best_similarity(
        query: Optional[np.ndarray],
        references: List[np.ndarray],
        face: bool,
    ) -> float:
        if query is None or not references:
            return -1.0
        best = -1.0
        q = np.asarray(query, dtype=np.float32)
        qnorm = np.linalg.norm(q)
        if qnorm <= 1e-8:
            return -1.0
        q = q / qnorm
        for ref in references:
            if ref is None:
                continue
            r = np.asarray(ref, dtype=np.float32)
            rnorm = np.linalg.norm(r)
            if rnorm <= 1e-8:
                continue
            r = r / rnorm
            try:
                score = float(np.dot(q, r))
            except Exception:
                continue
            if score > best:
                best = score
        return best

    def _append_history(self, history: List[np.ndarray], embedding: Optional[np.ndarray]) -> None:
        if embedding is None or embedding.size == 0:
            return
        vec = np.asarray(embedding, dtype=np.float32).copy()
        norm = np.linalg.norm(vec)
        if norm > 1e-8:
            vec /= norm
        history.append(vec)
        if len(history) > self.history_size:
            del history[:-self.history_size]

    # ------------------------------------------------------------------
    # Step 2 helper — accumulate votes per-track
    # ------------------------------------------------------------------
    def _accumulate_votes(
        self,
        local_key: Tuple[str, int],
        face_emb: Optional[np.ndarray],
        body_emb: Optional[np.ndarray],
        timestamp: float,
    ) -> Optional[int]:
        """
        Cast a vote for a registered identity based on the current frame.
        Returns the confirmed GID once votes reach confirm_frames, else None.

        Priority:
          1. Face embedding (ArcFace) — most reliable.
          2. Body Re-ID (OSNet) — fallback when face is not detected.

        A vote is only cast when the score clearly exceeds face_threshold.
        If the best score is BELOW the threshold, any existing vote streak
        for that candidate is reset so a bad frame cannot coast on past votes.
        """
        best_candidate: Optional[int] = None
        best_score: float = -1.0
        using_face: bool = False

        # ── Primary: face ─────────────────────────────────────────────
        if face_emb is not None:
            for gid, record in self.identities.items():
                if not record.is_registered or record.face_embedding is None:
                    continue
                score = float(np.dot(face_emb, record.face_embedding))
                if score >= self.face_threshold and score > best_score:
                    best_score = score
                    best_candidate = gid
                    using_face = True

        # ── Fallback: body Re-ID (only if NO face detected) ──────────
        if best_candidate is None and face_emb is None and body_emb is not None:
            for gid, record in self.identities.items():
                if not record.is_registered:
                    continue
                score = 1.0 - cosine(body_emb, record.body_embedding)

                if score >= self.body_registered_threshold and score > best_score:
                    best_score = score
                    best_candidate = gid

        # ── Update vote buffer ─────────────────────────────────────────
        vote_buf = self._votes.setdefault(local_key, {})

        if best_candidate is None:
            # No strong match this frame — reset ALL streak counters
            vote_buf.clear()
            return None

        # Increment the winning candidate's count and reset others
        for k in list(vote_buf.keys()):
            if k != best_candidate:
                vote_buf.pop(k)

        vote_buf[best_candidate] = vote_buf.get(best_candidate, 0) + 1
        count = vote_buf[best_candidate]


        if count >= self.confirm_frames:
            self._votes.pop(local_key, None)
            print(
                f"  >>> CONFIRMED: '{self.identities[best_candidate].name}' "
                f"({self.confirm_frames} frames, score={best_score:.4f})"
            )
            return best_candidate

        return None

    # ------------------------------------------------------------------
    # Guest creation — never written to DB
    # ------------------------------------------------------------------
    def _create_guest(
        self,
        body_emb: Optional[np.ndarray],
        face_emb: Optional[np.ndarray],
        timestamp: float,
        camera_id: str,
    ) -> int:
        self._guest_counter += 1
        gid = self._next_global_id
        self._next_global_id += 1
        body_vec = body_emb if body_emb is not None else np.zeros((512,), dtype=np.float32)
        name = f"{self.GUEST_PREFIX} {self._guest_counter}"
        self.identities[gid] = RuntimeIdentity(
            identity_id=gid,
            name=name,
            body_embedding=body_vec.astype(np.float32),
            face_embedding=face_emb,
            last_seen_ts=timestamp,
            last_seen_camera=camera_id,
            is_registered=False,
            body_history=[body_vec.astype(np.float32).copy()],
            face_history=[face_emb.astype(np.float32).copy()] if face_emb is not None else [],
        )

        self.db.upsert_identity(gid, name, body_vec.astype(np.float32), face_emb)

        self._trim_identities()
        return gid

    def promote_identity(self, gid: int) -> bool:
        """Promote an anonymous Guest runtime identity to an enrolled profile."""
        record = self.identities.get(int(gid))
        if record is None:
            return False
        record.is_registered = True
        record.face_review_status = "confirmed"
        self._guest_held_by.pop(int(gid), None)
        self.db.upsert_identity(
            int(gid), record.name, record.body_embedding, record.face_embedding,
        )
        print(f"[IdentityManager] Promoted '{record.name}' (ID={int(gid)}) to enrolled identity")
        return True

    # ------------------------------------------------------------------
    # Embedding update (slow EMA — registered; faster — guests)
    # ------------------------------------------------------------------
    def _update_seen(
        self,
        gid: int,
        body_emb: Optional[np.ndarray],
        face_emb: Optional[np.ndarray],
        timestamp: float,
        camera_id: str,
    ) -> None:
        record = self.identities[gid]

        if body_emb is not None and body_emb.size > 0:
            alpha = 0.02 if record.is_registered else 0.15
            record.body_embedding = (
                (1 - alpha) * record.body_embedding + alpha * body_emb
            ).astype(np.float32)
            self._append_history(record.body_history, body_emb)
            if record.is_registered:
                self.db.upsert_identity(gid, record.name, record.body_embedding)

        if face_emb is not None:
            if record.face_embedding is None:
                record.face_embedding = face_emb.copy()
            elif record.is_registered:
                # Very slow drift for enrolled/reviewed identities. Keep the
                # gallery history as a separate set of anchors so cross-camera
                # matching does not depend on a single EMA vector.
                record.face_embedding = (
                    0.98 * record.face_embedding + 0.02 * face_emb
                ).astype(np.float32)
                norm = np.linalg.norm(record.face_embedding)
                if norm > 1e-8:
                    record.face_embedding /= norm
            self._append_history(record.face_history, face_emb)

            # Persist a newly discovered face even while the person is pending;
            # this makes a later confirm/deny decision survive a restart.
            if not record.is_registered:
                self.db.upsert_identity(
                    gid, record.name, record.body_embedding, record.face_embedding
                )

        record.last_seen_ts = timestamp
        record.last_seen_camera = camera_id

    # ------------------------------------------------------------------
    # Gallery trim — guests first, registered never pruned
    # ------------------------------------------------------------------
    def _trim_identities(self) -> None:
        if len(self.identities) <= self.max_gallery_size:
            return
        guests = sorted(
            [(gid, r) for gid, r in self.identities.items() if not r.is_registered],
            key=lambda x: x[1].last_seen_ts,
        )
        excess = len(self.identities) - self.max_gallery_size
        for gid, _ in guests[:excess]:
            self.identities.pop(gid, None)