"""รอบตรวจแม่เหล็กรายชั่วโมงของบ่อสุดท้าย

ทำไมไฟล์นี้เป็นตรรกะล้วน ไม่มีกล้องและไม่มีตาชั่ง
--------------------------------------------------
ส่วนนี้คือกฎของโรงงาน ไม่ใช่งานประมวลผลภาพ มันต้องถูกต้องก่อนที่โมเดลหรือ
ตาชั่งจะมาถึง และต้องทดสอบได้ครบทุกกรณีโดยไม่ต้องรอฮาร์ดแวร์ การรวมหลักฐาน
จากคันโยกกับน้ำหนักให้เป็นเหตุการณ์เดียวที่ตรวจย้อนหลังได้ คือหัวใจของระบบนี้

กฎที่โค้ดนี้บังคับ (ตามสเปคข้อ 18)
-----------------------------------
    คนอยู่ในภาพอย่างเดียว           ไม่ถือว่าตรวจแม่เหล็ก
    ยกคันโยกครบลำดับ                ถือว่ามีการตรวจ
    มีน้ำหนักนิ่งในช่วงเวลาเดียวกัน  ถือว่ายืนยันแล้ว
    จบรอบแล้วไม่มีการยกคันโยก       รอบนั้นขาดการตรวจ

สถานะของรอบ
-----------
    upcoming         ยังไม่ถึงเวลา
    waiting          เป็นรอบปัจจุบัน ยังไม่มีการตรวจ
    completed        ตรวจแล้ว
    verify_required  ยกคันโยกแล้วแต่ตาชั่งที่ออนไลน์อยู่ไม่ให้น้ำหนักที่ใช้ได้
    missed           จบรอบแล้วไม่มีการตรวจ ทั้งที่กล้องเห็นภาพเกือบทั้งชั่วโมง
    no_data          จบรอบแล้วไม่มีการตรวจ แต่กล้องดับหรือขาดช่วงเกินเกณฑ์

ทำไมต้องมี no_data แยกจาก missed
---------------------------------
ถ้ากล้องดับไปครึ่งชั่วโมงแล้วระบบรายงานว่า "คนงานไม่ได้ตรวจ" นั่นคือการกล่าวหา
ด้วยข้อมูลที่ระบบเองไม่มี รายงานที่เอาไปใช้กับคนต้องแยกให้ออกระหว่าง
"เห็นแล้วว่าไม่ได้ทำ" กับ "มองไม่เห็นจึงไม่รู้" สองอย่างนี้นำไปสู่การแก้ปัญหา
ที่ต่างกันคนละเรื่อง — อย่างแรกคุยกับหน้างาน อย่างหลังซ่อมกล้อง

ช่วงที่ยังไม่มีตาชั่ง
---------------------
`scale_mode='absent'` ทำให้การยกคันโยกครบลำดับปิดรอบได้เลย โดยติดป้าย
`weight_source='unavailable'` ไว้ทุกเหตุการณ์ เมื่อตาชั่งมาถึงให้เปลี่ยนเป็น
'online' แล้วกฎน้ำหนักจะมีผลทันทีโดยไม่ต้องแก้โค้ด และเหตุการณ์เก่ายังอ่านได้ว่า
ตอนนั้นไม่มีน้ำหนักยืนยันเพราะอะไร
"""
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..shifts import BANGKOK, DAY_START_HOUR, GROUPS, REPORT_HOURS, midnight, report_window
from .lever import LeverActivation
from .weight import WeightReading

UPCOMING = 'upcoming'
WAITING = 'waiting'
COMPLETED = 'completed'
VERIFY_REQUIRED = 'verify_required'
MISSED = 'missed'
NO_DATA = 'no_data'

# ที่มาของน้ำหนักในเหตุการณ์ — เก็บเป็นข้อมูลถาวร เพื่อให้รายงานย้อนหลังอธิบายตัวเองได้
MEASURED = 'measured'
UNAVAILABLE = 'unavailable'   # ยังไม่ได้ติดตาชั่ง
SCALE_OFFLINE = 'scale_offline'  # ติดแล้วแต่ติดต่อไม่ได้ตอนนั้น
MISSING = 'missing'           # ตาชั่งออนไลน์ แต่ไม่มีน้ำหนักนิ่งในช่วงเวลานั้น

SCALE_MODES = ('absent', 'online', 'offline')


def round_key_of(timestamp: float) -> str:
    """คีย์ของรอบชั่วโมงตามเวลาไทย เช่น 2026-09-22T10"""
    return datetime.fromtimestamp(timestamp, BANGKOK).strftime('%Y-%m-%dT%H')


