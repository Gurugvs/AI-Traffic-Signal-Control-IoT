"""Separate automatic emergency-vehicle detector.

This does not modify normal vehicle detection. It uses specific emergency
classes only and deliberately avoids the generic 'emergency vehicle' prompt.
"""
from dataclasses import dataclass
from ultralytics import YOLO
import cv2

EMERGENCY_CLASSES = [
    "ambulance", "fire truck", "fire engine", "police car", "police vehicle"
]

@dataclass
class EmergencyDetection:
    label: str
    confidence: float
    box: tuple

class EmergencyDetector:
    def __init__(self, model_name="yolov8s-worldv2.pt", confidence=0.60):
        self.confidence = confidence
        self.model = YOLO(model_name)
        self.model.set_classes(EMERGENCY_CLASSES)

    def detect(self, image):
        results = self.model.predict(source=image, conf=self.confidence, iou=0.45, verbose=False)
        out = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                if conf < self.confidence or not (0 <= cls_id < len(EMERGENCY_CLASSES)):
                    continue
                out.append(EmergencyDetection(
                    EMERGENCY_CLASSES[cls_id], conf,
                    tuple(map(int, box.xyxy[0].tolist()))
                ))
        return out

    def annotate(self, image, detections):
        out = image.copy()
        for d in detections:
            x1,y1,x2,y2 = d.box
            cv2.rectangle(out, (x1,y1), (x2,y2), (0,0,255), 3)
            cv2.putText(out, f'EMERGENCY: {d.label} {d.confidence:.2f}',
                        (x1,max(25,y1-8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,255), 2)
        return out

    # Backward-compatible method for older UI code.
    def draw(self, image, detections):
        return self.annotate(image, detections)
