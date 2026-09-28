from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np
import supervision as sv
import torch
import torch.nn.functional as F
import torchreid


class SingleCameraTracker:
    """
    Per-camera ByteTrack wrapper.
    """

    def __init__(
        self,
        track_activation_threshold: float = 0.25,
        lost_track_buffer: int = 30,
        minimum_matching_threshold: float = 0.80,
        frame_rate: int = 30,
    ) -> None:
        self.tracker = sv.ByteTrack(
            track_activation_threshold=track_activation_threshold,
            lost_track_buffer=lost_track_buffer,
            minimum_matching_threshold=minimum_matching_threshold,
            frame_rate=frame_rate,
        )

    def update(self, detections: sv.Detections) -> sv.Detections:
        if len(detections) == 0:
            return detections
        return self.tracker.update_with_detections(detections)


class DeepReIDExtractor:
    """
    Deep Re-ID feature extractor using torchreid OSNet backbone.
    """

    def __init__(
        self,
        model_name: str = "osnet_x1_0",
        model_weights: Optional[str] = None,
        device: str = "cpu",
        input_size: tuple[int, int] = (256, 128),
    ) -> None:
        self.device = torch.device(device if device != "auto" else ("cuda:0" if torch.cuda.is_available() else "cpu"))
        self.input_h, self.input_w = input_size
        self.model = torchreid.models.build_model(
            name=model_name,
            num_classes=1000,
            pretrained=not bool(model_weights),
        )
        if model_weights:
            torchreid.utils.load_pretrained_weights(self.model, model_weights)
        self.model.eval()
        self.model.to(self.device)
        self._mean = torch.tensor([0.485, 0.456, 0.406], device=self.device).view(3, 1, 1)
        self._std = torch.tensor([0.229, 0.224, 0.225], device=self.device).view(3, 1, 1)

    def _extract_crop(self, frame: np.ndarray, xyxy: np.ndarray) -> Optional[np.ndarray]:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = xyxy.astype(int)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w - 1, x2), min(h - 1, y2)
        if x2 <= x1 or y2 <= y1:
            return None

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        return crop

    def _preprocess_crop(self, crop: np.ndarray) -> torch.Tensor:
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (self.input_w, self.input_h), interpolation=cv2.INTER_LINEAR)
        tensor = torch.from_numpy(resized).permute(2, 0, 1).float() / 255.0
        tensor = tensor.to(self.device)
        tensor = (tensor - self._mean) / self._std
        return tensor

    def encode(self, frame: np.ndarray, xyxy: np.ndarray) -> Optional[np.ndarray]:
        crop = self._extract_crop(frame, xyxy)
        if crop is None:
            return None
        tensor = self._preprocess_crop(crop).unsqueeze(0)
        with torch.no_grad():
            feat = self.model(tensor)
            feat = F.normalize(feat, p=2, dim=1)
        return feat.squeeze(0).detach().cpu().numpy().astype(np.float32)

    def encode_batch(self, frames_and_boxes: List[tuple[np.ndarray, np.ndarray]]) -> List[Optional[np.ndarray]]:
        """
        Batch embedding extraction. Returns one feature per input item.
        Invalid crops return None while preserving index alignment.
        """
        if not frames_and_boxes:
            return []

        valid_indices: List[int] = []
        tensors: List[torch.Tensor] = []
        outputs: List[Optional[np.ndarray]] = [None] * len(frames_and_boxes)

        for idx, (frame, xyxy) in enumerate(frames_and_boxes):
            crop = self._extract_crop(frame, xyxy)
            if crop is None:
                continue
            tensors.append(self._preprocess_crop(crop))
            valid_indices.append(idx)

        if not tensors:
            return outputs

        batch = torch.stack(tensors, dim=0)
        with torch.no_grad():
            feats = self.model(batch)
            feats = F.normalize(feats, p=2, dim=1)
        feat_np = feats.detach().cpu().numpy().astype(np.float32)

        for out_idx, feat in zip(valid_indices, feat_np):
            outputs[out_idx] = feat
        return outputs


ReIDCandidate = Tuple[str, int, np.ndarray, np.ndarray, float]