def round_bounds(round_key: str) -> tuple[float, float]:
    start = datetime.strptime(round_key, '%Y-%m-%dT%H').replace(tzinfo=BANGKOK)
    return start.timestamp(), (start + timedelta(hours=1)).timestamp()


@dataclass(frozen=True)
class Inspection:
    """การตรวจแม่เหล็กหนึ่งครั้งพร้อมหลักฐานที่รวมได้"""
    round_key: str
    completed_at: float
    status: str
    weight_source: str
    lever_started_at: float
    lever_completed_at: float
    lever_held_seconds: float
    weight_kg: float | None = None
    helmet_status: str | None = None
    person_track_id: int | None = None

    def event_id(self, camera_id: str, task_id: str) -> str:
        """ไอดีที่คำนวณซ้ำได้จากข้อมูลเดิม ส่งซ้ำกี่ครั้งก็ไม่เกิดแถวซ้ำ

        ใช้เวลาเริ่มยกคันโยกเป็นตัวแยก เพราะเป็นจุดที่ไม่เปลี่ยนอีกแล้ว ต่างจาก
        completed_at ที่ขยับได้ถ้าน้ำหนักมาช้า
        """
        return f'{camera_id}:{task_id}:{int(self.lever_started_at * 1_000_000)}'

    def payload(self) -> dict:
        return {
            'round_key': self.round_key,
            'inspection_status': self.status,
            'completed_at': self.completed_at,
            'weight_kg': self.weight_kg,
            'weight_stable': self.weight_kg is not None,
            'weight_source': self.weight_source,
            'lever_activated': True,
            'lever_start_time': self.lever_started_at,
            'lever_complete_time': self.lever_completed_at,
            'lever_held_seconds': round(self.lever_held_seconds, 2),
            'helmet_status': self.helmet_status,
            'person_track_id': self.person_track_id,
        }


@dataclass
class _Pending:
    activation: LeverActivation
    deadline: float
    helmet_status: str | None
    person_track_id: int | None


