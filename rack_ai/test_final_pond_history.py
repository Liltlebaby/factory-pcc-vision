"""เทสต์เส้นทางข้อมูลย้อนหลัง: worker ส่งเข้ามา → เก็บลง SQLite → อ่านกลับเป็นรายงานรายวัน

จุดสำคัญคือรายงานต้องสร้างใหม่จากฐานข้อมูลทุกครั้ง ไม่ใช่จากหน่วยความจำของ worker
ไม่งั้นรีสตาร์ต worker ทีเดียวประวัติหายทั้งหมด และย้อนดูวันอื่นไม่ได้เลย
"""
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from rack_ai.lab.store import LabStore
from rack_ai.registry import CAMERA_BY_ID
from rack_ai.shifts import BANGKOK, report_window
from rack_ai.final_pond import RoundLedger, round_key_of, summarise
from rack_ai.final_pond.ingest import normalise_coverage, normalise_events
from rack_ai.final_pond.lever import LeverActivation
from rack_ai.final_pond.rounds import COMPLETED, MEASURED, MISSED, NO_DATA, UNAVAILABLE
from rack_ai.final_pond.weight import WeightReading

CAMERA = CAMERA_BY_ID['final-pond-cam-01']
TASK = 'magnet-inspection'


def at(hour, minute=0, second=0, day=22, month=9):
    return datetime(2026, month, day, hour, minute, second, tzinfo=BANGKOK).timestamp()


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as root:
        yield LabStore(Path(root))


def inspection_event(ledger, hour, minute=3, day=22, weight=None):
    """สร้างรอบตรวจหนึ่งครั้งแล้วแปลงเป็น event ที่พร้อมบันทึก"""
    started = at(hour, minute, 0, day=day)
    activation = LeverActivation(started, started + 20, 0.9, 1.4)
    if weight is None:
        inspection = ledger.record_lever(activation, helmet_status='PASS', person_track_id=21)
    else:
        ledger.record_weight(WeightReading(started + 12, weight, 6, 0.01))
        inspection = ledger.record_lever(activation, helmet_status='PASS', person_track_id=21)
    return {
        'task_id': TASK,
        'type': 'magnet_inspection',
        'occurred_at': inspection.completed_at,
        'event_id': inspection.event_id(CAMERA.camera_id, TASK),
        'rule_version': 'magnet-check-v1',
        'payload': inspection.payload(),
    }


def ingest(store, events, coverage=(), now=None):
    moment = now if now is not None else at(23, 0)
    prepared = normalise_events(CAMERA, events, moment) if events else []
    entries = normalise_coverage([{'round_key': key, 'seconds': seconds} for key, seconds in coverage], moment)
    with store.connect() as db:
        for event in prepared:
            store.append_event(event, db)
        if entries:
            store.add_coverage(CAMERA.camera_id, entries, db)
    return prepared


# ---------- การตรวจข้อมูลขาเข้า ----------

def test_station_id_comes_from_the_registry_not_the_worker():
    """worker ที่ตั้งค่าผิดต้องเขียนเหตุการณ์ลงสถานีอื่นไม่ได้"""
    event = {'task_id': TASK, 'type': 'magnet_inspection', 'occurred_at': at(10),
             'station_id': 'furnace-temperature', 'payload': {}}
    prepared = normalise_events(CAMERA, [event], at(11))
    assert prepared[0]['station_id'] == 'final-pond'


def test_unknown_task_is_rejected():
    event = {'task_id': 'rack-counting', 'type': 'rack_counted', 'occurred_at': at(10)}
    with pytest.raises(ValueError, match='ไม่อยู่ในทะเบียน'):
        normalise_events(CAMERA, [event], at(11))


def test_event_type_must_match_the_task_type():
    event = {'task_id': TASK, 'type': 'ppe_violation', 'occurred_at': at(10)}
    with pytest.raises(ValueError, match='ชนิดเหตุการณ์'):
        normalise_events(CAMERA, [event], at(11))


