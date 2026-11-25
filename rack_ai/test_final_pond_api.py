"""เทสต์ endpoint จริงผ่าน FastAPI TestClient

ส่วนที่เทสต์อื่นไม่ครอบคือการต่อสาย: pydantic model, route, และการแปลง
ValueError เป็น HTTP status ที่ถูกต้อง ถ้าตรงนี้ผิด worker จะได้ 422 ตลอด
โดยที่ตรรกะข้างในถูกหมด ซึ่งเป็นอาการที่หาสาเหตุยากที่สุดตอนอยู่หน้างาน

โมดูลหนักอย่าง cv2/ultralytics ถูกแทนด้วย stub เพราะ endpoint พวกนี้ไม่แตะ
กล้องเลย และเราส่ง service ปลอมเข้า create_app อยู่แล้ว
"""
import sys
import tempfile
import types
from datetime import datetime
from pathlib import Path

import pytest

for name in ('cv2', 'ultralytics', 'numpy'):
    if name not in sys.modules:
        try:
            __import__(name)
        except ImportError:
            module = types.ModuleType(name)
            module.__getattr__ = lambda attribute: types.SimpleNamespace()
            sys.modules[name] = module

from fastapi.testclient import TestClient  # noqa: E402

from rack_ai.app import create_app  # noqa: E402
from rack_ai.config import Settings  # noqa: E402
from rack_ai.registry import CAMERAS  # noqa: E402
from rack_ai.runtime import CountJournal  # noqa: E402
from rack_ai.shifts import BANGKOK  # noqa: E402
from rack_ai.final_pond.rounds import COMPLETED, MISSED, NO_DATA  # noqa: E402

CAMERA = 'final-pond-cam-01'


def at(hour, minute=0, day=22):
    return datetime(2026, 9, day, hour, minute, tzinfo=BANGKOK).timestamp()


class FakePipeline:
    """แทน RackService — endpoint ที่เทสต์ไม่แตะกล้องหรือโมเดล"""
    def __init__(self, root):
        self.journal = CountJournal(root)
        self.journal.store = None

    def snapshot(self):
        return {'running': False, 'camera': {}, 'fps': {}, 'timestamp': None}

    def start(self): pass
    def close(self): pass


@pytest.fixture
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as root:
        monkeypatch.setenv('CAMERA_RTSP_AI', 'rtsp://example.invalid/stream')
        monkeypatch.setenv('RACK_API_TOKEN', '')
        monkeypatch.setenv('RECORD_ROOT', str(Path(root) / 'rec'))
        monkeypatch.setenv('LAB_ROOT', str(Path(root) / 'lab'))
        # กล้องบ่อสุดท้ายในทะเบียนเป็น planned ต้องเปิดเป็น active ก่อน worker จึงส่งได้
        cameras = tuple(
            camera.__class__(**{**camera.__dict__, 'lifecycle': 'active'})
            if camera.camera_id == CAMERA else camera
            for camera in CAMERAS
        )
        app = create_app(Settings(), service=FakePipeline(Path(root) / 'lab'),
                         camera_definitions=cameras)
        yield TestClient(app)


def inspection(hour, day=22, weight=None, status=COMPLETED, source='unavailable'):
    completed = at(hour, 3, day=day)
    return {
        'task_id': 'magnet-inspection',
        'type': 'magnet_inspection',
        'occurred_at': completed,
        'event_id': f'{CAMERA}:magnet-inspection:{int(completed * 1_000_000)}',
        'payload': {
            'round_key': f'2026-09-{day:02d}T{hour:02d}',
            'inspection_status': status,
            'completed_at': completed,
            'weight_kg': weight,
            'weight_source': source,
            'lever_activated': True,
        },
    }


def test_planned_camera_cannot_post_events(monkeypatch):
    # ทะเบียนจริงยังเป็น planned สำหรับกล้องบ่อสุดท้าย worker ภายนอกจึงต้องถูกปฏิเสธ
    with tempfile.TemporaryDirectory() as root:
        monkeypatch.setenv('CAMERA_RTSP_AI', 'rtsp://example.invalid/stream')
        monkeypatch.setenv('RACK_API_TOKEN', '')
        monkeypatch.setenv('RECORD_ROOT', str(Path(root) / 'rec'))
        monkeypatch.setenv('LAB_ROOT', str(Path(root) / 'lab'))
        app = create_app(Settings(), service=FakePipeline(Path(root) / 'lab'), camera_definitions=CAMERAS)
        response = TestClient(app).post(f'/api/v1/workers/{CAMERA}/events',
                                        json={'events': [], 'coverage': [{'round_key': '2026-09-22T10', 'seconds': 60}]})
    assert response.status_code == 409
    assert response.json()['detail'] == 'camera_is_not_active'


