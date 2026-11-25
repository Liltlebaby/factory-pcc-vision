"""ทดสอบค่าที่ตั้งจากหน้างานจริง ด้วยสัญญาณจริงที่บันทึกไว้

ต่างจากเทสต์อื่นที่ใช้ภาพสังเคราะห์ ชุดนี้ใช้ตัวเลขที่วัดมาจากกล้องจริง
ตอนมีคนงานมาทำงานที่คันโยกเมื่อ 19 ก.ย. 2026 ถ้าแก้ตรรกะแล้วชุดนี้ไม่ผ่าน
แปลว่าเหตุการณ์ที่เคยตรวจได้จะตรวจไม่ได้อีก ซึ่งเป็นการถดถอยที่เทสต์สังเคราะห์
มองไม่เห็น เพราะข้อมูลจริงมีเสียงรบกวนและจังหวะที่คิดเองไม่ออก
"""
from rack_ai.final_pond.lever import LeverAbandoned, LeverActivation, LeverStateMachine
from rack_ai.final_pond.tuning import DIFF_RATIO, LEVER_ROI, LEVER_SETTINGS, SAMPLE_INTERVAL
from rack_ai.final_pond.probe import parse_roi


def replay(**overrides):
    settings = {**LEVER_SETTINGS, **overrides}
    machine = LeverStateMachine(**settings)
    events = []
    for index, value in enumerate(DIFF_RATIO):
        event = machine.sample(index * SAMPLE_INTERVAL, min(1.0, value))
        if event is not None:
            events.append(event)
    return events


def test_the_recorded_visit_is_detected_exactly_once():
    found = [event for event in replay() if isinstance(event, LeverActivation)]
    assert len(found) == 1, found
    assert found[0].held_seconds >= LEVER_SETTINGS['hold_seconds']
    assert found[0].peak_position > 0.5


def test_the_small_aftershock_is_rejected():
    """หลังคนงานถอยออก มีจังหวะกระเพื่อมเล็ก ๆ ที่ต้องไม่นับเป็นการตรวจซ้ำ"""
    rejected = [event for event in replay() if isinstance(event, LeverAbandoned)]
    assert len(rejected) == 1, rejected
    assert rejected[0].peak_position < 0.5


def test_quiet_stretches_produce_nothing():
    """ช่วงที่ไม่มีใครอยู่ต้องเงียบสนิท ไม่ใช่แค่ไม่ผ่านเกณฑ์"""
    quiet = [value for value in DIFF_RATIO if value < 0.08]
    assert len(quiet) > 150, 'ชุดข้อมูลต้องมีช่วงเงียบมากพอจึงจะพิสูจน์อะไรได้'
    machine = LeverStateMachine(**LEVER_SETTINGS)
    assert all(machine.sample(index * SAMPLE_INTERVAL, value) is None
               for index, value in enumerate(quiet))


def test_thresholds_sit_between_the_measured_noise_and_the_measured_event():
    """เกณฑ์ต้องอยู่ระหว่างค่ารบกวนกับค่าจริงที่วัดได้ ไม่ใช่ชิดด้านใดด้านหนึ่ง"""
    assert 0.091 < LEVER_SETTINGS['rest_below'] < LEVER_SETTINGS['check_above'] < 0.674
    # เผื่อระยะจากยอดจริงอย่างน้อยสองเท่า เพื่อให้วันที่แสงหรือมุมเปลี่ยนไปยังจับได้
    assert LEVER_SETTINGS['check_above'] * 2 < 0.674


def test_detection_survives_a_moderate_shift_in_thresholds():
    """ถ้าขยับเกณฑ์ขึ้นลงพอสมควรแล้วยังเจอครั้งเดียว แปลว่าไม่ได้ฟิตกับข้อมูลชุดนี้เกินไป"""
    for rest, check in ((0.08, 0.20), (0.10, 0.30), (0.12, 0.25)):
        found = [event for event in replay(rest_below=rest, check_above=check)
                 if isinstance(event, LeverActivation)]
        assert len(found) == 1, (rest, check, found)


def test_roi_is_a_valid_normalised_box():
    assert parse_roi(','.join(str(value) for value in LEVER_ROI)) == LEVER_ROI
