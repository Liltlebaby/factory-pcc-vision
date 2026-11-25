"""worker ของกล้องบ่อสุดท้าย — ต่อภาพเข้ากับกฎ แล้วส่งผลให้ Vision Monitor

ทำไมเป็นโปรเซสแยก
------------------
ตัวนับเก๊ะรันอยู่ในโปรเซสของ Vision Monitor เอง ถ้าเอางานกล้องตัวนี้ไปรวมด้วย
สองงานจะแย่ง GIL กันจน inference ของทั้งคู่ช้าลง ซึ่งเคยเกิดมาแล้วตอนที่ผู้ชม
MJPEG ทำให้ fps ของตัวนับตก worker นี้จึงคุยกับ Vision Monitor ผ่าน HTTP เท่านั้น
และใช้ฐานข้อมูลกับทะเบียนกล้องร่วมกัน

แบ่งหน้าที่ชัดเจน
-----------------
    handle_frame()  ตรรกะล้วน ป้อนเฟรมแล้วคืนเหตุการณ์ ทดสอบได้โดยไม่ต้องมีกล้อง
    run()           วนอ่าน RTSP และยิง HTTP ซึ่งเป็นส่วนที่ทดสอบอัตโนมัติยาก

ที่แบ่งแบบนี้เพราะบั๊กที่แพงที่สุดอยู่ในตรรกะ ไม่ใช่ใน IO — และตรรกะคือส่วนที่
เขียนเทสต์ครอบได้จริง
"""
import logging
import os
import time
from dataclasses import dataclass, field

from .ppe import HelmetMonitor, HelmetResolved, HelmetViolation
from .presence import PresenceAlert, PresenceMonitor, PresenceReturned
from .vision import summarise

log = logging.getLogger('vision.final_pond')

TASK_ID = 'ppe-helmet'
# การไม่มีคนในพื้นที่เป็นงานแยกในทะเบียน เปิดใช้ได้ก่อนงานหมวก
PRESENCE_TASK_ID = 'work-area-presence'
RULE_VERSION = 'final-pond-people-v1'


