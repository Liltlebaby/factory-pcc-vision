"""เทสต์ตรรกะรอบตรวจแม่เหล็กและคันโยก — ไม่ต้องใช้กล้อง โมเดล หรือตาชั่ง

กรณีทดสอบเลือกจากรายการทดสอบหน้างานในสเปคข้อ 20 โดยตรง เพราะข้อผิดพลาดที่
แพงที่สุดของระบบนี้ไม่ใช่การตรวจไม่เจอ แต่คือการรายงานว่าตรวจแล้วทั้งที่ไม่มีใครตรวจ
"""
from datetime import datetime, timedelta

from rack_ai.shifts import BANGKOK
from rack_ai.final_pond import LeverStateMachine, RoundLedger, StableWeight, round_key_of, summarise
from rack_ai.final_pond.lever import PARTIAL_TRAVEL, TIMEOUT, TOO_BRIEF, LeverActivation, LeverAbandoned
from rack_ai.final_pond.rounds import (
    COMPLETED, MEASURED, MISSED, MISSING, NO_DATA, UNAVAILABLE, UPCOMING,
    VERIFY_REQUIRED, WAITING,
)
from rack_ai.final_pond.weight import WeightReading


def at(hour, minute=0, second=0, day=22):
    return datetime(2026, 9, day, hour, minute, second, tzinfo=BANGKOK).timestamp()


def feed(machine, samples):
    """ป้อนค่าเป็นชุด คืนเหตุการณ์ทั้งหมดที่เกิดขึ้น"""
    events = []
    for moment, position in samples:
        event = machine.sample(moment, position)
        if event is not None:
            events.append(event)
    return events


def steady(start, position, count, step=0.1):
    return [(start + index * step, position) for index in range(count)]


# ---------- คันโยก ----------

def test_lever_full_sequence_activates():
    machine = LeverStateMachine()
    samples = (steady(0.0, 0.05, 5) + steady(0.5, 0.45, 4) + steady(0.9, 0.85, 15)
               + steady(2.4, 0.40, 4) + steady(2.8, 0.03, 5))
    events = feed(machine, samples)
    assert len(events) == 1, events
    assert isinstance(events[0], LeverActivation)
    assert events[0].held_seconds >= machine.hold_seconds
    assert events[0].peak_position >= 0.85


def test_lever_partial_travel_is_rejected():
    """คันโยกขยับไม่สุด — คนแตะแล้วปล่อย ไม่ถือว่าตรวจ"""
    machine = LeverStateMachine()
    events = feed(machine, steady(0.0, 0.03, 5) + steady(0.5, 0.40, 10) + steady(1.5, 0.02, 5))
    assert [event.reason for event in events] == [PARTIAL_TRAVEL]
    assert all(isinstance(event, LeverAbandoned) for event in events)


def test_machine_vibration_never_activates():
    """เครื่องจักรสั่น: ค่ากระโดดสลับเฟรมเดียว ต้องไม่ผ่าน debounce"""
    machine = LeverStateMachine()
    samples = []
    for index in range(200):
        samples.append((index * 0.1, 0.9 if index % 2 else 0.05))
    assert feed(machine, samples) == []
    assert machine.state == 'rest'


def test_lever_touched_too_briefly_is_rejected():
    machine = LeverStateMachine(hold_seconds=1.0)
    events = feed(machine, steady(0.0, 0.02, 5) + steady(0.5, 0.80, 4) + steady(0.9, 0.02, 5))
    assert [event.reason for event in events] == [TOO_BRIEF]


def test_lever_stuck_times_out():
    """คันโยกค้างอยู่ที่ตำแหน่งตรวจนานผิดปกติ ไม่ควรค้างรออย่างเดียว"""
    machine = LeverStateMachine(max_sequence_seconds=10)
    events = feed(machine, steady(0.0, 0.02, 5) + steady(0.5, 0.85, 200, step=0.5))
    assert [event.reason for event in events] == [TIMEOUT]
    assert machine.state == 'rest'


