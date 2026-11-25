"""เทสต์การต่อภาพเข้ากับกฎ โดยใช้ตัวตรวจปลอม ไม่ต้องมีกล้องหรือโมเดล

จุดที่เทสต์ชุดนี้เฝ้าเป็นพิเศษคือรอยต่อ — แต่ละโมดูลถูกทดสอบแยกมาแล้ว
บั๊กที่เหลือจึงมักอยู่ตรงที่เอามาต่อกัน เช่น ลืมแยกกรณีกล้องดับ
หรือเอาคนที่ตัดสินไม่ได้ไปนับเป็นคนที่อยู่ในพื้นที่
"""
import pytest

from rack_ai.final_pond.ppe import HelmetMonitor
from rack_ai.final_pond.presence import PresenceMonitor
from rack_ai.final_pond.vision import Box, Detection, observe_frame
from rack_ai.final_pond.worker import PRESENCE_TASK_ID, TASK_ID, FinalPondWorker

MINUTE = 60.0
FRAME = object()          # worker ไม่แตะเนื้อในเฟรม แค่ส่งต่อให้ vision
FRAME_HEIGHT = 1296


class FakeVision:
    """คืนผลที่กำหนดไว้ล่วงหน้า เพื่อควบคุมสถานการณ์ได้ทุกเฟรม"""
    def __init__(self):
        self.people, self.detections = [], []

    def set(self, people, detections=()):
        self.people, self.detections = people, list(detections)

    def observe(self, frame):
        return observe_frame(FRAME_HEIGHT, self.people, self.detections)


def person(x=1000, height=300):
    return Box(x, 400, x + 120, 400 + height)


def head(label, subject, confidence=0.9):
    middle = (subject.x1 + subject.x2) / 2
    size = subject.width * 0.55
    return Detection(label, Box(middle - size / 2, subject.y1 + 5,
                                middle + size / 2, subject.y1 + 5 + size), confidence)


@pytest.fixture
def setup():
    vision = FakeVision()
    worker = FinalPondWorker(
        camera_id='final-pond-cam-01',
        vision=vision,
        helmet=HelmetMonitor(confirm_seconds=2.5, confirm_samples=8),
        presence=PresenceMonitor(absent_seconds=10 * MINUTE),
    )
    return worker, vision


def run_frames(worker, count, start=0.0, step=0.2):
    events = []
    for index in range(count):
        events.extend(worker.handle_frame(start + index * step, FRAME))
    return events


def test_a_bare_head_produces_one_violation_event(setup):
    worker, vision = setup
    subject = person()
    vision.set([(1, subject, 0.9)], [head('head', subject)])
    events = run_frames(worker, 40)
    assert [event['type'] for event in events] == ['ppe_violation']
    assert events[0]['task_id'] == TASK_ID
    assert events[0]['payload']['track_id'] == 1
    assert 'event_id' in events[0], 'ต้องมี event_id คงที่ เพื่อกันแถวซ้ำตอนส่งใหม่'


def test_a_helmet_produces_nothing(setup):
    worker, vision = setup
    subject = person()
    vision.set([(1, subject, 0.9)], [head('helmet', subject)])
    assert run_frames(worker, 60) == []


def test_undecided_people_produce_nothing(setup):
    """โมเดลมองไม่เห็นศีรษะเลยทั้งนาที ต้องไม่มีการฟ้อง"""
    worker, vision = setup
    vision.set([(1, person(), 0.9)], [])
    assert run_frames(worker, 300) == []


def test_a_present_worker_never_triggers_the_absence_rule(setup):
    worker, vision = setup
    subject = person()
    vision.set([(1, subject, 0.9)], [head('helmet', subject)])
    events = run_frames(worker, 400, step=5.0)     # ราว 33 นาที
    assert [event for event in events if event['type'] == 'station_unattended'] == []


def test_an_empty_frame_triggers_the_absence_rule(setup):
    worker, vision = setup
    vision.set([], [])
    events = run_frames(worker, 200, step=5.0)     # ราว 16 นาที
    unattended = [event for event in events if event['type'] == 'station_unattended']
    assert len(unattended) == 1
    assert unattended[0]['payload']['absent_seconds'] >= 10 * MINUTE
    # การไม่มีคนเป็นงานเฝ้าพื้นที่ ไม่ใช่งานหมวก
    assert unattended[0]['task_id'] == PRESENCE_TASK_ID


def test_a_dead_camera_never_triggers_the_absence_rule(setup):
    """frame=None คือมองไม่เห็น ต้องไม่กลายเป็น 'คนงานไม่อยู่'"""
    worker, _ = setup
    events = []
    for index in range(400):
        events.extend(worker.handle_frame(index * 5.0, None))
    assert events == []
    assert worker.presence_latest['presence_status'] == 'blind'
    assert worker.presence_latest['seconds_since_person'] is None


def test_a_tiny_distant_figure_does_not_count_as_someone_present(setup):
    """คนเล็กเกินกว่าจะตัดสินได้ ต้องไม่รีเซ็ตนาฬิกาการหายไป

    ไม่งั้นเงาหรือกล่องหลอกเล็ก ๆ ที่โผล่มาเป็นครั้งคราวจะกลบการหายจริงตลอดกาล
    """
    worker, vision = setup
    vision.set([(1, person(height=20), 0.9)], [])   # สูง 1.5% ของเฟรม
    events = run_frames(worker, 200, step=5.0)
    assert len([e for e in events if e['type'] == 'station_unattended']) == 1


