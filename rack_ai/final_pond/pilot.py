"""Background preview and work-area presence monitoring for the final pond.

Two modes, chosen by which model is configured:

    area  FINAL_POND_PERSON_MODEL — a general person detector (yolo11s, ideally
          its OpenVINO export). Only presence in the work zone is judged.
    ppe   FINAL_POND_PPE_MODEL only — the small pilot PPE model, kept for
          comparison. It mistakes cement sacks for workers, so prefer area mode.

Neither mode issues helmet or magnet-compliance events. Only a confirmed
5-minute absence from the pond work zone is alertable, with an evidence image.
"""

import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from .presence import PresenceAlert, PresenceMonitor, PresenceReturned
from .vision import BARE_HEAD_NAMES, HELMET_NAMES, PERSON_NAMES, Box, Detection, classify_helmet


log = logging.getLogger('vision.final_pond.ppe')

# Normalised work area in camera 11. Use the feet of a worker box so a person
# merely visible in the right-hand corridor does not clear the absence timer.
# Keep this separate from the magnet-lever ROI (which is no longer drawn).
# v2 (2026-10-03): drawn by the factory on the camera 11 substream view — the pond,
# the walkway along it and the area up to the pillar line. The sack pile right of
# the pillar line is deliberately outside, as is the corridor behind the pond.
POND_WORK_ZONE = ((0.00, 0.58), (0.51, 0.07), (0.84, 0.13),
                  (0.81, 1.00), (0.00, 1.00))
ZONE_VERSION = 'final-pond-cam11-v2'
PRESENCE_CONFIDENCE = 0.35
PRESENCE_TASK_ID = 'work-area-presence'
CAMERA_ID = 'final-pond-cam-01'
# A worker missing for an hour repeats an alert every 10 minutes; keeping a month
# of evidence bounds the folder without losing anything a review would ask for.
EVIDENCE_KEEP_SECONDS = 30 * 24 * 3600
EVIDENCE_NAME = re.compile(r'^[A-Za-z0-9_.-]+\.jpg$')


@dataclass(frozen=True)
class WorkerFilter:
    """คัดกล่อง "คน" ที่โมเดลนำร่องตรวจผิดออก ก่อนนับและก่อนวาดลงภาพ

    โมเดลนำร่องยังไม่ได้เทรนด้วยภาพจากกล้อง 11 จึงตีความรถโฟล์คลิฟต์ เสา ถังปูน
    เป็น "คน" ด้วยคะแนนต่ำ (เจอจริง 0.29 และ 0.32 ในภาพเดียวกับที่คนจริงได้ 0.72)
    ตัวกรองนี้ตัดกล่องที่เป็นไปไม่ได้ทางกายภาพออก โดยดูสามอย่าง

        คะแนนความมั่นใจ  กล่องหลอกของโมเดลนี้เกาะอยู่แถบคะแนนต่ำ
        ความสูงของกล่อง  เทียบกับความสูงภาพ เล็กเกิน = จุดรบกวน ใหญ่เกิน = เครื่องจักร
        สัดส่วนกว้าง/สูง  คนยืนต้องสูงกว่ากว้าง กล่องที่กว้างกว่าสูงมากคือวัตถุ

    ตัวกรองนี้เป็นการบรรเทาอาการ ไม่ใช่การแก้ที่ต้นเหตุ ทางแก้จริงคือเทรนโมเดล
    ด้วยภาพจากกล้องตัวนี้เอง ค่าทั้งหมดจึงปรับได้จาก environment โดยไม่ต้องแก้โค้ด
    """

    confidence: float = 0.45
    min_height_ratio: float = 0.04
    max_height_ratio: float = 0.75
    max_aspect_ratio: float = 1.50     # กว้าง ÷ สูง

    def reject_reason(self, item, width: int, height: int) -> str | None:
        """คืนเหตุผลที่ตัดกล่องนี้ทิ้ง หรือ None ถ้ากล่องนี้ผ่าน"""
        if item.confidence < self.confidence:
            return 'confidence'
        box_height = item.box.y2 - item.box.y1
        box_width = item.box.x2 - item.box.x1
        if height <= 0 or box_height <= 0:
            return 'shape'
        ratio = box_height / height
        if ratio < self.min_height_ratio:
            return 'too_small'
        if ratio > self.max_height_ratio:
            return 'too_large'
        if box_width / box_height > self.max_aspect_ratio:
            return 'too_wide'
        return None


