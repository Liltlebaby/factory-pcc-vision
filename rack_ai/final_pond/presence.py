"""เฝ้าว่ามีคนงานอยู่ในพื้นที่บ่อสุดท้ายหรือไม่ และเตือนเมื่อหายไปนานเกินกำหนด

กฎของโรงงาน
------------
ห้ามคนงานหายออกจากพื้นที่บ่อสุดท้ายเกิน 5 นาที ถ้าเกินให้แจ้งเตือน

ทำไมต้องแยก "ไม่เห็นคน" ออกจาก "กล้องมองไม่เห็น"
-------------------------------------------------
นี่คือหัวใจของไฟล์นี้ ถ้ากล้องดับ สาย RTSP หลุด หรือ DVR ส่งภาพ NO VIDEO มาแทน
ระบบจะไม่เห็นคนเหมือนกัน แต่ความหมายต่างกันคนละเรื่อง

    เห็นภาพชัด ไม่มีคน 5 นาที    →  คนงานไม่อยู่จริง ควรเตือน
    กล้องดับ 5 นาที               →  ไม่รู้ว่ามีคนหรือเปล่า ควรซ่อมกล้อง

ถ้ารวมสองอย่างนี้เป็นเรื่องเดียว ระบบจะกล่าวหาคนงานด้วยข้อมูลที่ตัวเองไม่มี
และพอเตือนผิดบ่อย ๆ คนจะเลิกสนใจการเตือน ซึ่งอันตรายกว่าไม่มีระบบเตือนเลย
หลักเดียวกับที่ rounds.py แยก missed ออกจาก no_data

ทำไมต้องยืนยันหลายเฟรมก่อนนับว่า "มีคน"
----------------------------------------
โมเดลตรวจคนพลาดเป็นครั้งคราว เจอคนผีเฟรมเดียวได้ ถ้านับเฟรมเดียวว่ามีคน
การหายไปจริง ๆ 5 นาทีจะถูกรีเซ็ตกลางทางโดยไม่มีใครรู้ แล้วการเตือนที่ควรเกิด
ก็จะไม่เกิด — เป็นความผิดพลาดที่เงียบที่สุดและตรวจสอบย้อนหลังยากที่สุด

ช่วงพัก (เช่น พักเที่ยง 12:00–13:00)
------------------------------------
คนงานออกจากพื้นที่ได้ตามปกติ จึงไม่นับเวลาและไม่เตือนในช่วงนี้ เมื่อหมดช่วงพัก
นาฬิกาเริ่มนับใหม่จากศูนย์ ไม่นับต่อจากก่อนพัก — คนที่ออกไป 11:58 แล้วกลับมา
13:02 ต้องไม่โดนเตือน และทุกคนได้ 5 นาทีเต็มหลังหมดพักเพื่อกลับเข้าพื้นที่
"""
import time
from dataclasses import dataclass, field
from datetime import datetime

from ..shifts import BANGKOK

ATTENDED = 'attended'          # เห็นคนอยู่
ABSENT = 'absent'              # ไม่พบคน แต่ยังไม่ครบเกณฑ์แจ้งเตือน
UNATTENDED = 'unattended'      # ไม่พบคนครบเกณฑ์แจ้งเตือนแล้ว
BLIND = 'blind'                # กล้องมองไม่เห็น จึงไม่รู้
UNKNOWN = 'unknown'            # เพิ่งเริ่มทำงาน ยังไม่มีข้อมูลพอ
BREAK = 'break'                # ช่วงพักที่โรงงานกำหนด ไม่นับเวลาและไม่เตือน


def parse_quiet_periods(text: str) -> tuple[tuple[int, int], ...]:
    """'12:00-13:00, 00:00-00:30' -> ((720, 780), (0, 30)) เป็นนาทีของวัน เวลาไทย

    ไม่รับช่วงข้ามเที่ยงคืน (เช่น 23:30-00:30) ให้แบ่งเป็นสองช่วงแทน เพื่อให้ไม่มีกรณีกำกวม
    """
    periods = []
    for part in (piece.strip() for piece in (text or '').split(',')):
        if not part:
            continue
        try:
            start_text, end_text = (value.strip() for value in part.split('-'))
            start_hour, start_minute = (int(value) for value in start_text.split(':'))
            end_hour, end_minute = (int(value) for value in end_text.split(':'))
        except ValueError as exc:
            raise ValueError(f'ช่วงพักต้องเป็นรูปแบบ HH:MM-HH:MM: {part!r}') from exc
        start, end = start_hour * 60 + start_minute, end_hour * 60 + end_minute
        if not (0 <= start_hour < 24 and 0 <= start_minute < 60 and 0 <= end_hour <= 24
                and 0 <= end_minute < 60 and start < end <= 24 * 60):
            raise ValueError(f'ช่วงพักไม่ถูกต้องหรือข้ามเที่ยงคืน: {part!r}')
        periods.append((start, end))
    return tuple(periods)


