"""เทสต์การแปลงกล่องจากโมเดลเป็นผลว่าใส่หมวกหรือไม่

ความผิดพลาดที่อันตรายที่สุดของชั้นนี้คือการตีความ "มองไม่เห็นหมวก" ว่าเป็น
"ไม่ใส่หมวก" เพราะมันทำให้ระบบฟ้องคนที่ใส่หมวกอยู่ เทสต์ส่วนใหญ่จึงพิสูจน์ว่า
กรณีที่ไม่มีหลักฐานชัดต้องออกมาเป็น UNDECIDED ไม่ใช่ VIOLATION
"""
import pytest

from rack_ai.final_pond.ppe import HelmetMonitor, HelmetViolation
from rack_ai.final_pond.vision import (
    PASS, UNDECIDED, VIOLATION, Box, Detection, classify_helmet, observe_frame, summarise,
)

FRAME_HEIGHT = 1296


def person(x=1000, y=400, width=120, height=300):
    return Box(x, y, x + width, y + height)


def head_box(label, subject, confidence=0.9, shift=0.0):
    """กล่องศีรษะที่ทับช่วงบนของกล่องคน"""
    middle = (subject.x1 + subject.x2) / 2
    size = subject.width * 0.55
    top = subject.y1 + subject.height * 0.02 + shift
    return Detection(label, Box(middle - size / 2, top, middle + size / 2, top + size), confidence)


# ---------- ไม่มีหลักฐาน = ไม่ตัดสิน ----------

def test_no_head_boxes_at_all_is_undecided():
    """โมเดลมองไม่เห็นศีรษะ ไม่ได้แปลว่าคนไม่ใส่หมวก"""
    assert classify_helmet(person(), []) == (UNDECIDED, 0.0)


def test_unrelated_labels_do_not_decide_anything():
    subject = person()
    noise = [Detection('vest', subject, 0.95), Detection('boots', subject, 0.9)]
    assert classify_helmet(subject, noise)[0] == UNDECIDED


def test_a_helmet_on_someone_else_does_not_count():
    """หมวกของคนที่ยืนข้าง ๆ ต้องไม่ถูกนับเป็นหมวกของคนนี้

    ถ้าพลาดข้อนี้ ระบบจะบอกว่าทุกคนใส่หมวก ตราบใดที่มีใครสักคนในเฟรมใส่อยู่
    """
    me = person(x=1000)
    neighbour = person(x=1400)
    assert classify_helmet(me, [head_box('helmet', neighbour)])[0] == UNDECIDED


def test_a_helmet_box_at_the_feet_does_not_count():
    """หมวกที่วางอยู่กับพื้นข้างเท้า ไม่ใช่หมวกที่สวมอยู่"""
    subject = person()
    floor = Detection('helmet', Box(subject.x1, subject.y2 - 40, subject.x2, subject.y2), 0.9)
    assert classify_helmet(subject, [floor])[0] == UNDECIDED


def test_conflicting_boxes_of_similar_confidence_stay_undecided():
    """โมเดลเห็นทั้งหมวกและหัวเปล่าด้วยความมั่นใจพอ ๆ กัน = ตัดสินด้วยส่วนต่างที่ไร้ความหมาย"""
    subject = person()
    both = [head_box('helmet', subject, 0.71), head_box('head', subject, 0.68)]
    assert classify_helmet(subject, both)[0] == UNDECIDED


# ---------- มีหลักฐานชัด = ตัดสินได้ ----------

def test_helmet_in_the_head_region_passes():
    subject = person()
    status, confidence = classify_helmet(subject, [head_box('helmet', subject, 0.88)])
    assert status == PASS and confidence == 0.88


def test_bare_head_in_the_head_region_is_a_violation():
    subject = person()
    status, confidence = classify_helmet(subject, [head_box('head', subject, 0.83)])
    assert status == VIOLATION and confidence == 0.83


def test_a_clear_winner_between_conflicting_boxes_decides():
    subject = person()
    both = [head_box('helmet', subject, 0.92), head_box('head', subject, 0.40)]
    assert classify_helmet(subject, both)[0] == PASS


@pytest.mark.parametrize('label', ['hardhat', 'Hard-Hat', 'SAFETY-HELMET', 'with_helmet'])
def test_helmet_label_spellings_are_accepted(label):
    """ชุดน้ำหนักแต่ละชุดตั้งชื่อคลาสไม่เหมือนกัน ต้องรองรับหลายแบบ"""
    subject = person()
    assert classify_helmet(subject, [head_box(label, subject)])[0] == PASS


