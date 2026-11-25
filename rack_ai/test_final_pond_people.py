"""เทสต์กฎเรื่องคนงาน: การสวมหมวก และการห้ามหายออกจากเฟรมเกิน 10 นาที

ความผิดพลาดที่แพงที่สุดของสองเรื่องนี้ไม่เหมือนกัน
    หมวก      ฟ้องผิดบ่อย ๆ แล้วไม่มีใครเชื่ออีกเลย
    คนหาย     ไม่ฟ้องทั้งที่ควรฟ้อง โดยไม่มีใครรู้ว่าพลาดไป
เทสต์จึงเน้นสองทิศนี้เป็นหลัก
"""
import pytest

from rack_ai.final_pond.ppe import (
    PASS, UNDECIDED, VIOLATION, HelmetMonitor, HelmetResolved, HelmetViolation,
)
from rack_ai.final_pond.presence import (
    ABSENT, ATTENDED, BLIND, UNATTENDED, UNKNOWN, PresenceAlert, PresenceMonitor, PresenceReturned,
)

MINUTE = 60.0


# ---------- หมวกนิรภัย ----------

def feed_helmet(monitor, start, count, helmet, step=0.2, track=1, height=0.20):
    events = []
    for index in range(count):
        event = monitor.observe(start + index * step, track, helmet, height)
        if event is not None:
            events.append(event)
    return events


def test_no_helmet_must_persist_before_it_is_reported():
    """สเปคข้อ 4: ยืนยัน 2-3 วินาทีก่อนฟ้อง"""
    monitor = HelmetMonitor(confirm_seconds=2.5, confirm_samples=8)
    assert feed_helmet(monitor, 0.0, 8, helmet=False) == []       # 1.4 วินาที ยังไม่ถึง
    events = feed_helmet(monitor, 1.6, 8, helmet=False)
    assert len(events) == 1 and isinstance(events[0], HelmetViolation)
    assert events[0].confirmed_seconds >= 2.5


def test_a_brief_glimpse_of_no_helmet_is_not_a_violation():
    """คนหันหัวหรือโดนบังชั่วครู่ ต้องไม่กลายเป็นการฟ้อง"""
    monitor = HelmetMonitor()
    assert feed_helmet(monitor, 0.0, 30, helmet=True) == []
    assert feed_helmet(monitor, 6.0, 4, helmet=False) == []       # แวบเดียว
    assert feed_helmet(monitor, 7.0, 30, helmet=True) == []


def test_one_violation_per_person_not_per_frame():
    """คนเดียวยืนอยู่นาน ต้องได้เหตุการณ์เดียว ไม่ใช่พันรายการ"""
    monitor = HelmetMonitor()
    events = feed_helmet(monitor, 0.0, 600, helmet=False)
    assert len([e for e in events if isinstance(e, HelmetViolation)]) == 1


def test_putting_the_helmet_on_closes_the_violation():
    monitor = HelmetMonitor()
    feed_helmet(monitor, 0.0, 40, helmet=False)
    events = feed_helmet(monitor, 20.0, 5, helmet=True)
    assert len(events) == 1 and isinstance(events[0], HelmetResolved)


def test_taking_it_off_again_reports_again():
    monitor = HelmetMonitor()
    feed_helmet(monitor, 0.0, 40, helmet=False)
    feed_helmet(monitor, 20.0, 5, helmet=True)
    events = feed_helmet(monitor, 30.0, 40, helmet=False)
    assert len([e for e in events if isinstance(e, HelmetViolation)]) == 1


def test_a_distant_person_is_undecided_not_a_violation():
    """คนไกลสุดเฟรมตัดสินไม่ได้ การฟ้องจากภาพแบบนั้นคือการเดา"""
    monitor = HelmetMonitor(min_height_ratio=0.08)
    assert feed_helmet(monitor, 0.0, 200, helmet=False, height=0.03) == []


def test_a_low_confidence_reading_is_ignored():
    monitor = HelmetMonitor(min_confidence=0.5)
    events = [monitor.observe(index * 0.2, 1, False, 0.2, confidence=0.3) for index in range(200)]
    assert not any(events)


def test_walking_away_briefly_does_not_reset_the_clock():
    """เดินไกลออกไปแล้วกลับมา ต้องไม่ได้เริ่มนับใหม่ ไม่งั้นเลี่ยงการฟ้องได้ง่าย"""
    monitor = HelmetMonitor(confirm_seconds=2.5, confirm_samples=8)
    feed_helmet(monitor, 0.0, 6, helmet=False)                         # เริ่มนับ
    for index in range(10):                                            # เดินไกล ตัดสินไม่ได้
        assert monitor.observe(2.0 + index * 0.2, 1, False, 0.02) is None
    events = feed_helmet(monitor, 4.0, 4, helmet=False)
    assert len(events) == 1, 'เวลาที่สะสมไว้ก่อนเดินออกไปต้องยังนับอยู่'


