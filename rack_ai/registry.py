"""Registry ของกล้องและงาน AI ที่ปลอดภัยสำหรับส่งออกผ่าน API.

ข้อมูลลับ เช่น RTSP URL และ token ไม่อยู่ใน registry นี้ โดยตั้งใจให้ configuration
ที่เปิดเผยต่อ PCC แยกออกจาก credential ของ worker กล้อง
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


Lifecycle = Literal["active", "planned", "disabled"]


@dataclass(frozen=True)
class AITaskDefinition:
    task_id: str
    name: str
    task_type: str
    station_id: str
    lifecycle: Lifecycle
    output_metrics: tuple[str, ...]
    model_required: bool = True

    def public(self) -> dict:
        value = asdict(self)
        value["output_metrics"] = list(self.output_metrics)
        return value


@dataclass(frozen=True)
class CameraDefinition:
    camera_id: str
    name: str
    station_id: str
    location: str
    lifecycle: Lifecycle
    tasks: tuple[AITaskDefinition, ...]

    def public(self) -> dict:
        value = asdict(self)
        value["tasks"] = [task.public() for task in self.tasks]
        return value


CAMERAS = (
    CameraDefinition(
        camera_id="camera-09",
        name="Camera 09",
        station_id="rack-infeed",
        location="หอโรยยาง · ก่อนเข้าเตา · LINE-1",
        lifecycle="active",
        tasks=(
            # งานนี้นับ "เก๊ะ" ที่ออกจากหอโรยยางก่อนเข้าเตา ไม่ใช่ก้อนยาง
            # ชื่อ rubber_* ถูกปล่อยไว้ให้เซ็นเซอร์นับก้อนยางก่อนแพ็คที่จะมาทีหลัง
            AITaskDefinition(
                task_id="rack-counting",
                name="นับเก๊ะหอโรยยางก่อนเข้าเตา",
                task_type="line_crossing_count",
                station_id="rack-infeed",
                lifecycle="active",
                output_metrics=("rack_count", "active_tracks", "last_event"),
            ),
        ),
    ),
    # กล้องบ่อสุดท้ายทำสามงานจากภาพเดียวกัน ตามที่โรงงานกำหนด
    #   เฝ้าพื้นที่      ไม่มีคนในพื้นที่ทำงานเกิน 5 นาทีให้เตือน ใช้แค่โมเดลตรวจคน
    #   ตรวจหมวกนิรภัย  ทำตลอดเวลาที่กล้องเห็นภาพ ไม่ขึ้นกับรอบตรวจแม่เหล็ก
    #   รอบตรวจแม่เหล็ก ทำเป็นรอบทุกชั่วโมง ต้องเห็นการยกคันโยกจึงถือว่าตรวจ
    # งานเหล่านี้ต้องแยกกันเด็ดขาด เพราะชั่วโมงที่ไม่มีใครมาตรวจแม่เหล็กก็ยังต้อง
    # เตือนเรื่องหมวกได้ และรอบที่ตรวจแม่เหล็กแล้วก็ยังอาจมีคนไม่สวมหมวกอยู่
    # เฝ้าพื้นที่แยกจากหมวกเพราะเปิดใช้ได้ก่อน ขณะที่โมเดลหมวกยังต้องเทรนด้วยภาพจริง
    # ถ้ารวมกัน งานหมวกที่ยังไม่พร้อมจะลากสถานะของงานพื้นที่หายไปด้วย
    #
    # lifecycle ยังเป็น planned จนกว่าจะยืนยันช่อง DVR และ RTSP ของกล้องตัวนี้
    # เปลี่ยนเป็น active เมื่อไหร่ worker จึงจะส่ง heartbeat เข้าได้
    CameraDefinition(
        camera_id="final-pond-cam-01",
        name="บ่อสุดท้าย กล้อง 01",
        station_id="final-pond",
        location="บ่อสุดท้าย · จุดตรวจแม่เหล็ก · รอยืนยันช่อง DVR",
        lifecycle="planned",
        tasks=(
            AITaskDefinition(
                task_id="work-area-presence",
                name="เฝ้าพื้นที่ทำงานบ่อสุดท้าย · ไม่มีคนเกิน 5 นาที",
                task_type="area_presence",
                station_id="final-pond",
                lifecycle="planned",
                output_metrics=("presence_status", "seconds_since_person",
                                "unattended_alerts", "workers_in_zone",
                                "people_count", "filtered_out"),
            ),
            AITaskDefinition(
                task_id="ppe-helmet",
                name="ตรวจหมวกนิรภัยของคนงานตลอดเวลา",
                task_type="ppe_compliance",
                station_id="final-pond",
                lifecycle="planned",
                output_metrics=("people_count", "helmet_pass", "no_helmet",
                                "violation_count", "assessment_status"),
            ),
            # งานนี้ไม่ต้องใช้โมเดลของตัวเอง มันอ่านผลจากคันโยกกับตาชั่ง
            # จึงเป็นงานเดียวที่เดินได้ก่อนโมเดลหมวกจะเทรนเสร็จ
            AITaskDefinition(
                task_id="magnet-inspection",
                name="รอบตรวจแม่เหล็กรายชั่วโมง",
                task_type="hourly_inspection",
                station_id="final-pond",
                lifecycle="planned",
                output_metrics=("round_key", "round_status", "last_checked_at",
                                "last_weight_kg", "awaiting_weight"),
                model_required=False,
            ),
        ),
    ),
    # กล้องตรวจสถานะงาน (work-status-camera) ถูกถอดออก 2026-10-05 ตามที่โรงงานแจ้ง
    # งานเฝ้าคนในพื้นที่ใช้ work-area-presence ของกล้องบ่อสุดท้ายแทน
)

CAMERA_BY_ID = {camera.camera_id: camera for camera in CAMERAS}


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field_name} must be a non-empty string')
    return value.strip()


def _parse_task(value: object, camera_station_id: str) -> AITaskDefinition:
    if not isinstance(value, dict):
        raise ValueError('camera task must be an object')
    lifecycle = value.get('lifecycle')
    if lifecycle not in ('active', 'planned', 'disabled'):
        raise ValueError('task lifecycle must be active, planned, or disabled')
    station_id = _required_text(value.get('station_id'), 'task.station_id')
    if station_id != camera_station_id:
        raise ValueError('task station_id must match its camera station_id')
    metrics = value.get('output_metrics')
    if not isinstance(metrics, list) or not metrics or not all(isinstance(metric, str) and metric for metric in metrics):
        raise ValueError('task.output_metrics must be a non-empty string array')
    return AITaskDefinition(
        task_id=_required_text(value.get('task_id'), 'task.task_id'),
        name=_required_text(value.get('name'), 'task.name'),
        task_type=_required_text(value.get('task_type'), 'task.task_type'),
        station_id=station_id,
        lifecycle=lifecycle,
        output_metrics=tuple(metrics),
        model_required=bool(value.get('model_required', True)),
    )


def _parse_camera(value: object) -> CameraDefinition:
    if not isinstance(value, dict):
        raise ValueError('camera must be an object')
    forbidden = {'rtsp', 'source', 'url', 'token', 'password'} & {str(key).lower() for key in value}
    if forbidden:
        raise ValueError('camera registry must not contain credentials or stream URLs')
    lifecycle = value.get('lifecycle')
    if lifecycle not in ('active', 'planned', 'disabled'):
        raise ValueError('camera lifecycle must be active, planned, or disabled')
    station_id = _required_text(value.get('station_id'), 'camera.station_id')
    raw_tasks = value.get('tasks')
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError('camera.tasks must be a non-empty array')
    return CameraDefinition(
        camera_id=_required_text(value.get('camera_id'), 'camera.camera_id'),
        name=_required_text(value.get('name'), 'camera.name'),
        station_id=station_id,
        location=_required_text(value.get('location'), 'camera.location'),
        lifecycle=lifecycle,
        tasks=tuple(_parse_task(task, station_id) for task in raw_tasks),
    )


def validate_camera_registry(cameras: tuple[CameraDefinition, ...]) -> tuple[CameraDefinition, ...]:
    if not cameras:
        raise ValueError('camera registry must contain at least one camera')
    camera_ids = [camera.camera_id for camera in cameras]
    task_ids = [task.task_id for camera in cameras for task in camera.tasks]
    if len(camera_ids) != len(set(camera_ids)):
        raise ValueError('camera_id values must be unique')
    if len(task_ids) != len(set(task_ids)):
        raise ValueError('task_id values must be unique')
    return cameras


def load_camera_registry(path: Path | str) -> tuple[CameraDefinition, ...]:
    """Load public camera/task metadata. Stream credentials stay in environment variables."""
    registry_path = Path(path)
    try:
        payload = json.loads(registry_path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise ValueError(f'camera registry not found: {registry_path}') from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f'invalid camera registry JSON: {registry_path}') from exc
    if not isinstance(payload, dict) or not isinstance(payload.get('cameras'), list):
        raise ValueError('camera registry root must contain a cameras array')
    return validate_camera_registry(tuple(_parse_camera(camera) for camera in payload['cameras']))


def cameras_for_station(station_id: str, cameras: tuple[CameraDefinition, ...] = CAMERAS) -> list[CameraDefinition]:
    return [camera for camera in cameras if camera.station_id == station_id]


def active_camera_status(
    camera: CameraDefinition,
    snapshot: dict,
    model_name: str,
    signal: dict | None = None,
) -> dict:
    """Map legacy Camera 09 snapshot ไปสู่ contract กลางโดยไม่เผย tracks/ภาพ.

    `signal` คือผลถาม DVR ว่าช่องนี้ยังมีสัญญาณเข้าไหม (rack_ai/dvr.py) แยกจาก
    camera_status เพราะสองอย่างนี้ไม่เท่ากัน: เมื่อสายกล้องอนาล็อกหลุด DVR ยังส่ง
    ภาพ NO VIDEO ออกมาเรื่อย ๆ camera_status จึงเป็น online ทั้งที่มองไม่เห็นอะไร
    """
    camera_state = snapshot.get("camera") or {}
    fps = snapshot.get("fps") or {}
    running = bool(snapshot.get("running"))
    task = camera.tasks[0]
    return {
        "camera_id": camera.camera_id,
        "name": camera.name,
        "station_id": camera.station_id,
        "location": camera.location,
        "lifecycle": camera.lifecycle,
        "camera_status": "online" if camera_state.get("connected") else "offline",
        "source_signal": signal,
        "data_status": "live" if running else "offline",
        "updated_at": snapshot.get("timestamp"),
        "camera_fps": float(fps.get("camera") or 0),
        "tasks": [
            {
                **task.public(),
                "runtime_status": "running" if running else "unavailable",
                "model_version": snapshot.get("model") or model_name,
                "inference_fps": float(fps.get("inference") or 0),
                "latest": {
                    "rack_count": int(snapshot.get("rack_count") or 0),
                    "active_tracks": int(snapshot.get("active_tracks") or 0),
                    "last_event": snapshot.get("lastEvent"),
                },
            }
        ],
    }


def planned_camera_status(camera: CameraDefinition) -> dict:
    return {
        "camera_id": camera.camera_id,
        "name": camera.name,
        "station_id": camera.station_id,
        "location": camera.location,
        "lifecycle": camera.lifecycle,
        "camera_status": "not_installed",
        "data_status": "not_installed",
        "updated_at": None,
        "camera_fps": 0,
        "tasks": [
            {**task.public(), "runtime_status": "not_installed", "model_version": None, "inference_fps": 0, "latest": None}
            for task in camera.tasks
        ],
    }


def unavailable_camera_status(camera: CameraDefinition) -> dict:
    """Status for an installed/active camera whose dedicated runtime is not online yet."""
    value = planned_camera_status(camera)
    value.update(camera_status='offline', data_status='offline')
    for task in value['tasks']:
        task['runtime_status'] = 'unavailable'
    return value
