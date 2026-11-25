"""One VideoCapture owner per source; consumers receive frame copies."""
import logging
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

log = logging.getLogger('rack.camera')


@dataclass(frozen=True)
class FramePacket:
    frame_id: int
    timestamp: float
    monotonic: float
    generation: int
    frame: np.ndarray

    @property
    def width(self) -> int:
        return self.frame.shape[1]

    @property
    def height(self) -> int:
        return self.frame.shape[0]


class FrameBuffer:
    def __init__(self):
        self.lock = threading.Lock()
        self.packet: FramePacket | None = None

    def put(self, packet: FramePacket) -> None:
        with self.lock:
            self.packet = packet

    def get(self, after: int = -1) -> FramePacket | None:
        with self.lock:
            p = self.packet
            if p is None or p.frame_id <= after:
                return None
            return FramePacket(p.frame_id, p.timestamp, p.monotonic, p.generation, p.frame.copy())


class RTSPReader:
    def __init__(self, source: str, retry: float = 3):
        self.source, self.retry = source, retry
        self.buffer = FrameBuffer()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name='rtsp-reader', daemon=True)
        self.lock = threading.Lock()
        self.state = {'connected': False, 'fps': 0.0, 'last_frame_at': 0.0, 'error': 'not_started'}

    def start(self):
        self.thread.start()

    def status(self, stale: float) -> dict:
        with self.lock:
            value = dict(self.state)
        value['stale'] = time.monotonic() - value.pop('last_frame_at') > stale
        return value

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=12)
        if self.thread.is_alive():
            log.error('camera_shutdown_timeout')

    def _run(self):
        frame_id, generation = 0, 0
        failures, last_warning = 0, -float('inf')
        while not self.stop_event.is_set():
            cap = None
            try:
                if not self.source:
                    raise RuntimeError('missing_source')
                if self.source.startswith(('rtsp://', 'rtsps://')):
                    cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG, [
                        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 4000,
                        cv2.CAP_PROP_READ_TIMEOUT_MSEC, 4000])
                else:
                    cap = cv2.VideoCapture(int(self.source) if self.source.isdigit() else self.source)
                if not cap.isOpened():
                    raise RuntimeError('camera_unavailable')
                generation += 1
                if failures:
                    log.info('camera_reconnected generation=%s attempts=%s', generation, failures)
                else:
                    log.info('camera_connected generation=%s', generation)
                failures, last_warning = 0, -float('inf')
                ticks, since = 0, time.monotonic()
                file_source = not self.source.startswith(('rtsp://', 'rtsps://')) and not self.source.isdigit()
                interval = 1 / max(1, cap.get(cv2.CAP_PROP_FPS)) if file_source else 0
                while not self.stop_event.is_set():
                    began = time.monotonic()
                    ok, frame = cap.read()
                    if not ok:
                        raise RuntimeError('camera_disconnected')
                    captured_at = time.monotonic()
                    frame_id += 1
                    ticks += 1
                    self.buffer.put(FramePacket(frame_id, time.time(), captured_at, generation, frame))
                    elapsed = began - since
                    with self.lock:
                        self.state.update(connected=True, error=None, last_frame_at=captured_at)
                        if elapsed >= 1:
                            self.state['fps'] = round(ticks / elapsed, 2)
                            ticks, since = 0, began
                    if file_source:
                        self.stop_event.wait(max(0, interval - (time.monotonic() - began)))
            except Exception as exc:
                # Never log exception text: backend errors can include RTSP credentials.
                failures += 1
                now = time.monotonic()
                if failures == 1 or now - last_warning >= 60:
                    log.warning('camera_disconnected error_type=%s retry_attempt=%s', type(exc).__name__, failures)
                    last_warning = now
                else:
                    log.debug('camera_reconnect_pending retry_attempt=%s', failures)
                with self.lock:
                    self.state.update(connected=False, error='camera_unavailable', fps=0)
            finally:
                if cap is not None:
                    cap.release()  # released only by the owning reader
            self.stop_event.wait(self.retry)
