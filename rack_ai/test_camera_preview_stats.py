"""สถิติสัญญาณภาพของกล้องบ่อสุดท้าย — ทดสอบโดยไม่ต้องมีกล้อง"""
import time

from rack_ai.camera_preview import CameraPreview


def feed(preview, times):
    for moment in times:
        preview._grabs.append(moment)
    preview._last_grab = times[-1]


def test_fps_is_measured_from_frames_received_from_the_dvr():
    preview = CameraPreview('rtsp://example.invalid/stream')
    now = time.monotonic()
    feed(preview, [now - 2 + i / 25 for i in range(51)])
    preview._connected = True
    stats = preview.stats()
    assert 24 <= stats['source_fps'] <= 26
    assert stats['connected'] is True
    assert stats['longest_gap_ms'] <= 50


def test_a_stall_shows_up_as_a_long_gap():
    preview = CameraPreview('rtsp://example.invalid/stream')
    now = time.monotonic()
    feed(preview, [now - 4 + i / 25 for i in range(25)] + [now - 1.5 + i / 25 for i in range(20)])
    preview._connected = True
    assert preview.stats()['longest_gap_ms'] >= 1400


def test_no_frames_means_not_connected_and_zero_fps():
    stats = CameraPreview('rtsp://example.invalid/stream').stats()
    assert stats['connected'] is False and stats['source_fps'] == 0 and stats['last_frame_age'] is None


def test_stale_frames_count_as_disconnected():
    preview = CameraPreview('rtsp://example.invalid/stream')
    feed(preview, [time.monotonic() - 9])
    preview._connected = True
    assert preview.stats()['connected'] is False