def test_future_timestamps_are_rejected():
    """นาฬิกา worker เพี้ยนแล้วเขียนอนาคต จะไปโผล่ในรายงานของวันที่ยังไม่มาถึง"""
    event = {'task_id': TASK, 'type': 'magnet_inspection', 'occurred_at': at(12)}
    with pytest.raises(ValueError, match='อนาคต'):
        normalise_events(CAMERA, [event], at(10))
    assert normalise_events(CAMERA, [event], at(11, 58))[0]['task_id'] == TASK


def test_duplicate_event_ids_within_one_batch_are_rejected():
    event = {'task_id': TASK, 'type': 'magnet_inspection', 'occurred_at': at(10), 'event_id': 'x:y:1'}
    with pytest.raises(ValueError, match='ซ้ำกัน'):
        normalise_events(CAMERA, [event, dict(event)], at(11))


def test_coverage_seconds_cannot_exceed_one_hour():
    with pytest.raises(ValueError, match='0 ถึง 3600'):
        normalise_coverage([{'round_key': '2026-09-22T10', 'seconds': 4000}], at(11))


def test_coverage_round_key_format_is_enforced():
    with pytest.raises(ValueError, match='YYYY-MM-DDTHH'):
        normalise_coverage([{'round_key': '2026-09-22', 'seconds': 10}], at(11))


# ---------- การเก็บและอ่านกลับ ----------

def test_resending_the_same_inspection_does_not_duplicate_it(store):
    ledger = RoundLedger(scale_mode='absent')
    event = inspection_event(ledger, 10)
    ingest(store, [event])
    ingest(store, [event])
    start, end = report_window('2026-09-22')
    assert len(store.inspection_payloads(start, end, camera_id=CAMERA.camera_id)) == 1


def test_coverage_accumulates_across_calls_and_caps_at_one_hour(store):
    ingest(store, [], coverage=[('2026-09-22T10', 900)])
    ingest(store, [], coverage=[('2026-09-22T10', 900)])
    assert store.coverage(CAMERA.camera_id, '2026-09-22T00', '2026-09-22T23') == {'2026-09-22T10': 1800.0}
    ingest(store, [], coverage=[('2026-09-22T10', 3000)])
    assert store.coverage(CAMERA.camera_id, '2026-09-22T00', '2026-09-22T23')['2026-09-22T10'] == 3600.0


def test_coverage_query_is_limited_to_the_requested_range(store):
    ingest(store, [], coverage=[('2026-09-21T23', 100), ('2026-09-22T10', 200), ('2026-09-23T08', 300)])
    found = store.coverage(CAMERA.camera_id, '2026-09-22T07', '2026-09-23T07')
    assert found == {'2026-09-22T10': 200.0}


def test_coverage_is_kept_per_camera(store):
    ingest(store, [], coverage=[('2026-09-22T10', 600)])
    with store.connect() as db:
        store.add_coverage('work-status-camera', [('2026-09-22T10', 1200)], db)
    assert store.coverage(CAMERA.camera_id, '2026-09-22T00', '2026-09-22T23')['2026-09-22T10'] == 600.0
    assert store.coverage('work-status-camera', '2026-09-22T00', '2026-09-22T23')['2026-09-22T10'] == 1200.0


# ---------- รายงานย้อนหลัง ----------

def daily(store, date_key, now):
    start, end = report_window(date_key)
    found = store.inspection_payloads(start, end, camera_id=CAMERA.camera_id)
    coverage = store.coverage(CAMERA.camera_id, round_key_of(start), round_key_of(end - 1))
    return summarise(found, coverage, date_key, now=now)


def test_history_of_a_past_day_is_rebuilt_from_storage(store):
    """หัวใจของข้อนี้: ไม่แตะ ledger ที่สร้างข้อมูลเลย อ่านจากฐานข้อมูลล้วน ๆ"""
    ledger = RoundLedger(scale_mode='online')
    events = [inspection_event(ledger, hour, weight=8.40 + hour / 100, day=20) for hour in (8, 9, 11)]
    coverage = [(f'2026-09-20T{hour:02d}', 3600.0) for hour in (8, 9, 10, 11)]
    ingest(store, events, coverage, now=at(23, 0, day=20))

    report = daily(store, '2026-09-20', now=at(12, 0, day=22))
    by_key = {item['round_key']: item for item in report['rounds']}

    assert by_key['2026-09-20T08']['status'] == COMPLETED
    assert by_key['2026-09-20T09']['status'] == COMPLETED
    assert by_key['2026-09-20T10']['status'] == MISSED, 'กล้องเห็นครบชั่วโมงแต่ไม่มีใครตรวจ'
    assert by_key['2026-09-20T11']['status'] == COMPLETED
    assert by_key['2026-09-20T12']['status'] == NO_DATA, 'ไม่มี coverage จึงไม่กล่าวหา'
    assert by_key['2026-09-20T08']['weight_kg'] == 8.48
    assert by_key['2026-09-20T08']['weight_source'] == MEASURED
    assert report['compliance'] == round(3 / 4, 4)