@dataclass(frozen=True)
class PresenceAlert:
    """แจ้งว่าไม่มีคนงานในพื้นที่นานเกินกำหนด"""
    since: float               # เวลาที่เห็นคนครั้งสุดท้าย
    at: float                  # เวลาที่ออกการเตือนนี้
    repeat: int                # ครั้งที่เท่าไรของการหายรอบนี้ เริ่มที่ 1

    @property
    def absent_seconds(self) -> float:
        return self.at - self.since

    def payload(self) -> dict:
        return {
            'absent_since': self.since,
            'absent_seconds': round(self.absent_seconds, 1),
            'repeat': self.repeat,
        }


@dataclass(frozen=True)
class PresenceReturned:
    """แจ้งว่าคนงานกลับเข้ามาแล้ว หลังจากเคยเตือนว่าหายไป"""
    since: float
    at: float

    @property
    def absent_seconds(self) -> float:
        return self.at - self.since

    def payload(self) -> dict:
        return {'absent_since': self.since, 'absent_seconds': round(self.absent_seconds, 1)}


@dataclass
class PresenceMonitor:
    """ติดตามการมีอยู่ของคนงาน และออกการเตือนเมื่อหายนานเกินกำหนด

    ป้อนข้อมูลด้วย observe() ทุกครั้งที่ประมวลผลเฟรมได้ ไม่ว่าจะเจอคนหรือไม่
    และต้องบอกด้วยว่าตอนนั้นกล้องเห็นภาพจริงหรือเปล่า
    """

    # หายเกินเท่านี้จึงเตือน ค่าตั้งต้นตามกฎโรงงานคือ 5 นาที
    absent_seconds: float = 300.0
    # เตือนซ้ำทุกเท่านี้ถ้ายังไม่กลับมา ไม่ใช่เตือนรัวทุกเฟรม
    repeat_seconds: float = 600.0
    # ต้องเห็นคนติดกันกี่ครั้งจึงนับว่ามีคนจริง กันโมเดลเห็นคนผีเฟรมเดียว
    confirm_samples: int = 3
    # ช่องว่างระหว่างเฟรมที่ยาวกว่านี้ถือว่าขาดช่วง ไม่นับเป็นช่วงที่เฝ้าอยู่
    max_gap_seconds: float = 30.0
    # ช่วงพักเป็นนาทีของวันตามเวลาไทย จาก parse_quiet_periods()
    quiet_periods: tuple[tuple[int, int], ...] = ()
    clock: object = field(default=time.time)

    last_seen_at: float | None = field(default=None, init=False)
    last_observed_at: float | None = field(default=None, init=False)
    blind_since: float | None = field(default=None, init=False)
    _run: int = field(default=0, init=False)
    _alerts: int = field(default=0, init=False)
    _last_alert_at: float | None = field(default=None, init=False)
    _currently_seen: bool = field(default=False, init=False)
    _in_break: bool = field(default=False, init=False)

    def in_quiet_period(self, at: float) -> bool:
        if not self.quiet_periods:
            return False
        local = datetime.fromtimestamp(at, BANGKOK)
        minute = local.hour * 60 + local.minute
        return any(start <= minute < end for start, end in self.quiet_periods)

    def __post_init__(self):
        if self.absent_seconds <= 0 or self.repeat_seconds <= 0:
            raise ValueError('ช่วงเวลาต้องเป็นค่าบวก')
        if self.confirm_samples < 1:
            raise ValueError('confirm_samples ต้องเป็นจำนวนเต็มบวก')
        if self.max_gap_seconds <= 0:
            raise ValueError('max_gap_seconds ต้องเป็นค่าบวก')

    def restore(self, last_seen_at: float | None):
        """ตั้งเวลาที่เห็นคนครั้งสุดท้ายจากที่บันทึกไว้ ใช้ตอน worker เริ่มใหม่

        ถ้าไม่มีขั้นตอนนี้ การรีสตาร์ต worker จะรีเซ็ตนาฬิกาการหายไปทุกครั้ง
        และคนงานที่หายไปแล้ว 4 นาทีจะได้เวลาใหม่อีก 5 นาทีฟรี ๆ
        """
        self.last_seen_at = last_seen_at

    def observe(self, at: float, people: int, seeing: bool = True):
        """ป้อนผลของหนึ่งเฟรม คืนเหตุการณ์ถ้ามี ไม่งั้นคืน None

        `people`  จำนวนคนที่โมเดลตรวจพบในเฟรมนี้
        `seeing`  กล้องเห็นภาพจริงหรือไม่ ถ้า False ระบบจะหยุดนับเวลาการหาย
        """
        if people < 0:
            raise ValueError('จำนวนคนต้องไม่ติดลบ')

        if self.in_quiet_period(at):
            # ช่วงพัก: ไม่นับเวลา ไม่เตือน และไม่ปล่อยให้ช่องว่างระหว่างพักถูกนับว่าขาดช่วง
            self._in_break = True
            self._run = 0
            self._currently_seen = False
            self.blind_since = None
            self.last_observed_at = at
            return None
        if self._in_break:
            # เพิ่งหมดพัก: เริ่มนับใหม่จากตอนนี้ และปิดการเตือนที่ค้างจากก่อนพัก
            self._in_break = False
            self.last_seen_at = at
            self._alerts = 0
            self._last_alert_at = None

        if not seeing:
            # ช่วงที่มองไม่เห็นไม่นับเป็นการหายของคน และไม่รีเซ็ตด้วย
            # เพราะการที่กล้องกลับมาไม่ได้แปลว่ามีคนเดินเข้ามา
            if self.blind_since is None:
                self.blind_since = at
            self._run = 0
            self.last_observed_at = at
            return None

        # กล้องเพิ่งกลับมาเห็นภาพ ช่วงที่มองไม่เห็นต้องไม่ถูกนับเป็นเวลาที่คนหาย
        if self.blind_since is not None:
            if self.last_seen_at is not None:
                self.last_seen_at += at - self.blind_since
            self.blind_since = None
        elif self.last_observed_at is not None and at - self.last_observed_at > self.max_gap_seconds:
            # ขาดช่วงยาวโดยไม่ได้แจ้งว่ามองไม่เห็น ปฏิบัติแบบเดียวกันเพื่อความปลอดภัย
            if self.last_seen_at is not None:
                self.last_seen_at += at - self.last_observed_at
        self.last_observed_at = at

        if people > 0:
            self._run += 1
            if self._run >= self.confirm_samples:
                self._currently_seen = True
                returned = None
                if self._alerts and self.last_seen_at is not None:
                    returned = PresenceReturned(since=self.last_seen_at, at=at)
                self.last_seen_at = at
                self._alerts = 0
                self._last_alert_at = None
                return returned
            return None

        self._run = 0
        self._currently_seen = False
        if self.last_seen_at is None:
            # ยังไม่เคยเห็นใครเลยตั้งแต่เริ่ม ให้เริ่มจับเวลาจากเฟรมแรกที่เห็นภาพ
            self.last_seen_at = at
            return None

        absent = at - self.last_seen_at
        if absent < self.absent_seconds:
            return None
        if self._last_alert_at is not None and at - self._last_alert_at < self.repeat_seconds:
            return None
        self._alerts += 1
        self._last_alert_at = at
        return PresenceAlert(since=self.last_seen_at, at=at, repeat=self._alerts)

    def status(self, now: float | None = None) -> str:
        moment = now if now is not None else self.clock()
        if self.in_quiet_period(moment):
            return BREAK
        if self.blind_since is not None:
            return BLIND
        if self.last_seen_at is None:
            return UNKNOWN
        if self._currently_seen:
            return ATTENDED
        return UNATTENDED if moment - self.last_seen_at >= self.absent_seconds else ABSENT

    def snapshot(self, now: float | None = None) -> dict:
        """ค่าที่ heartbeat ส่งให้ Vision Monitor — scalar ทั้งหมด"""
        moment = now if now is not None else self.clock()
        absent = None
        if self.last_seen_at is not None and self.blind_since is None and not self.in_quiet_period(moment):
            absent = round(max(0.0, moment - self.last_seen_at), 1)
        return {
            'presence_status': self.status(moment),
            'seconds_since_person': absent,
            'unattended_alerts': self._alerts,
        }