def test_returning_closes_the_alert(setup):
    worker, vision = setup
    vision.set([], [])
    run_frames(worker, 200, step=5.0)
    subject = person()
    vision.set([(1, subject, 0.9)], [head('helmet', subject)])
    events = run_frames(worker, 5, start=1100.0, step=5.0)
    assert [event['type'] for event in events] == ['station_attended']


def test_snapshot_matches_the_registered_metrics(setup):
    worker, vision = setup
    subject = person()
    vision.set([(1, subject, 0.9)], [head('head', subject)])
    run_frames(worker, 20)
    from rack_ai.registry import CAMERA_BY_ID
    tasks = {t.task_id: t for t in CAMERA_BY_ID['final-pond-cam-01'].tasks}
    assert set(worker.latest) == set(tasks[TASK_ID].output_metrics)
    assert set(worker.presence_latest) <= set(tasks[PRESENCE_TASK_ID].output_metrics)


def test_presence_runs_without_a_helmet_model(setup):
    """งานเฝ้าพื้นที่ต้องรายงานผลได้ แม้ยังไม่มีโมเดลหมวก — เหตุผลที่แยกงานออกมา"""
    worker, vision = setup
    worker.helmet_model_ready = False
    vision.set([(1, person(), 0.9)], [])
    run_frames(worker, 5)
    tasks = {task['task_id']: task for task in worker.heartbeat(True, 2.0, 2.0, 'yolo11s')['tasks']}
    assert tasks[PRESENCE_TASK_ID]['runtime_status'] == 'running'
    assert tasks[PRESENCE_TASK_ID]['latest']['presence_status'] == 'attended'
    assert tasks[TASK_ID]['runtime_status'] == 'unavailable'
    assert tasks[TASK_ID]['latest'] is None


def test_heartbeat_shape_is_accepted_by_the_runtime_registry(setup):
    """ยิง heartbeat จริงเข้า WorkerRuntimeRegistry เพื่อพิสูจน์ว่าไม่โดน 422"""
    worker, vision = setup
    subject = person()
    vision.set([(1, subject, 0.9)], [head('helmet', subject)])
    run_frames(worker, 20)

    from rack_ai.registry import CAMERA_BY_ID
    from rack_ai.worker_runtime import WorkerRuntimeRegistry

    camera = CAMERA_BY_ID['final-pond-cam-01']
    runtime = WorkerRuntimeRegistry(stale_seconds=15)
    status = runtime.update(camera, worker.heartbeat(True, 3.0, 3.0, 'best.pt'))
    assert status['camera_status'] == 'online'
    assert status['tasks'][0]['runtime_status'] == 'running'


def test_events_pass_the_ingest_validator(setup):
    """เหตุการณ์ที่ worker สร้าง ต้องบันทึกได้จริง ไม่ใช่แค่หน้าตาถูก"""
    worker, vision = setup
    subject = person()
    vision.set([(1, subject, 0.9)], [head('head', subject)])
    events = run_frames(worker, 40)

    from rack_ai.final_pond.ingest import normalise_events
    from rack_ai.registry import CAMERA_BY_ID

    prepared = normalise_events(CAMERA_BY_ID['final-pond-cam-01'], events, now=events[-1]['occurred_at'] + 1)
    assert prepared[0]['station_id'] == 'final-pond'
    assert prepared[0]['rule_version'] == 'final-pond-people-v1'


def test_missing_configuration_fails_loudly(monkeypatch):
    """ตั้งค่าไม่ครบต้องหยุดทันที ไม่ใช่รันไปเงียบ ๆ โดยไม่ตรวจอะไรเลย"""
    from rack_ai.final_pond.worker import settings_from_env
    monkeypatch.delenv('FINAL_POND_RTSP', raising=False)
    monkeypatch.delenv('FINAL_POND_PERSON_MODEL', raising=False)
    with pytest.raises(SystemExit, match='FINAL_POND_RTSP'):
        settings_from_env()


def test_heartbeat_declares_every_task_the_camera_has(setup):
    """Vision Monitor ปฏิเสธ heartbeat ที่รายงานงานไม่ครบ

    กล้องตัวนี้มีสองงาน แต่ worker ทำได้งานเดียว ถ้าลืมรายงานอีกงาน
    ระบบจะขึ้นว่ากล้องออฟไลน์ตลอดโดยไม่มีอะไรบอกว่าเพราะอะไร
    """
    worker, _ = setup
    from rack_ai.registry import CAMERA_BY_ID

    camera = CAMERA_BY_ID['final-pond-cam-01']
    reported = {task['task_id'] for task in worker.heartbeat(True, 3.0, 3.0, None)['tasks']}
    assert reported == {task.task_id for task in camera.tasks}


def test_the_unimplemented_task_is_reported_as_unavailable_not_running(setup):
    """รายงานว่ามีอยู่ได้ แต่ห้ามอ้างว่ากำลังทำงาน ไม่งั้นหน้าจอจะโกหก"""
    worker, _ = setup
    tasks = {task['task_id']: task for task in worker.heartbeat(True, 3.0, 3.0, None)['tasks']}
    assert tasks['magnet-inspection']['runtime_status'] == 'unavailable'
    assert tasks['magnet-inspection']['latest'] is None