DEFAULT_WORKER_FILTER = WorkerFilter()


def split_workers(detections, shape, rules: WorkerFilter = DEFAULT_WORKER_FILTER):
    """แยกกล่องคนออกเป็น (ที่เชื่อได้, ที่ถูกตัดทิ้งพร้อมเหตุผล)

    คืนรายการที่ถูกตัดด้วย เพื่อให้หน้าจอบอกได้ว่ากรองอะไรออกไปกี่กล่อง
    ถ้าคนจริงถูกตัดทิ้ง จะได้เห็นและปรับค่าได้ ไม่ใช่หายไปเงียบ ๆ
    """
    height, width = shape[:2]
    kept, rejected = [], []
    for item in detections:
        if item.label.strip().lower() not in PERSON_NAMES:
            continue
        reason = rules.reject_reason(item, width, height)
        (rejected.append((item, reason)) if reason else kept.append(item))
    return kept, rejected


def _inside_polygon(x, y, vertices=POND_WORK_ZONE):
    inside = False
    previous = vertices[-1]
    for current in vertices:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
        previous = current
    return inside


def _feet_in_zone(item, width: int, height: int) -> bool:
    """Judge by the bottom-centre of the box (where the feet are), not the box centre,
    so someone standing in the corridor behind the pond is not counted as inside."""
    return _inside_polygon((item.box.x1 + item.box.x2) / (2 * width), item.box.y2 / height)


def workers_in_pond(detections, shape, rules: WorkerFilter = DEFAULT_WORKER_FILTER):
    """นับคนที่ยืนอยู่ในพื้นที่บ่อจริง — รับเฉพาะกล่องที่ผ่านตัวกรองแล้ว

    รับ detections ดิบได้เหมือนเดิม (เรียกจากที่อื่นได้) เพราะกรองให้ในตัว
    """
    height, width = shape[:2]
    kept, _ = split_workers(detections, shape, rules)
    return sum(
        item.confidence >= PRESENCE_CONFIDENCE and _feet_in_zone(item, width, height)
        for item in kept
    )


def _draw_zone(image):
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    points = np.array([(int(x * width), int(y * height)) for x, y in POND_WORK_ZONE], dtype=np.int32)
    overlay = image.copy()
    cv2.fillPoly(overlay, [points], (90, 160, 40))
    cv2.addWeighted(overlay, 0.12, image, 0.88, 0, image)
    cv2.polylines(image, [points], True, (90, 200, 60), 2, cv2.LINE_AA)


def _draw_label(image, x1, y1, label, color):
    import cv2

    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.46
    width = cv2.getTextSize(label, font, scale, 1)[0][0]
    lx = max(0, min(x1, image.shape[1] - width - 8))
    ly = max(56, y1)
    cv2.rectangle(image, (lx, ly - 21), (lx + width + 8, ly + 3), color, -1)
    cv2.putText(image, label, (lx + 4, ly - 4), font, scale, (255, 255, 255), 1, cv2.LINE_AA)


