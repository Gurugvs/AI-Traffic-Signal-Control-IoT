"""Existing normal vehicle detector. Keep this module separate from emergency detection."""
from ultralytics import YOLO

# COCO vehicle classes used by the normal detector.
VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck"}

class VehicleDetector:
    def __init__(self, model_path="yolo11n.pt", confidence=0.25):
        self.model = YOLO(model_path)
        self.confidence = confidence

    def detect(self, image):
        results = self.model.predict(source=image, conf=self.confidence, verbose=False)
        detections = []
        for result in results:
            if result.boxes is None:
                continue
            names = result.names
            for box in result.boxes:
                cls_id = int(box.cls[0])
                label = names.get(cls_id, str(cls_id)) if isinstance(names, dict) else names[cls_id]
                if label in VEHICLE_CLASSES:
                    detections.append({
                        "label": label,
                        "confidence": float(box.conf[0]),
                        "box": tuple(map(int, box.xyxy[0].tolist()))
                    })
        return detections, results

    def annotate(self, image, detections):
        import cv2
        out = image.copy()
        for d in detections:
            x1, y1, x2, y2 = d["box"]
            cv2.rectangle(out, (x1,y1), (x2,y2), (0,255,0), 2)
            cv2.putText(out, f'{d["label"]} {d["confidence"]:.2f}', (x1,max(20,y1-7)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,255,0), 2)
        return out
