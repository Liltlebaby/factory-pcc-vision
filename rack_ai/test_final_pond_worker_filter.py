"""ตัวกรองกล่อง "คน" ของกล้องบ่อสุดท้าย

เคสในไฟล์นี้อ้างอิงภาพจริงจากกล้อง 11 (28 ก.ย. 2569) ที่โมเดลนำร่องตีความ
รถโฟล์คลิฟต์เป็นคนด้วยคะแนน 0.29 และเสา/เครื่องจักรด้วย 0.32 ขณะที่คนจริง
ในภาพเดียวกันได้ 0.72 — กรอบภาพ 958x557
"""
from rack_ai.final_pond.pilot import (
    DEFAULT_WORKER_FILTER, WorkerFilter, draw_detections, split_workers, workers_in_pond,
)
from rack_ai.final_pond.vision import Box, Detection

FRAME = (557, 958, 3)


def worker(x1, y1, x2, y2, confidence, label='person'):
    return Detection(label, Box(x1, y1, x2, y2), confidence)


# กล่องจากภาพจริง
REAL_PERSON = worker(757, 160, 790, 250, 0.72)         # คนเสื้อม่วง ยืนข้างบ่อ
FORKLIFT = worker(297, 44, 580, 150, 0.29)             # รถโฟล์คลิฟต์มุมซ้ายบน
PILLAR = worker(633, 255, 865, 545, 0.32)              # เสา/เครื่องจักรฝั่งขวา


def test_the_real_worker_is_kept():
    kept, rejected = split_workers([REAL_PERSON], FRAME)
    assert len(kept) == 1 and rejected == []


def test_the_two_false_boxes_from_the_real_frame_are_rejected():
    kept, rejected = split_workers([REAL_PERSON, FORKLIFT, PILLAR], FRAME)
    assert [item.confidence for item in kept] == [0.72]
    assert {reason for _, reason in rejected} == {'confidence'}


def test_a_confident_but_machine_sized_box_is_rejected_by_height():
    # กล่องสูงเกินครึ่งภาพไม่ใช่คนในมุมกล้องนี้ ถึงโมเดลจะมั่นใจก็ตาม
    machine = worker(100, 30, 400, 520, 0.90)
    kept, rejected = split_workers([machine], FRAME)
    assert kept == [] and rejected[0][1] == 'too_large'


def test_a_box_wider_than_tall_is_rejected():
    conveyor = worker(100, 300, 600, 380, 0.80)
    kept, rejected = split_workers([conveyor], FRAME)
    assert kept == [] and rejected[0][1] == 'too_wide'


def test_a_speck_is_rejected():
    speck = worker(400, 300, 410, 312, 0.80)
    kept, rejected = split_workers([speck], FRAME)
    assert kept == [] and rejected[0][1] == 'too_small'


def test_non_person_labels_are_not_counted_as_workers():
    kept, rejected = split_workers([Detection('helmet', Box(760, 160, 780, 175), 0.9)], FRAME)
    assert kept == [] and rejected == []


def test_thresholds_can_be_loosened_without_touching_code():
    """ลดเกณฑ์คะแนนแล้วกล่องคะแนนต่ำกลับมา แต่รูปทรงยังคัดของที่เป็นไปไม่ได้อยู่

    รถโฟล์คลิฟต์กว้าง 283 สูง 106 กว้างกว่าสูง 2.7 เท่า จึงยังถูกตัดด้วยรูปทรง
    ต่อให้ลดเกณฑ์คะแนนลงจนรับกล่อง 0.29 ก็ตาม
    """
    loose = WorkerFilter(confidence=0.2)
    kept, rejected = split_workers([REAL_PERSON, FORKLIFT, PILLAR], FRAME, loose)
    assert sorted(item.confidence for item in kept) == [0.32, 0.72]
    assert [reason for _, reason in rejected] == ['too_wide']


def test_presence_count_uses_the_filter_so_machines_do_not_reset_the_timer():
    # กล่องหลอกที่มั่นใจเกินเกณฑ์ presence แต่ใหญ่เกินจริง ต้องไม่นับเป็นคนในบ่อ
    machine_in_zone = worker(200, 30, 500, 500, 0.80)
    assert workers_in_pond([machine_in_zone], FRAME) == 0
    assert workers_in_pond([worker(400, 300, 430, 390, 0.80)], FRAME) == 1


def test_counts_report_how_many_boxes_were_filtered_out():
    class FakeImage:
        shape = FRAME

        def copy(self):
            return self

    calls = {}

    class FakeCv2:
        FONT_HERSHEY_SIMPLEX = 0
        LINE_AA = 16
        IMWRITE_JPEG_QUALITY = 1

        def rectangle(self, *a, **k): calls.setdefault('rectangle', 0)
        def putText(self, *a, **k): calls.setdefault('putText', 0)
        def getTextSize(self, *a, **k): return ((40, 10), 3)

    import sys
    sys.modules['cv2'] = FakeCv2()
    try:
        _, counts = draw_detections(FakeImage(), [REAL_PERSON, FORKLIFT, PILLAR])
    finally:
        del sys.modules['cv2']
    assert counts['people_count'] == 1
    assert counts['filtered_out'] == 2


def test_default_filter_matches_documented_values():
    assert DEFAULT_WORKER_FILTER.confidence == 0.45
    assert DEFAULT_WORKER_FILTER.max_height_ratio == 0.75