class ReIDMicroBatcher:
    """
    Time-gated micro-batcher for Re-ID workloads.
    Flush policy:
    - immediate flush when max batch size is reached
    - timed flush when oldest queued item waited >= max_wait_ms
    """

    def __init__(self, max_wait_ms: float = 15.0, max_batch_size: int = 64) -> None:
        self.max_wait_s = max_wait_ms / 1000.0
        self.max_batch_size = max(1, int(max_batch_size))
        self._queue: Deque[ReIDCandidate] = deque()
        self._oldest_enqueue_ts: Optional[float] = None

    def add(self, item: ReIDCandidate) -> Optional[List[ReIDCandidate]]:
        if not self._queue:
            self._oldest_enqueue_ts = time.perf_counter()
        self._queue.append(item)
        if len(self._queue) >= self.max_batch_size:
            return self.flush()
        return None

    def flush_due(self) -> Optional[List[ReIDCandidate]]:
        if not self._queue:
            return None
        if self._oldest_enqueue_ts is None:
            self._oldest_enqueue_ts = time.perf_counter()
            return None
        if (time.perf_counter() - self._oldest_enqueue_ts) >= self.max_wait_s:
            return self.flush()
        return None

    def flush(self) -> List[ReIDCandidate]:
        batch = list(self._queue)
        self._queue.clear()
        self._oldest_enqueue_ts = None
        return batch


