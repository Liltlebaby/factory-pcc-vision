"""เทสต์ส่วนสรุปผลของเครื่องมือวัด — ไม่ต้องมีโมเดลหรือภาพ"""
from rack_ai.final_pond.check import report


def row(people, helmet_pass=0, no_helmet=0, undecided=None):
    undecided = people - helmet_pass - no_helmet if undecided is None else undecided
    return {'frame': 'x.jpg', 'people': people, 'helmet_pass': helmet_pass,
            'no_helmet': no_helmet, 'undecided': undecided}


def test_empty_input_does_not_divide_by_zero():
    assert report([])['decided_ratio'] is None


def test_frames_without_people_do_not_distort_the_ratio():
    """เฟรมที่ไม่มีคนต้องไม่ถูกนับเป็น 'ตัดสินไม่ได้' เพราะไม่มีอะไรให้ตัดสิน"""
    totals = report([row(0), row(0), row(2, helmet_pass=2)])
    assert totals['empty_frames'] == 2
    assert totals['people_total'] == 2
    assert totals['decided_ratio'] == 1.0


def test_ratio_counts_people_not_frames():
    totals = report([row(4, helmet_pass=1, no_helmet=1), row(1)])
    assert totals['people_total'] == 5
    assert totals['decided'] == 2
    assert totals['undecided'] == 3
    assert totals['decided_ratio'] == 0.4


def test_people_per_frame_includes_empty_frames():
    assert report([row(2), row(0)])['people_per_frame'] == 1.0
