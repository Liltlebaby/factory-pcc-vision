import asyncio
import hmac
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Query
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, Response

from .config import Settings
from .dvr import monitor_from
from .camera_preview import CameraPreview
from .final_pond.pilot import PeePreview, WorkerFilter
from .final_pond.presence import parse_quiet_periods
from . import shifts as shift_report
from .final_pond import rounds as magnet
from .final_pond.ingest import normalise_coverage, normalise_events
from .service import RackService
from .registry import (
    CameraDefinition,
    active_camera_status,
    cameras_for_station,
    load_camera_registry,
    planned_camera_status,
    validate_camera_registry,
)
from .worker_runtime import WorkerRuntimeRegistry
from .lab.api import router as lab_router
from .lab.jobs import LabManager
import threading
import sqlite3


class RecordingRequest(BaseModel):
    duration_minutes: float = Field(default=10, gt=0, le=60, allow_inf_nan=False)
    name: str = Field(default='Camera09', max_length=100, pattern=r'^[\w .-]+$')
    annotated: bool = False


class ScheduleRequest(RecordingRequest):
    start_at: datetime


class EventPolicy(BaseModel):
    enabled: bool = False
    duration_minutes: float = Field(default=10,ge=1,le=60,allow_inf_nan=False)
    cooldown_seconds: float = Field(default=900,ge=60,le=86400,allow_inf_nan=False)
    low_confidence: bool = True
    multiple_racks: bool = True
    rack_exit: bool = False
    annotated: bool = False


class WorkerTaskHeartbeat(BaseModel):
    task_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    runtime_status: Literal['running', 'unavailable']
    model_version: str | None = Field(default=None, max_length=255)
    inference_fps: float = Field(default=0, ge=0, le=240, allow_inf_nan=False)
    latest: dict[str, Any] | None = None


class WorkerHeartbeat(BaseModel):
    camera_status: Literal['online', 'offline']
    camera_fps: float = Field(default=0, ge=0, le=240, allow_inf_nan=False)
    tasks: list[WorkerTaskHeartbeat] = Field(min_length=1, max_length=20)


class WorkerCoverageItem(BaseModel):
    """เวลาที่กล้องเห็นภาพจริงในรอบหนึ่งชั่วโมง ส่งสะสมเป็นช่วง ๆ ระหว่างชั่วโมง"""
    round_key: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}$')
    seconds: float = Field(ge=0, le=3600, allow_inf_nan=False)


class WorkerEventItem(BaseModel):
    task_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    type: str = Field(min_length=1, max_length=60, pattern=r'^[A-Za-z0-9_.-]+$')
    occurred_at: float | str
    # worker ควรกำหนดเอง เพราะรู้ว่าอะไรคือตัวแยกเหตุการณ์ที่แท้จริง ส่งซ้ำจึงไม่เกิดแถวซ้ำ
    event_id: str | None = Field(default=None, max_length=160, pattern=r'^[A-Za-z0-9_.:-]+$')
    model_version: str | None = Field(default=None, max_length=255)
    rule_version: str | None = Field(default=None, max_length=255)
    payload: dict[str, Any] | None = None


class WorkerEventBatch(BaseModel):
    events: list[WorkerEventItem] = Field(default_factory=list, max_length=50)
    coverage: list[WorkerCoverageItem] = Field(default_factory=list, max_length=50)