def _draw_label_bg(
    frame: np.ndarray,
    text: str,
    x1: int,
    y1: int,
    color: tuple,
    font_scale: float = 0.6,
    thickness: int = 2,
) -> None:
    """Draw a filled background rectangle behind the label for readability."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    label_y = max(th + baseline + 6, y1 - 4)
    # Background rectangle
    cv2.rectangle(
        frame,
        (x1, label_y - th - baseline - 4),
        (x1 + tw + 6, label_y + 2),
        color,
        cv2.FILLED,
    )
    # White text on colored background
    cv2.putText(
        frame, text, (x1 + 3, label_y - baseline - 2),
        font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA,
    )


def annotate_tracked_objects(
    frame: np.ndarray,
    detections: sv.Detections,
    class_name_map: Dict[int, str],
    global_ids: Dict[int, int],
    global_names: Optional[Dict[int, str]],
    camera_id: str,
    threat_class_ids: Optional[set[int]] = None,
    flash_on: bool = False,
    show_fps: bool = False,
    fps: float = 0.0,
    face_boxes: Optional[Dict[int, np.ndarray]] = None,
    face_review_statuses: Optional[Dict[int, str]] = None,
) -> np.ndarray:
    out = frame.copy()
    if len(detections) == 0:
        return out

    xyxy = detections.xyxy
    class_ids = detections.class_id if detections.class_id is not None else np.full(len(detections), -1)
    confs = detections.confidence if detections.confidence is not None else np.zeros(len(detections))
    track_ids = detections.tracker_id if detections.tracker_id is not None else np.full(len(detections), -1)

    for i in range(len(detections)):
        x1, y1, x2, y2 = xyxy[i].astype(int)
        cls_id = int(class_ids[i])
        conf = float(confs[i])
        tid = int(track_ids[i])
        gid = global_ids.get(tid, -1)
        gname = (global_names or {}).get(tid, "Unknown")

        label_name = class_name_map.get(cls_id, f"class_{cls_id}")
        is_threat = cls_id in (threat_class_ids or set())
        is_guest = gname.startswith("Guest")

        review_status = str((face_review_statuses or {}).get(gid, "pending"))

        if is_threat:
            alert_color = (0, 0, 255) if flash_on else (0, 255, 255)
            cv2.rectangle(out, (x1, y1), (x2, y2), alert_color, 4)
            cv2.rectangle(out, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), (255, 255, 255), 1)
            label = f"ALERT: {label_name} {conf:.2f}"
            cv2.putText(out, label, (x1, max(24, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, alert_color, 2)
        elif review_status == "denied":
            # Human-denied face → red box so the operator can see the decision live.
            box_color = (0, 0, 255)
            cv2.rectangle(out, (x1, y1), (x2, y2), box_color, 3)
            label = f"  {gname}  [HIGH RISK]"
            _draw_label_bg(out, label, x1, y1, box_color)
        elif review_status == "confirmed":
            # Human-confirmed face → green box.
            box_color = (30, 210, 60)
            cv2.rectangle(out, (x1, y1), (x2, y2), box_color, 3)
            label = f"  {gname}  [FACE VERIFIED]"
            _draw_label_bg(out, label, x1, y1, box_color)
        elif is_guest:
            # Unknown person → orange-blue box
            box_color = (30, 140, 220)
            cv2.rectangle(out, (x1, y1), (x2, y2), box_color, 2)
            label = f"{gname}  [{conf:.2f}]"
            _draw_label_bg(out, label, x1, y1, box_color)
        else:
            # Registered person awaiting manual face review.
            box_color = (30, 180, 220)
            cv2.rectangle(out, (x1, y1), (x2, y2), box_color, 2)
            label = f"  {gname}  [{conf:.2f}]"
            _draw_label_bg(out, label, x1, y1, box_color)

        # Face-level bounding box: the manual review decision is applied to
        # the face itself, not just the full-body person detection.
        face_box = (face_boxes or {}).get(tid)
        if face_box is not None and len(face_box) == 4:
            fx1, fy1, fx2, fy2 = np.asarray(face_box).astype(int)
            if review_status == "denied":
                face_color = (0, 0, 255)
                face_text = "FACE DENIED"
            elif review_status == "confirmed":
                face_color = (30, 210, 60)
                face_text = "FACE VERIFIED"
            else:
                face_color = (0, 190, 255)
                face_text = "FACE REVIEW"
            cv2.rectangle(out, (fx1, fy1), (fx2, fy2), face_color, 3)
            _draw_label_bg(out, face_text, fx1, fy1, face_color, font_scale=0.48, thickness=1)

    if show_fps:
        cv2.putText(out, f"FPS: {fps:.1f}", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (50, 200, 255), 2)
    return out


def make_grid(frames: Dict[str, np.ndarray], max_view_width: int = 640) -> np.ndarray:
    if not frames:
        return np.zeros((480, 640, 3), dtype=np.uint8)

    camera_ids = sorted(frames.keys())
    prepared = []
    for camera_id in camera_ids:
        frame = frames[camera_id]
        h, w = frame.shape[:2]
        scale = min(1.0, max_view_width / max(1, w))
        resized = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LINEAR)
        prepared.append(resized)

    n = len(prepared)
    cols = int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / cols))

    tile_h = max(img.shape[0] for img in prepared)
    tile_w = max(img.shape[1] for img in prepared)
    canvas = np.zeros((rows * tile_h, cols * tile_w, 3), dtype=np.uint8)

    for idx, img in enumerate(prepared):
        r = idx // cols
        c = idx % cols
        y0, x0 = r * tile_h, c * tile_w
        h, w = img.shape[:2]
        canvas[y0 : y0 + h, x0 : x0 + w] = img
    return canvas


def create_offline_tile(
    camera_id: str,
    width: int = 640,
    height: int = 360,
    pulse_on: bool = False,
) -> np.ndarray:
    tile = np.zeros((height, width, 3), dtype=np.uint8)
    tile[:, :] = (20, 20, 20)
    border_color = (0, 0, 200) if pulse_on else (0, 180, 255)
    cv2.rectangle(tile, (8, 8), (width - 8, height - 8), border_color, 2)
    cv2.putText(
        tile,
        f"{camera_id}: OFFLINE - RETRYING...",
        (20, height // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (220, 220, 220),
        2,
    )
    return tile


def make_grid_with_offline(
    camera_ids: List[str],
    frames_by_camera: Dict[str, np.ndarray],
    max_view_width: int = 640,
    offline_size: tuple[int, int] = (640, 360),
    pulse_on: bool = False,
) -> np.ndarray:
    if not camera_ids:
        return np.zeros((480, 640, 3), dtype=np.uint8)

    prepared = []
    for camera_id in camera_ids:
        if camera_id in frames_by_camera:
            frame = frames_by_camera[camera_id]
        else:
            frame = create_offline_tile(
                camera_id=camera_id,
                width=offline_size[0],
                height=offline_size[1],
                pulse_on=pulse_on,
            )
        h, w = frame.shape[:2]
        scale = min(1.0, max_view_width / max(1, w))
        prepared.append(cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LINEAR))

    n = len(prepared)
    cols = int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / cols))
    tile_h = max(img.shape[0] for img in prepared)
    tile_w = max(img.shape[1] for img in prepared)
    canvas = np.zeros((rows * tile_h, cols * tile_w, 3), dtype=np.uint8)

    for idx, img in enumerate(prepared):
        r = idx // cols
        c = idx % cols
        y0, x0 = r * tile_h, c * tile_w
        h, w = img.shape[:2]
        canvas[y0 : y0 + h, x0 : x0 + w] = img
    return canvas