def draw_area_detections(frame, detections, rules: WorkerFilter = DEFAULT_WORKER_FILTER,
                         show_rejected: bool = False):
    """Annotate a frame for the presence task: the work zone, who is inside it, who is not."""
    import cv2

    image = frame.copy()
    height, width = image.shape[:2]
    _draw_zone(image)
    people, rejected = split_workers(detections, image.shape, rules)
    counts = {'people_count': len(people), 'workers_in_zone': 0, 'filtered_out': len(rejected)}
    if show_rejected:
        for item, reason in rejected:
            x1, y1, x2, y2 = (int(v) for v in (item.box.x1, item.box.y1, item.box.x2, item.box.y2))
            cv2.rectangle(image, (x1, y1), (x2, y2), (130, 130, 130), 1)
            cv2.putText(image, f'{reason} {item.confidence:.2f}', (x1 + 2, max(48, y1) - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (130, 130, 130), 1, cv2.LINE_AA)
    for item in people:
        inside = item.confidence >= PRESENCE_CONFIDENCE and _feet_in_zone(item, width, height)
        counts['workers_in_zone'] += inside
        color, label = ((46, 170, 60), f'IN ZONE {item.confidence:.2f}') if inside \
            else ((120, 120, 120), f'OUTSIDE {item.confidence:.2f}')
        x1, y1, x2, y2 = (int(v) for v in (item.box.x1, item.box.y1, item.box.x2, item.box.y2))
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        _draw_label(image, x1, y1, label, color)
    cv2.rectangle(image, (0, 0), (image.shape[1], 37), (16, 26, 39), -1)
    text = (f'CAM 11 / WORK AREA AI  |  IN ZONE {counts["workers_in_zone"]}  '
            f'OUTSIDE {counts["people_count"] - counts["workers_in_zone"]}  '
            f'FILTERED {counts["filtered_out"]}')
    cv2.putText(image, text, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (255, 255, 255), 1, cv2.LINE_AA)
    return image, counts


def detections_from_result(result):
    found = []
    if result.boxes is None:
        return found
    for row in result.boxes:
        x1, y1, x2, y2 = (float(value) for value in row.xyxy[0])
        found.append(Detection(
            str(result.names[int(row.cls[0])]), Box(x1, y1, x2, y2), float(row.conf[0]),
        ))
    return found


def draw_detections(frame, detections, rules: WorkerFilter = DEFAULT_WORKER_FILTER,
                    show_rejected: bool = False):
    import cv2

    image = frame.copy()
    counts = {'people_count': 0, 'helmet_pass': 0, 'no_helmet': 0, 'undecided': 0, 'filtered_out': 0}
    heads = [item for item in detections if item.label.strip().lower() in HELMET_NAMES | BARE_HEAD_NAMES]
    workers, rejected = split_workers(detections, image.shape, rules)
    counts['filtered_out'] = len(rejected)
    font = cv2.FONT_HERSHEY_SIMPLEX
    if show_rejected:
        # โหมดปรับค่า: วาดกล่องที่ถูกตัดเป็นเส้นบางสีเทา พร้อมเหตุผล
        for item, reason in rejected:
            x1, y1, x2, y2 = (int(v) for v in (item.box.x1, item.box.y1, item.box.x2, item.box.y2))
            cv2.rectangle(image, (x1, y1), (x2, y2), (130, 130, 130), 1)
            cv2.putText(image, f'{reason} {item.confidence:.2f}', (x1 + 2, max(48, y1) - 4),
                        font, 0.38, (130, 130, 130), 1, cv2.LINE_AA)
    for item in workers:
        status, head_conf = classify_helmet(item.box, heads)
        counts['people_count'] += 1
        if status == 'PASS':
            counts['helmet_pass'] += 1
            color, label = (46, 170, 60), f'WORKER / HELMET {head_conf:.2f}'
        elif status == 'VIOLATION':
            counts['no_helmet'] += 1
            color, label = (50, 55, 230), f'WORKER / BARE HEAD {head_conf:.2f}'
        else:
            counts['undecided'] += 1
            color, label = (0, 180, 255), f'WORKER / UNKNOWN {item.confidence:.2f}'
        x1, y1, x2, y2 = (int(v) for v in (item.box.x1, item.box.y1, item.box.x2, item.box.y2))
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        scale = 0.46
        width = cv2.getTextSize(label, font, scale, 1)[0][0]
        lx = max(0, min(x1, image.shape[1] - width - 8))
        ly = max(56, y1)
        cv2.rectangle(image, (lx, ly - 21), (lx + width + 8, ly + 3), color, -1)
        cv2.putText(image, label, (lx + 4, ly - 4), font, scale, (255, 255, 255), 1, cv2.LINE_AA)

    for item in heads:
        color = (46, 170, 60) if item.label.strip().lower() in HELMET_NAMES else (50, 55, 230)
        x1, y1, x2, y2 = (int(v) for v in (item.box.x1, item.box.y1, item.box.x2, item.box.y2))
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 1)

    cv2.rectangle(image, (0, 0), (image.shape[1], 37), (16, 26, 39), -1)
    text = (f'CAM 11 / PEE AI PILOT  |  WORKERS {counts["people_count"]}  '
            f'HELMET {counts["helmet_pass"]}  BARE {counts["no_helmet"]}  '
            f'UNKNOWN {counts["undecided"]}  FILTERED {counts["filtered_out"]}')
    cv2.putText(image, text, (8, 24), font, 0.40, (255, 255, 255), 1, cv2.LINE_AA)
    return image, counts


