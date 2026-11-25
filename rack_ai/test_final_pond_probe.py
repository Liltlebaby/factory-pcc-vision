"""เทสต์ส่วนคำนวณสัญญาณของ probe ด้วยภาพสังเคราะห์

ใช้ภาพที่รู้คำตอบอยู่แล้ว เพื่อยืนยันว่า `rise` เพิ่มขึ้นจริงเมื่อวัตถุยกสูงขึ้น
ถ้าตรงนี้ผิดทิศ การวัดหน้างานทั้งรอบจะเสียเปล่า และกว่าจะรู้ก็ต้องรอรอบตรวจใหม่
"""
import numpy as np
import pytest

from rack_ai.final_pond.probe import (
    CHANGE_THRESHOLD, crop, parse_roi, position_signals, reference_frame,
)


def blank(value=120, size=(100, 40)):
    return np.full(size, value, dtype=np.uint8)


def with_bar(top_row, height=20, value=250, size=(100, 40)):
    """วาดแท่งสว่างกินความกว้างทั้ง ROI เริ่มที่แถว top_row"""
    frame = blank(size=size)
    frame[top_row:top_row + height, :] = value
    return frame


def test_parse_roi_accepts_normalised_box():
    assert parse_roi('0.555,0.412,0.597,0.623') == (0.555, 0.412, 0.597, 0.623)


@pytest.mark.parametrize('text', ['0.5,0.5,0.4,0.9', '1.2,0,1.3,1', 'a,b,c,d', '0,0,1'])
def test_parse_roi_rejects_bad_input(text):
    with pytest.raises(ValueError):
        parse_roi(text)


def test_crop_uses_fractions_of_the_frame():
    frame = np.arange(100 * 200, dtype=np.uint8).reshape(100, 200)
    piece = crop(frame, (0.5, 0.5, 1.0, 1.0))
    assert piece.shape == (50, 100)


def test_crop_never_returns_an_empty_slice():
    """ROI แคบมากต้องยังได้อย่างน้อย 1 พิกเซล ไม่ใช่ array ว่างที่ทำให้พังทีหลัง"""
    frame = np.zeros((100, 200), dtype=np.uint8)
    piece = crop(frame, (0.10, 0.10, 0.1001, 0.1001))
    assert piece.shape[0] >= 1 and piece.shape[1] >= 1


def test_no_change_gives_zero_signal():
    reference = blank()
    signals = position_signals(reference.copy(), reference)
    assert signals['diff_ratio'] == 0.0
    assert signals['rise'] == 0.0


def test_rise_increases_as_the_object_moves_up():
    reference = blank()
    heights = [position_signals(with_bar(top), reference)['rise'] for top in (75, 50, 25, 0)]
    assert heights == sorted(heights), heights
    assert heights[0] < heights[-1]
    assert heights[-1] == pytest.approx(1.0)


def test_rise_measures_the_top_of_the_change_not_its_size():
    """แท่งสั้นที่อยู่สูง ต้องให้ค่ามากกว่าแท่งยาวที่อยู่ต่ำ"""
    reference = blank()
    tall_low = position_signals(with_bar(60, height=40), reference)
    short_high = position_signals(with_bar(10, height=5), reference)
    assert short_high['rise'] > tall_low['rise']
    assert short_high['diff_ratio'] < tall_low['diff_ratio']


def test_sensor_noise_below_threshold_is_ignored():
    reference = blank(120)
    noisy = blank(120 + CHANGE_THRESHOLD - 1)
    assert position_signals(noisy, reference)['diff_ratio'] == 0.0


def test_a_few_stray_pixels_do_not_lift_rise():
    """พิกเซลหลงไม่กี่จุดที่ขอบบนต้องไม่ดัน rise ขึ้นสุด"""
    reference = blank()
    frame = blank()
    frame[0, :3] = 255  # 3 จาก 40 พิกเซลของแถวบนสุด ต่ำกว่าเกณฑ์ครอบครองแถว
    assert position_signals(frame, reference)['rise'] == 0.0


def test_reference_is_robust_to_someone_standing_in_the_way():
    """คนยืนบังไม่กี่เฟรมต้องไม่ทำให้ภาพอ้างอิงเพี้ยน มัธยฐานจึงดีกว่าค่าเฉลี่ย"""
    rest = blank(120)
    blocked = blank(20)
    reference = reference_frame([rest] * 7 + [blocked] * 3)
    assert np.array_equal(reference, rest)
    assert position_signals(rest, reference)['diff_ratio'] == 0.0


def test_mismatched_shapes_are_rejected_loudly():
    with pytest.raises(ValueError, match='ขนาดเท่ากัน'):
        position_signals(blank(size=(50, 40)), blank(size=(100, 40)))


def test_reference_needs_at_least_one_frame():
    with pytest.raises(ValueError, match='ไม่มีเฟรม'):
        reference_frame([])


def test_signals_feed_the_state_machine_unchanged():
    """ต่อ probe เข้ากับ LeverStateMachine ด้วยลำดับสังเคราะห์ที่เลียนการยกคันโยก"""
    from rack_ai.final_pond.lever import LeverActivation, LeverStateMachine

    reference = blank()
    machine = LeverStateMachine(rest_below=0.2, check_above=0.65, hold_seconds=0.8)
    # แถวที่ 90 ของ 100 = rise ต่ำ, แถวที่ 20 = rise สูง
    script = [(90, 5), (55, 4), (20, 15), (90, 6)]
    events, clock = [], 0.0
    for top_row, repeats in script:
        for _ in range(repeats):
            rise = position_signals(with_bar(top_row, height=5), reference)['rise']
            event = machine.sample(clock, rise)
            if event is not None:
                events.append(event)
            clock += 0.1
    assert len(events) == 1 and isinstance(events[0], LeverActivation), events


# ---------- โหมดอ่านย้อนหลัง ----------

@pytest.mark.parametrize('source,target,expected', [
    (25.0, 5.0, 5), (25.0, 25.0, 1), (15.0, 5.0, 3),
    (25.0, 100.0, 1), (0.0, 5.0, 1), (None, 5.0, 1),
])
def test_stride_matches_the_requested_sample_rate(source, target, expected):
    from rack_ai.final_pond.probe import stride_for
    assert stride_for(source, target) == expected


def test_global_brightness_shift_is_not_movement():
    """กล้องปรับแสงทั้งภาพ ไม่ใช่การเคลื่อนไหว ต้องไม่ทำให้สัญญาณกระโดด"""
    reference = blank(110)
    brighter = blank(110 + CHANGE_THRESHOLD * 3)
    darker = blank(110 - CHANGE_THRESHOLD * 2)
    for frame in (brighter, darker):
        signals = position_signals(frame, reference)
        assert signals['diff_ratio'] == 0.0, signals
        assert signals['rise'] == 0.0, signals


def test_real_movement_still_detected_under_a_brightness_shift():
    """หักแสงออกแล้วต้องยังเห็นของที่ขยับจริง ไม่ใช่กลบไปทั้งหมด"""
    reference = blank(110)
    frame = with_bar(20, height=10, value=250, size=(100, 40))
    frame = np.clip(frame.astype(np.int16) + CHANGE_THRESHOLD * 2, 0, 255).astype(np.uint8)
    signals = position_signals(frame, reference)
    assert signals['rise'] > 0.7, signals
    assert signals['diff_ratio'] > 0.0
