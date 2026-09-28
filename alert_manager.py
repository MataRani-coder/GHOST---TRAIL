from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Alert types
# ─────────────────────────────────────────────────────────────────────────────
ALERT_UNKNOWN_PERSON     = "unknown_person"       # legacy — kept for compatibility
ALERT_THREAT_OBJECT      = "threat_object"
ALERT_ANOMALOUS_BEHAVIOR = "anomalous_behavior"   # Ghost Trail: behavior-graph flag, identity still anonymous
ALERT_WATCHLIST_MATCH    = "watchlist_match"      # Ghost Trail: escalated + matched a registered identity

# Priority (higher wins when multiple alerts are active on one camera) and
# on-screen styling for each alert type. BGR colors (OpenCV convention).
_ALERT_STYLE = {
    ALERT_THREAT_OBJECT: {
        "priority": 3,
        "overlay_color": (0, 0, 180),
        "border_color": (0, 0, 255),
        "banner_color": (0, 0, 200),
        "icon_text": "!! THREAT DETECTED !!",
    },
    ALERT_WATCHLIST_MATCH: {
        "priority": 2,
        "overlay_color": (0, 40, 170),
        "border_color": (0, 90, 255),
        "banner_color": (0, 60, 200),
        "icon_text": "!! WATCHLIST MATCH !!",
    },
    ALERT_ANOMALOUS_BEHAVIOR: {
        "priority": 1,
        "overlay_color": (120, 70, 10),
        "border_color": (232, 211, 143),
        "banner_color": (150, 90, 20),
        "icon_text": "!! ANOMALOUS BEHAVIOR !!",
    },
    ALERT_UNKNOWN_PERSON: {
        "priority": 1,
        "overlay_color": (0, 60, 200),
        "border_color": (0, 100, 255),
        "banner_color": (0, 80, 220),
        "icon_text": "!! UNKNOWN PERSON !!",
    },
}


@dataclass
class Alert:
    alert_type: str          # ALERT_UNKNOWN_PERSON | ALERT_THREAT_OBJECT
    camera_id: str
    message: str             # e.g. "Unknown Person Detected"
    detail: str              # e.g. "Guest 2 on cam_1"
    timestamp: float = field(default_factory=time.time)
    # How long the alert stays visible on-screen (seconds)
    duration_sec: float = 4.0

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.timestamp) > self.duration_sec

    @property
    def age_fraction(self) -> float:
        """0.0 = just created, 1.0 = expired."""
        return min(1.0, (time.time() - self.timestamp) / self.duration_sec)


