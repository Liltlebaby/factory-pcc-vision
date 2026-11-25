"""ตรวจการสวมหมวกนิรภัยของคนงาน ทำงานตลอดเวลาที่กล้องเห็นภาพ

แยกขาดจากรอบตรวจแม่เหล็ก ตามกฎข้อ 1 ของสเปค: ชั่วโมงที่ไม่มีใครมาตรวจแม่เหล็ก
ก็ยังต้องเตือนเรื่องหมวก และรอบที่ตรวจแม่เหล็กแล้วก็ยังอาจมีคนไม่สวมหมวกอยู่

ทำไมต้องยืนยันหลายวินาทีก่อนฟ้อง
---------------------------------
คนหันหัว ก้มตัว เดินผ่านเสา หรือภาพเบลอชั่วขณะ ทำให้โมเดลมองไม่เห็นหมวกได้
ทั้งที่ใส่อยู่ ถ้าฟ้องทันทีที่เฟรมเดียวบอกว่าไม่มีหมวก ระบบจะฟ้องผิดทั้งวัน
แล้วไม่มีใครเชื่ออีกเลย สเปคข้อ 4 จึงกำหนดให้ยืนยันต่อเนื่อง 2-3 วินาที

ทำไมต้องมีขนาดขั้นต่ำ
---------------------
คนที่อยู่ไกลสุดเฟรมสูงไม่กี่สิบพิกเซล โมเดลแยกไม่ออกว่าใส่หมวกหรือไม่ การฟ้อง
จากภาพแบบนั้นคือการเดา ไม่ใช่การตรวจ คนที่เล็กกว่าเกณฑ์จึงถูกนับว่า "ตัดสินไม่ได้"
ไม่ใช่ "ไม่สวมหมวก" — เป็นหลักเดียวกับ no_data ในรายงานรอบตรวจ

หนึ่งคนหนึ่งการฟ้อง
-------------------
ฟ้องครั้งเดียวต่อหนึ่ง track ไม่ใช่ทุกเฟรมที่ยังไม่ใส่หมวก ไม่งั้นคนคนเดียว
ที่ยืนทำงานสิบนาทีจะสร้างเหตุการณ์หลายพันรายการจนกลบทุกอย่างในฐานข้อมูล
"""
import time
from dataclasses import dataclass, field

PASS = 'PASS'
VIOLATION = 'VIOLATION'
UNDECIDED = 'UNDECIDED'


@dataclass(frozen=True)
class HelmetViolation:
    """คนงานหนึ่งคนที่ยืนยันแล้วว่าไม่สวมหมวก"""
    track_id: int
    first_seen_at: float
    confirmed_at: float
    samples: int

    @property
    def confirmed_seconds(self) -> float:
        return self.confirmed_at - self.first_seen_at

    def event_id(self, camera_id: str, task_id: str) -> str:
        """ไอดีที่คำนวณซ้ำได้ ส่งซ้ำกี่ครั้งก็ไม่เกิดแถวซ้ำใน ai_events"""
        return f'{camera_id}:{task_id}:{int(self.first_seen_at * 1_000_000)}:{self.track_id}'

    def payload(self) -> dict:
        return {
            'track_id': self.track_id,
            'helmet_status': VIOLATION,
            'first_seen_at': self.first_seen_at,
            'confirmed_at': self.confirmed_at,
            'confirmed_seconds': round(self.confirmed_seconds, 2),
            'samples': self.samples,
        }


@dataclass(frozen=True)
class HelmetResolved:
    """คนที่เคยถูกฟ้อง กลับมาสวมหมวกแล้ว — ปิดเรื่องให้ ไม่ค้างเป็นปัญหาลอย"""
    track_id: int
    at: float

    def payload(self) -> dict:
        return {'track_id': self.track_id, 'helmet_status': PASS, 'resolved_at': self.at}


@dataclass
class _Track:
    first_no_helmet_at: float | None = None
    no_helmet_samples: int = 0
    reported: bool = False
    last_at: float = 0.0