@dataclass
class FinalPondWorker:
    """รวมผลจากภาพเข้ากับกฎของโรงงาน แล้วคืนเหตุการณ์ที่ต้องบันทึก

    `vision` ต้องมีเมธอด observe(frame) -> list[PersonObservation]
    ฉีดเข้ามาเพื่อให้เทสต์ใช้ตัวปลอมได้ และเพื่อให้เปลี่ยนโมเดลได้โดยไม่แตะไฟล์นี้
    """

    camera_id: str
    vision: object
    helmet_model_ready: bool = True
    helmet: HelmetMonitor = field(default_factory=HelmetMonitor)
    presence: PresenceMonitor = field(default_factory=PresenceMonitor)
    # งานที่จดไว้ในทะเบียนกล้องแล้วแต่ worker นี้ยังทำไม่ได้
    #
    # Vision Monitor บังคับว่า heartbeat ต้องรายงานงานให้ครบทุกงานของกล้องนั้น
    # ไม่งั้นตอบ 422 แล้วหน้าจอจะขึ้นว่ากล้องออฟไลน์โดยไม่บอกสาเหตุ กล้องบ่อสุดท้าย
    # มีสองงาน เมื่อ worker ทำได้แค่งานเดียวจึงต้องรายงานอีกงานว่า unavailable
    # ซึ่งตรงความจริง: งานนั้นมีอยู่ในแผน แต่ยังไม่ได้เดิน
    idle_tasks: tuple[str, ...] = ('magnet-inspection',)
    # ค่าปัจจุบันของงานหมวกและงานเฝ้าพื้นที่ แยกกันตามทะเบียน
    latest: dict = field(default_factory=dict, init=False)
    presence_latest: dict = field(default_factory=dict, init=False)

    def handle_frame(self, at: float, frame) -> list[dict]:
        """ประมวลผลหนึ่งเฟรม คืนรายการเหตุการณ์ที่พร้อมส่งเข้า API

        `frame` เป็น None เมื่ออ่านภาพไม่ได้ ซึ่งต้องแยกจาก "เห็นภาพแต่ไม่มีคน"
        ให้เด็ดขาด ไม่งั้นกล้องดับจะกลายเป็นการกล่าวหาคนงาน
        """
        if frame is None:
            self.presence.observe(at, 0, seeing=False)
            self.latest = self.helmet.snapshot(0, 0, 0)
            self.presence_latest = {**self.presence.snapshot(at), 'workers_in_zone': None}
            return []

        observations = self.vision.observe(frame)
        totals = summarise(observations)
        events = []

        for found in observations:
            if not found.decided:
                continue
            event = self.helmet.observe(at, found.track_id, found.helmet,
                                        found.height_ratio, found.confidence)
            if isinstance(event, HelmetViolation):
                events.append(self._event('ppe_violation', event.confirmed_at, event.payload(),
                                          event.event_id(self.camera_id, TASK_ID)))
            elif isinstance(event, HelmetResolved):
                events.append(self._event('ppe_resolved', event.at, event.payload()))

        # นับเฉพาะคนที่โมเดลมั่นใจพอ ไม่ใช่ทุกกล่องที่โผล่มา เพราะกล่องความมั่นใจต่ำ
        # หนึ่งกล่องไม่ควรรีเซ็ตนาฬิกาการหายไป 5 นาทีของจริง
        confident = sum(1 for item in observations
                        if self.helmet.assess(item.height_ratio, item.confidence))
        event = self.presence.observe(at, confident, seeing=True)
        if isinstance(event, PresenceAlert):
            events.append(self._event('station_unattended', event.at, event.payload(),
                                      task_id=PRESENCE_TASK_ID))
        elif isinstance(event, PresenceReturned):
            events.append(self._event('station_attended', event.at, event.payload(),
                                      task_id=PRESENCE_TASK_ID))

        self.helmet.expire(at)
        self.latest = self.helmet.snapshot(totals['people'], totals['helmet_pass'], totals['no_helmet'])
        self.presence_latest = {**self.presence.snapshot(at), 'workers_in_zone': confident}
        return events

    def _event(self, kind: str, at: float, payload: dict, event_id: str | None = None,
               task_id: str = TASK_ID) -> dict:
        event = {'task_id': task_id, 'type': kind, 'occurred_at': at,
                 'rule_version': RULE_VERSION, 'payload': payload}
        if event_id:
            event['event_id'] = event_id
        return event

    def heartbeat(self, camera_online: bool, camera_fps: float, inference_fps: float,
                  model_version: str | None) -> dict:
        helmet_running = camera_online and self.helmet_model_ready
        return {
            'camera_status': 'online' if camera_online else 'offline',
            'camera_fps': round(camera_fps, 2),
            'tasks': [
                {
                    # ต้องการแค่โมเดลตรวจคน จึงทำงานได้แม้ยังไม่มีโมเดลหมวก
                    'task_id': PRESENCE_TASK_ID,
                    'runtime_status': 'running' if camera_online else 'unavailable',
                    'model_version': model_version if camera_online else None,
                    'inference_fps': round(inference_fps, 2) if camera_online else 0,
                    'latest': self.presence_latest if camera_online and self.presence_latest else None,
                },
                {
                    'task_id': TASK_ID,
                    'runtime_status': 'running' if helmet_running else 'unavailable',
                    'model_version': model_version if helmet_running else None,
                    'inference_fps': round(inference_fps, 2) if helmet_running else 0,
                    'latest': self.latest if helmet_running and self.latest else None,
                },
                *({
                    'task_id': task_id,
                    'runtime_status': 'unavailable',
                    'model_version': None,
                    'inference_fps': 0,
                    'latest': None,
                } for task_id in self.idle_tasks),
            ],
        }


