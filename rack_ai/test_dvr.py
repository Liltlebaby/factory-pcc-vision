"""ทดสอบด้วย XML จริงที่ DVR ตอบกลับมา ไม่ใช่ตัวอย่างที่แต่งขึ้น"""
import unittest
import os
from unittest.mock import patch
from rack_ai.dvr import parse_channels, classify, channel_of, DvrMonitor

# คัดลอกจากผลจริงของ DS-7216HGHI-F1 V3.4.83 build 170526
REAL = '''<?xml version="1.0" encoding="UTF-8" ?>
<VideoInputChannelList version="1.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<VideoInputChannel version="1.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<id>1</id><inputPort>1</inputPort><videoInputEnabled>true</videoInputEnabled>
<name>Camera 01</name><videoFormat>PAL</videoFormat><resDesc>1080P25 Lite</resDesc>
</VideoInputChannel>
<VideoInputChannel version="1.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<id>9</id><inputPort>9</inputPort><videoInputEnabled>true</videoInputEnabled>
<name>Camera 09</name><videoFormat>PAL</videoFormat><resDesc>1080P25 Lite</resDesc>
</VideoInputChannel>
<VideoInputChannel version="1.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<id>12</id><inputPort>12</inputPort><videoInputEnabled>true</videoInputEnabled>
<name>Camera 12</name><videoFormat>PAL</videoFormat><resDesc>NO VIDEO</resDesc>
</VideoInputChannel>
</VideoInputChannelList>'''


class ParseTests(unittest.TestCase):
    def test_reads_every_channel_despite_repeated_namespaces(self):
        channels = parse_channels(REAL)
        self.assertEqual(channels[1], '1080P25 Lite')
        self.assertEqual(channels[9], '1080P25 Lite')
        self.assertEqual(channels[12], 'NO VIDEO')

    def test_signal_classification_matches_the_device(self):
        channels = parse_channels(REAL)
        self.assertEqual(classify(channels[9]), 'ok')
        self.assertEqual(classify(channels[12]), 'no_video')
        self.assertEqual(classify(''), 'unknown')
        # DVR เขียนด้วยตัวพิมพ์ใหญ่ แต่ไม่ควรพึ่งตัวพิมพ์
        self.assertEqual(classify('no video'), 'no_video')

    def test_channel_derived_from_rtsp_path(self):
        self.assertEqual(channel_of('rtsp://u:p@h:554/Streaming/Channels/901'), 9)
        self.assertEqual(channel_of('rtsp://u:p@h:554/Streaming/Channels/1201'), 12)
        self.assertIsNone(channel_of('rtsp://u:p@h:554/Streaming/Channels/abc'))


class MonitorTests(unittest.TestCase):
    def test_disabled_without_a_usable_source(self):
        monitor = DvrMonitor('')
        self.assertFalse(monitor.enabled)
        monitor.start()
        self.assertEqual(monitor.status()['error'], 'disabled')

    def test_credentials_are_never_exposed_by_status(self):
        monitor = DvrMonitor('rtsp://user:secret%40123@192.168.1.65:554/Streaming/Channels/901')
        self.assertTrue(monitor.enabled)
        self.assertEqual(monitor.channel, 9)
        self.assertNotIn('secret', str(monitor.status()))

    def test_unreachable_host_reports_error_and_never_raises(self):
        monitor = DvrMonitor('rtsp://u:p@127.0.0.1:1/Streaming/Channels/901')
        state = monitor._poll_once()
        self.assertFalse(state['reachable'])
        self.assertEqual(state['signal'], 'unknown')
        self.assertIsNotNone(state['error'])

    def test_lan_dvr_request_ignores_environment_proxy(self):
        monitor = DvrMonitor('rtsp://u:p@192.168.1.65:554/Streaming/Channels/901')
        with patch.dict(os.environ, {'http_proxy': 'http://127.0.0.1:9'}), \
             patch('socket.create_connection', side_effect=RuntimeError('test stop')) as connect:
            with self.assertRaises(RuntimeError):
                monitor._opener().open('http://192.168.1.65/ISAPI/System/Video/inputs/channels')
        self.assertEqual(connect.call_args.args[0], ('192.168.1.65', 80))


if __name__ == '__main__':
    unittest.main(verbosity=2)
