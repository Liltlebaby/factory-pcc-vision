"""ถาม DVR ว่าช่องกล้องยังมีสัญญาณอยู่ไหม ผ่าน ISAPI

ปัญหาที่แก้
-----------
เมื่อสายโคแอกซ์ของกล้องอนาล็อกหลุด DVR ไม่ได้หยุดส่งสตรีม แต่ส่งภาพดำที่เขียนว่า
NO VIDEO ออกมาแทน ฝั่งเราจึงยังเห็นเฟรมไหลเข้ามา 25 fps, camera.connected เป็น true,
ไม่ stale — แต่ตรวจไม่เจอเก๊ะสักใบ ซึ่งแยกไม่ออกจากช่วงที่สายการผลิตหยุดจริง
หน้าจอจะขึ้นเขียวว่าปกติทั้งที่กล้องตาบอด

ตัวชี้วัดที่ใช้
--------------
`/ISAPI/System/Video/inputs/channels` คืนทุกช่องในคำขอเดียว โดยมี `resDesc` บอก
โหมดสัญญาณที่จับได้จริง ทดสอบกับเครื่องจริงแล้ว (DS-7216HGHI-F1 / V3.4.83):

    ช่อง 9  (ภาพมาปกติ)  -> <resDesc>1080P25 Lite</resDesc>
    ช่อง 12 (ไม่มีสัญญาณ) -> <resDesc>NO VIDEO</resDesc>

ระวัง: `videoInputEnabled` เป็น true ทั้งสองช่อง ใช้ตัดสินสัญญาณไม่ได้ แม้ชื่อจะ
ชวนให้เข้าใจแบบนั้น

ข้อจำกัดที่ตั้งใจ
-----------------
เธรดนี้แยกจากลูป inference โดยสิ้นเชิง ไม่เรียก pipeline.snapshot() และไม่แตะ lock
ใด ๆ ของมัน — เคยมีกรณีที่ผู้ชม MJPEG วน 20 ครั้ง/วินาทีเรียก snapshot() แล้วทำให้
inference fps ตกจาก 5 เหลือไม่ถึง 2 จึงยิงแค่นาทีละครั้งและเก็บผลเป็น dict ธรรมดา
ที่แทนที่ทั้งก้อน (atomic ภายใต้ GIL) ผู้อ่านจึงไม่ต้องรอ lock เลย
"""
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timezone

log = logging.getLogger('rack.dvr')

CHANNELS_PATH = '/ISAPI/System/Video/inputs/channels'
NO_VIDEO = 'no video'
REQUEST_TIMEOUT = 6


def _text(value: str | None) -> str:
    return (value or '').strip()


def parse_channels(xml_text: str) -> dict[int, str]:
    """คืน {หมายเลขช่อง: resDesc} — ตัด namespace ทิ้งเพราะเฟิร์มแวร์นี้ใส่ซ้ำซ้อนทุกชั้น"""
    root = ElementTree.fromstring(xml_text)
    found: dict[int, str] = {}
    for node in root.iter():
        if node.tag.rsplit('}', 1)[-1] != 'VideoInputChannel':
            continue
        fields = {child.tag.rsplit('}', 1)[-1]: _text(child.text) for child in node}
        try:
            channel = int(fields.get('id', ''))
        except ValueError:
            continue
        found[channel] = fields.get('resDesc', '')
    return found


def classify(res_desc: str) -> str:
    if not res_desc:
        return 'unknown'
    return 'no_video' if res_desc.strip().lower() == NO_VIDEO else 'ok'


def channel_of(source: str) -> int | None:
    """901 -> 9 · RTSP ของ Hikvision ใช้ <ช่อง><สตรีม> เช่น 901 = ช่อง 9 main stream"""
    tail = urllib.parse.urlsplit(source).path.rsplit('/', 1)[-1]
    if not tail.isdigit() or len(tail) < 2:
        return None
    return int(tail[:-2]) or None


class DvrMonitor:
    """โพลสถานะสัญญาณของช่องที่เราใช้ แล้วเก็บผลล่าสุดไว้ให้ API อ่าน"""

    def __init__(self, source: str, interval: float = 60.0):
        self.interval = max(10.0, interval)
        self.channel = channel_of(source)
        parts = urllib.parse.urlsplit(source)
        self.host = parts.hostname or ''
        self._user = urllib.parse.unquote(parts.username or '')
        self._password = urllib.parse.unquote(parts.password or '')
        self.enabled = bool(self.host and self.channel and parts.scheme.startswith('rtsp'))
        self._state = self._blank('not_checked_yet')
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name='dvr-monitor', daemon=True)

    def _blank(self, error: str | None) -> dict:
        return {
            'checked_at': None,
            'reachable': False,
            'channel': self.channel,
            'signal': 'unknown',
            'resolution': None,
            'error': error,
        }

    def _opener(self):
        manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        manager.add_password(None, f'http://{self.host}/', self._user, self._password)
        return urllib.request.build_opener(
            # DVR อยู่ใน LAN; พร็อกซีจาก environment อาจทำให้ ISAPI ล้มเหลว
            # แม้ RTSP ยังรับภาพได้ตามปกติ
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPDigestAuthHandler(manager),
            urllib.request.HTTPBasicAuthHandler(manager),
        )

    def start(self):
        if not self.enabled:
            self._state = self._blank('disabled')
            log.info('dvr_monitor_disabled host=%s channel=%s', self.host or '-', self.channel)
            return
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=3)

    def status(self) -> dict:
        """อ่านผลล่าสุด — ไม่มี lock เพราะ _state ถูกแทนที่ทั้งก้อน ไม่ได้แก้ในที่"""
        return self._state

    def _poll_once(self) -> dict:
        opener = self._opener()
        try:
            with opener.open(f'http://{self.host}{CHANNELS_PATH}', timeout=REQUEST_TIMEOUT) as response:
                body = response.read(200_000).decode('utf-8', 'replace')
        except urllib.error.HTTPError as error:
            # 401/403 = บัญชีที่ใช้ดึงภาพไม่มีสิทธิ์อ่านสถานะ ต้องขอสิทธิ์เพิ่ม
            reason = 'forbidden' if error.code in (401, 403) else f'http_{error.code}'
            return self._blank(reason)
        except Exception as error:
            return self._blank(type(error).__name__.lower())

        try:
            channels = parse_channels(body)
        except ElementTree.ParseError:
            return self._blank('bad_xml')

        res_desc = channels.get(self.channel or -1)
        if res_desc is None:
            return self._blank('channel_not_listed')
        return {
            'checked_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'reachable': True,
            'channel': self.channel,
            'signal': classify(res_desc),
            'resolution': res_desc,
            'error': None,
        }

    def _run(self):
        previous = None
        while not self._stop.is_set():
            state = self._poll_once()
            self._state = state
            signal = state['signal'] if state['reachable'] else state['error']
            if signal != previous:
                log.info('dvr_channel_signal channel=%s signal=%s resolution=%s',
                         self.channel, signal, state['resolution'])
                previous = signal
            # แบ่งการรอเป็นช่วงสั้น ๆ เพื่อให้ปิดบริการได้ทันทีโดยไม่ต้องรอครบนาที
            deadline = time.monotonic() + self.interval
            while not self._stop.is_set() and time.monotonic() < deadline:
                self._stop.wait(0.5)


def monitor_from(settings) -> DvrMonitor:
    interval = float(os.getenv('DVR_POLL_SECONDS', '60'))
    source = '' if os.getenv('DVR_MONITOR', 'on').lower() == 'off' else settings.source
    return DvrMonitor(source, interval)
