"""Bounded, shared-buffer RAW recording. No VideoCapture is opened here."""
import json
import logging
import re
import shutil
import sqlite3
import threading
import time
import uuid
import math
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import cv2

log = logging.getLogger('rack.recording')


class ClipStore:
    """Small persistence boundary; replacement repositories can use PostgreSQL."""
    def __init__(self, root: Path):
        self.root = root.resolve()
        (self.root / 'raw').mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS recordings (id TEXT PRIMARY KEY, metadata TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / 'recordings.sqlite3', timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, value: dict):
        content = json.dumps(value, ensure_ascii=False)
        # Atomic sidecar replacement; source and destination are always under root.
        temporary = self.root / (value['clip_id'] + '.json.tmp')
        temporary.write_text(content, encoding='utf-8')
        temporary.replace(self.root / (value['clip_id'] + '.json'))
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO recordings VALUES (?,?)', (value['clip_id'], content))

    def list(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT metadata FROM recordings ORDER BY json_extract(metadata,'$.start_time') DESC LIMIT 500")]

    def recover(self):
        """Called once at service startup, never while another recorder is active."""
        with self.connect() as db:
            values = [json.loads(r[0]) for r in db.execute('SELECT metadata FROM recordings')]
        for value in values:
            if value['status'] == 'recording':
                value.update(status='interrupted', error='service_interrupted')
                self.save(value)

    def get(self, clip_id):
        if not re.fullmatch(r'clip_[0-9a-f]{32}', clip_id):
            raise ValueError('invalid_clip_id')
        with self.connect() as db:
            row = db.execute('SELECT metadata FROM recordings WHERE id=?', (clip_id,)).fetchone()
        if row is None:
            raise KeyError(clip_id)
        return json.loads(row[0])

    def file(self, clip_id, kind='raw'):
        value = self.get(clip_id)
        if value['status'] == 'recording':
            raise RuntimeError('clip_not_finalized')
        key = {'raw':'file_path', 'annotated':'annotated_path', 'metadata':None}.get(kind, 'invalid')
        if key == 'invalid':
            raise ValueError('invalid_file_kind')
        relative = clip_id+'.json' if key is None else value.get(key)
        if not relative:
            raise KeyError(kind)
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('invalid_file_path')
        if not path.is_file():
            raise KeyError(kind)
        return path

    def archive(self, clip_id: str):
        if not re.fullmatch(r'clip_[0-9a-f]{32}', clip_id):
            raise ValueError('invalid_clip_id')
        with self.connect() as db:
            row = db.execute('SELECT metadata FROM recordings WHERE id=?', (clip_id,)).fetchone()
        if row is None:
            raise KeyError(clip_id)
        value = json.loads(row[0])
        value['status'] = 'archived'  # recoverable deletion: preserve bytes for audit
        self.save(value)


class OpenCVRecorder:
    """One clip at a time, fixed-rate sampling. Duplicates explicitly reported."""
    def __init__(self, buffer, root: Path, stale: float = 5, fps: float = 10, provider=None):
        self.buffer, self.root, self.stale, self.fps = buffer, root, stale, fps
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.state = {'active': False, 'clip_id': None, 'error': None}
        self.store = None  # storage failure does not prevent camera/inference startup
        self.provider = provider
        self.storage_lock = threading.Lock()

    def storage(self):
        with self.storage_lock:
            if self.store is None:
                self.store = ClipStore(self.root)
            return self.store

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def start(self, duration_minutes: float, name: str, annotated=False, source='manual'):
        if not math.isfinite(duration_minutes) or not 0 < duration_minutes <= 60:
            raise ValueError('invalid_duration')
        if not re.fullmatch(r'[\w .-]{1,100}', name) or source not in ('manual','scheduled','event'):
            raise ValueError('invalid_recording_options')
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise RuntimeError('recording_already_active')
            packet = self.buffer.get()
            if packet is None or time.monotonic()-packet.monotonic > self.stale:
                raise RuntimeError('camera_not_ready')
            self.storage()
            if shutil.disk_usage(self.store.root).free < 1024**3:
                raise RuntimeError('disk_space_below_1GB')
            clip_id = 'clip_' + uuid.uuid4().hex
            self.stop_event.clear()
            self.state = {'active':True,'clip_id':clip_id,'elapsed_seconds':0,
                          'duration_seconds':duration_minutes*60,'error':None}
            self.thread = threading.Thread(target=self._run,
                args=(clip_id, duration_minutes*60, name, packet, annotated, source),name='rack-recorder',daemon=True)
            self.thread.start()
            return dict(self.state)

    def stop(self):
        self.stop_event.set()
        thread = self.thread
        if thread:
            thread.join(timeout=30)
            if thread.is_alive():
                raise RuntimeError('recording_stop_timeout')
        return self.snapshot()

    def history(self):
        return self.storage().list()

    def archive(self, clip_id):
        with self.lock:
            if self.state['active'] and self.state['clip_id'] == clip_id:
                raise RuntimeError('cannot_archive_active_clip')
        self.storage().archive(clip_id)

    def _run(self, clip_id, duration, name, first, annotated=False, source='manual'):
        started = time.monotonic()
        value = {'clip_id':clip_id,'camera':'Camera09','name':name,'source':source,
                 'start_time':datetime.now(timezone.utc).isoformat(),'status':'recording',
                 'requested_duration_seconds':duration,'fps':self.fps,
                 'resolution':f'{first.width}x{first.height}','file_path':f'raw/{clip_id}.mp4',
                 'raw':True,'encoder':'opencv_mp4v','frames_written':0,'duplicate_frames':0,
                 'rack_events':0,'average_confidence':None,
                 'note':'AI statistics sampled in wall-clock recording window; dual streams are not frame-synchronized.'}
        if getattr(self,'fallback_note',None):
            value['fallback'] = self.fallback_note
        audit = RecordingAudit(self.provider, self.store.root, clip_id, annotated)
        writer = None
        error = None
        try:
            self.store.save(value)
            writer = cv2.VideoWriter(str(self.store.root / value['file_path']),
                                    cv2.VideoWriter_fourcc(*'mp4v'),self.fps,(first.width,first.height))
            if not writer.isOpened():
                raise RuntimeError('writer_unavailable')
            previous = -1
            log.info('recording_started clip_id=%s seconds=%s',clip_id,duration)
            while not self.stop_event.is_set() and time.monotonic()-started < duration:
                packet = self.buffer.get()
                if packet is None or time.monotonic()-packet.monotonic > self.stale:
                    raise RuntimeError('camera_stale')
                if packet.generation != first.generation or packet.frame.shape != first.frame.shape:
                    raise RuntimeError('camera_reconnected_or_resolution_changed')
                if shutil.disk_usage(self.store.root).free < 100*1024**2:
                    raise RuntimeError('disk_space_low')
                writer.write(packet.frame)
                audit.sample()
                value['duplicate_frames'] += int(packet.frame_id == previous)
                previous = packet.frame_id
                value['frames_written'] += 1
                elapsed = time.monotonic()-started
                with self.lock:
                    self.state['elapsed_seconds'] = round(elapsed,2)
                # Never queue old frames. Abort if encoder cannot maintain timeline.
                deadline = started + value['frames_written']/self.fps
                if time.monotonic()-deadline > 1:
                    raise RuntimeError('encoder_too_slow')
                self.stop_event.wait(max(0,deadline-time.monotonic()))
            value['status'] = 'stopped' if self.stop_event.is_set() else 'recorded'
        except Exception as exc:
            error = str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
            value['status'] = 'failed'
            log.error('recording_failed clip_id=%s error_type=%s',clip_id,type(exc).__name__)
        finally:
            if writer:
                writer.release()
            value.update(audit.close())
            if writer and value['frames_written']:
                check = cv2.VideoCapture(str(self.store.root/value['file_path']))
                try:
                    readable, _ = check.read()
                    if not readable:
                        error, value['status'] = 'clip_unreadable', 'failed'
                finally:
                    check.release()
            value.update(end_time=datetime.now(timezone.utc).isoformat(),
                         duration_seconds=time.monotonic()-started,
                         video_duration_seconds=value['frames_written']/self.fps,error=error)
            try:
                self.store.save(value)
            except Exception:
                error = 'metadata_save_failed'
                value['status'] = 'failed'
                log.error('recording_metadata_save_failed clip_id=%s',clip_id)
            with self.lock:
                self.state.update(active=False,error=error,status=value['status'])
            log.info('recording_stopped clip_id=%s status=%s',clip_id,value['status'])


class RecordingAudit:
    """Sample latest inference, bounded aggregates and optional review-only video."""
    def __init__(self, provider, root, clip_id, annotated):
        self.provider, self.root, self.clip_id = provider, root, clip_id
        self.annotated = annotated
        self.writer = None
        self.last_frame = -1
        self.last_count = None
        self.events = self.samples = self.low = self.annotated_frames = 0
        self.score_sum = 0.0
        self.error = None
        self.path = None
        self.started = time.monotonic()
        self.next_video = self.started

    def sample(self):
        if self.provider is None:
            return
        state, jpeg = self.provider()
        if time.monotonic()-state.get('_monotonic',0) > 5:
            return
        count = state.get('rack_count',0)
        if self.last_count is not None:
            self.events += max(0,count-self.last_count)
        self.last_count = count
        if state['frame_id'] != self.last_frame:
            for track in state.get('tracks',[]):
                confidence = track['confidence']
                self.samples += 1
                self.score_sum += confidence
                self.low += int(confidence < .7)
            self.last_frame = state['frame_id']
        if self.annotated and jpeg and self.error is None and time.monotonic() >= self.next_video:
            import numpy as np
            frame = cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR)
            if frame is None:
                self.error = 'annotated_decode_failed'
                return
            if self.writer is None:
                (self.root/'annotated').mkdir(exist_ok=True)
                self.path = f'annotated/{self.clip_id}_annotated.mp4'
                self.size = (frame.shape[1],frame.shape[0])
                self.writer = cv2.VideoWriter(str(self.root/self.path),cv2.VideoWriter_fourcc(*'mp4v'),5,self.size)
                if not self.writer.isOpened():
                    self.error = 'annotated_writer_failed'
                    return
            if (frame.shape[1],frame.shape[0]) != self.size:
                self.error = 'annotated_resolution_changed'
                return
            self.writer.write(frame)
            self.annotated_frames += 1
            self.next_video = time.monotonic()+.19

    def close(self):
        if self.writer:
            self.writer.release()
        return dict(rack_events=self.events, average_confidence=self.score_sum/self.samples if self.samples else None,
                    detection_observations=self.samples,low_confidence_detections=self.low,
                    annotated_path=self.path,annotated_error=self.error,annotated_frames=self.annotated_frames,
                    annotated_timing='sampled 5 FPS review only; gaps are not filled')