def test_lever_recovers_after_abandoned_sequence():
    """ลำดับที่ล้มเหลวต้องไม่ทำให้การยกครั้งถัดไปหาย"""
    machine = LeverStateMachine()
    first = feed(machine, steady(0.0, 0.02, 5) + steady(0.5, 0.40, 8) + steady(1.4, 0.02, 5))
    second = feed(machine, steady(10.0, 0.02, 4) + steady(10.5, 0.88, 15) + steady(12.0, 0.02, 5))
    assert len(first) == 1 and isinstance(first[0], LeverAbandoned)
    assert len(second) == 1 and isinstance(second[0], LeverActivation)


# ---------- น้ำหนัก ----------

def test_weight_becomes_stable_once_per_weighing():
    scale = StableWeight(tolerance_kg=0.05, samples=5, hold_seconds=1.0, minimum_kg=0.1)
    readings = [scale.sample(index * 0.3, 8.42) for index in range(20)]
    found = [reading for reading in readings if reading is not None]
    assert len(found) == 1, 'วางของค้างไว้ต้องได้ค่าเดียว ไม่ใช่ทุกเฟรม'
    assert found[0].value_kg == 8.42


def test_weight_impact_spike_is_not_a_weighing():
    """แรงกระแทกครั้งเดียวต้องไม่ถูกบันทึกเป็นการชั่ง"""
    scale = StableWeight()
    samples = [(0.0, 0.0), (0.3, 0.0), (0.6, 14.0), (0.9, 0.0), (1.2, 0.0), (1.5, 0.0)]
    assert all(scale.sample(moment, value) is None for moment, value in samples)


def test_weight_drifting_never_settles():
    scale = StableWeight(tolerance_kg=0.05)
    assert all(scale.sample(index * 0.3, 8.0 + index * 0.1) is None for index in range(20))


def test_weight_empty_scale_is_ignored():
    scale = StableWeight(minimum_kg=0.5)
    assert all(scale.sample(index * 0.3, 0.02) is None for index in range(20))


def test_second_weighing_reported_after_scale_cleared():
    scale = StableWeight(samples=4, hold_seconds=0.9, minimum_kg=0.1)
    first = [scale.sample(index * 0.3, 8.40) for index in range(8)]
    cleared = [scale.sample(3.0 + index * 0.3, 0.0) for index in range(6)]
    second = [scale.sample(6.0 + index * 0.3, 9.10) for index in range(8)]
    assert len([item for item in first if item]) == 1
    assert not any(cleared)
    assert len([item for item in second if item]) == 1


# ---------- รอบตรวจ ----------

def test_round_key_follows_bangkok_clock():
    assert round_key_of(at(10, 3, 38)) == '2026-09-22T10'
    assert round_key_of(at(0, 0, 1)) == '2026-09-22T00'
    assert round_key_of(at(23, 59, 59)) == '2026-09-22T23'


def test_lever_alone_completes_round_while_scale_absent():
    ledger = RoundLedger(scale_mode='absent')
    inspection = ledger.record_lever(LeverActivation(at(10, 3, 18), at(10, 3, 38), 0.9, 1.4))
    assert inspection.status == COMPLETED
    assert inspection.weight_source == UNAVAILABLE
    assert inspection.weight_kg is None
    assert ledger.snapshot(at(10, 30))['round_status'] == COMPLETED


def test_weight_arriving_before_lever_completes_is_matched():
    """ตามตัวอย่างในสเปค: ชั่งเสร็จ 10:03:27 คันโยกกลับเข้าที่ 10:03:38"""
    ledger = RoundLedger(scale_mode='online')
    assert ledger.record_weight(WeightReading(at(10, 3, 27), 8.42, 6, 0.01)) is None
    inspection = ledger.record_lever(LeverActivation(at(10, 3, 18), at(10, 3, 38), 0.9, 1.4))
    assert inspection.status == COMPLETED
    assert inspection.weight_source == MEASURED
    assert inspection.weight_kg == 8.42


def test_weight_arriving_after_lever_completes_is_matched():
    ledger = RoundLedger(scale_mode='online')
    assert ledger.record_lever(LeverActivation(at(10, 3, 18), at(10, 3, 30), 0.9, 1.2)) is None
    inspection = ledger.record_weight(WeightReading(at(10, 3, 50), 8.37, 6, 0.02))
    assert inspection.status == COMPLETED
    assert inspection.weight_kg == 8.37