@dataclass
class HelmetMonitor:
    """แปลงผลตรวจรายเฟรมเป็นเหตุการณ์ระดับคน

    ป้อนด้วย observe() ทีละคนต่อเฟรม โดยส่งผลว่าเฟรมนั้นเห็นหมวกหรือไม่
    การแปลงภาพเป็นผลนั้นเป็นหน้าที่ของโมเดล ไฟล์นี้ไม่รู้จักภาพเลย
    """

    # ต้องเห็นว่าไม่สวมหมวกต่อเนื่องนานเท่านี้จึงฟ้อง (สเปคข้อ 4 ระบุ 2-3 วินาที)
    confirm_seconds: float = 2.5
    # และต้องมีตัวอย่างอย่างน้อยเท่านี้ด้วย กันกรณีเฟรมมาห่างจนเวลาผ่านไปเอง
    confirm_samples: int = 8
    # คนที่สูงน้อยกว่าสัดส่วนนี้ของเฟรม ถือว่าตัดสินไม่ได้ ไม่ใช่ไม่สวมหมวก
    min_height_ratio: float = 0.08
    # ความมั่นใจขั้นต่ำของผลตรวจที่จะเอามาใช้ตัดสิน
    min_confidence: float = 0.50
    # ไม่เห็น track นี้นานเท่านี้ ถือว่าออกจากเฟรมแล้ว ล้างสถานะทิ้ง
    track_timeout_seconds: float = 30.0
    clock: object = field(default=time.time)

    tracks: dict[int, _Track] = field(default_factory=dict, init=False)

    def __post_init__(self):
        if self.confirm_seconds < 0 or self.confirm_samples < 1:
            raise ValueError('เกณฑ์การยืนยันไม่ถูกต้อง')
        if not 0 < self.min_height_ratio < 1 or not 0 <= self.min_confidence <= 1:
            raise ValueError('เกณฑ์ขนาดหรือความมั่นใจไม่ถูกต้อง')
        if self.track_timeout_seconds <= 0:
            raise ValueError('track_timeout_seconds ต้องเป็นค่าบวก')

    def assess(self, height_ratio: float, confidence: float) -> bool:
        """ผลตรวจนี้เชื่อถือได้พอจะเอามาตัดสินไหม"""
        return height_ratio >= self.min_height_ratio and confidence >= self.min_confidence

    def observe(self, at: float, track_id: int, helmet: bool,
                height_ratio: float, confidence: float = 1.0):
        """ป้อนผลของคนหนึ่งคนในหนึ่งเฟรม คืนเหตุการณ์ถ้ามี"""
        track = self.tracks.get(track_id)
        if track is None:
            track = self.tracks[track_id] = _Track()
        track.last_at = at

        if not self.assess(height_ratio, confidence):
            # ตัดสินไม่ได้ ไม่นับเป็นทั้งผ่านและไม่ผ่าน และไม่ล้างเวลาที่สะสมไว้
            # คนเดินไกลออกไปชั่วครู่แล้วเดินกลับมา ไม่ควรได้เริ่มนับใหม่
            return None

        if helmet:
            resolved = HelmetResolved(track_id=track_id, at=at) if track.reported else None
            track.first_no_helmet_at = None
            track.no_helmet_samples = 0
            track.reported = False
            return resolved

        if track.first_no_helmet_at is None:
            track.first_no_helmet_at = at
        track.no_helmet_samples += 1
        if track.reported:
            return None
        if (at - track.first_no_helmet_at >= self.confirm_seconds
                and track.no_helmet_samples >= self.confirm_samples):
            track.reported = True
            return HelmetViolation(
                track_id=track_id,
                first_seen_at=track.first_no_helmet_at,
                confirmed_at=at,
                samples=track.no_helmet_samples,
            )
        return None

    def expire(self, now: float | None = None) -> int:
        """ล้าง track ที่ออกจากเฟรมไปแล้ว ป้องกันหน่วยความจำโตไม่จำกัด"""
        moment = now if now is not None else self.clock()
        stale = [key for key, track in self.tracks.items()
                 if moment - track.last_at > self.track_timeout_seconds]
        for key in stale:
            del self.tracks[key]
        return len(stale)

    def snapshot(self, people: int, helmet_pass: int, no_helmet: int) -> dict:
        """ค่าที่ heartbeat ส่งให้ Vision Monitor — scalar ทั้งหมด"""
        return {
            'people_count': people,
            'helmet_pass': helmet_pass,
            'no_helmet': no_helmet,
            'violation_count': sum(1 for track in self.tracks.values() if track.reported),
            'assessment_status': VIOLATION if no_helmet else (PASS if people else UNDECIDED),
        }
