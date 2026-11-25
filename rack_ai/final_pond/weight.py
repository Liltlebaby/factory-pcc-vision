"""ตรวจว่าน้ำหนักบนตาชั่งนิ่งแล้วจริง

ทำไมต้องมีโมดูลนี้
------------------
ตาชั่งอุตสาหกรรมส่งค่าออกมาต่อเนื่องแม้ยังไม่มีอะไรวาง และค่าจะแกว่งจากแรงสั่น
ของเครื่องจักรกับจังหวะที่คนวางของลง ถ้าเอาค่าดิบมาใช้ทันที แรงกระแทกครั้งเดียว
จะถูกบันทึกเป็นการชั่งจริง ตามสเปคข้อ 9 จึงต้องรอให้ค่านิ่งก่อน

นิยาม "นิ่ง" ที่ใช้
-------------------
    มีค่าอย่างน้อย samples ตัว
    ค่าสูงสุดกับต่ำสุดในหน้าต่างต่างกันไม่เกิน tolerance_kg
    หน้าต่างกินเวลาอย่างน้อย hold_seconds
    ค่าเฉลี่ยไม่น้อยกว่า minimum_kg (กันการรายงานตาชั่งเปล่าว่าเป็นการชั่ง)

หนึ่งการชั่งให้หนึ่งค่า
-----------------------
เมื่อรายงานไปแล้ว จะไม่รายงานซ้ำจนกว่าน้ำหนักจะกลับลงไปต่ำกว่า minimum_kg หรือ
ขยับออกไปเกิน tolerance ซึ่งหมายถึงมีการยกออกและวางของใหม่ ถ้าไม่มีกฎนี้
การชั่งครั้งเดียวที่วางค้างไว้ห้าวินาทีจะกลายเป็นการตรวจหลายสิบครั้ง

ถ้าอุปกรณ์มี stable flag ของตัวเอง ให้ส่งเข้ามาทาง `device_stable` ได้ โมดูลนี้
จะใช้เป็นเงื่อนไขเพิ่ม ไม่ใช่แทนการคำนวณ เพราะ flag ของแต่ละรุ่นเชื่อถือไม่เท่ากัน
"""
from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WeightReading:
    """ค่าน้ำหนักที่ยืนยันแล้วว่านิ่ง"""
    at: float
    value_kg: float
    samples: int
    spread_kg: float


@dataclass
class StableWeight:
    tolerance_kg: float = 0.05
    samples: int = 5
    hold_seconds: float = 1.0
    minimum_kg: float = 0.10
    # ค่าที่เก่ากว่านี้ถูกทิ้ง เพื่อไม่ให้ค่าค้างจากนาทีก่อนมาทำให้ดูนิ่ง
    window_seconds: float = 5.0

    _window: deque = field(default_factory=deque, init=False)
    _reported: float | None = field(default=None, init=False)

    def __post_init__(self):
        if self.tolerance_kg < 0 or self.minimum_kg < 0:
            raise ValueError('tolerance และ minimum ต้องไม่เป็นลบ')
        if self.samples < 2:
            raise ValueError('ต้องใช้อย่างน้อย 2 ค่าจึงจะบอกได้ว่านิ่ง')
        if self.hold_seconds < 0 or self.window_seconds <= self.hold_seconds:
            raise ValueError('window_seconds ต้องมากกว่า hold_seconds')

    def reset(self):
        self._window.clear()
        self._reported = None

    def sample(self, at: float, value_kg: float, device_stable: bool = True) -> WeightReading | None:
        """ป้อนค่าหนึ่งครั้งจากตาชั่ง คืนค่าเมื่อเพิ่งนิ่ง ไม่งั้นคืน None"""
        if value_kg < 0:
            raise ValueError('น้ำหนักติดลบ แสดงว่าตาชั่งยังไม่ได้ tare')
        # ค่ากระโดดเกิน tolerance คือตาชั่งกำลังเปลี่ยนสถานะ ไม่ใช่ค่าที่นิ่งอยู่
        # ล้างหน้าต่างทิ้งแล้วเริ่มนับใหม่ ไม่งั้นการชั่งครั้งถัดไปต้องรอให้ค่าเก่า
        # หมดอายุตาม window_seconds ก่อน ทำให้สองการชั่งที่ติดกันหายไปครั้งหนึ่ง
        if self._window and abs(value_kg - self._window[-1][1]) > self.tolerance_kg:
            self._window.clear()
        self._window.append((at, value_kg))
        while self._window and at - self._window[0][0] > self.window_seconds:
            self._window.popleft()

        values = [value for _, value in self._window]
        # ปลดล็อกให้รายงานครั้งใหม่ได้ เมื่อของถูกยกออกหรือมีการวางของใหม่
        if self._reported is not None:
            if value_kg < self.minimum_kg or abs(value_kg - self._reported) > self.tolerance_kg:
                self._reported = None

        if not device_stable or len(self._window) < self.samples:
            return None
        span = self._window[-1][0] - self._window[0][0]
        spread = max(values) - min(values)
        average = sum(values) / len(values)
        if span < self.hold_seconds or spread > self.tolerance_kg or average < self.minimum_kg:
            return None
        if self._reported is not None:
            return None
        self._reported = average
        return WeightReading(at=at, value_kg=round(average, 3), samples=len(values), spread_kg=round(spread, 4))