def test_lever_without_weight_needs_verification_when_scale_online():
    """Rule 4: ขยับคันโยกอย่างเดียวไม่ถือว่าตรวจสำเร็จ เมื่อตาชั่งใช้งานได้"""
    ledger = RoundLedger(scale_mode='online', weight_wait_seconds=60)
    assert ledger.record_lever(LeverActivation(at(10, 3, 18), at(10, 3, 38), 0.9, 1.4)) is None
    assert ledger.tick(at(10, 4, 0)) == []
    expired = ledger.tick(at(10, 5, 0))
    assert len(expired) == 1
    assert expired[0].status == VERIFY_REQUIRED
    assert expired[0].weight_source == MISSING
    assert ledger.snapshot(at(10, 30))['round_status'] == VERIFY_REQUIRED


def test_inspection_belongs_to_the_round_the_lever_started_in():
    """ตรวจ 10:59:50 ชั่งเสร็จ 11:00:10 ต้องเข้ารอบ 10:00 ไม่ใช่ 11:00"""
    ledger = RoundLedger(scale_mode='online')
    ledger.record_lever(LeverActivation(at(10, 59, 45), at(10, 59, 58), 0.9, 1.3))
    inspection = ledger.record_weight(WeightReading(at(11, 0, 10), 8.5, 6, 0.01))
    assert inspection.round_key == '2026-09-22T10'


def test_multiple_inspections_in_one_hour_all_kept():
    ledger = RoundLedger(scale_mode='absent')
    ledger.record_lever(LeverActivation(at(10, 3), at(10, 3, 20), 0.9, 1.1))
    ledger.record_lever(LeverActivation(at(10, 40), at(10, 40, 20), 0.9, 1.2))
    assert len(ledger.inspections['2026-09-22T10']) == 2
    assert ledger.snapshot(at(10, 50))['round_status'] == COMPLETED


def test_event_id_is_stable_across_resends():
    activation = LeverActivation(at(10, 3, 18), at(10, 3, 38), 0.9, 1.4)
    first = RoundLedger(scale_mode='absent').record_lever(activation)
    second = RoundLedger(scale_mode='absent').record_lever(activation)
    assert first.event_id('final-pond-cam-01', 'magnet-inspection') == \
           second.event_id('final-pond-cam-01', 'magnet-inspection')


# ---------- รายงาน ----------

def inspection_row(hour, weight=None, status=COMPLETED, source=UNAVAILABLE, day=22):
    return {
        'round_key': f'2026-09-{day:02d}T{hour:02d}',
        'status': status,
        'completed_at': at(hour, 3, day=day),
        'weight_kg': weight,
        'weight_source': source,
        'helmet_status': 'PASS',
    }


def test_report_covers_the_same_report_day_as_the_rack_report():
    report = summarise([], {}, '2026-09-22', now=at(8, 0, day=23))
    assert len(report['rounds']) == 25
    assert report['rounds'][0]['round_key'] == '2026-09-22T07'
    assert report['rounds'][-1]['round_key'] == '2026-09-23T07'
    assert report['rounds'][-1]['next_day'] is True
    assert [item['shift'] for item in report['rounds']].count('day') == 11
    assert [item['shift'] for item in report['rounds']].count('outside') == 2
    assert [item['shift'] for item in report['rounds']].count('night') == 12


def test_report_separates_missed_from_no_data():
    full_hour = 3600.0
    coverage = {'2026-09-22T09': full_hour, '2026-09-22T10': 120.0}
    report = summarise([], coverage, '2026-09-22', now=at(12, 0))
    by_key = {item['round_key']: item for item in report['rounds']}
    assert by_key['2026-09-22T09']['status'] == MISSED, 'กล้องเห็นทั้งชั่วโมงแต่ไม่มีใครตรวจ'
    assert by_key['2026-09-22T10']['status'] == NO_DATA, 'กล้องเห็นแค่ 2 นาที จึงไม่รู้'
    assert by_key['2026-09-22T08']['status'] == NO_DATA, 'ไม่มีข้อมูล coverage เลย'


def test_report_marks_current_and_future_rounds():
    report = summarise([], {}, '2026-09-22', now=at(10, 30))
    by_key = {item['round_key']: item for item in report['rounds']}
    assert by_key['2026-09-22T10']['status'] == WAITING
    assert by_key['2026-09-22T11']['status'] == UPCOMING
    assert by_key['2026-09-23T07']['status'] == UPCOMING


