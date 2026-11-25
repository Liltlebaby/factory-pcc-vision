"""YOLO model and ByteTrack are used exclusively by the inference worker."""
from .config import Settings


class RackDetector:
    def __init__(self, settings: Settings):
        import torch
        from ultralytics import YOLO
        if not settings.model.is_file():
            raise FileNotFoundError('model_missing')
        self.model = YOLO(str(settings.model))
        self.cfg = settings
        self.device = 0 if torch.cuda.is_available() else 'cpu'
        # Half precision is GPU-only. 'off' keeps a GPU run numerically comparable
        # to the CPU service, which matters when thresholds tuned on a rented GPU
        # are meant to be deployed on the on-prem CPU machine.
        self.half = self.device != 'cpu' and settings.half != 'off'
        from ultralytics.cfg import DEFAULT_CFG_DICT
        self.precision = ({'quantize': 16 if self.half else 32} if 'quantize' in DEFAULT_CFG_DICT
                          else {'half': self.half})

    def reset(self):
        for tracker in getattr(getattr(self.model, 'predictor', None), 'trackers', []):
            tracker.reset()

    def infer(self, frame) -> list[dict]:
        # Reuse existing rack geometry/overlap filter without launching legacy app.
        from ai.rack_detector.offline_track_count import filter_racks
        result = self.model.track(frame, persist=True, tracker='bytetrack.yaml', classes=[0],
                                  conf=self.cfg.confidence, iou=self.cfg.iou, imgsz=self.cfg.imgsz,
                                  device=self.device, verbose=False, **self.precision)[0]
        if result.boxes.id is None:
            return []
        h, w = frame.shape[:2]
        items = filter_racks(result.boxes.xyxy.cpu().numpy(), result.boxes.id.int().cpu().tolist(),
                             result.boxes.conf.cpu().tolist(), w, h)
        return [{'track_id': item['track_id'], 'class_id': 0, 'class_name': 'rack',
                 'confidence': float(item['score']), 'bbox': [float(v) for v in item['box']]} for item in items]
