from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import supervision as sv
from ultralytics import YOLO


class YoloDetector:
    """
    Ultralytics YOLO wrapper with class filtering and supervision output.
    """

    def __init__(
        self,
        weights: str = "yolov8n.pt",
        device: str = "auto",
        conf_thres: float = 0.35,
        iou_thres: float = 0.5,
        classes: Optional[List[int]] = None,
        imgsz: int = 640,
    ) -> None:
        self.model = YOLO(weights)
        self.device = device
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.classes = classes
        self.imgsz = imgsz

    def infer(self, frame: np.ndarray) -> sv.Detections:
        result = self.model.predict(
            source=frame,
            conf=self.conf_thres,
            iou=self.iou_thres,
            classes=self.classes,
            device=self.device,
            imgsz=self.imgsz,
            verbose=False,
        )[0]

        if result.boxes is None or len(result.boxes) == 0:
            return sv.Detections.empty()

        xyxy = result.boxes.xyxy.detach().cpu().numpy()
        confidence = result.boxes.conf.detach().cpu().numpy()
        class_id = result.boxes.cls.detach().cpu().numpy().astype(int)

        return sv.Detections(xyxy=xyxy, confidence=confidence, class_id=class_id)

    def class_name_map(self) -> Dict[int, str]:
        # Ultralytics keeps class names in model.names.
        names = self.model.names
        if isinstance(names, dict):
            return {int(k): str(v) for k, v in names.items()}
        return {i: str(name) for i, name in enumerate(names)}
