import copy
import hashlib
import logging
import threading
import time
from datetime import datetime, timezone

import cv2

from .camera import RTSPReader
from .config import Settings
from .counter import RackCounter
from .detector import RackDetector
from .preview_filter import select_preview_tracks
from .recording import OpenCVRecorder
from .streamcopy import FFmpegRecorder
from .recording_control import RecordingControl
import shutil
from .runtime import CountJournal
from pathlib import Path

log = logging.getLogger('rack.service')


def model_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class RackService:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.camera = RTSPReader(cfg.source, cfg.retry)
        use_copy = (cfg.record_mode != 'opencv' and cfg.record_source and cfg.record_source != cfg.source
                    and shutil.which('ffmpeg') and shutil.which('ffprobe'))
        if cfg.record_mode == 'copy' and not use_copy:
            raise ValueError('Copy mode needs a distinct recording stream and ffmpeg/ffprobe')
        self.record_camera = (RTSPReader(cfg.record_source, cfg.retry)
                              if not use_copy and cfg.record_source and cfg.record_source != cfg.source else self.camera)
        recorder_class = FFmpegRecorder if use_copy else OpenCVRecorder
        extra = {'source_url':cfg.record_source} if use_copy else {}
        self.recorder = recorder_class(self.record_camera.buffer,cfg.record_root,cfg.stale,cfg.record_fps,
                                       provider=self.recording_observation,**extra)
        self.recording_control = RecordingControl(self.recorder,self.recording_observation)
        self.counter = RackCounter(cfg)
        self.counter_lock = threading.Lock()
        self.journal = CountJournal(cfg.record_root/'runtime')
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._infer, name='rack-inference', daemon=True)
        self.started = time.monotonic()
        self.jpeg = None
        self.result_at = 0.0
        self.result = {'frame_id': -1, 'count': 0, 'rack_count': 0, 'tracks': [], 'running': False,
                       'error': 'starting', 'lastEvent': None, 'inference_fps': 0, 'total_detections': 0,
                       'model': cfg.model.name}

    def start(self):
        self.counter.count = self.journal.start()
        with self.lock:
            self.result.update(count=self.counter.count,rack_count=self.counter.count)
        try:
            self.recorder.storage().recover()
        except Exception:
            log.error('recording_recovery_failed')
        self.camera.start()
        if self.record_camera is not self.camera:
            self.record_camera.start()
        self.thread.start()
        self.recording_control.start()

    def close(self):
        self.stop.set()
        self.recording_control.close()
        try:
            self.recorder.stop()
        except RuntimeError:
            log.error('recorder_shutdown_timeout')
        if self.record_camera is not self.camera:
            self.record_camera.close()
        self.camera.close()
        self.thread.join(timeout=15)
        self.journal.close()
        if self.thread.is_alive():
            log.error('inference_shutdown_timeout')

    def snapshot(self):
        with self.lock:
            result = copy.deepcopy(self.result)
            result_age = time.monotonic() - self.result_at
        camera = self.camera.status(self.cfg.stale)
        result.update(type='frame_result', camera=camera, uptime=time.monotonic()-self.started)
        result['running'] = result['running'] and camera['connected'] and not camera['stale']
        result['running'] = result['running'] and result_age <= self.cfg.stale
        result['result_age_seconds'] = round(result_age,2) if self.result_at else None
        result['fps'] = {'camera': camera['fps'], 'inference': result['inference_fps']}
        result['active_tracks'] = len(result['tracks']) if result['running'] else 0
        result['recording'] = self.recorder.snapshot()
        result['recording']['controller_error'] = self.recording_control.error
        result['recording']['backend'] = type(self.recorder).__name__
        result['counter_storage_error'] = self.journal.error
        return result

    def recording_observation(self):
        with self.lock:
            state = copy.deepcopy(self.result)
            state['_monotonic'] = self.result_at
            return state,self.jpeg

    def preview(self):
        with self.lock:
            return self.result['frame_id'], self.jpeg

    def reset_count(self):
        """Reset the live and persisted counter without restarting the camera."""
        with self.counter_lock:
            self.counter.count = 0
            self.counter.last_event = None
            self.counter.last_at = -float('inf')
            self.counter.reset_tracks()
        with self.lock:
            self.result.update(count=0, rack_count=0, lastEvent=None, tracks=[])
        self.journal.submit(0, None)
        return {'rack_count': 0, 'status': 'reset'}

    def _infer(self):
        try:
            hash_before_load = model_sha256(self.cfg.model)
            detector = RackDetector(self.cfg)
            loaded_model_sha256 = model_sha256(self.cfg.model)
            if loaded_model_sha256 != hash_before_load:
                raise RuntimeError('model file changed while loading')
            log.info('model_loaded device=%s fp16=%s', detector.device, detector.half)
        except Exception as exc:
            with self.lock:
                self.result.update(error='model_load_failed', running=False)
            log.error('model_load_failed error_type=%s', type(exc).__name__)
            return
        last_id, generation = -1, -1
        total = 0
        completed_at = None
        while not self.stop.is_set():
            began = time.monotonic()
            packet = self.camera.buffer.get(last_id)
            if packet is None or began - packet.monotonic > self.cfg.stale:
                self.stop.wait(.05)
                continue
            last_id = packet.frame_id
            try:
                if generation != packet.generation:
                    detector.reset()
                    self.counter.reset_tracks()
                    generation = packet.generation
                tracks = detector.infer(packet.frame)
                with self.counter_lock:
                    before = self.counter.count
                    tracks = self.counter.update(tracks, packet.height, packet.timestamp)
                    current_count = self.counter.count
                    current_event = self.counter.last_event
                if before != current_count:
                    log.info('rack_counted count=%s', current_count)
                    durable_event=dict(current_event,model_version=self.cfg.model.name,
                                       model_sha256=loaded_model_sha256,rule_version='rack-count-v1')
                    self.journal.submit(current_count,durable_event)
                total += len(tracks)
                frame = packet.frame
                visible_tracks = select_preview_tracks(tracks, packet.height*self.cfg.line)
                for d in visible_tracks:
                    x1,y1,x2,y2 = map(int, d['bbox'])
                    color = (0,0,255) if d['counted'] else (0,255,0)
                    cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)
                    cv2.putText(frame, f"ID {d['track_id']} {d['confidence']:.2f}", (x1,max(25,y1-5)), 0,.7,color,2)
                y = int(packet.height*self.cfg.line)
                cv2.line(frame,(0,y),(packet.width,y),(255,0,255),2)
                cv2.putText(frame,f'RACK OUT: {current_count}',(20,50),0,1,(0,255,255),2)
                if self.recorder.snapshot()['active']:
                    cv2.putText(frame,'REC RAW',(20,85),0,.7,(0,0,255),2)
                ok, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY,80])
                now = time.monotonic()
                measured_fps = 0 if completed_at is None else 1 / max(now-completed_at, .001)
                completed_at = now
                with self.lock:
                    self.result_at = time.monotonic()
                    if ok:
                        self.jpeg = jpg.tobytes()
                    self.result.update(frame_id=last_id, timestamp=datetime.fromtimestamp(packet.timestamp,timezone.utc).isoformat(),
                        count=current_count, rack_count=current_count, tracks=tracks, running=True,
                        preview_tracks=visible_tracks, preview_suppressed=len(tracks)-len(visible_tracks),
                        error=None, lastEvent=current_event, total_detections=total,
                        inference_fps=round(measured_fps,2),
                        width=packet.width,height=packet.height,model=self.cfg.model.name,device=str(detector.device))
            except Exception as exc:
                with self.lock:
                    self.result.update(error='inference_failed',running=False)
                log.error('inference_failed error_type=%s',type(exc).__name__)
                self.stop.wait(1)
            self.stop.wait(max(0,1/self.cfg.inference_fps-(time.monotonic()-began)))
