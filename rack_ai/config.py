import os
import math
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class Settings:
    source: str = field(default_factory=lambda: os.getenv('CAMERA_RTSP_AI', os.getenv('CAMERA_SOURCE', '')))
    final_pond_source: str = field(default_factory=lambda: os.getenv('FINAL_POND_RTSP', ''))
    final_pond_ppe_model: Path | None = field(default_factory=lambda: Path(os.environ['FINAL_POND_PPE_MODEL']) if os.getenv('FINAL_POND_PPE_MODEL') else None)
    final_pond_ppe_fps: float = field(default_factory=lambda: float(os.getenv('FINAL_POND_PPE_FPS', '5')))
    # โมเดลตรวจคนสำหรับงานเฝ้าพื้นที่ (เช่น yolo11s_openvino_model) — ตั้งแล้วจะใช้แทนโมเดล PPE นำร่อง
    final_pond_person_model: Path | None = field(default_factory=lambda: Path(os.environ['FINAL_POND_PERSON_MODEL']) if os.getenv('FINAL_POND_PERSON_MODEL') else None)
    # งานเฝ้าพื้นที่ไม่ต้องเร็ว: คนหายเกิน 5 นาทีถึงเตือน 1-2 ภาพต่อวินาทีก็พอ
    final_pond_area_fps: float = field(default_factory=lambda: float(os.getenv('FINAL_POND_AREA_FPS', '2')))
    final_pond_evidence_dir: Path = field(default_factory=lambda: Path(os.getenv('FINAL_POND_EVIDENCE_DIR', 'rack_ai/data/final_pond/evidence')))
    # ช่วงพักที่ไม่นับเวลาไม่มีคนและไม่เตือน เวลาไทย เช่น '12:00-13:00' หลายช่วงคั่นด้วย ,
    final_pond_quiet_hours: str = field(default_factory=lambda: os.getenv('FINAL_POND_QUIET_HOURS', ''))
    final_pond_absent_seconds: float = field(default_factory=lambda: float(os.getenv('FINAL_POND_ABSENT_SECONDS', '300')))
    # ตัวกรองกล่อง "คน" ของกล้องบ่อสุดท้าย — โมเดลนำร่องยังตรวจเครื่องจักรเป็นคน
    # ปรับค่าที่นี่ได้โดยไม่ต้องแก้โค้ด ดูผลได้จาก FINAL_POND_SHOW_REJECTED=1
    final_pond_worker_confidence: float = field(default_factory=lambda: float(os.getenv('FINAL_POND_WORKER_CONFIDENCE', '0.45')))
    final_pond_worker_min_height: float = field(default_factory=lambda: float(os.getenv('FINAL_POND_WORKER_MIN_HEIGHT', '0.04')))
    final_pond_worker_max_height: float = field(default_factory=lambda: float(os.getenv('FINAL_POND_WORKER_MAX_HEIGHT', '0.75')))
    final_pond_worker_max_aspect: float = field(default_factory=lambda: float(os.getenv('FINAL_POND_WORKER_MAX_ASPECT', '1.50')))
    final_pond_show_rejected: bool = field(default_factory=lambda: os.getenv('FINAL_POND_SHOW_REJECTED', '') not in ('', '0', 'false', 'False'))
    record_source: str = field(default_factory=lambda: os.getenv('CAMERA_RTSP_RECORD', ''))
    record_mode: str = field(default_factory=lambda: os.getenv('RECORD_MODE', 'auto'))
    record_fps: float = field(default_factory=lambda: float(os.getenv('RECORD_FPS','10')))
    record_root: Path = field(default_factory=lambda: Path(os.getenv('RECORD_ROOT','rack_ai/data/recordings')))
    lab_root: Path = field(default_factory=lambda: Path(os.getenv('LAB_ROOT','rack_ai/data/lab')))
    yoloe_model: Path = field(default_factory=lambda: Path(os.getenv('YOLOE_MODEL_PATH','models/pretrained/yoloe-26n-seg.pt')))
    model: Path = field(default_factory=lambda: Path(os.getenv('RACK_MODEL_PATH', 'ai/rack_detector/runs/rack_yolo11n/weights/best.pt')))
    camera_registry: Path = field(default_factory=lambda: Path(os.getenv('CAMERA_REGISTRY_PATH', 'rack_ai/cameras.json')))
    primary_camera_id: str = field(default_factory=lambda: os.getenv('PRIMARY_CAMERA_ID', 'camera-09'))
    inference_fps: float = field(default_factory=lambda: float(os.getenv('INFERENCE_FPS', '5')))
    confidence: float = field(default_factory=lambda: float(os.getenv('RACK_CONFIDENCE', '.55')))
    # NMS overlap threshold. Racks that travel touching produce boxes that overlap
    # by design in this camera angle; a low value deletes the rack behind before
    # tracking ever sees it. 0.70 matches ai/rack_detector/offline_track_count.py.
    iou: float = field(default_factory=lambda: float(os.getenv('RACK_IOU', '.70')))
    imgsz: int = field(default_factory=lambda: int(os.getenv('RACK_IMGSZ', '640')))
    # 'auto' = half precision when a GPU is present, 'off' = always float32.
    # Use 'off' when tuning on a GPU for a CPU deployment.
    half: str = field(default_factory=lambda: os.getenv('RACK_HALF', 'auto'))
    line: float = field(default_factory=lambda: float(os.getenv('COUNT_LINE_RATIO', '.60')))
    movement: float = field(default_factory=lambda: float(os.getenv('MIN_DOWNWARD_PIXELS', '10')))
    cooldown: float = field(default_factory=lambda: float(os.getenv('EVENT_COOLDOWN_SECONDS', '1.5')))
    # 'spatial' suppresses only overlapping repeat crossings inside the cooldown;
    # 'global' restores the previous blanket suppression.
    dedupe: str = field(default_factory=lambda: os.getenv('COUNT_DEDUPE', 'spatial'))
    duplicate_iou: float = field(default_factory=lambda: float(os.getenv('COUNT_DUPLICATE_IOU', '.55')))
    duplicate_containment: float = field(default_factory=lambda: float(os.getenv('COUNT_DUPLICATE_CONTAINMENT', '.80')))
    anchor: str = field(default_factory=lambda: os.getenv('COUNT_ANCHOR', 'center'))
    retry: float = field(default_factory=lambda: float(os.getenv('CAMERA_RETRY_SECONDS', '3')))
    stale: float = field(default_factory=lambda: float(os.getenv('CAMERA_STALE_SECONDS', '5')))
    worker_stale: float = field(default_factory=lambda: float(os.getenv('WORKER_STALE_SECONDS', '15')))
    token: str = field(default_factory=lambda: os.getenv('RACK_API_TOKEN', ''))
    pcc_url: str = field(default_factory=lambda: os.getenv('PCC_PUBLIC_URL', 'http://localhost:3000'))
    origins: list[str] = field(default_factory=lambda: os.getenv('PCC_ORIGINS', 'http://localhost:8011,http://127.0.0.1:8011').split(','))

    def __post_init__(self):
        if self.record_mode not in ('auto','opencv','copy') or not 1 <= self.record_fps <= 30:
            raise ValueError('Invalid recording settings')
        if not all(math.isfinite(x) for x in (self.inference_fps, self.line, self.movement,
                   self.cooldown, self.retry, self.stale, self.worker_stale, self.confidence, self.iou,
                   self.duplicate_iou, self.duplicate_containment, self.final_pond_ppe_fps,
                   self.final_pond_area_fps,
                   self.final_pond_absent_seconds, self.final_pond_worker_confidence,
                   self.final_pond_worker_min_height, self.final_pond_worker_max_height,
                   self.final_pond_worker_max_aspect)):
            raise ValueError('Settings must be finite')
        if not 0 < self.final_pond_ppe_fps <= 20:
            raise ValueError('FINAL_POND_PPE_FPS must be between 0 and 20')
        if not 0 < self.final_pond_area_fps <= 20:
            raise ValueError('FINAL_POND_AREA_FPS must be between 0 and 20')
        # ตั้งผิดรูปแบบต้องหยุดตั้งแต่เปิดระบบ ไม่ใช่เงียบแล้วเตือนช่วงพักทั้งที่ตั้งใจยกเว้น
        from .final_pond.presence import parse_quiet_periods
        parse_quiet_periods(self.final_pond_quiet_hours)
        if not 0 <= self.final_pond_worker_confidence <= 1:
            raise ValueError('FINAL_POND_WORKER_CONFIDENCE must be between 0 and 1')
        if not 0 <= self.final_pond_worker_min_height < self.final_pond_worker_max_height <= 1:
            raise ValueError('FINAL_POND_WORKER_MIN_HEIGHT must be below MAX_HEIGHT, both within 0..1')
        if self.final_pond_worker_max_aspect <= 0:
            raise ValueError('FINAL_POND_WORKER_MAX_ASPECT must be positive')
        if self.final_pond_absent_seconds <= 0:
            raise ValueError('FINAL_POND_ABSENT_SECONDS must be positive')
        if self.half not in ('auto', 'off'):
            raise ValueError('RACK_HALF must be auto or off')
        if self.dedupe not in ('spatial', 'global'):
            raise ValueError('COUNT_DEDUPE must be spatial or global')
        if not 0 <= self.duplicate_iou <= 1 or not 0 <= self.duplicate_containment <= 1:
            raise ValueError('Duplicate thresholds must be between 0 and 1')
        if self.movement <= 0 or self.cooldown < 0:
            raise ValueError('Movement must be positive and cooldown nonnegative')
        self.origins = [value.strip() for value in self.origins if value.strip()]
        if not 0 < self.inference_fps <= 60 or not 0 <= self.line <= 1:
            raise ValueError('Invalid inference FPS or count line')
        if self.anchor not in ('center', 'top', 'bottom') or self.retry <= 0 or self.stale <= 0 or self.worker_stale <= 0:
            raise ValueError('Invalid anchor or camera timing')
        if not 0 <= self.confidence <= 1 or not 0 <= self.iou <= 1 or self.imgsz < 32:
            raise ValueError('Invalid detector parameters')
        if not self.primary_camera_id or not all(character.isalnum() or character in '-_' for character in self.primary_camera_id):
            raise ValueError('PRIMARY_CAMERA_ID must contain only letters, numbers, hyphens, or underscores')
        pcc = urlparse(self.pcc_url)
        if pcc.scheme not in ('http', 'https') or not pcc.netloc:
            raise ValueError('PCC_PUBLIC_URL must be an absolute http(s) URL')
