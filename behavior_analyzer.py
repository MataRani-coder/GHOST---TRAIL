"""
behavior_analyzer.py
=====================
Ghost Trail's behavior-anomaly layer.

This is the piece that turns a generic "person tracker" into Ghost Trail:
instead of alerting on every anonymous person the cameras see, it scores
*behavior* — dwell time, loitering, repeat passes, cross-camera zone-hopping,
off-hours presence — into an explainable risk tier, and only then decides
whether to (a) escalate the track to face recognition against the watchlist,
and (b) raise an alert, with a plain-language reason attached.

"Anonymous until it matters."

Two granularities:
  - LOCAL  (camera_id, track_id): cheap, available before cross-camera Re-ID
    has resolved a global identity. Used to gate whether face recognition is
    even attempted for a track — most people passing through stay anonymous
    (body-embedding only) and never reach this stage.
  - GLOBAL (global_id): available once GlobalIdentityManager has stitched the
    track across cameras. Used to catch loitering and zone-hopping across the
    whole perimeter, and to decide whether to raise a dashboard alert.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# ── Risk tiers ────────────────────────────────────────────────────────────
RISK_NONE = "none"
RISK_WATCH = "watch"
RISK_SUSPICIOUS = "suspicious"
RISK_HIGH = "high_risk"

_RISK_ORDER = {RISK_NONE: 0, RISK_WATCH: 1, RISK_SUSPICIOUS: 2, RISK_HIGH: 3}

RISK_LABELS = {
    RISK_NONE: "Normal",
    RISK_WATCH: "Watch",
    RISK_SUSPICIOUS: "Suspicious",
    RISK_HIGH: "High Risk",
}


@dataclass
class _TrackRecord:
    first_seen_ts: float
    last_seen_ts: float
    zones_visited: List[Tuple[str, float]] = field(default_factory=list)  # (camera_id, ts)
    reentry_count: int = 0
    last_alerted_tier: str = RISK_NONE


class BehaviorAnalyzer:
    """
    Explainable behavior-anomaly scorer.

    All thresholds are intentionally short here (seconds, not minutes) so the
    effect is visible in a live demo; tune them up for real deployment via
    the `behavior:` section of config.yaml.
    """

    def __init__(
        self,
        watch_dwell_sec: float = 8.0,
        suspicious_dwell_sec: float = 20.0,
        high_risk_dwell_sec: float = 45.0,
        off_hours_start: int = 22,  # 22:00
        off_hours_end: int = 6,     # 06:00
        reentry_high_risk: int = 3,
        zone_hop_window_sec: float = 90.0,
    ) -> None:
        self.watch_dwell_sec = watch_dwell_sec
        self.suspicious_dwell_sec = suspicious_dwell_sec
        self.high_risk_dwell_sec = high_risk_dwell_sec
        self.off_hours_start = off_hours_start
        self.off_hours_end = off_hours_end
        self.reentry_high_risk = reentry_high_risk
        self.zone_hop_window_sec = zone_hop_window_sec

        self._local: Dict[Tuple[str, int], _TrackRecord] = {}
        self._global: Dict[int, _TrackRecord] = {}

    # ------------------------------------------------------------------
    def _is_off_hours(self, ts: float) -> bool:
        hour = time.localtime(ts).tm_hour
        if self.off_hours_start > self.off_hours_end:
            return hour >= self.off_hours_start or hour < self.off_hours_end
        return self.off_hours_start <= hour < self.off_hours_end

    # ------------------------------------------------------------------
    def _score(self, rec: _TrackRecord, ts: float) -> Tuple[str, str]:
        """Turn a track's history into (risk_tier, human-readable reason)."""
        dwell = ts - rec.first_seen_ts
        n_zones = len({z for z, _ in rec.zones_visited})

        reasons: List[str] = []
        tier = RISK_NONE

        if dwell >= self.high_risk_dwell_sec:
            tier = RISK_HIGH
            reasons.append(f"{dwell:.0f}s continuous presence")
        elif dwell >= self.suspicious_dwell_sec:
            tier = RISK_SUSPICIOUS
            reasons.append(f"{dwell:.0f}s dwell time")
        elif dwell >= self.watch_dwell_sec:
            tier = RISK_WATCH
            reasons.append(f"{dwell:.0f}s in view")

        if rec.reentry_count >= self.reentry_high_risk:
            tier = RISK_HIGH
            reasons.append(f"{rec.reentry_count} repeat passes")
        elif rec.reentry_count >= 1 and _RISK_ORDER[tier] < _RISK_ORDER[RISK_SUSPICIOUS]:
            tier = RISK_SUSPICIOUS
            reasons.append(f"{rec.reentry_count} repeat pass(es)")

        if n_zones >= 2 and _RISK_ORDER[tier] < _RISK_ORDER[RISK_SUSPICIOUS]:
            tier = RISK_SUSPICIOUS
            reasons.append(f"crossed {n_zones} camera zones")

        if self._is_off_hours(ts) and tier != RISK_NONE:
            bump = {RISK_WATCH: RISK_SUSPICIOUS, RISK_SUSPICIOUS: RISK_HIGH, RISK_HIGH: RISK_HIGH}
            if tier in bump:
                tier = bump[tier]
                reasons.append("outside normal activity hours")

        reason = ", ".join(reasons) if reasons else "normal activity"
        return tier, reason

    # ------------------------------------------------------------------
    # LOCAL (pre-identity) — gates whether face recognition runs at all
    # ------------------------------------------------------------------
    def update_local(self, camera_id: str, track_id: int, timestamp: float) -> Tuple[str, str]:
        key = (camera_id, track_id)
        rec = self._local.get(key)
        if rec is None:
            rec = _TrackRecord(first_seen_ts=timestamp, last_seen_ts=timestamp)
            self._local[key] = rec
        rec.last_seen_ts = timestamp
        return self._score(rec, timestamp)

    def should_escalate_to_face(self, camera_id: str, track_id: int, timestamp: float) -> bool:
        """True once a track's LOCAL behavior alone earns suspicion.
        Below this, the track is never run through face recognition —
        it stays a fully anonymous body-embedding-only Guest."""
        tier, _ = self.update_local(camera_id, track_id, timestamp)
        return _RISK_ORDER[tier] >= _RISK_ORDER[RISK_SUSPICIOUS]

    # ------------------------------------------------------------------
    # GLOBAL (post cross-camera stitching) — drives alerts
    # ------------------------------------------------------------------
    def update_global(self, global_id: int, camera_id: str, timestamp: float) -> Tuple[str, str]:
        rec = self._global.get(global_id)
        if rec is None:
            rec = _TrackRecord(first_seen_ts=timestamp, last_seen_ts=timestamp)
            self._global[global_id] = rec

        same_cam_hits = [t for z, t in rec.zones_visited if z == camera_id]
        if same_cam_hits and (timestamp - same_cam_hits[-1]) > 3.0:
            rec.reentry_count += 1

        rec.zones_visited.append((camera_id, timestamp))
        cutoff = timestamp - self.zone_hop_window_sec
        rec.zones_visited = [(z, t) for z, t in rec.zones_visited if t >= cutoff]
        rec.last_seen_ts = timestamp

        return self._score(rec, timestamp)

    def should_alert(self, global_id: int, tier: str) -> bool:
        """De-duped: fires only the first time a track reaches a NEW,
        higher risk tier — not every frame it stays there."""
        rec = self._global.get(global_id)
        if rec is None:
            return False
        if _RISK_ORDER[tier] >= _RISK_ORDER[RISK_SUSPICIOUS] and _RISK_ORDER[tier] > _RISK_ORDER[rec.last_alerted_tier]:
            rec.last_alerted_tier = tier
            return True
        return False

    # ------------------------------------------------------------------
    def cleanup_local(self, camera_id: str, active_track_ids: List[int]) -> None:
        active = {(camera_id, tid) for tid in active_track_ids}
        stale = [k for k in self._local if k[0] == camera_id and k not in active]
        for k in stale:
            self._local.pop(k, None)