def test_two_people_are_tracked_separately():
    monitor = HelmetMonitor()
    for index in range(40):
        monitor.observe(index * 0.2, 1, False, 0.2)
        monitor.observe(index * 0.2, 2, True, 0.2)
    assert monitor.tracks[1].reported is True
    assert monitor.tracks[2].reported is False


def test_finished_tracks_are_cleaned_up():
    monitor = HelmetMonitor(track_timeout_seconds=30)
    feed_helmet(monitor, 0.0, 10, helmet=True, track=7)
    assert monitor.expire(now=100.0) == 1
    assert monitor.tracks == {}


def test_snapshot_reports_the_worst_case_present():
    monitor = HelmetMonitor()
    assert monitor.snapshot(2, 1, 1)['assessment_status'] == VIOLATION
    assert monitor.snapshot(2, 2, 0)['assessment_status'] == PASS
    assert monitor.snapshot(0, 0, 0)['assessment_status'] == UNDECIDED


# ---------- ห้ามหายเกิน 10 นาที ----------

def observe_span(monitor, start, seconds, people, seeing=True, step=5.0):
    events = []
    moment = start
    while moment <= start + seconds:
        event = monitor.observe(moment, people, seeing=seeing)
        if event is not None:
            events.append(event)
        moment += step
    return events


def test_alert_fires_only_after_the_full_ten_minutes():
    monitor = PresenceMonitor(absent_seconds=10 * MINUTE)
    observe_span(monitor, 0.0, 30, people=1)
    assert observe_span(monitor, 40.0, 9 * MINUTE, people=0) == []
    events = observe_span(monitor, 10 * MINUTE, 3 * MINUTE, people=0)
    assert len(events) == 1 and isinstance(events[0], PresenceAlert)
    assert events[0].absent_seconds >= 10 * MINUTE


def test_someone_present_never_alerts():
    monitor = PresenceMonitor(absent_seconds=10 * MINUTE)
    assert observe_span(monitor, 0.0, 60 * MINUTE, people=2) == []
    assert monitor.status(60 * MINUTE) == ATTENDED


def test_a_blind_camera_never_accuses_anyone():
    """กล้องดับครึ่งชั่วโมงต้องไม่กลายเป็น 'คนงานไม่อยู่' — เป็นคนละเรื่องกัน"""
    monitor = PresenceMonitor(absent_seconds=10 * MINUTE)
    observe_span(monitor, 0.0, 30, people=1)
    assert observe_span(monitor, 40.0, 30 * MINUTE, people=0, seeing=False) == []
    assert monitor.status(30 * MINUTE) == BLIND
    assert monitor.snapshot(30 * MINUTE)['seconds_since_person'] is None


def test_time_spent_blind_does_not_count_towards_the_absence():
    """กล้องกลับมาแล้วต้องไม่ฟ้องทันที เพราะช่วงที่มองไม่เห็นเราไม่รู้อะไรเลย"""
    monitor = PresenceMonitor(absent_seconds=10 * MINUTE)
    observe_span(monitor, 0.0, 30, people=1)
    observe_span(monitor, 40.0, 30 * MINUTE, people=0, seeing=False)
    events = observe_span(monitor, 31 * MINUTE, 5 * MINUTE, people=0)
    assert events == [], 'เวลาที่กล้องดับต้องไม่ถูกนับเป็นเวลาที่คนหาย'
    later = observe_span(monitor, 37 * MINUTE, 6 * MINUTE, people=0)
    assert len(later) == 1, 'แต่พอเห็นภาพชัดครบ 10 นาทีแล้วต้องฟ้อง'


def test_one_ghost_detection_cannot_cancel_a_real_absence():
    """โมเดลเห็นคนผีเฟรมเดียวต้องไม่รีเซ็ตนาฬิกา ไม่งั้นการเตือนจะหายไปเงียบ ๆ"""
    monitor = PresenceMonitor(absent_seconds=10 * MINUTE, confirm_samples=3)
    observe_span(monitor, 0.0, 30, people=1)
    observe_span(monitor, 40.0, 5 * MINUTE, people=0)
    assert monitor.observe(6 * MINUTE, 1) is None          # เฟรมเดียว ไม่พอยืนยัน
    events = observe_span(monitor, 6 * MINUTE + 5, 6 * MINUTE, people=0)
    assert len(events) == 1, 'ต้องยังฟ้องตามกำหนดเดิม'


def test_repeat_alerts_are_spaced_not_every_frame():
    monitor = PresenceMonitor(absent_seconds=10 * MINUTE, repeat_seconds=10 * MINUTE)
    observe_span(monitor, 0.0, 30, people=1)
    events = observe_span(monitor, 40.0, 45 * MINUTE, people=0)
    assert [event.repeat for event in events] == [1, 2, 3, 4]