class AlertManager:
    """
    Manages active alerts and renders them on top of frames.

    Features:
      • Full-screen red/orange tinted overlay (fades in/out)
      • Bold alert banner at top of frame
      • Animated pulsing border around the frame
      • Deduplication: same alert type per camera suppressed for cooldown_sec
      • Console logging for each new alert
    """

    def __init__(self, cooldown_sec: float = 5.0) -> None:
        self.cooldown_sec = cooldown_sec
        self._active: List[Alert] = []
        # last time each (alert_type, camera_id) was triggered
        self._last_triggered: dict[tuple[str, str], float] = {}

    # ──────────────────────────────────────────────────────────────────
    def trigger(
        self,
        alert_type: str,
        camera_id: str,
        message: str,
        detail: str = "",
        entity_id: str = None,
    ) -> bool:
        """Fire a new alert if cooldown has passed. Also logs to console."""
        key = (alert_type, camera_id, entity_id)
        now = time.time()
        if now - self._last_triggered.get(key, 0.0) < self.cooldown_sec:
            return False  # still in cooldown

        self._last_triggered[key] = now
        alert = Alert(
            alert_type=alert_type,
            camera_id=camera_id,
            message=message,
            detail=detail,
        )
        self._active.append(alert)

        # Console output
        icon = "🚨" if alert_type == ALERT_THREAT_OBJECT else "⚠️ "
        print(f"  [{icon} ALERT] {message} | {detail} | camera={camera_id}")
        return True

    # ──────────────────────────────────────────────────────────────────
    def tick(self) -> None:
        """Remove expired alerts. Call once per frame."""
        self._active = [a for a in self._active if not a.is_expired]

    # ──────────────────────────────────────────────────────────────────
    def has_active(self, camera_id: Optional[str] = None) -> bool:
        if camera_id is None:
            return bool(self._active)
        return any(a.camera_id == camera_id for a in self._active)

    # ──────────────────────────────────────────────────────────────────
    def render_onto(self, frame: np.ndarray, camera_id: str) -> np.ndarray:
        """
        Overlay all active alerts for this camera onto `frame`.
        Returns the modified frame.
        """
        cam_alerts = [a for a in self._active if a.camera_id == camera_id]
        if not cam_alerts:
            return frame

        out = frame.copy()
        h, w = out.shape[:2]
        t = time.time()

        # ── Pick dominant alert (highest priority, then most recent) ──
        dominant = max(
            cam_alerts,
            key=lambda a: (
                _ALERT_STYLE.get(a.alert_type, _ALERT_STYLE[ALERT_UNKNOWN_PERSON])["priority"],
                a.timestamp,
            ),
        )
        style = _ALERT_STYLE.get(dominant.alert_type, _ALERT_STYLE[ALERT_UNKNOWN_PERSON])

        # ── Colors ───────────────────────────────────────────────────
        overlay_color = style["overlay_color"]
        border_color  = style["border_color"]
        banner_color  = style["banner_color"]
        icon_text     = style["icon_text"]

        # ── Pulsing opacity (0.10 – 0.28) ────────────────────────────
        pulse = 0.5 + 0.5 * np.sin(t * 6.0)          # 0..1
        alpha = 0.10 + 0.18 * pulse                   # 0.10..0.28

        # Fade out in last 20% of alert lifetime
        age_f = dominant.age_fraction
        if age_f > 0.8:
            alpha *= 1.0 - (age_f - 0.8) / 0.2

        # ── Red/orange tint overlay ───────────────────────────────────
        overlay = np.full_like(out, overlay_color, dtype=np.uint8)
        cv2.addWeighted(overlay, alpha, out, 1 - alpha, 0, out)

        # ── Pulsing animated border ───────────────────────────────────
        border_thickness = int(4 + 4 * pulse)
        cv2.rectangle(out, (0, 0), (w - 1, h - 1), border_color, border_thickness)
        # Second inner border for depth
        inset = border_thickness + 2
        inner_alpha = 0.6
        inner_color = tuple(min(255, int(c * inner_alpha)) for c in border_color)
        cv2.rectangle(out, (inset, inset), (w - inset - 1, h - inset - 1),
                      inner_color, 1)

        # ── Top alert banner ─────────────────────────────────────────
        banner_h = 56
        banner = np.zeros((banner_h, w, 3), dtype=np.uint8)
        banner[:] = banner_color

        # Gradient effect on banner
        for col in range(w):
            factor = 0.6 + 0.4 * (col / max(1, w))
            banner[:, col] = [int(c * factor) for c in banner_color]

        # Icon/title text
        font = cv2.FONT_HERSHEY_SIMPLEX
        # Pulsing text scale
        text_scale = 0.85 + 0.10 * pulse
        (tw, th), _ = cv2.getTextSize(icon_text, font, text_scale, 2)
        tx = max(8, (w - tw) // 2)
        ty = banner_h // 2 + th // 2

        # Shadow
        cv2.putText(banner, icon_text, (tx + 2, ty + 2), font,
                    text_scale, (0, 0, 0), 3, cv2.LINE_AA)
        # Main text (white)
        cv2.putText(banner, icon_text, (tx, ty), font,
                    text_scale, (255, 255, 255), 2, cv2.LINE_AA)

        # Blend banner onto top of frame
        out[:banner_h] = cv2.addWeighted(
            out[:banner_h], 0.25, banner, 0.75, 0
        )

        # ── Detail line just below banner ────────────────────────────
        detail_y = banner_h + 22
        detail_text = f"{dominant.message}  |  {dominant.detail}"
        (dtw, _), _ = cv2.getTextSize(detail_text, font, 0.52, 1)
        dtx = max(8, (w - dtw) // 2)
        # Shadow
        cv2.putText(out, detail_text, (dtx + 1, detail_y + 1), font,
                    0.52, (0, 0, 0), 2, cv2.LINE_AA)
        cv2.putText(out, detail_text, (dtx, detail_y), font,
                    0.52, (255, 220, 180), 1, cv2.LINE_AA)

        # ── Small alert count badge (bottom-right) ───────────────────
        if len(cam_alerts) > 1:
            badge = f"+{len(cam_alerts) - 1} more alerts"
            cv2.putText(out, badge, (w - 160, h - 12), font,
                        0.45, (200, 200, 255), 1, cv2.LINE_AA)

        return out
