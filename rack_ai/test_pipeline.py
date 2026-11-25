"""Run from project root: python -m unittest rack_ai.test_pipeline -v."""
import time
import unittest
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from rack_ai.app import create_app
from rack_ai.camera import FrameBuffer, FramePacket, RTSPReader
from rack_ai.config import Settings
from rack_ai.counter import RackCounter


class PipelineTests(unittest.TestCase):
    def test_latest_frame_and_consumer_isolation(self):
        buffer = FrameBuffer()
        for i in range(100):
            buffer.put(FramePacket(i, time.time(), time.monotonic(), 1, np.zeros((20, 30, 3), np.uint8)))
        packet = buffer.get()
        self.assertEqual(packet.frame_id, 99)
        packet.frame[:] = 255
        self.assertEqual(buffer.get().frame.max(), 0)
        self.assertIsNone(buffer.get(99))

    def test_count_once_and_no_count_born_below_line(self):
        counter = RackCounter(Settings(line=.5, movement=5, cooldown=0))
        for i, y in enumerate([20, 40, 60, 70, 30, 70]):
            counter.update([dict(track_id=1, confidence=.8, bbox=[0,y-5,20,y+5])], 100, i)
        self.assertEqual(counter.count, 1)
        for i, y in enumerate([60,70,80]):
            counter.update([dict(track_id=2, confidence=.8, bbox=[0,y-5,20,y+5])], 100, i+10)
        self.assertEqual(counter.count, 1)

    def test_upward_not_counted(self):
        counter = RackCounter(Settings(line=.5, cooldown=0))
        for i,y in enumerate([80,60,40,20]):
            counter.update([dict(track_id=1, confidence=.8, bbox=[0,y-5,20,y+5])],100,i)
        self.assertEqual(counter.count,0)

    def test_validation(self):
        for args in [dict(cooldown=-1),dict(retry=float('nan')),dict(movement=0)]:
            with self.assertRaises(ValueError):
                Settings(**args)

    def test_reader_reconnect_and_shutdown(self):
        class Capture:
            def isOpened(self): return False
            def release(self): pass
        with patch('rack_ai.camera.cv2.VideoCapture', return_value=Capture()) as opened, \
             patch('rack_ai.camera.log.warning') as warned:
            reader = RTSPReader('rtsp://test.invalid/stream', retry=.01)
            reader.start()
            time.sleep(.06)
            reader.close()
            self.assertGreaterEqual(opened.call_count, 2)
            self.assertEqual(warned.call_count, 1)
            self.assertFalse(reader.thread.is_alive())
            self.assertFalse(reader.status(1)['connected'])

    def test_api_and_two_websocket_clients(self):
        service = FakeService()
        with TestClient(create_app(Settings(token='test-token'),service)) as client:
            self.assertEqual(client.get('/health').status_code,200)
            self.assertEqual(client.get('/api/status').status_code,401)
            self.assertEqual(client.get('/api/status',headers={'Authorization':'Bearer test-token'}).status_code,200)
            with client.websocket_connect('/ws/rack-counter') as first:
                first.send_json({'token':'test-token'})
                with client.websocket_connect('/ws/rack-counter') as second:
                    second.send_json({'token':'test-token'})
                    self.assertEqual(first.receive_json()['rack_count'],3)
                    self.assertEqual(second.receive_json()['rack_count'],3)
            reset = client.post('/api/rack-counter/reset',headers={'Authorization':'Bearer test-token'})
            self.assertEqual(reset.status_code,200)
            self.assertEqual(reset.json()['rack_count'],0)
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect('/ws/rack-counter') as invalid:
                    invalid.send_json([])
                    invalid.receive_json()
        self.assertTrue(service.closed)


class FakeService:
    closed = False
    count = 3
    def start(self): pass
    def close(self): self.closed = True
    def snapshot(self): return {'running':True,'rack_count':self.count,'frame_id':10,'type':'frame_result'}
    def preview(self): return (10,b'jpeg')
    def reset_count(self): self.count=0; return {'rack_count':0,'status':'reset'}


class ServiceDefaultsTests(unittest.TestCase):
    def test_snapshot_can_report_configured_model_before_first_frame(self):
        from pathlib import Path
        from rack_ai.service import RackService

        service = RackService(Settings(source='unused', model=Path('models/rack-production-v3.pt')))
        self.assertEqual(service.snapshot()['model'], 'rack-production-v3.pt')


if __name__ == '__main__':
    unittest.main()