def test_returning_closes_the_alert():
    monitor = PresenceMonitor(absent_seconds=10 * MINUTE)
    observe_span(monitor, 0.0, 30, people=1)
    observe_span(monitor, 40.0, 12 * MINUTE, people=0)
    events = observe_span(monitor, 13 * MINUTE, 30, people=1)
    assert len(events) == 1 and isinstance(events[0], PresenceReturned)
    assert events[0].absent_seconds >= 10 * MINUTE
    assert monitor.status(13 * MINUTE + 30) == ATTENDED


def test_returning_without_a_prior_alert_is_silent():
    monitor = PresenceMonitor(absent_seconds=10 * MINUTE)
    observe_span(monitor, 0.0, 30, people=1)
    observe_span(monitor, 40.0, 5 * MINUTE, people=0)
    assert observe_span(monitor, 6 * MINUTE, 30, people=1) == []


def test_restart_does_not_grant_a_fresh_ten_minutes():
    """รีสตาร์ต worker แล้วนาฬิกาต้องไม่เริ่มใหม่ ไม่งั้นเลี่ยงการเตือนได้ด้วยการรีสตาร์ต"""
    monitor = PresenceMonitor(absent_seconds=10 * MINUTE)
    monitor.restore(last_seen_at=0.0)
    events = observe_span(monitor, 9 * MINUTE, 3 * MINUTE, people=0)
    assert len(events) == 1
    assert events[0].since == 0.0


def test_status_is_unknown_before_anything_is_observed():
    monitor = PresenceMonitor()
    assert monitor.status(0.0) == UNKNOWN


def test_absence_is_measured_from_the_first_clear_frame_when_nobody_was_ever_seen():
    monitor = PresenceMonitor(absent_seconds=10 * MINUTE)
    assert monitor.observe(100.0, 0) is None
    assert monitor.status(100.0) == ABSENT
    events = observe_span(monitor, 105.0, 11 * MINUTE, people=0)
    assert len(events) == 1
    assert events[0].since == 100.0


@pytest.mark.parametrize('bad', [{'absent_seconds': 0}, {'repeat_seconds': -1},
                                 {'confirm_samples': 0}, {'max_gap_seconds': 0}])
def test_invalid_settings_are_rejected(bad):
    with pytest.raises(ValueError):
        PresenceMonitor(**bad)


# ---------- สัญญากับ Vision Monitor ----------

def test_snapshots_together_match_the_registered_metrics():
    """heartbeat ที่มี metric ไม่ตรงทะเบียนจะถูกปฏิเสธด้วย 422 และหน้าจอจะขึ้นว่า
    กล้องออฟไลน์โดยไม่บอกสาเหตุ เทสต์นี้กันไม่ให้เพิ่ม metric แล้วลืมแก้ทะเบียน"""
    from rack_ai.registry import CAMERA_BY_ID

    tasks = {t.task_id: t for t in CAMERA_BY_ID['final-pond-cam-01'].tasks}
    helmet = set(HelmetMonitor().snapshot(0, 0, 0))
    assert helmet == set(tasks['ppe-helmet'].output_metrics), \
        helmet.symmetric_difference(tasks['ppe-helmet'].output_metrics)
    presence = set(PresenceMonitor().snapshot(0.0))
    assert presence <= set(tasks['work-area-presence'].output_metrics), \
        presence - set(tasks['work-area-presence'].output_metrics)


def test_the_alerts_can_actually_be_stored():
    """เหตุการณ์ที่สองโมดูลนี้ออก ต้องผ่านด่านตรวจของ ingest ได้จริง
    ไม่งั้นระบบจะตรวจเจอแต่บันทึกไม่ได้ ซึ่งเท่ากับไม่มีใครได้รับแจ้ง"""
    from rack_ai.final_pond.ingest import normalise_events
    from rack_ai.registry import CAMERA_BY_ID

    camera = CAMERA_BY_ID['final-pond-cam-01']
    violation = HelmetViolation(track_id=21, first_seen_at=1000.0, confirmed_at=1003.0, samples=12)
    alert = PresenceAlert(since=1000.0, at=1600.0, repeat=1)
    events = [
        {'task_id': 'ppe-helmet', 'type': 'ppe_violation', 'occurred_at': 1003.0,
         'event_id': violation.event_id('final-pond-cam-01', 'ppe-helmet'),
         'payload': violation.payload()},
        {'task_id': 'work-area-presence', 'type': 'station_unattended', 'occurred_at': 1600.0,
         'payload': alert.payload()},
    ]
    prepared = normalise_events(camera, events, now=1700.0)
    assert [item['type'] for item in prepared] == ['ppe_violation', 'station_unattended']
    # งานหมวกออกเหตุการณ์คนหายไม่ได้แล้ว — สองงานแยกกันในทะเบียน
    with pytest.raises(ValueError):
        normalise_events(camera, [{**events[1], 'task_id': 'ppe-helmet'}], now=1700.0)
    assert all(item['station_id'] == 'final-pond' for item in prepared)
    assert prepared[1]['payload']['absent_seconds'] == 600.0
