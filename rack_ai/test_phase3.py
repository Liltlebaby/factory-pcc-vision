import tempfile
import time
import unittest
import shutil
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient

from rack_ai.app import create_app
from rack_ai.camera import FrameBuffer, FramePacket
from rack_ai.config import Settings
from rack_ai.recording import ClipStore, OpenCVRecorder
from rack_ai.recording_control import RecordingControl, DEFAULT_POLICY
from rack_ai.test_pipeline import FakeService
from rack_ai.streamcopy import FFmpegRecorder


class Phase3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.buffer = FrameBuffer()
        self.frame = np.full((64,96,3),80,np.uint8)
        self.buffer.put(FramePacket(1,time.time(),time.monotonic(),1,self.frame))
        self.observation = dict(frame_id=1,rack_count=5,tracks=[dict(confidence=.5)],_monotonic=time.monotonic())
        _,jpg=cv2.imencode('.jpg',np.full((64,96,3),200,np.uint8))
        self.provider = lambda: (self.observation,jpg.tobytes())
        self.recorder = OpenCVRecorder(self.buffer,self.root,provider=self.provider)
        self.controller = RecordingControl(self.recorder,self.provider)

    def tearDown(self):
        self.recorder.stop()
        self.temp.cleanup()

    def test_schedules_persist_cancel_and_dispatch_once(self):
        now=time.time()
        job=self.controller.add(now+60,dict(duration_minutes=10,name='test',annotated=False))
        other=RecordingControl(self.recorder,self.provider)
        self.assertEqual(other.jobs()[0]['id'],job['id'])
        with patch.object(self.recorder,'start',return_value={'clip_id':'x'}) as start:
            self.controller.tick(now+61)
            self.controller.tick(now+62)
            start.assert_called_once_with(10,'test',False,source='scheduled')
        pending=self.controller.add(time.time()+600,dict(duration_minutes=15,name='cancel'))
        self.controller.cancel(pending['id'])
        self.assertIn('cancelled',[job['status'] for job in self.controller.jobs()])

    def test_overdue_and_busy_do_not_start(self):
        now=time.time()
        self.controller.add(now+1,dict(duration_minutes=10,name='missed'))
        with patch.object(self.recorder,'start') as start:
            self.controller.tick(now+100)
            start.assert_not_called()
        self.assertEqual(self.controller.jobs()[0]['status'],'missed')
        self.controller.add(time.time()+5,dict(duration_minutes=15,name='busy'))
        with patch.object(self.recorder,'snapshot',return_value={'active':True}):
            self.controller.tick(time.time()+6)
        self.assertEqual(self.controller.jobs()[0]['status'],'skipped_busy')

    def test_event_opt_in_and_persistent_cooldown(self):
        with patch.object(self.recorder,'start') as start:
            self.controller.tick()
            start.assert_not_called()
            self.controller.set_policy(dict(DEFAULT_POLICY,enabled=True))
            self.observation['frame_id']=2
            self.controller.tick()
            self.observation['frame_id']=3
            self.controller.tick()
            self.assertEqual(start.call_count,1)
            self.assertEqual(start.call_args.kwargs['source'],'event')

    def test_annotated_separate_and_confidence_statistics(self):
        self.recorder.start(.01,'audit',annotated=True)
        self.recorder.thread.join(5)
        value=self.recorder.history()[0]
        self.assertEqual(value['status'],'recorded')
        self.assertEqual(value['average_confidence'],.5)
        self.assertEqual(value['detection_observations'],1)
        self.assertNotEqual(value['file_path'],value['annotated_path'])
        for kind,expected in [('raw',80),('annotated',200)]:
            cap=cv2.VideoCapture(str(self.recorder.storage().file(value['clip_id'],kind)))
            try:
                ok,frame=cap.read()
                self.assertTrue(ok)
                self.assertLess(abs(float(frame.mean())-expected),10)
            finally:
                cap.release()

    def test_interrupted_recovery_and_path_validation(self):
        store=self.recorder.storage()
        identity='clip_'+'a'*32
        store.save(dict(clip_id=identity,status='recording',start_time='2026',file_path='../outside.mp4'))
        store.recover()
        self.assertEqual(store.get(identity)['status'],'interrupted')
        with self.assertRaises(ValueError):
            store.file(identity)
        for duration in (float('nan'),0,-1,61):
            with self.assertRaises(ValueError):
                self.recorder.start(duration,'test')

    def test_api_validation_and_schedule_timezone(self):
        service=FakeService()
        service.recorder=self.recorder
        service.recording_control=self.controller
        with TestClient(create_app(Settings(),service)) as client:
            self.assertEqual(client.post('/api/recordings/start',json={'duration_minutes':-10}).status_code,422)
            self.assertEqual(client.post('/api/recording-schedules',json={'start_at':'2030-01-01T00:00:00'}).status_code,422)
            self.assertFalse(client.get('/api/recording-policy').json()['enabled'])
            self.assertEqual(client.post('/api/recording-policy',json={'enabled':True,'duration_minutes':15}).status_code,200)
            self.assertEqual(client.get('/api/recordings/invalid/file/raw').status_code,404)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'ffmpeg tools unavailable')
    def test_stream_copy_local_fixture(self):
        source=self.root/'fixture.mp4'
        writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'mp4v'),10,(96,64))
        for _ in range(30):
            writer.write(self.frame)
        writer.release()
        recorder=FFmpegRecorder(self.buffer,self.root/'copy',provider=self.provider,source_url=str(source))
        recorder.start(.02,'copy_test')
        try:
            recorder.thread.join(15)
            self.assertFalse(recorder.thread.is_alive())
            clip=recorder.history()[0]
            self.assertEqual(clip['status'],'recorded',clip)
            self.assertEqual(clip['encoder'],'ffmpeg_stream_copy')
            self.assertGreater(clip['video_duration_seconds'],0)
            self.assertTrue(recorder.storage().file(clip['clip_id']).is_file())
        finally:
            recorder.stop()
