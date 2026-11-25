import tempfile
import unittest
import time
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from rack_ai.final_pond.pilot import (
    PRESENCE_TASK_ID, PeePreview, WorkerFilter, draw_area_detections, draw_detections, workers_in_pond,
)
from rack_ai.final_pond.presence import PresenceAlert, PresenceMonitor
from rack_ai.final_pond.vision import Box, Detection


class FakeBoxes:
    """Minimal stand-in for an Ultralytics result's boxes."""
    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        for (x1, y1, x2, y2), cls, conf in self.rows:
            yield SimpleNamespace(xyxy=[[x1, y1, x2, y2]], cls=[cls], conf=[conf])


class PersonModel:
    """COCO-like model: class 0 is person, plus other classes the area mode must skip."""
    names = {0: 'person', 2: 'car', 56: 'chair'}

    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def predict(self, *_args, **kwargs):
        self.calls.append(kwargs)
        return [SimpleNamespace(boxes=FakeBoxes(self.rows), names=self.names)]


class PeePilotTests(unittest.TestCase):
    def test_presence_waits_five_minutes_and_pauses_for_blind_camera(self):
        monitor = PresenceMonitor()
        self.assertEqual(monitor.absent_seconds, 300)
        self.assertIsNone(monitor.observe(1000, 0))
        self.assertIsNone(monitor.observe(1020, 0))
        self.assertIsNone(monitor.observe(1030, 0, seeing=False))
        self.assertIsNone(monitor.observe(1600, 0))
        # the 570 s the camera was blind do not count: alert at 1000 + 30 + 300
        for moment in range(1620, 1880, 20):
            self.assertIsNone(monitor.observe(moment, 0))
        self.assertIsInstance(monitor.observe(1890, 0), PresenceAlert)

    @staticmethod
    def _bangkok(hour, minute, second=0):
        from datetime import datetime
        from rack_ai.shifts import BANGKOK
        return datetime(2026, 10, 5, hour, minute, second, tzinfo=BANGKOK).timestamp()

    def _run_empty(self, monitor, start, end, step=20):
        alerts = []
        moment = start
        while moment <= end:
            event = monitor.observe(moment, 0)
            if isinstance(event, PresenceAlert):
                alerts.append(event)
            moment += step
        return alerts

    def test_quiet_periods_parse_and_reject_bad_text(self):
        from rack_ai.final_pond.presence import parse_quiet_periods
        self.assertEqual(parse_quiet_periods('12:00-13:00'), ((720, 780),))
        self.assertEqual(parse_quiet_periods(' 12:00-13:00 , 17:00-17:30 '), ((720, 780), (1020, 1050)))
        self.assertEqual(parse_quiet_periods(''), ())
        for bad in ('12-13', '13:00-12:00', '23:30-00:30', '25:00-26:00', 'noon'):
            with self.assertRaises(ValueError, msg=bad):
                parse_quiet_periods(bad)

    def test_lunch_break_neither_counts_nor_alerts(self):
        from rack_ai.final_pond.presence import parse_quiet_periods
        monitor = PresenceMonitor(quiet_periods=parse_quiet_periods('12:00-13:00'))
        # left the pond at 11:58, nobody until 13:02 -> still within 5 minutes after the break
        self.assertEqual(self._run_empty(monitor, self._bangkok(11, 58), self._bangkok(13, 2)), [])
        self.assertEqual(monitor.status(self._bangkok(12, 30)), 'break')
        self.assertIsNone(monitor.snapshot(self._bangkok(12, 30))['seconds_since_person'])

    def test_after_the_break_the_timer_restarts_from_zero(self):
        from rack_ai.final_pond.presence import parse_quiet_periods
        monitor = PresenceMonitor(quiet_periods=parse_quiet_periods('12:00-13:00'))
        alerts = self._run_empty(monitor, self._bangkok(11, 58), self._bangkok(13, 10))
        self.assertEqual(len(alerts), 1)
        # first alert 5 minutes after the break ended, not after the 2 minutes before it
        self.assertGreaterEqual(alerts[0].at, self._bangkok(13, 5))
        self.assertLess(alerts[0].at, self._bangkok(13, 6))
        self.assertEqual(alerts[0].since, self._bangkok(13, 0))

    def test_without_a_break_the_same_absence_alerts(self):
        monitor = PresenceMonitor()
        alerts = self._run_empty(monitor, self._bangkok(11, 58), self._bangkok(13, 2))
        self.assertTrue(alerts)
        self.assertLess(alerts[0].at, self._bangkok(12, 4))

    def test_settings_reject_malformed_quiet_hours(self):
        from rack_ai.config import Settings
        with self.assertRaises(ValueError):
            Settings(final_pond_quiet_hours='12-13')
        self.assertEqual(Settings(final_pond_quiet_hours='12:00-13:00').final_pond_quiet_hours, '12:00-13:00')

    def test_only_confident_workers_in_pond_reset_presence(self):
        found = [
            Detection('worker', Box(200, 180, 320, 390), 0.9),
            Detection('worker', Box(850, 180, 960, 390), 0.9),
            Detection('worker', Box(250, 180, 350, 390), 0.3),
            Detection('worker', Box(710, 180, 800, 390), 0.9),
        ]
        self.assertEqual(workers_in_pond(found, (600, 1000, 3)), 2)

    def test_pilot_alerts_after_five_minutes_and_saves_event_with_evidence(self):
        class Model:
            names = {0: 'worker'}

            def predict(self, *_args, **_kwargs):
                return [SimpleNamespace(boxes=None)]

        saved = []
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(Path, 'is_file', return_value=True):
                worker = PeePreview(Path('test-model.pt'), interval=0.001,
                                    on_presence_event=saved.append, evidence_dir=Path(folder))
            # This test jumps the clock; the normal monitor correctly pauses gaps >30s.
            worker.presence.max_gap_seconds = 301
            worker._model = Model()
            frame = np.zeros((600, 1000, 3), dtype=np.uint8)
            with patch('cv2.imdecode', return_value=frame), patch('time.time', side_effect=[1000.0, 1301.0]):
                worker.frame(b'first')
                worker._last_started_at = 0
                worker.frame(b'second')
            worker._flush_events()
            self.assertEqual(len(saved), 1)
            event = saved[0]
            self.assertEqual(event['type'], 'station_unattended')
            self.assertEqual(event['task_id'], PRESENCE_TASK_ID)
            self.assertGreaterEqual(event['payload']['absent_seconds'], 300)
            self.assertEqual(worker.status()['presence_status'], 'unattended')
            # the frame that triggered the alert is kept, and only by its plain file name
            name = event['payload']['evidence_image']
            path = worker.evidence_path(name)
            self.assertIsNotNone(path)
            self.assertEqual(path.read_bytes()[:2], b'\xff\xd8')
            self.assertNotIn(':', name)

    def test_evidence_lookup_refuses_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'ok.jpg').write_bytes(b'\xff\xd8x')
            with patch.object(Path, 'is_file', return_value=True):
                worker = PeePreview(Path('test-model.pt'), evidence_dir=Path(folder))
            self.assertIsNotNone(worker.evidence_path('ok.jpg'))
            for name in ('../ok.jpg', '..\\ok.jpg', 'sub/ok.jpg', 'ok.png', 'C:ok.jpg'):
                self.assertIsNone(worker.evidence_path(name), name)

    def test_area_mode_uses_the_person_model_and_counts_only_feet_in_the_zone(self):
        model = PersonModel([
            ((300, 200, 420, 500), 0, 0.82),     # standing in the pond zone
            ((900, 100, 980, 280), 0, 0.80),     # far right corridor, outside the zone
            ((500, 300, 600, 420), 0, 0.30),     # low score, e.g. a cement sack
        ])
        with patch.object(Path, 'is_dir', return_value=True), patch.object(Path, 'is_file', return_value=False):
            worker = PeePreview(Path('pee.pt'), person_model_path=Path('yolo11s_openvino_model'),
                                interval=0.001, worker_filter=WorkerFilter(confidence=0.35))
        self.assertTrue(worker.enabled)
        self.assertEqual(worker.mode, 'area')
        self.assertEqual(worker.model_path.name, 'yolo11s_openvino_model')
        worker._model = model
        worker._person_classes = [0]
        with patch('cv2.imdecode', return_value=np.zeros((600, 1000, 3), dtype=np.uint8)):
            worker.frame(b'jpeg')
        self.assertEqual(model.calls[0]['classes'], [0])
        status = worker.status()
        self.assertEqual(status['people_count'], 2)
        self.assertEqual(status['filtered_out'], 1)
        self.assertEqual(status['workers_in_zone'], 1)
        self.assertNotIn('helmet_pass', status)

    def test_area_drawing_reports_inside_and_outside(self):
        frame = np.zeros((600, 1000, 3), dtype=np.uint8)
        items = [Detection('person', Box(300, 200, 420, 500), 0.9),
                 Detection('person', Box(900, 100, 980, 280), 0.9)]
        output, counts = draw_area_detections(frame, items)
        self.assertEqual(counts, {'people_count': 2, 'workers_in_zone': 1, 'filtered_out': 0})
        self.assertEqual(np.count_nonzero(frame), 0)
        self.assertGreater(np.count_nonzero(output), 0)

    def test_stale_camera_is_blind_not_an_absence_alert(self):
        with patch.object(Path, 'is_file', return_value=True):
            worker = PeePreview(Path('test-model.pt'))
        worker._latest = {'people_count': 1, 'presence_status': 'attended',
                          'seconds_since_person': 0}
        worker._last_at = time.monotonic() - 9
        status = worker.status()
        self.assertFalse(status['camera_online'])
        self.assertEqual(status['presence_status'], 'blind')
        self.assertIsNone(status['people_count'])
        self.assertIsNone(status['seconds_since_person'])
        self.assertIsNone(worker.cached_frame())

    def test_cadence_is_measured_from_inference_start(self):
        class SlowModel:
            calls = 0

            def predict(self, *_args, **_kwargs):
                self.calls += 1
                time.sleep(0.15)
                return [SimpleNamespace(boxes=None)]

        with patch.object(Path, 'is_file', return_value=True):
            worker = PeePreview(Path('test-model.pt'), interval=0.2)
        model = SlowModel()
        worker._model = model
        with patch('cv2.imdecode', return_value=np.zeros((100, 100, 3), dtype=np.uint8)):
            worker.frame(b'fake-jpeg')
            time.sleep(0.1)
            worker.frame(b'fake-jpeg')
        self.assertEqual(model.calls, 2)

    def test_background_worker_processes_without_browser_request(self):
        class Source:
            def latest(self):
                return (1.0, b'camera-frame')

        with patch.object(Path, 'is_file', return_value=True):
            worker = PeePreview(Path('test-model.pt'), interval=0.01)
            processed = threading.Event()

            def process(jpeg):
                self.assertEqual(jpeg, b'camera-frame')
                worker._jpeg = b'annotated-frame'
                worker._latest = {'people_count': 1}
                worker._last_at = time.monotonic()
                processed.set()

            with patch.object(worker, 'frame', side_effect=process) as mocked:
                worker.start(Source())
                self.assertTrue(processed.wait(2))
                time.sleep(0.2)
                self.assertEqual(mocked.call_count, 1)
                self.assertEqual(worker.cached_frame(), b'annotated-frame')
                self.assertEqual(worker.status()['people_count'], 1)
                self.assertEqual(worker.status()['inference_fps'], 0.0)
                worker.close()
                self.assertFalse(worker._thread.is_alive())

    def test_head_classes_are_matched_to_their_own_workers(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        items = [
            Detection('worker', Box(20, 80, 120, 380), 0.9),
            Detection('helmet', Box(42, 85, 93, 132), 0.8),
            Detection('worker', Box(220, 80, 320, 380), 0.9),
            Detection('bare_head', Box(243, 85, 294, 132), 0.8),
            Detection('worker', Box(420, 80, 520, 380), 0.9),
        ]
        output, counts = draw_detections(frame, items)
        self.assertEqual(output.shape, frame.shape)
        self.assertEqual(counts, {'people_count': 3, 'helmet_pass': 1,
                                  'no_helmet': 1, 'undecided': 1, 'filtered_out': 0})
        self.assertEqual(np.count_nonzero(frame), 0)

    def test_missing_head_is_unknown_not_bare(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        _, counts = draw_detections(frame, [Detection('worker', Box(20, 80, 120, 380), 0.9)])
        self.assertEqual(counts['no_helmet'], 0)
        self.assertEqual(counts['undecided'], 1)


if __name__ == '__main__':
    unittest.main()