def settings_from_env() -> dict:
    required = ('FINAL_POND_RTSP', 'FINAL_POND_PERSON_MODEL')
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        # ล้มให้ดังตั้งแต่ตอนเริ่ม ดีกว่ารันไปเงียบ ๆ แล้วไม่มีใครรู้ว่าไม่ได้ตรวจอะไรเลย
        raise SystemExit(f'ต้องตั้งค่า environment เหล่านี้ก่อน: {", ".join(missing)}')
    return {
        'source': os.getenv('FINAL_POND_RTSP'),
        'person_model': os.getenv('FINAL_POND_PERSON_MODEL'),
        'ppe_model': os.getenv('FINAL_POND_PPE_MODEL') or None,
        'camera_id': os.getenv('VISION_CAMERA_ID', 'final-pond-cam-01'),
        'fps': float(os.getenv('FINAL_POND_FPS', '3')),
        'imgsz': int(os.getenv('FINAL_POND_IMGSZ', '640')),
        'confidence': float(os.getenv('FINAL_POND_CONFIDENCE', '0.35')),
        'absent_seconds': float(os.getenv('FINAL_POND_ABSENT_SECONDS', '300')),
        'stale_seconds': float(os.getenv('FINAL_POND_STALE_SECONDS', '10')),
    }


def run(argv=None) -> int:
    import cv2

    from ..worker_client import WorkerClientSettings, WorkerHeartbeatClient
    from .vision import YoloVision

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    cfg = settings_from_env()
    client = WorkerHeartbeatClient(WorkerClientSettings())
    vision = YoloVision(cfg['person_model'], cfg['ppe_model'],
                        imgsz=cfg['imgsz'], confidence=cfg['confidence'])
    worker = FinalPondWorker(
        camera_id=cfg['camera_id'],
        vision=vision,
        helmet_model_ready=cfg['ppe_model'] is not None,
        presence=PresenceMonitor(absent_seconds=cfg['absent_seconds']),
    )
    if cfg['ppe_model'] is None:
        log.warning('ไม่ได้ตั้ง FINAL_POND_PPE_MODEL — ทุกคนจะเป็น UNDECIDED '
                    'กฎห้ามคนหายยังทำงานปกติ แต่จะไม่มีการฟ้องเรื่องหมวก')

    capture = cv2.VideoCapture(cfg['source'])
    interval = 1.0 / cfg['fps']
    pending, last_frame_at, frames, began = [], None, 0, time.monotonic()

    try:
        while True:
            ok, frame = capture.read()
            now = time.time()
            if not ok:
                worker.handle_frame(now, None)
                capture.release()
                time.sleep(1.0)
                capture = cv2.VideoCapture(cfg['source'])
                continue
            # ภาพค้างนานเกินไปก็เท่ากับมองไม่เห็น ต่อให้ read() บอกว่าสำเร็จ
            seeing = last_frame_at is None or now - last_frame_at <= cfg['stale_seconds']
            last_frame_at = now
            frames += 1
            pending.extend(worker.handle_frame(now, frame if seeing else None))

            elapsed = max(1e-6, time.monotonic() - began)
            body = worker.heartbeat(True, frames / elapsed, frames / elapsed,
                                    os.path.basename(cfg['ppe_model'] or cfg['person_model']))
            try:
                client.publish(body)
                if pending:
                    _post_events(client.settings, cfg['camera_id'], pending)
                    pending = []
            except Exception as exc:
                # เก็บเหตุการณ์ไว้ส่งใหม่ ไม่ทิ้ง เพราะการฟ้องที่หายไปคือการฟ้องที่ไม่เกิดขึ้น
                log.warning('ส่งผลไม่สำเร็จ error_type=%s ค้างอยู่ %d รายการ',
                            type(exc).__name__, len(pending))
                pending = pending[-200:]
            time.sleep(interval)
    except KeyboardInterrupt:
        log.info('หยุดตามคำสั่ง')
    finally:
        capture.release()
    return 0


def _post_events(settings, camera_id: str, events: list[dict]):
    import json
    from urllib.parse import quote
    from urllib.request import Request, urlopen

    endpoint = f"{settings.api_url.rstrip('/')}/api/v1/workers/{quote(camera_id, safe='')}/events"
    headers = {'Content-Type': 'application/json'}
    if settings.token:
        headers['Authorization'] = f'Bearer {settings.token}'
    # ส่งทีละไม่เกิน 50 ตามที่ฝั่ง API รับได้
    for index in range(0, len(events), 50):
        request = Request(endpoint, data=json.dumps({'events': events[index:index + 50]},
                                                    ensure_ascii=False).encode('utf-8'),
                          headers=headers, method='POST')
        with urlopen(request, timeout=settings.timeout_seconds) as response:
            response.read()


if __name__ == '__main__':
    raise SystemExit(run())