def test_each_day_is_independent(store):
    ledger = RoundLedger(scale_mode='absent')
    ingest(store, [inspection_event(ledger, 10, day=20)],
           [('2026-09-20T10', 3600.0)], now=at(23, 0, day=20))
    ingest(store, [inspection_event(ledger, 14, day=21)],
           [('2026-09-21T14', 3600.0)], now=at(23, 0, day=21))

    first = daily(store, '2026-09-20', now=at(12, 0, day=22))
    second = daily(store, '2026-09-21', now=at(12, 0, day=22))

    assert first['tally'][COMPLETED] == 1
    assert second['tally'][COMPLETED] == 1
    assert {item['round_key'] for item in first['rounds']} \
        .isdisjoint({item['round_key'] for item in second['rounds']} - {'2026-09-21T07'})


def test_night_shift_rounds_land_in_the_day_they_started(store):
    """กะดึกข้ามเที่ยงคืน — รอบตีสองของคืนวันที่ 20 ต้องอยู่ในรายงานวันที่ 20"""
    ledger = RoundLedger(scale_mode='absent')
    events = [inspection_event(ledger, 22, day=20), inspection_event(ledger, 2, day=21)]
    ingest(store, events, [('2026-09-20T22', 3600.0), ('2026-09-21T02', 3600.0)],
           now=at(9, 0, day=21))

    report = daily(store, '2026-09-20', now=at(12, 0, day=22))
    by_key = {item['round_key']: item for item in report['rounds']}
    assert by_key['2026-09-20T22']['status'] == COMPLETED
    assert by_key['2026-09-21T02']['status'] == COMPLETED
    assert by_key['2026-09-21T02']['shift'] == 'night'
    assert by_key['2026-09-21T02']['next_day'] is True


def test_report_keeps_the_verdict_recorded_at_the_time(store):
    """เปลี่ยนกฎภายหลังต้องไม่ย้อนไปแก้ผลของวันเก่า"""
    ledger = RoundLedger(scale_mode='absent')
    ingest(store, [inspection_event(ledger, 10, day=20)],
           [('2026-09-20T10', 3600.0)], now=at(23, 0, day=20))
    report = daily(store, '2026-09-20', now=at(12, 0, day=22))
    row = {item['round_key']: item for item in report['rounds']}['2026-09-20T10']
    assert row['status'] == COMPLETED
    assert row['weight_source'] == UNAVAILABLE, 'ยังอ่านได้ว่าวันนั้นไม่มีตาชั่ง'


def test_day_with_no_data_at_all_reports_no_data_not_missed(store):
    report = daily(store, '2026-09-19', now=at(12, 0, day=22))
    assert report['tally'][NO_DATA] == 25
    assert report['tally'][MISSED] == 0
    assert report['compliance'] is None, 'ไม่มีรอบที่ตัดสินได้ จึงไม่ควรรายงานเป็น 0%'


def test_events_are_written_as_utc_and_read_back_in_bangkok(store):
    ledger = RoundLedger(scale_mode='absent')
    event = inspection_event(ledger, 2, day=21)
    prepared = ingest(store, [event], now=at(9, 0, day=21))
    assert prepared[0]['occurred_at'].endswith('Z')
    stored = datetime.fromisoformat(prepared[0]['occurred_at'].replace('Z', '+00:00'))
    assert stored.astimezone(BANGKOK).hour == 2
    assert stored.astimezone(timezone.utc).hour == 19