@dataclass
class RoundLedger:
    """สถานะสดของรอบตรวจ ใช้ในโปรเซส worker

    ถือข้อมูลเฉพาะที่ต้องใช้ตัดสินใจตอนนี้ ความถาวรเป็นหน้าที่ของ ai_events
    ฝั่ง Vision Monitor รายงานย้อนหลังจึงสร้างจากฐานข้อมูลด้วย `summarise`
    ไม่ใช่จากหน่วยความจำของ worker ที่หายไปเมื่อรีสตาร์ต
    """

    scale_mode: str = 'absent'
    # น้ำหนักที่มาก่อนคันโยกจบลำดับก็นับ — ตามตัวอย่างในสเปคข้อ 10 ที่ชั่งเสร็จ
    # ก่อนคันโยกกลับเข้าที่ 11 วินาที
    weight_lookback_seconds: float = 45.0
    # รอน้ำหนักหลังคันโยกกลับเข้าที่นานเท่านี้ ก่อนตัดสินว่าไม่มีน้ำหนักยืนยัน
    weight_wait_seconds: float = 60.0
    # กล้องต้องเห็นภาพไม่น้อยกว่าสัดส่วนนี้ของชั่วโมง จึงกล้าบอกว่า "ไม่ได้ตรวจ"
    coverage_ratio: float = 0.5
    clock: object = field(default=time.time)

    inspections: dict[str, list[Inspection]] = field(default_factory=dict, init=False)
    coverage: dict[str, float] = field(default_factory=dict, init=False)
    _pending: list[_Pending] = field(default_factory=list, init=False)
    _weights: list[WeightReading] = field(default_factory=list, init=False)

    def __post_init__(self):
        if self.scale_mode not in SCALE_MODES:
            raise ValueError(f'scale_mode ต้องเป็นหนึ่งใน {SCALE_MODES}')
        if self.weight_wait_seconds <= 0 or self.weight_lookback_seconds < 0:
            raise ValueError('ช่วงเวลารอน้ำหนักไม่ถูกต้อง')
        if not 0 <= self.coverage_ratio <= 1:
            raise ValueError('coverage_ratio ต้องอยู่ระหว่าง 0 ถึง 1')

    # ---- ข้อมูลเข้า ----

    def record_coverage(self, at: float, seconds: float):
        """บันทึกว่ากล้องเห็นภาพจริงกี่วินาทีในรอบที่เวลานี้อยู่

        worker เรียกทุกครั้งที่ประมวลผลได้สำเร็จ ไม่ใช่ทุกครั้งที่ลูปเดิน
        เพราะช่วงที่ RTSP หลุดหรือ DVR ส่งภาพ NO VIDEO ต้องไม่ถูกนับเป็นการเห็น
        """
        if seconds < 0:
            raise ValueError('seconds ต้องไม่เป็นลบ')
        key = round_key_of(at)
        self.coverage[key] = self.coverage.get(key, 0.0) + seconds

    def record_lever(self, activation: LeverActivation, helmet_status: str | None = None,
                     person_track_id: int | None = None) -> Inspection | None:
        """รับการยกคันโยกที่ครบลำดับแล้ว คืน Inspection ถ้าปิดได้ทันที"""
        if self.scale_mode != 'online':
            source = UNAVAILABLE if self.scale_mode == 'absent' else SCALE_OFFLINE
            return self._close(activation, None, source, helmet_status, person_track_id)

        matched = self._take_weight(activation.started_at - self.weight_lookback_seconds,
                                    activation.completed_at + self.weight_wait_seconds)
        if matched is not None:
            return self._close(activation, matched, MEASURED, helmet_status, person_track_id)

        self._pending.append(_Pending(
            activation=activation,
            deadline=activation.completed_at + self.weight_wait_seconds,
            helmet_status=helmet_status,
            person_track_id=person_track_id,
        ))
        return None

    def record_weight(self, reading: WeightReading) -> Inspection | None:
        """รับน้ำหนักที่นิ่งแล้ว จับคู่กับคันโยกที่ค้างอยู่ถ้ามี"""
        for index, pending in enumerate(self._pending):
            lower = pending.activation.started_at - self.weight_lookback_seconds
            if lower <= reading.at <= pending.deadline:
                self._pending.pop(index)
                return self._close(pending.activation, reading, MEASURED,
                                   pending.helmet_status, pending.person_track_id)
        # ยังไม่มีคันโยกค้าง เก็บไว้เผื่อคันโยกจบลำดับทีหลัง แล้วตัดของเก่าออก
        self._weights.append(reading)
        horizon = reading.at - (self.weight_lookback_seconds + self.weight_wait_seconds)
        self._weights = [item for item in self._weights if item.at >= horizon]
        return None

    def tick(self, now: float | None = None) -> list[Inspection]:
        """ปิดคันโยกที่รอน้ำหนักเกินกำหนด — ต้องเรียกเป็นระยะจากลูปของ worker"""
        moment = now if now is not None else self.clock()
        expired = [pending for pending in self._pending if pending.deadline < moment]
        self._pending = [pending for pending in self._pending if pending.deadline >= moment]
        return [
            self._close(pending.activation, None, MISSING,
                        pending.helmet_status, pending.person_track_id)
            for pending in expired
        ]

    # ---- ข้อมูลออก ----

    def snapshot(self, now: float | None = None) -> dict:
        """ค่าที่ heartbeat ส่งให้ Vision Monitor — ต้องเป็น scalar ทั้งหมด"""
        moment = now if now is not None else self.clock()
        key = round_key_of(moment)
        current = self.inspections.get(key, [])
        latest = current[-1] if current else None
        return {
            'round_key': key,
            'round_status': self._status(key, moment),
            'last_checked_at': latest.completed_at if latest else None,
            'last_weight_kg': latest.weight_kg if latest else None,
            'awaiting_weight': len(self._pending),
        }

    def _take_weight(self, lower: float, upper: float) -> WeightReading | None:
        for index, reading in enumerate(self._weights):
            if lower <= reading.at <= upper:
                return self._weights.pop(index)
        return None

    def _close(self, activation: LeverActivation, reading: WeightReading | None,
               source: str, helmet_status: str | None, person_track_id: int | None) -> Inspection:
        # รอบของการตรวจยึดตามเวลาที่เริ่มยกคันโยก ไม่ใช่เวลาที่น้ำหนักมาถึง
        # ไม่งั้นการตรวจตอน 10:59:50 ที่ชั่งเสร็จ 11:00:10 จะไปตกรอบ 11:00
        # แล้วรอบ 10:00 จะถูกรายงานว่าขาดการตรวจทั้งที่คนทำแล้ว
        key = round_key_of(activation.started_at)
        status = COMPLETED if source != MISSING else VERIFY_REQUIRED
        inspection = Inspection(
            round_key=key,
            completed_at=reading.at if reading is not None else activation.completed_at,
            status=status,
            weight_source=source,
            lever_started_at=activation.started_at,
            lever_completed_at=activation.completed_at,
            lever_held_seconds=activation.held_seconds,
            weight_kg=reading.value_kg if reading is not None else None,
            helmet_status=helmet_status,
            person_track_id=person_track_id,
        )
        self.inspections.setdefault(key, []).append(inspection)
        return inspection

    def _status(self, round_key: str, now: float) -> str:
        found = self.inspections.get(round_key, [])
        start, end = round_bounds(round_key)
        return _round_status(found, self.coverage.get(round_key, 0.0), start, end, now, self.coverage_ratio)


