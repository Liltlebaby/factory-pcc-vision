import json
import tempfile
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

from rack_ai.camera import FrameBuffer, FramePacket
from rack_ai.recording import OpenCVRecorder


class RecordingTests(unittest.TestCase):
    def test_raw_video_metadata_and_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            buffer = FrameBuffer()
            raw = np.full((64,96,3),80,np.uint8)
            buffer.put(FramePacket(1,time.time(),time.monotonic(),1,raw))
            recorder = OpenCVRecorder(buffer,Path(directory),stale=5)
            recorder.start(.01,'unit_test')
            recorder.thread.join(5)
            self.assertFalse(recorder.thread.is_alive())
            clip = recorder.history()[0]
            self.assertEqual(clip['status'],'recorded')
            self.assertGreater(clip['frames_written'],0)
            self.assertGreater(clip['duplicate_frames'],0)
            cap = cv2.VideoCapture(str(Path(directory)/clip['file_path']))
            try:
                ok,frame = cap.read()
                self.assertTrue(ok)
                self.assertLess(abs(float(frame.mean())-80),10)
            finally:
                cap.release()
            self.assertEqual(buffer.get().frame.mean(),80)
            self.assertTrue(json.loads((Path(directory)/(clip['clip_id']+'.json')).read_text())['raw'])
            recorder.archive(clip['clip_id'])
            self.assertEqual(recorder.history()[0]['status'],'archived')
            self.assertTrue((Path(directory)/clip['file_path']).exists())
            with self.assertRaises(ValueError):
                recorder.archive('../outside')

    def test_reject_missing_camera(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = OpenCVRecorder(FrameBuffer(),Path(directory))
            with self.assertRaises(RuntimeError):
                recorder.start(10,'test')

    def test_stop_and_reject_overlapping_start(self):
        with tempfile.TemporaryDirectory() as directory:
            buffer = FrameBuffer()
            buffer.put(FramePacket(1,time.time(),time.monotonic(),1,np.zeros((64,96,3),np.uint8)))
            recorder = OpenCVRecorder(buffer,Path(directory))
            recorder.start(15,'test')
            with self.assertRaises(RuntimeError):
                recorder.start(10,'another')
            recorder.stop()
            self.assertFalse(recorder.snapshot()['active'])
            self.assertEqual(recorder.history()[0]['status'],'stopped')


if __name__ == '__main__':
    unittest.main()
