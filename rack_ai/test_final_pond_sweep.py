"""เทสต์การจัดอันดับผลการกวาด — ไม่ต้องมีโมเดล"""
from rack_ai.final_pond.sweep import rank


def row(label, people, seconds, empty=0):
    return {'label': label, 'people': people, 'seconds': seconds, 'empty': empty}


def test_more_people_wins():
    ordered = rank([row('a', 10, 5.0), row('b', 40, 90.0), row('c', 25, 8.0)])
    assert [item['label'] for item in ordered] == ['b', 'c', 'a']


def test_speed_breaks_a_tie():
    """เจอเท่ากันให้เลือกตัวที่เร็วกว่า เพราะจะต้องรันตลอด 24 ชั่วโมง"""
    ordered = rank([row('slow', 30, 120.0), row('fast', 30, 12.0)])
    assert [item['label'] for item in ordered] == ['fast', 'slow']


def test_empty_input_is_safe():
    assert rank([]) == []
