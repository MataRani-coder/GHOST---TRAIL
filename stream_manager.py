from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import cv2
import numpy as np


@dataclass
class FramePacket:
    camera_id: str
    frame: np.ndarray
    timestamp: float
    frame_index: int


class CameraStream:
    """
    Threaded camera reader that keeps only the latest frames in a small queue.
    This prevents pipeline backpressure from freezing capture.
    """

    def __init__(
        self,
        camera_id: str,
        source: Any,
        target_fps: float = 20.0,
        reconnect_interval_sec: float = 2.0,
        queue_size: int = 2,
        rotation: int = 0,
    ) -> None:
        self.camera_id = camera_id
        self.source = source
        self.target_fps = float(target_fps)
        self.reconnect_interval_sec = float(reconnect_interval_sec)
        self.frame_queue: "queue.Queue[FramePacket]" = queue.Queue(maxsize=max(1, queue_size))

        self._capture: Optional[cv2.VideoCapture] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._frame_index = 0
        self._last_ok_time = 0.0
        self.connected: bool = False
        self.enabled: bool = True
        self.rotation = int(rotation)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name=f"stream-{self.camera_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._release_capture()

    def read_latest(self) -> Optional[FramePacket]:
        latest: Optional[FramePacket] = None
        while True:
            try:
                latest = self.frame_queue.get_nowait()
            except queue.Empty:
                break
        return latest

    def _run(self) -> None:
        while not self._stop_event.is_set():
            if self._capture is None or not self._capture.isOpened():
                self._open_capture()
                if self._capture is None or not self._capture.isOpened():
                    time.sleep(self.reconnect_interval_sec)
                    continue

            # ── Drain buffered frames — grab without decoding ────────────
            # This throws away stale frames so we always decode the LATEST
            # one, eliminating the 10-20 second backlog.
            drained = 0
            while drained < 30:  # safety cap
                grabbed = self._capture.grab()
                if not grabbed:
                    break
                drained += 1
                # Stop draining when no more frames are immediately ready
                # (grab would block → we have caught up to live)
                try:
                    if not self._capture.grab():
                        break
                    drained += 1
                except Exception:
                    break

            # Decode only the most recent grabbed frame
            ok, frame = self._capture.retrieve()
            if not ok or frame is None:
                # Try a normal read as fallback
                ok, frame = self._capture.read()
                if not ok or frame is None:
                    self.connected = False
                    self._release_capture()
                    time.sleep(self.reconnect_interval_sec)
                    continue

            # Apply rotation if configured
            if self.rotation == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self.rotation == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif self.rotation == 270 or self.rotation == -90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            self._frame_index += 1
            packet = FramePacket(
                camera_id=self.camera_id,
                frame=frame,
                timestamp=time.time(),
                frame_index=self._frame_index,
            )
            self._last_ok_time = packet.timestamp
            self.connected = True
            self._put_latest(packet)
            # No sleep here — we want to drain as fast as possible
            # to stay as close to real-time as possible

    def _check_reachability(self) -> bool:
        """Check if a network source is reachable to prevent OpenCV hang/crash."""
        if isinstance(self.source, str) and (self.source.startswith("http://") or self.source.startswith("https://") or self.source.startswith("rtsp://")):
            try:
                import urllib.parse, socket
                parsed = urllib.parse.urlparse(self.source)
                host = parsed.hostname
                port = parsed.port or (443 if parsed.scheme == "https" else (554 if parsed.scheme == "rtsp" else 80))
                if host:
                    with socket.create_connection((host, port), timeout=2.0):
                        return True
            except Exception as e:
                print(f"[WARN] Camera {self.camera_id} source {self.source} is unreachable: {e}")
                return False
        return True

    def _open_capture(self) -> None:
        self._release_capture()

        # Prevent OpenCV from crashing on unreachable network streams
        if not self._check_reachability():
            return

        # Force DirectShow backend for local Windows webcams
        if isinstance(self.source, int) or (isinstance(self.source, str) and self.source.isdigit()):
            self._capture = cv2.VideoCapture(int(self.source), cv2.CAP_DSHOW)
        else:
            # Set a 5-second timeout and low latency flags for FFMPEG
            import os
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "timeout;5000|rw_timeout;5000|flags;low_delay|fflags;nobuffer|analyzeduration;0|probesize;32"
            self._capture = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)

        if self._capture is not None and not self._capture.isOpened():
            self._capture = None
            return

        # ── Minimise internal buffer to reduce latency ───────────────
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        # For network streams: disable extra buffering
        if not (isinstance(self.source, int) or (isinstance(self.source, str) and self.source.isdigit())):
            self._capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

    def _release_capture(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def _put_latest(self, packet: FramePacket) -> None:
        if self.frame_queue.full():
            try:
                _ = self.frame_queue.get_nowait()
            except queue.Empty:
                pass
        self.frame_queue.put_nowait(packet)


class StreamManager:
    def __init__(self, camera_configs: List[Dict[str, Any]], stream_cfg: Dict[str, Any]) -> None:
        self.streams: Dict[str, CameraStream] = {}
        for camera_cfg in camera_configs:
            camera_id = str(camera_cfg["camera_id"])
            source = camera_cfg["source"]
            self.streams[camera_id] = CameraStream(
                camera_id=camera_id,
                source=source,
                target_fps=stream_cfg.get("target_fps", 20),
                reconnect_interval_sec=stream_cfg.get("reconnect_interval_sec", 2.0),
                queue_size=stream_cfg.get("queue_size", 2),
                rotation=camera_cfg.get("rotation", 0),
            )

    def start_all(self) -> None:
        for stream in self.streams.values():
            stream.start()

    def stop_all(self) -> None:
        for stream in self.streams.values():
            stream.stop()

    def get_latest_frames(self) -> Dict[str, FramePacket]:
        latest: Dict[str, FramePacket] = {}
        for camera_id, stream in self.streams.items():
            packet = stream.read_latest()
            if packet is not None:
                latest[camera_id] = packet
        return latest