class PeePreview:
    def __init__(self, model_path: Path | None, *, imgsz: int = 640,
                 confidence: float = 0.25, interval: float = 0.2,
                 absent_seconds: float = 300.0, on_presence_event=None,
                 worker_filter: WorkerFilter | None = None, show_rejected: bool = False,
                 person_model_path: Path | None = None, evidence_dir: Path | None = None,
                 quiet_periods: tuple[tuple[int, int], ...] = ()):
        # A dedicated person model wins over the PPE pilot: it only has to find people,
        # and the pilot's "worker" class fires on the cement sacks beside the pond.
        self.mode = 'area' if person_model_path else 'ppe'
        chosen = person_model_path or model_path
        self.model_path = Path(chosen) if chosen else None
        # An OpenVINO export is a folder, a PyTorch model is a file.
        self.enabled = self.model_path is not None and (self.model_path.is_file() or self.model_path.is_dir())
        self.evidence_dir = Path(evidence_dir) if evidence_dir else None
        self._person_classes = None
        self.imgsz = imgsz
        self.confidence = confidence
        self.interval = interval
        # ตัวกรองทำงานหลังโมเดล จึงตั้ง conf ของโมเดลต่ำไว้ได้ แล้วมาคัดทีหลัง
        # ข้อดีคือเห็นว่ากรองอะไรออกไปบ้าง แทนที่จะหายไปตั้งแต่ในโมเดล
        self.worker_filter = worker_filter or DEFAULT_WORKER_FILTER
        self.show_rejected = show_rejected
        self.presence = PresenceMonitor(absent_seconds=absent_seconds, quiet_periods=quiet_periods)
        self.on_presence_event = on_presence_event
        self._pending_events = deque()
        self._next_event_retry_at = 0.0
        self._model = None
        self._lock = threading.Lock()
        self._jpeg = None
        self._last_at = 0.0
        self._last_started_at = 0.0
        self._latest = None
        self._samples = deque(maxlen=30)
        self._last_inference_ms = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, source):
        if not self.enabled or self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(source,),
                                        name='final-pond-ppe', daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _run(self, source):
        previous_at = None
        while not self._stop.is_set():
            latest = source.latest()
            if latest is not None and latest[0] != previous_at:
                previous_at = latest[0]
                try:
                    began = time.monotonic()
                    previous_inference_at = self._last_at
                    self.frame(latest[1])
                    if self._last_at != previous_inference_at:
                        self._last_inference_ms = (time.monotonic() - began) * 1000
                except Exception:
                    log.exception('final_pond_background_inference_failed')
                    self.presence.observe(time.time(), 0, seeing=False)
                    self._stop.wait(3)
                    continue
            elif self._last_at and time.monotonic() - self._last_at > max(8.0, self.interval * 3):
                self.presence.observe(time.time(), 0, seeing=False)
            self._flush_events()
            self._stop.wait(0.02)

    def _flush_events(self):
        if self.on_presence_event is None or time.monotonic() < self._next_event_retry_at:
            return
        while self._pending_events:
            try:
                self.on_presence_event(self._pending_events[0])
            except Exception:
                log.exception('final_pond_presence_alert_save_failed')
                self._next_event_retry_at = time.monotonic() + 5
                return
            self._pending_events.popleft()

    def status(self):
        latest = self._latest
        if latest is None:
            return None
        if time.monotonic() - self._last_at > max(8.0, self.interval * 3):
            return {**latest, 'people_count': None, 'helmet_pass': None,
                    'no_helmet': None, 'undecided': None, 'filtered_out': None,
                    'workers_in_pond': None, 'workers_in_zone': None,
                    'camera_online': False, 'presence_status': 'blind',
                    'seconds_since_person': None, 'inference_fps': 0.0,
                    'inference_ms': round(self._last_inference_ms, 1)}
        samples = tuple(self._samples)
        fps = ((len(samples) - 1) / (samples[-1] - samples[0])
               if len(samples) > 1 and samples[-1] > samples[0] else 0.0)
        return {**latest, 'camera_online': True, 'inference_fps': round(fps, 2),
                'inference_ms': round(self._last_inference_ms, 1)}

    def cached_frame(self) -> bytes | None:
        if not (self.status() or {}).get('camera_online'):
            return None
        return self._jpeg

    def frame(self, source_jpeg: bytes) -> bytes:
        import cv2
        import numpy as np
        from ultralytics import YOLO

        if not self.enabled:
            raise RuntimeError('PEE pilot model is not configured')
        with self._lock:
            now = time.monotonic()
            if self._jpeg is not None and now - self._last_started_at < self.interval:
                return self._jpeg
            # Limit start-to-start cadence; do not add model execution time on
            # top of the configured interval (which used to cap us near 2 FPS).
            self._last_started_at = now
            if self._model is None:
                # task='detect' lets Ultralytics load an OpenVINO folder without guessing
                self._model = YOLO(str(self.model_path), task='detect')
                names = {str(value).strip().lower() for value in self._model.names.values()}
                if not names & PERSON_NAMES:
                    raise RuntimeError(f'Model has no worker/person class: {sorted(names)}')
                if self.mode == 'area':
                    # A COCO model also returns forklifts and chairs; skip them in the model
                    self._person_classes = [index for index, label in self._model.names.items()
                                            if str(label).strip().lower() in PERSON_NAMES]
            image = cv2.imdecode(np.frombuffer(source_jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError('Unable to decode camera JPEG')
            result = self._model.predict(image, imgsz=self.imgsz, conf=self.confidence,
                                         classes=self._person_classes, verbose=False)[0]
            detections = detections_from_result(result)
            if self.mode == 'area':
                output, counts = draw_area_detections(image, detections, self.worker_filter, self.show_rejected)
            else:
                output, counts = draw_detections(image, detections, self.worker_filter, self.show_rejected)
            ok, encoded = cv2.imencode('.jpg', output, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                raise RuntimeError('Unable to encode PEE preview JPEG')
            self._jpeg = encoded.tobytes()
            self._last_at = time.monotonic()
            observed_at = time.time()
            in_zone = workers_in_pond(detections, image.shape, self.worker_filter)
            event = self.presence.observe(observed_at, in_zone, seeing=True)
            if isinstance(event, (PresenceAlert, PresenceReturned)):
                kind = 'station_unattended' if isinstance(event, PresenceAlert) else 'station_attended'
                event_id = f'{CAMERA_ID}:{PRESENCE_TASK_ID}:{kind}:{int(event.at * 1_000_000)}'
                payload = {**event.payload(), 'review_required': True, 'zone_version': ZONE_VERSION}
                if kind == 'station_unattended':
                    evidence = self._save_evidence(event_id, self._jpeg, observed_at)
                    if evidence:
                        payload['evidence_image'] = evidence
                self._pending_events.append({
                    'task_id': PRESENCE_TASK_ID, 'type': kind, 'occurred_at': event.at,
                    'event_id': event_id, 'model_version': self.model_path.name,
                    'rule_version': 'final-pond-presence-v1', 'payload': payload,
                })
            self._latest = {**counts, 'workers_in_pond': in_zone, 'workers_in_zone': in_zone,
                            **self.presence.snapshot(observed_at)}
            self._samples.append(self._last_at)
            return self._jpeg

    def _save_evidence(self, event_id: str, jpeg: bytes, now: float) -> str | None:
        """Keep the frame that triggered an absence alert, so a reviewer can see the empty zone.

        A failed write must not cost the alert itself; the event is saved without an image."""
        if self.evidence_dir is None:
            return None
        name = re.sub(r'[^A-Za-z0-9_.-]', '_', event_id) + '.jpg'
        try:
            self.evidence_dir.mkdir(parents=True, exist_ok=True)
            (self.evidence_dir / name).write_bytes(jpeg)
            cutoff = now - EVIDENCE_KEEP_SECONDS
            for old in self.evidence_dir.glob('*.jpg'):
                if old.stat().st_mtime < cutoff:
                    old.unlink(missing_ok=True)
        except OSError:
            log.exception('final_pond_evidence_save_failed')
            return None
        return name

    def evidence_path(self, name: str) -> Path | None:
        """Resolve a stored evidence image by name, refusing anything that is not a plain file name."""
        if self.evidence_dir is None or not EVIDENCE_NAME.match(name):
            return None
        path = self.evidence_dir / name
        return path if path.is_file() else None
