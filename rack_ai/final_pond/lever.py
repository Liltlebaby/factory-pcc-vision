"""State machine ของคันโยกแม่เหล็กที่บ่อสุดท้าย

ทำไมต้องดู "ตำแหน่ง" ไม่ใช่ "ความเคลื่อนไหว"
---------------------------------------------
ถ้าตัดสินด้วยค่า motion อย่างเดียว เครื่องจักรที่สั่นตลอดเวลาจะทำให้ค่าสูงค้าง
และระบบจะรายงานว่ามีการตรวจแม่เหล็กทุกชั่วโมงทั้งที่ไม่มีใครมาแตะคันโยก
โมดูลนี้จึงรับค่าเป็น "ระยะห่างจากตำแหน่งพัก" 0..1 แล้วบังคับว่าต้องครบลำดับ

    พัก → ยกขึ้น → ถึงตำแหน่งตรวจและค้างไว้นานพอ → กลับมาตำแหน่งพัก

ลำดับที่ไม่ครบจะถูกทิ้งพร้อมเหตุผล ซึ่งครอบกรณีทดสอบหน้างานตามสเปคข้อ 20 คือ
คันโยกขยับไม่สุด เครื่องจักรสั่น และคนยืนบังคันโยก

โมดูลนี้ไม่รู้จักภาพหรือโมเดล มันรับแค่ตัวเลขต่อเฟรม ทำให้ทดสอบได้ครบทุกกรณี
โดยไม่ต้องมีกล้อง ส่วนการแปลงภาพใน ROI ให้เป็นตัวเลขนี้เป็นงานของ detector
"""
from dataclasses import dataclass, field

REST = 'rest'
RISING = 'rising'
HELD = 'held'

# เหตุผลที่ลำดับไม่สมบูรณ์ ใช้เพื่อให้หน้างานแก้ปัญหาได้ ไม่ใช่แค่บอกว่า "ไม่ผ่าน"
PARTIAL_TRAVEL = 'partial_travel'
TOO_BRIEF = 'too_brief'
TIMEOUT = 'timeout'


@dataclass(frozen=True)
class LeverActivation:
    """การยกคันโยกที่ครบลำดับแล้วหนึ่งครั้ง"""
    started_at: float
    completed_at: float
    peak_position: float
    held_seconds: float

    @property
    def duration_seconds(self) -> float:
        return self.completed_at - self.started_at


@dataclass(frozen=True)
class LeverAbandoned:
    """ลำดับที่เริ่มแล้วแต่ไม่ครบ เก็บไว้เพื่อวิเคราะห์ ไม่ถือเป็นการตรวจ"""
    started_at: float
    ended_at: float
    peak_position: float
    reason: str