def test_unknown_camera_is_404(client):
    response = client.post('/api/v1/workers/nope/events',
                           json={'coverage': [{'round_key': '2026-09-22T10', 'seconds': 60}]})
    assert response.status_code == 404


def test_primary_camera_is_rejected(client):
    response = client.post('/api/v1/workers/camera-09/events',
                           json={'coverage': [{'round_key': '2026-09-22T10', 'seconds': 60}]})
    assert response.status_code == 409


def test_empty_body_is_rejected(client):
    response = client.post(f'/api/v1/workers/{CAMERA}/events', json={'events': [], 'coverage': []})
    assert response.status_code == 422


def test_bad_round_key_is_rejected_by_the_model(client):
    response = client.post(f'/api/v1/workers/{CAMERA}/events',
                           json={'coverage': [{'round_key': '22/09/2026', 'seconds': 60}]})
    assert response.status_code == 422


def test_wrong_event_type_for_task_is_rejected(client):
    bad = inspection(10)
    bad['type'] = 'ppe_violation'
    response = client.post(f'/api/v1/workers/{CAMERA}/events', json={'events': [bad]})
    assert response.status_code == 422
    assert 'ชนิดเหตุการณ์' in response.json()['detail']


def test_events_and_coverage_store_and_report_back(client):
    payload = {
        'events': [inspection(8, day=20), inspection(9, day=20, weight=8.42, source='measured')],
        'coverage': [{'round_key': f'2026-09-20T{hour:02d}', 'seconds': 3600}
                     for hour in (8, 9, 10)],
    }
    stored = client.post(f'/api/v1/workers/{CAMERA}/events', json=payload)
    assert stored.status_code == 200, stored.text
    assert stored.json()['stored'] == 2

    report = client.get('/api/v1/final-pond/magnet-rounds', params={'date': '2026-09-20'})
    assert report.status_code == 200, report.text
    body = report.json()
    assert body['storage'] == 'ok'
    assert body['camera_id'] == CAMERA
    assert len(body['rounds']) == 25
    rows = {item['round_key']: item for item in body['rounds']}
    assert rows['2026-09-20T08']['status'] == COMPLETED
    assert rows['2026-09-20T09']['weight_kg'] == 8.42
    assert rows['2026-09-20T10']['status'] == MISSED
    assert rows['2026-09-20T12']['status'] == NO_DATA


def test_resent_batch_does_not_duplicate(client):
    payload = {'events': [inspection(8, day=20)],
               'coverage': [{'round_key': '2026-09-20T08', 'seconds': 1800}]}
    client.post(f'/api/v1/workers/{CAMERA}/events', json=payload)
    second = client.post(f'/api/v1/workers/{CAMERA}/events', json=payload)
    assert second.status_code == 200
    # coverage บวกสะสม ส่วนเหตุการณ์กันซ้ำด้วย event_id
    assert second.json()['coverage']['2026-09-20T08'] == 3600.0

    report = client.get('/api/v1/final-pond/magnet-rounds', params={'date': '2026-09-20'}).json()
    rows = {item['round_key']: item for item in report['rounds']}
    assert len(rows['2026-09-20T08']['inspections']) == 1


def test_history_for_several_days_is_independent(client):
    for day in (18, 19, 20):
        client.post(f'/api/v1/workers/{CAMERA}/events', json={
            'events': [inspection(10, day=day)],
            'coverage': [{'round_key': f'2026-09-{day}T10', 'seconds': 3600}],
        })
    for day in (18, 19, 20):
        body = client.get('/api/v1/final-pond/magnet-rounds',
                          params={'date': f'2026-09-{day}'}).json()
        assert body['tally'][COMPLETED] == 1, day
        rows = {item['round_key']: item for item in body['rounds']}
        assert rows[f'2026-09-{day}T10']['status'] == COMPLETED


def test_bad_date_parameter_is_rejected(client):
    assert client.get('/api/v1/final-pond/magnet-rounds', params={'date': '20-09-2026'}).status_code == 422


def test_day_without_data_reports_no_data(client):
    body = client.get('/api/v1/final-pond/magnet-rounds', params={'date': '2026-09-01'}).json()
    assert body['tally'][NO_DATA] == 25
    assert body['compliance'] is None