def _round_status(inspections, coverage_seconds: float, start: float, end: float,
                  now: float, coverage_ratio: float) -> str:
    """สถานะของรอบเดียว ใช้ร่วมกันระหว่างสถานะสดและรายงานย้อนหลัง"""
    if any(item['status'] == COMPLETED if isinstance(item, dict) else item.status == COMPLETED
           for item in inspections):
        return COMPLETED
    if inspections:
        # มีการยกคันโยกแต่ยังไม่มีน้ำหนักยืนยัน
        return VERIFY_REQUIRED
    if now < start:
        return UPCOMING
    if now < end:
        return WAITING
    return MISSED if coverage_seconds >= coverage_ratio * (end - start) else NO_DATA


def summarise(inspections, coverage_by_round: dict[str, float], date_key: str,
              now: float | None = None, coverage_ratio: float = 0.5) -> dict:
    """รายงานรอบตรวจของวันรายงานหนึ่งวัน สร้างจากเหตุการณ์ที่บันทึกไว้จริง

    ใช้ขอบวันรายงานเดียวกับรายงานนับเก๊ะ คือ 07:00 ถึง 08:00 ของวันถัดไป
    เพื่อให้สองหน้าจอใน PCC พูดถึง "วันรายงาน" เดียวกัน ไม่ใช่คนละนิยาม

    `inspections` เป็น list ของ dict ที่มีคีย์ round_key, status, completed_at,
    weight_kg, weight_source, helmet_status — ตรงกับ payload ที่เก็บใน ai_events
    """
    moment = now if now is not None else datetime.now(BANGKOK).timestamp()
    base = midnight(date_key)
    by_round: dict[str, list[dict]] = {}
    for item in inspections:
        by_round.setdefault(item['round_key'], []).append(item)

    group_of = {}
    for key, name, start_hour, end_hour in GROUPS:
        for hour in range(start_hour, end_hour):
            group_of[hour] = (key, name)

    rounds = []
    for index in range(REPORT_HOURS):
        offset = DAY_START_HOUR + index
        start = base + timedelta(hours=offset)
        end = start + timedelta(hours=1)
        key = start.strftime('%Y-%m-%dT%H')
        found = sorted(by_round.get(key, []), key=lambda item: item['completed_at'])
        coverage = coverage_by_round.get(key, 0.0)
        group_key, group_name = group_of.get(offset, ('outside', 'นอกกะ'))
        rounds.append({
            'round_key': key,
            'hour': offset % 24,
            'label': f'{offset % 24:02d}:00–{offset % 24:02d}:59',
            'start': start.timestamp(),
            'end': end.timestamp(),
            'next_day': offset >= 24,
            'shift': group_key,
            'shift_name': group_name,
            'status': _round_status(found, coverage, start.timestamp(), end.timestamp(),
                                   moment, coverage_ratio),
            'inspections': found,
            'checked_at': found[0]['completed_at'] if found else None,
            'weight_kg': found[0].get('weight_kg') if found else None,
            'weight_source': found[0].get('weight_source') if found else None,
            'coverage_seconds': round(coverage, 1),
        })

    start, end = report_window(date_key)
    tally = {status: 0 for status in (UPCOMING, WAITING, COMPLETED, VERIFY_REQUIRED, MISSED, NO_DATA)}
    for item in rounds:
        tally[item['status']] += 1
    elapsed = [item for item in rounds if item['status'] not in (UPCOMING, WAITING)]
    judged = [item for item in elapsed if item['status'] != NO_DATA]
    return {
        'date': date_key,
        'start': start,
        'end': end,
        'rounds': rounds,
        'tally': tally,
        # คิดสัดส่วนจากรอบที่ระบบมองเห็นจริงเท่านั้น รอบที่กล้องดับไม่เข้าตัวหาร
        # เพราะมันไม่ใช่ทั้งผ่านและไม่ผ่าน
        'judged_rounds': len(judged),
        'compliance': round(tally[COMPLETED] / len(judged), 4) if judged else None,
    }