@dataclass
class LeverStateMachine:
    """แปลงกระแสค่าตำแหน่งคันโยกให้เป็นเหตุการณ์การยกคันโยก

    พารามิเตอร์ทั้งหมดตั้งค่าได้ เพราะค่าที่เหมาะสมขึ้นกับมุมกล้องและระยะชักของ
    คันโยกจริง ค่าเริ่มต้นเป็นจุดตั้งต้นที่สมเหตุสมผล ต้องปรับจากวิดีโอหน้างาน
    """

    # ต่ำกว่านี้ถือว่าอยู่ตำแหน่งพัก
    rest_below: float = 0.20
    # สูงกว่านี้ถือว่าถึงตำแหน่งตรวจ
    check_above: float = 0.65
    # ต้องค้างที่ตำแหน่งตรวจนานเท่านี้ จึงถือว่าตรวจจริง ไม่ใช่แค่ปัดผ่าน
    hold_seconds: float = 0.8
    # ลำดับที่ยาวกว่านี้ถือว่าคันโยกค้างหรือตัวเลขเพี้ยน ไม่ใช่การตรวจปกติ
    max_sequence_seconds: float = 30.0
    # ต้องเห็นระดับเดิมติดกันกี่เฟรมจึงยอมเปลี่ยนสถานะ กันค่ากระโดดเฟรมเดียว
    debounce_samples: int = 3

    state: str = field(default=REST, init=False)
    # หลังจบลำดับหนึ่ง ต้องเห็นคันโยกกลับถึงตำแหน่งพักจริงก่อนจะเริ่มจับลำดับใหม่
    # ถ้าไม่มีเงื่อนไขนี้ คันโยกที่ค้างอยู่ที่ตำแหน่งตรวจจะยิง timeout ซ้ำทุกรอบ
    # max_sequence_seconds ไปเรื่อย ๆ กลายเป็นการแจ้งเตือนรบกวนที่ไม่มีใครอ่าน
    _armed: bool = field(default=True, init=False)
    _started_at: float | None = field(default=None, init=False)
    _peak: float = field(default=0.0, init=False)
    _held_since: float | None = field(default=None, init=False)
    _held_seconds: float = field(default=0.0, init=False)
    _level: str | None = field(default=None, init=False)
    _level_run: int = field(default=0, init=False)

    def __post_init__(self):
        if not 0 <= self.rest_below < self.check_above <= 1:
            raise ValueError('ต้องเป็น 0 <= rest_below < check_above <= 1')
        if self.hold_seconds < 0 or self.max_sequence_seconds <= self.hold_seconds:
            raise ValueError('max_sequence_seconds ต้องมากกว่า hold_seconds')
        if self.debounce_samples < 1:
            raise ValueError('debounce_samples ต้องเป็นจำนวนเต็มบวก')

    def _classify(self, position: float) -> str:
        if position <= self.rest_below:
            return REST
        if position >= self.check_above:
            return 'check'
        return 'mid'

    def _confirmed(self, level: str) -> bool:
        """ระดับนี้เห็นติดกันครบ debounce แล้วหรือยัง"""
        return self._level == level and self._level_run >= self.debounce_samples

    def _reset(self):
        self.state = REST
        self._armed = False
        self._started_at = None
        self._peak = 0.0
        self._held_since = None
        self._held_seconds = 0.0

    def sample(self, at: float, position: float) -> LeverActivation | LeverAbandoned | None:
        """ป้อนค่าหนึ่งเฟรม คืนเหตุการณ์เมื่อลำดับจบ ไม่งั้นคืน None"""
        if not 0 <= position <= 1:
            raise ValueError('position ต้องอยู่ระหว่าง 0 ถึง 1')
        level = self._classify(position)
        self._level_run = self._level_run + 1 if level == self._level else 1
        self._level = level

        if self.state == REST:
            if not self._armed:
                # รอให้คันโยกกลับถึงตำแหน่งพักยืนยันแล้วก่อน จึงพร้อมจับลำดับใหม่
                if self._confirmed(REST):
                    self._armed = True
                return None
            # ออกจากตำแหน่งพักอย่างต่อเนื่องเท่านั้นจึงเริ่มจับลำดับ
            # ค่ากระโดดเฟรมเดียวจากการสั่นจะไม่ผ่านเงื่อนไขนี้
            if level != REST and self._level_run >= self.debounce_samples:
                self.state = RISING
                self._started_at = at
                self._peak = position
            return None

        self._peak = max(self._peak, position)

        if self._started_at is not None and at - self._started_at > self.max_sequence_seconds:
            event = LeverAbandoned(self._started_at, at, self._peak, TIMEOUT)
            self._reset()
            return event

        if self.state == RISING:
            if self._confirmed('check'):
                self.state = HELD
                self._held_since = at
            elif self._confirmed(REST):
                # ขยับแล้วแต่ไม่ถึงตำแหน่งตรวจ — คนอาจแตะแล้วปล่อย หรือยกไม่สุด
                event = LeverAbandoned(self._started_at, at, self._peak, PARTIAL_TRAVEL)
                self._reset()
                return event
            return None

        # HELD
        if level == 'check' and self._held_since is not None:
            self._held_seconds = at - self._held_since
        if self._confirmed(REST):
            started = self._started_at
            peak = self._peak
            held = self._held_seconds
            self._reset()
            if held >= self.hold_seconds:
                return LeverActivation(started, at, peak, held)
            # ถึงตำแหน่งตรวจแต่ผ่านไปเร็วเกินไป ไม่นับเป็นการตรวจ
            return LeverAbandoned(started, at, peak, TOO_BRIEF)
        return None