@pytest.mark.parametrize('label', ['head', 'bare_head', 'no-helmet', 'NO_HELMET', 'without_helmet'])
def test_bare_head_label_spellings_are_accepted(label):
    subject = person()
    assert classify_helmet(subject, [head_box(label, subject)])[0] == VIOLATION


# ---------- ทั้งเฟรม ----------

def test_each_person_is_judged_from_their_own_head():
    wearing = person(x=600)
    bare = person(x=1200)
    detections = [head_box('helmet', wearing, 0.9), head_box('head', bare, 0.9)]
    people = [(1, wearing, 0.9), (2, bare, 0.9)]
    found = {item.track_id: item for item in observe_frame(FRAME_HEIGHT, people, detections)}
    assert found[1].helmet_status == PASS
    assert found[2].helmet_status == VIOLATION


def test_height_ratio_is_relative_to_the_frame():
    subject = person(height=259)
    found = observe_frame(FRAME_HEIGHT, [(1, subject, 0.9)], [])[0]
    assert found.height_ratio == pytest.approx(0.20, abs=0.005)


def test_summary_keeps_undecided_separate_from_the_counts():
    """helmet_pass + no_helmet น้อยกว่า people ได้ ส่วนต่างคือคนที่ตัดสินไม่ได้"""
    a, b, c = person(x=400), person(x=800), person(x=1200)
    detections = [head_box('helmet', a, 0.9), head_box('head', b, 0.9)]
    people = [(1, a, 0.9), (2, b, 0.9), (3, c, 0.9)]
    totals = summarise(observe_frame(FRAME_HEIGHT, people, detections))
    assert totals == {'people': 3, 'helmet_pass': 1, 'no_helmet': 1, 'undecided': 1}


def test_an_empty_frame_summarises_to_zero():
    assert summarise([]) == {'people': 0, 'helmet_pass': 0, 'no_helmet': 0, 'undecided': 0}


def test_frame_height_must_be_positive():
    with pytest.raises(ValueError):
        observe_frame(0, [], [])


# ---------- ต่อกับชั้นกฎ ----------

def test_undecided_frames_never_become_a_violation():
    """ต่อ vision เข้ากับ ppe จริง: คนหันหลังทั้งนาทีต้องไม่ถูกฟ้อง"""
    subject = person()
    monitor = HelmetMonitor(confirm_seconds=2.5, confirm_samples=8)
    events = []
    for index in range(300):
        found = observe_frame(FRAME_HEIGHT, [(1, subject, 0.9)], [])[0]
        if found.decided:
            event = monitor.observe(index * 0.2, found.track_id, found.helmet,
                                    found.height_ratio, found.confidence)
            if event is not None:
                events.append(event)
    assert events == []


def test_a_genuinely_bare_head_does_become_a_violation():
    """และเมื่อมีหลักฐานชัดจริง ต้องฟ้องได้ ไม่ใช่เงียบไปทั้งหมด"""
    subject = person()
    detections = [head_box('head', subject, 0.9)]
    monitor = HelmetMonitor(confirm_seconds=2.5, confirm_samples=8)
    events = []
    for index in range(40):
        found = observe_frame(FRAME_HEIGHT, [(1, subject, 0.9)], detections)[0]
        if found.decided:
            event = monitor.observe(index * 0.2, found.track_id, found.helmet,
                                    found.height_ratio, found.confidence)
            if event is not None:
                events.append(event)
    assert len(events) == 1 and isinstance(events[0], HelmetViolation)


def test_turning_away_mid_count_does_not_reset_the_clock():
    """เห็นหัวเปล่า แล้วหันหลัง แล้วหันกลับมา เวลาที่นับไว้ต้องไม่หาย"""
    subject = person()
    bare = [head_box('head', subject, 0.9)]
    monitor = HelmetMonitor(confirm_seconds=2.5, confirm_samples=8)
    events = []
    script = [(bare, 6), ([], 15), (bare, 4)]   # เห็น 1.2 วิ → หันหลัง 3 วิ → เห็นอีก
    clock = 0.0
    for detections, count in script:
        for _ in range(count):
            found = observe_frame(FRAME_HEIGHT, [(1, subject, 0.9)], detections)[0]
            if found.decided:
                event = monitor.observe(clock, found.track_id, found.helmet,
                                        found.height_ratio, found.confidence)
                if event is not None:
                    events.append(event)
            clock += 0.2
    assert len(events) == 1, 'ช่วงที่ตัดสินไม่ได้ต้องไม่ล้างเวลาที่สะสมไว้'