def test_compliance_excludes_rounds_the_camera_could_not_see():
    coverage = {f'2026-09-22T{hour:02d}': 3600.0 for hour in (7, 8, 9)}
    rows = [inspection_row(7), inspection_row(8)]
    report = summarise(rows, coverage, '2026-09-22', now=at(10, 0))
    assert report['tally'][COMPLETED] == 2
    assert report['tally'][MISSED] == 1
    # ชั่วโมงที่ไม่มี coverage เป็น no_data และต้องไม่เข้าตัวหาร
    assert report['judged_rounds'] == 3
    assert report['compliance'] == round(2 / 3, 4)


def test_compliance_is_none_before_any_round_can_be_judged():
    report = summarise([], {}, '2026-09-22', now=at(7, 10))
    assert report['compliance'] is None
    assert report['tally'][UPCOMING] == 24
    assert report['tally'][WAITING] == 1


def test_report_surfaces_weight_and_source_for_the_round():
    coverage = {'2026-09-22T10': 3600.0}
    rows = [inspection_row(10, weight=8.42, source=MEASURED)]
    report = summarise(rows, coverage, '2026-09-22', now=at(12, 0))
    row = {item['round_key']: item for item in report['rounds']}['2026-09-22T10']
    assert row['status'] == COMPLETED
    assert row['weight_kg'] == 8.42
    assert row['weight_source'] == MEASURED


def test_round_with_only_unverified_lever_reports_verify_required():
    coverage = {'2026-09-22T10': 3600.0}
    rows = [inspection_row(10, status=VERIFY_REQUIRED, source=MISSING)]
    report = summarise(rows, coverage, '2026-09-22', now=at(12, 0))
    row = {item['round_key']: item for item in report['rounds']}['2026-09-22T10']
    assert row['status'] == VERIFY_REQUIRED
    assert report['compliance'] == 0.0


def test_snapshot_matches_the_registered_metrics_exactly():
    """Vision Monitor ปฏิเสธ heartbeat ที่มี metric ไม่ตรงทะเบียนด้วย 422

    ถ้าไม่มีเทสต์นี้ การเพิ่ม metric ในโค้ดแล้วลืมแก้ cameras.json จะทำให้ worker
    ส่ง heartbeat ไม่ผ่านตลอด และหน้าจอจะขึ้นว่ากล้องออฟไลน์โดยไม่มีใครรู้สาเหตุ
    """
    from rack_ai.registry import CAMERA_BY_ID

    task = {item.task_id: item for item in CAMERA_BY_ID['final-pond-cam-01'].tasks}['magnet-inspection']
    produced = set(RoundLedger(scale_mode='absent').snapshot(at(10, 0)))
    assert produced == set(task.output_metrics), produced.symmetric_difference(task.output_metrics)


def test_end_to_end_lever_and_scale_produce_one_completed_round():
    """ต่อสามโมดูลเข้าด้วยกันด้วยข้อมูลสังเคราะห์ ตรวจว่าผลลัพธ์เป็นรอบที่ปิดแล้ว"""
    machine = LeverStateMachine()
    scale = StableWeight(samples=4, hold_seconds=0.9, minimum_kg=0.1)
    ledger = RoundLedger(scale_mode='online')
    base = at(10, 3, 18)

    for moment, value in [(base + index * 0.3, 8.42) for index in range(8)]:
        reading = scale.sample(moment, value)
        if reading is not None:
            ledger.record_weight(reading)

    samples = (steady(base, 0.03, 4) + steady(base + 0.5, 0.50, 4)
               + steady(base + 1.0, 0.88, 15) + steady(base + 2.6, 0.03, 5))
    closed = [event for event in feed(machine, samples) if isinstance(event, LeverActivation)]
    assert len(closed) == 1
    inspection = ledger.record_lever(closed[0], helmet_status='PASS', person_track_id=21)

    assert inspection.status == COMPLETED
    assert inspection.weight_source == MEASURED
    assert inspection.weight_kg == 8.42
    assert inspection.helmet_status == 'PASS'

    report = summarise([inspection.payload() | {'status': inspection.status}],
                       {'2026-09-22T10': 3600.0}, '2026-09-22', now=at(12, 0))
    row = {item['round_key']: item for item in report['rounds']}['2026-09-22T10']
    assert row['status'] == COMPLETED
    assert report['compliance'] == 1.0
