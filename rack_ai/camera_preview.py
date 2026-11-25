"""Low-rate, read-only CCTV capture independent of the rack inference loop.

The RTSP URL stays server-side. One capture thread serves both the background
PEE worker and viewers. Without a background worker it remains on-demand.
"""

import logging
import threading
import time
from collections import deque


log = logging.getLogger('vision.preview')


class CameraPreview:
    def __init__(self, source: str, width: int = 960, fps: float = 20.0,
                 background_fps: float = 10.0):
        self.source = source
        self.enabled = bool(source)
        self.width = width
        self.interval = 1.0 / fps
        self.background_interval = 1.0 / background_fps
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_lock = threading.Lock()
        self._always_on = False
        self._last_request = 0.0
        self._latest: tuple[float, bytes] | None = None
        # สถิติการรับภาพจาก DVR — แยกจาก FPS ที่ส่งหน้าเว็บ/AI เพื่อใช้เทียบกับกล้อง 9
        # ว่าภาพกระตุกเพราะเครือข่าย/เครื่อง (เป็นทั้งสองกล้อง) หรือเฉพาะกล้องใดกล้องหนึ่ง
        self._grabs: deque[float] = deque(maxlen=400)
        self._connected = False
        self._connections = 0
        self._last_grab = 0.0
        self._resolution: str | None = None

    def frame(self) -> bytes | None:
        if not self.enabled:
            return None
        self._last_request = time.monotonic()
        self._ensure_started()
        latest = self.latest()
        return latest[1] if latest else None

    def start(self):
        """Keep the single DVR reader alive even without browser requests."""
        if self.enabled:
            self._always_on = True
            self._ensure_started()

    def _ensure_started(self):
        with self._thread_lock:
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._run, name='final-pond-preview', daemon=True)
                self._thread.start()

    def latest(self) -> tuple[float, bytes] | None:
        """Read the current frame without changing capture demand."""
        latest = self._latest
        return latest if latest and time.monotonic() - latest[0] < 5 else None

    def close(self):
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _run(self):
        import cv2

        while not self._stop.is_set():
            if not self._always_on and time.monotonic() - self._last_request > 15:
                self._latest = None
                return
            try:
                capture = cv2.VideoCapture(
                    self.source, cv2.CAP_FFMPEG,
                    [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000],
                )
            except (TypeError, cv2.error):
                capture = cv2.VideoCapture(self.source)
            if not capture.isOpened():
                capture.release()
                self._latest = None
                self._stop.wait(3)
                continue
            log.info('preview_source_connected camera=final-pond-cam-01')
            self._connected = True
            self._connections += 1
            last_encoded = 0.0
            try:
                while not self._stop.is_set() and (self._always_on or time.monotonic() - self._last_request <= 15):
                    # Grab every source packet to stay at the live edge, but only
                    # convert a frame to pixels when it is time to publish it.
                    # read() converted all ~25 DVR frames even at a 10 FPS preview.
                    ok = capture.grab()
                    if not ok:
                        self._latest = None
                        break
                    now = time.monotonic()
                    self._last_grab = now
                    self._grabs.append(now)
                    # The always-on AI needs only a few frames per second. Keep
                    # the old preview rate for direct raw-video viewers.
                    publish_interval = (self.interval if now - self._last_request <= 15
                                        else max(self.interval, self.background_interval))
                    if now - last_encoded < publish_interval:
                        continue
                    ok, frame = capture.retrieve()
                    if not ok:
                        self._latest = None
                        break
                    height, width = frame.shape[:2]
                    self._resolution = f'{width}x{height}'
                    if width > self.width:
                        frame = cv2.resize(frame, (self.width, round(height * self.width / width)))
                    encoded, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    if encoded:
                        self._latest = (now, buffer.tobytes())
                        last_encoded = now
            finally:
                self._connected = False
                capture.release()
            self._stop.wait(1)

    def stats(self, window: float = 3.0) -> dict:
        """FPS ที่รับจาก DVR จริงในช่วงล่าสุด ไม่ใช่ FPS ที่ส่งหน้าเว็บหรือ AI"""
        now = time.monotonic()
        recent = [moment for moment in tuple(self._grabs) if now - moment <= window]
        fps = ((len(recent) - 1) / (recent[-1] - recent[0])
               if len(recent) > 1 and recent[-1] > recent[0] else 0.0)
        age = now - self._last_grab if self._last_grab else None
        # ช่องว่างนานสุดระหว่างเฟรมใน 10 วินาทีล่าสุด บอกอาการกระตุกได้ดีกว่า FPS เฉลี่ย
        last10 = [moment for moment in tuple(self._grabs) if now - moment <= 10]
        longest = max((b - a for a, b in zip(last10, last10[1:])), default=0.0)
        return {
            'connected': self._connected and age is not None and age < 5,
            'source_fps': round(fps, 2),
            'last_frame_age': round(age, 2) if age is not None else None,
            'reconnects': max(0, self._connections - 1),
            'resolution': self._resolution,
            'longest_gap_ms': round(longest * 1000),
        }