def create_app(
    settings: Settings | None = None,
    service=None,
    camera_definitions: tuple[CameraDefinition, ...] | None = None,
    final_pond_preview: CameraPreview | None = None,
    final_pond_ai: PeePreview | None = None,
) -> FastAPI:
    cfg = settings or Settings()
    pipeline = service or RackService(cfg)
    camera_registry = (
        validate_camera_registry(tuple(camera_definitions))
        if camera_definitions is not None
        else load_camera_registry(cfg.camera_registry)
    )
    camera_by_id = {camera.camera_id: camera for camera in camera_registry}
    if cfg.primary_camera_id not in camera_by_id:
        raise ValueError(f'PRIMARY_CAMERA_ID is not present in registry: {cfg.primary_camera_id}')
    worker_runtime = WorkerRuntimeRegistry(cfg.worker_stale)
    # กล้องที่รับผิดชอบรอบตรวจแม่เหล็ก หาเอาจากชนิดงานในทะเบียน ไม่ฮาร์ดโค้ดไอดี
    # ย้ายกล้องหรือเปลี่ยนชื่อในทะเบียนแล้วรายงานยังตามไปถูกตัวเอง
    inspection_camera = next(
        (camera for camera in camera_registry
         if any(task.task_type == 'hourly_inspection' for task in camera.tasks)),
        None,
    )
    # เธรดแยกที่ถาม DVR นาทีละครั้งว่าช่องกล้องยังมีสัญญาณไหม
    # ไม่เรียก pipeline.snapshot() และไม่แตะ lock ของลูป inference
    dvr = monitor_from(cfg)
    # มีโมเดลตรวจคนเมื่อไหร่ งานบ่อสุดท้ายเหลือแค่เฝ้าพื้นที่ ซึ่งไม่ต้องเร็วเท่าการดูหมวก
    pond_ai_fps = cfg.final_pond_area_fps if cfg.final_pond_person_model else cfg.final_pond_ppe_fps
    pond_preview = final_pond_preview or CameraPreview(
        cfg.final_pond_source, background_fps=max(10, pond_ai_fps * 2))
    pond_camera_id = 'final-pond-cam-01'

    def save_pond_presence_event(event: dict):
        journal = getattr(pipeline, 'journal', None)
        if journal is None:
            raise RuntimeError('event_storage_unavailable')
        prepared = normalise_events(camera_by_id[pond_camera_id], [event], time.time())
        journal.ingest(pond_camera_id, prepared)

    pond_ai = final_pond_ai or PeePreview(
        cfg.final_pond_ppe_model, interval=1 / pond_ai_fps,
        absent_seconds=cfg.final_pond_absent_seconds,
        on_presence_event=save_pond_presence_event,
        worker_filter=WorkerFilter(
            confidence=cfg.final_pond_worker_confidence,
            min_height_ratio=cfg.final_pond_worker_min_height,
            max_height_ratio=cfg.final_pond_worker_max_height,
            max_aspect_ratio=cfg.final_pond_worker_max_aspect,
        ),
        show_rejected=cfg.final_pond_show_rejected,
        person_model_path=cfg.final_pond_person_model,
        evidence_dir=cfg.final_pond_evidence_dir,
        quiet_periods=parse_quiet_periods(cfg.final_pond_quiet_hours))

    # ค่าที่แต่ละงานของกล้องบ่อสุดท้ายรายงาน — แยกกันเพื่อให้งานหมวกที่ยังไม่เปิด
    # ไม่ลากสถานะของงานเฝ้าพื้นที่หายไปด้วย
    presence_keys = ('presence_status', 'seconds_since_person', 'unattended_alerts',
                     'workers_in_zone', 'workers_in_pond', 'people_count', 'filtered_out',
                     'camera_online', 'inference_fps', 'inference_ms')
    helmet_keys = ('people_count', 'helmet_pass', 'no_helmet', 'undecided', 'filtered_out',
                   'camera_online', 'inference_fps', 'inference_ms')

    def public_camera_status(camera: CameraDefinition) -> dict:
        if camera.camera_id == cfg.primary_camera_id:
            return active_camera_status(camera, pipeline.snapshot(), cfg.model.name, dvr.status())
        if camera.lifecycle == 'planned':
            status = planned_camera_status(camera)
            if camera.camera_id == pond_camera_id and pond_ai.enabled:
                latest = pond_ai.status()
                status['ai_pilot'] = True
                status['ai_mode'] = pond_ai.mode
                online = bool(latest and latest.get('camera_online', True))
                status['camera_status'] = 'online' if online else 'offline'
                status['data_status'] = 'pilot' if online else 'unavailable'
                for task in status['tasks']:
                    keys = presence_keys if task['task_id'] == 'work-area-presence' else \
                        helmet_keys if task['task_id'] == 'ppe-helmet' and pond_ai.mode == 'ppe' else None
                    if keys is None:
                        continue
                    task['runtime_status'] = 'pilot' if online else 'waiting'
                    task['model_version'] = pond_ai.model_path.name
                    task['inference_fps'] = latest.get('inference_fps', 0) if latest else 0
                    task['latest'] = {key: latest.get(key) for key in keys} if latest else None
            if camera.camera_id == pond_camera_id and pond_preview.enabled:
                stats = pond_preview.stats()
                status['camera_fps'] = stats['source_fps']
                status['source_stats'] = stats
            return status
        return worker_runtime.status(camera)
    lab = None
    lab_lock = threading.Lock()
    def manager():
        nonlocal lab
        with lab_lock:
            if lab is None:
                lab=LabManager(cfg)
                lab.recover()
        return lab

    @asynccontextmanager
    async def lifespan(app):
        pipeline.start()
        dvr.start()
        if pond_preview.enabled and pond_ai.enabled:
            pond_preview.start()
            pond_ai.start(pond_preview)
        try:
            yield
        finally:
            dvr.close()
            pond_ai.close()
            pond_preview.close()
            if lab is not None:
                await asyncio.to_thread(lab.close)
            await asyncio.to_thread(pipeline.close)

    app = FastAPI(title='Vision Monitor', lifespan=lifespan)
    app.state.pipeline = pipeline
    app.state.worker_runtime = worker_runtime
    @app.exception_handler(sqlite3.Error)
    async def database_error(request,exc):
        return JSONResponse({'error':'database_unavailable'},status_code=503)
    app.include_router(lab_router(manager,lambda:pipeline.recorder.storage()))
    app.add_middleware(CORSMiddleware, allow_origins=cfg.origins,allow_methods=['GET','POST','DELETE'],allow_headers=['Authorization','Content-Type'])

    def authorized(value: str) -> bool:
        return not cfg.token or hmac.compare_digest(value, 'Bearer '+cfg.token)

    @app.middleware('http')
    async def auth(request: Request, call_next):
        origin=request.headers.get('origin')
        if request.method in ('POST','DELETE','PUT','PATCH') and origin and origin not in cfg.origins:
            return JSONResponse({'error':'origin_not_allowed'},status_code=403)
        if request.method != 'OPTIONS' and request.url.path not in ('/','/monitor.js','/counting.js','/monitor.css','/health','/dataset','/dataset.js') and not authorized(request.headers.get('authorization','')):
            return JSONResponse({'error':'unauthorized'},status_code=401)
        return await call_next(request)

    @app.get('/health')
    def health():
        return {'alive':True,'ready':pipeline.snapshot()['running']}

    @app.get('/api/status')
    @app.get('/api/rack-counter/status')
    def status():
        return pipeline.snapshot()

    @app.get('/api/v1/cameras')
    def cameras():
        return {
            'items': [
                {
                    **camera.public(),
                    'status': public_camera_status(camera),
                    **({'preview_url': f'/api/v1/cameras/{pond_camera_id}/frame'}
                       if camera.camera_id == pond_camera_id and pond_preview.enabled else {}),
                    **({'preview_url': f'/api/v1/cameras/{pond_camera_id}/ai-frame', 'ai_pilot': True}
                       if camera.camera_id == pond_camera_id and pond_preview.enabled and pond_ai.enabled else {}),
                }
                for camera in camera_registry
            ],
            'total': len(camera_registry),
        }

    @app.get('/api/v1/system-links')
    def system_links():
        return {'pcc': cfg.pcc_url}

    @app.get('/api/v1/cameras/{camera_id}/status')
    def camera_status(camera_id: str):
        camera = camera_by_id.get(camera_id)
        if camera is None:
            raise HTTPException(404, 'camera_not_found')
        return public_camera_status(camera)

    @app.put('/api/v1/workers/{camera_id}/heartbeat')
    def worker_heartbeat(camera_id: str, body: WorkerHeartbeat):
        camera = camera_by_id.get(camera_id)
        if camera is None:
            raise HTTPException(404, 'camera_not_found')
        if camera.camera_id == cfg.primary_camera_id:
            raise HTTPException(409, 'primary_camera_uses_embedded_runtime')
        if camera.lifecycle != 'active':
            raise HTTPException(409, 'camera_is_not_active')
        try:
            return worker_runtime.update(camera, body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.post('/api/v1/workers/{camera_id}/events')
    def worker_events(camera_id: str, body: WorkerEventBatch):
        """รับเหตุการณ์จาก worker ภายนอก เช่น รอบตรวจแม่เหล็กและการไม่สวมหมวก

        heartbeat ส่งได้แค่ค่าปัจจุบันเป็น scalar ซึ่งหายไปเมื่อค่าถัดไปมาถึง
        สิ่งที่ต้องตรวจย้อนหลังได้จึงต้องมาทางนี้เพื่อลง ai_events อย่างถาวร
        """
        camera = camera_by_id.get(camera_id)
        if camera is None:
            raise HTTPException(404, 'camera_not_found')
        if camera.camera_id == cfg.primary_camera_id:
            raise HTTPException(409, 'primary_camera_uses_embedded_runtime')
        if camera.lifecycle != 'active':
            raise HTTPException(409, 'camera_is_not_active')
        journal = getattr(pipeline, 'journal', None)
        if journal is None:
            raise HTTPException(503, 'event_storage_unavailable')
        payload = body.model_dump()
        if not payload['events'] and not payload['coverage']:
            raise HTTPException(422, 'ต้องมี events หรือ coverage อย่างน้อยหนึ่งอย่าง')
        now = time.time()
        try:
            prepared = normalise_events(camera, payload['events'], now) if payload['events'] else []
            coverage = normalise_coverage(payload['coverage'], now)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        try:
            return journal.ingest(camera.camera_id, prepared, coverage)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        except sqlite3.Error:
            raise HTTPException(503, 'event_storage_unavailable')

    @app.get('/api/v1/final-pond/magnet-rounds')
    def magnet_rounds(
        date: str | None = Query(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    ):
        """รอบตรวจแม่เหล็กของวันรายงานหนึ่งวัน ย้อนหลังได้ทุกวันที่มีข้อมูล

        สร้างใหม่จาก ai_events ทุกครั้ง ไม่ได้อ่านจากหน่วยความจำของ worker
        รายงานจึงอยู่ครบแม้ worker จะรีสตาร์ตหรือย้ายเครื่อง และใช้ขอบวันรายงาน
        เดียวกับรายงานนับเก๊ะ คือ 07:00 ถึง 08:00 ของวันถัดไป
        """
        if inspection_camera is None:
            raise HTTPException(404, 'inspection_camera_not_registered')
        key = date or shift_report.today_key()
        start, end = shift_report.report_window(key)
        journal = getattr(pipeline, 'journal', None)
        if journal is None:
            report = magnet.summarise([], {}, key)
            report['storage'] = 'unavailable'
            return report
        try:
            found = journal.inspection_payloads(start, end, camera_id=inspection_camera.camera_id)
            coverage = journal.coverage(
                inspection_camera.camera_id,
                magnet.round_key_of(start),
                magnet.round_key_of(end - 1),
            )
        except (ValueError, sqlite3.Error):
            raise HTTPException(503, 'event_storage_unavailable')
        report = magnet.summarise(found, coverage, key)
        report['camera_id'] = inspection_camera.camera_id
        report['storage'] = 'ok'
        return report

    @app.get('/api/v1/final-pond/evidence/{name}')
    def final_pond_evidence(name: str):
        """ภาพหลักฐานตอนแจ้งเตือนไม่มีคนในพื้นที่ — ชื่อไฟล์มาจาก payload ของเหตุการณ์"""
        path = pond_ai.evidence_path(name)
        if path is None:
            raise HTTPException(404, 'evidence_not_found')
        return FileResponse(path, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=86400'})

    @app.get('/api/v1/stations/{station_id}/ai-status')
    def station_ai_status(station_id: str):
        matched = cameras_for_station(station_id, camera_registry)
        statuses = [public_camera_status(camera) for camera in matched]
        if not statuses:
            data_status = 'not_installed'
        elif any(item['data_status'] == 'live' for item in statuses):
            data_status = 'live'
        elif all(item['data_status'] == 'not_installed' for item in statuses):
            data_status = 'not_installed'
        else:
            data_status = 'offline'
        return {
            'station_id': station_id,
            'data_status': data_status,
            'cameras': statuses,
        }

    @app.get('/api/v1/events')
    def ai_events(
        cursor: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
        station_id: str | None = Query(default=None, pattern=r'^[A-Za-z0-9_-]{1,100}$'),
    ):
        journal = getattr(pipeline, 'journal', None)
        if journal is None:
            return {'items': [], 'next_cursor': cursor, 'has_more': False}
        try:
            return journal.events(after=cursor, limit=limit, station_id=station_id)
        except (ValueError, sqlite3.Error):
            raise HTTPException(503, 'event_storage_unavailable')

    @app.get('/api/v1/rack-count/daily')
    def rack_count_daily(
        date: str | None = Query(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
        station_id: str | None = Query(default=None, pattern=r'^[A-Za-z0-9_-]{1,100}$'),
    ):
        """ยอดนับเก๊ะของวันรายงานหนึ่งวัน แยกรายชั่วโมงและรายกะ

        วันรายงานคือ 07:00 ของวันที่ขอ ถึง 08:00 ของวันถัดไป ตรงกับนิยามกะที่
        PCC ใช้อยู่ ทั้งสองหน้าจอจึงได้ตัวเลขเดียวกันเสมอ
        """
        key = date or shift_report.today_key()
        start, end = shift_report.report_window(key)
        journal = getattr(pipeline, 'journal', None)
        if journal is None:
            # ไม่มีที่เก็บเหตุการณ์ = ตอบโครงว่างพร้อมบอกเหตุผล ดีกว่าตอบ 503
            # เพราะหน้าจอยังต้องวาดตารางชั่วโมงให้เห็นว่าระบบยังอยู่
            summary = shift_report.summarise([], key)
            summary['storage'] = 'unavailable'
            return summary
        try:
            times = journal.count_times(start, end, station_id=station_id)
        except (ValueError, sqlite3.Error):
            raise HTTPException(503, 'event_storage_unavailable')
        summary = shift_report.summarise(times, key)
        summary['storage'] = 'ok'
        return summary

    @app.post('/api/rack-counter/reset')
    def reset_counter():
        return pipeline.reset_count()

    @app.get('/')
    def monitor():
        return FileResponse(Path(__file__).parent / 'frontend/index_phase3.html')

    @app.get('/monitor.js')
    def script():
        return FileResponse(Path(__file__).parent / 'frontend/monitor_phase3.js',media_type='text/javascript')

    @app.get('/counting.js')
    def counting_script():
        return FileResponse(Path(__file__).parent / 'frontend/counting.js',media_type='text/javascript')

    @app.get('/monitor.css')
    def stylesheet():
        return FileResponse(Path(__file__).parent / 'frontend/monitor.css',media_type='text/css')

    @app.get('/api/live/frame')
    def preview_frame():
        frame_id, jpeg = pipeline.preview()
        if not jpeg or not pipeline.snapshot()['running']:
            raise HTTPException(503,'camera_not_ready')
        return Response(jpeg,media_type='image/jpeg',headers={'Cache-Control':'no-store','X-Frame-ID':str(frame_id)})

    @app.get('/api/v1/cameras/{camera_id}/frame')
    def camera_preview_frame(camera_id: str):
        if camera_id != pond_camera_id or camera_id not in camera_by_id:
            raise HTTPException(404, 'camera_not_found')
        if not pond_preview.enabled:
            raise HTTPException(503, 'preview_not_configured')
        jpeg = pond_preview.frame()
        if jpeg is None:
            raise HTTPException(503, 'camera_not_ready')
        return Response(jpeg, media_type='image/jpeg', headers={'Cache-Control': 'no-store'})

    @app.get('/api/v1/cameras/{camera_id}/ai-frame')
    def camera_ai_preview_frame(camera_id: str):
        if camera_id != pond_camera_id or camera_id not in camera_by_id:
            raise HTTPException(404, 'camera_not_found')
        if not pond_ai.enabled:
            raise HTTPException(503, 'pee_model_not_configured')
        jpeg = pond_ai.cached_frame()
        if jpeg is None:
            raise HTTPException(503, 'ai_preview_not_ready')
        return Response(jpeg, media_type='image/jpeg', headers={'Cache-Control': 'no-store'})

    @app.get('/api/recordings')
    def recordings():
        try:
            return pipeline.recorder.history()
        except Exception:
            raise HTTPException(503,'recording_storage_unavailable')

    @app.post('/api/recordings/start')
    def start_recording(body: RecordingRequest):
        try:
            return pipeline.recorder.start(body.duration_minutes,body.name,body.annotated)
        except RuntimeError as exc:
            raise HTTPException(409,str(exc))
        except Exception:
            raise HTTPException(503,'recording_storage_unavailable')

    @app.get('/api/recordings/{clip_id}/file/{kind}')
    def download(clip_id: str, kind: str):
        try:
            path = pipeline.recorder.storage().file(clip_id,kind)
            return FileResponse(path,filename=path.name,media_type='application/json' if kind=='metadata' else 'video/mp4')
        except (ValueError,KeyError):
            raise HTTPException(404,'file_not_found')
        except RuntimeError:
            raise HTTPException(409,'clip_not_finalized')

    @app.get('/api/recording-schedules')
    def schedules():
        try:
            return pipeline.recording_control.jobs()
        except Exception:
            raise HTTPException(503,'schedule_storage_unavailable')

    @app.post('/api/recording-schedules')
    def schedule(body: ScheduleRequest):
        if body.start_at.tzinfo is None:
            raise HTTPException(422,'start_at_requires_timezone')
        try:
            return pipeline.recording_control.add(body.start_at.timestamp(),body.model_dump(exclude={'start_at'}))
        except ValueError as exc:
            raise HTTPException(422,str(exc))
        except Exception:
            raise HTTPException(503,'schedule_storage_unavailable')

    @app.delete('/api/recording-schedules/{identity}')
    def cancel_schedule(identity: str):
        try:
            pipeline.recording_control.cancel(identity)
            return {'status':'cancelled'}
        except ValueError:
            raise HTTPException(409,'schedule_not_pending')
        except Exception:
            raise HTTPException(503,'schedule_storage_unavailable')

    @app.get('/api/recording-policy')
    def policy():
        try:
            return pipeline.recording_control.policy()
        except Exception:
            raise HTTPException(503,'policy_storage_unavailable')

    @app.post('/api/recording-policy')
    def set_policy(body: EventPolicy):
        try:
            return pipeline.recording_control.set_policy(body.model_dump())
        except Exception:
            raise HTTPException(503,'policy_storage_unavailable')

    @app.post('/api/recordings/stop')
    def stop_recording():
        try:
            return pipeline.recorder.stop()
        except RuntimeError:
            raise HTTPException(503,'recording_stop_timeout')

    @app.delete('/api/recordings/{clip_id}')
    def archive_recording(clip_id: str):
        try:
            pipeline.recorder.archive(clip_id)
            return {'status':'archived','recoverable':True}
        except ValueError:
            raise HTTPException(400,'invalid_clip_id')
        except KeyError:
            raise HTTPException(404,'clip_not_found')
        except RuntimeError as exc:
            raise HTTPException(409,str(exc))
        except Exception:
            raise HTTPException(503,'recording_storage_unavailable')

    @app.get('/api/live/stream')
    @app.get('/api/rack-counter/stream')
    async def preview(request: Request):
        async def frames():
            previous = -1
            while not await request.is_disconnected():
                frame_id, jpeg = pipeline.preview()
                if jpeg and frame_id != previous and pipeline.snapshot()['running']:
                    previous = frame_id
                    yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'+jpeg+b'\r\n'
                await asyncio.sleep(.05)
        return StreamingResponse(frames(),media_type='multipart/x-mixed-replace; boundary=frame',headers={'Cache-Control':'no-store'})

    @app.websocket('/ws/rack-counter')
    async def websocket(ws: WebSocket):
        origin = ws.headers.get('origin')
        if origin and origin not in cfg.origins:
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            if cfg.token:
                message = await asyncio.wait_for(ws.receive_json(),timeout=5)
                if not isinstance(message, dict) or not authorized('Bearer '+str(message.get('token',''))):
                    await ws.close(code=1008)
                    return
            while True:
                # Each client samples latest state; no AI-side queues or video payloads.
                await asyncio.wait_for(ws.send_json(pipeline.snapshot()),timeout=2)
                await asyncio.sleep(.2)
        except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError, ValueError):
            try:
                await ws.close(code=1008)
            except RuntimeError:
                pass
    return app


app = create_app()
