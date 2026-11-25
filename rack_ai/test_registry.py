import unittest
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from rack_ai.app import create_app
from rack_ai.config import Settings
from rack_ai.registry import CAMERA_BY_ID, CAMERAS, load_camera_registry
from rack_ai.test_pipeline import FakeService
from rack_ai.worker_runtime import WorkerRuntimeRegistry


class FakePreview:
    enabled = True

    def __init__(self, jpeg=b'\xff\xd8preview\xff\xd9'):
        self.jpeg = jpeg

    def frame(self):
        return self.jpeg

    def stats(self):
        return {'connected': True, 'source_fps': 12.5, 'longest_gap_ms': 80,
                'last_frame_age': 0.1, 'reconnects': 0, 'resolution': '704x576'}

    def start(self):
        pass

    def close(self):
        pass


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.app = create_app(Settings(source="unused", model=Path("models/current-rack.pt")), self.service)
        self.client = TestClient(self.app)

    def test_registry_has_unique_camera_and_task_ids(self):
        self.assertEqual(len(CAMERAS), len(CAMERA_BY_ID))
        task_ids = [task.task_id for camera in CAMERAS for task in camera.tasks]
        self.assertEqual(len(task_ids), len(set(task_ids)))

    def test_camera_list_exposes_no_credentials(self):
        response = self.client.get("/api/v1/cameras")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 2)
        serialized = str(payload).lower()
        self.assertNotIn("rtsp", serialized)
        self.assertNotIn("token", serialized)

    def test_final_pond_preview_is_separate_from_planned_ai(self):
        app = create_app(
            Settings(source='unused', final_pond_source='rtsp://viewer:secret@192.168.1.64/Streaming/Channels/1102'),
            self.service, final_pond_preview=FakePreview(),
        )
        with TestClient(app) as client:
            cameras = client.get('/api/v1/cameras').json()['items']
            pond = next(item for item in cameras if item['camera_id'] == 'final-pond-cam-01')
            self.assertEqual(pond['preview_url'], '/api/v1/cameras/final-pond-cam-01/frame')
            self.assertEqual(pond['status']['data_status'], 'not_installed')
            self.assertNotIn('secret', str(cameras))
            frame = client.get(pond['preview_url'])
            self.assertEqual(frame.status_code, 200)
            self.assertEqual(frame.headers['content-type'], 'image/jpeg')
            self.assertEqual(frame.content, b'\xff\xd8preview\xff\xd9')
            self.assertEqual(client.get('/api/v1/cameras/unknown/frame').status_code, 404)

    def test_final_pond_ai_starts_without_viewer_and_serves_cached_result(self):
        class BackgroundPreview(FakePreview):
            started = False

            def start(self):
                self.started = True

        class BackgroundAi:
            enabled = True
            mode = 'ppe'
            model_path = Path('test-pee.pt')
            started = False
            closed = False

            def start(self, source):
                self.started = source.started

            def close(self):
                self.closed = True

            def status(self):
                return {'people_count': 1, 'helmet_pass': 1, 'no_helmet': 0, 'undecided': 0}

            def cached_frame(self):
                return b'cached-ai-jpeg'

            def frame(self, source_jpeg):
                raise AssertionError('Browser requests must not run inference')

        preview = BackgroundPreview()
        ai = BackgroundAi()
        app = create_app(Settings(source='unused'), self.service,
                         final_pond_preview=preview, final_pond_ai=ai)
        with TestClient(app) as client:
            self.assertTrue(ai.started)
            response = client.get('/api/v1/cameras/final-pond-cam-01/ai-frame')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b'cached-ai-jpeg')
            status = client.get('/api/v1/cameras/final-pond-cam-01/status').json()
            self.assertEqual(status['data_status'], 'pilot')
        self.assertTrue(ai.closed)

    def test_area_mode_reports_presence_task_and_leaves_helmet_task_planned(self):
        class AreaAi:
            enabled = True
            mode = 'area'
            model_path = Path('yolo11s_openvino_model')

            def start(self, source):
                pass

            def close(self):
                pass

            def status(self):
                return {'people_count': 2, 'workers_in_zone': 1, 'workers_in_pond': 1,
                        'filtered_out': 0, 'presence_status': 'attended',
                        'seconds_since_person': 0, 'unattended_alerts': 0,
                        'helmet_pass': 0, 'camera_online': True, 'inference_fps': 2.0}

            def evidence_path(self, name):
                return None

        app = create_app(Settings(source='unused'), self.service,
                         final_pond_preview=FakePreview(), final_pond_ai=AreaAi())
        with TestClient(app) as client:
            status = client.get('/api/v1/cameras/final-pond-cam-01/status').json()
            tasks = {task['task_id']: task for task in status['tasks']}
            presence = tasks['work-area-presence']
            self.assertEqual(presence['runtime_status'], 'pilot')
            self.assertEqual(presence['model_version'], 'yolo11s_openvino_model')
            self.assertEqual(presence['latest']['workers_in_zone'], 1)
            self.assertEqual(presence['latest']['presence_status'], 'attended')
            self.assertNotIn('helmet_pass', presence['latest'])
            # helmet stays "not installed" until a trained helmet model exists
            self.assertEqual(tasks['ppe-helmet']['runtime_status'], 'not_installed')
            self.assertIsNone(tasks['ppe-helmet']['latest'])
            self.assertEqual(client.get('/api/v1/final-pond/evidence/missing.jpg').status_code, 404)

    def test_registry_file_rejects_stream_credentials(self):
        payload = {
            "cameras": [{
                "camera_id": "unsafe-camera",
                "name": "Unsafe",
                "station_id": "test-station",
                "location": "Test",
                "lifecycle": "planned",
                "rtsp": "rtsp://user:password@example.test/stream",
                "tasks": [{
                    "task_id": "unsafe-task",
                    "name": "Unsafe task",
                    "task_type": "test",
                    "station_id": "test-station",
                    "lifecycle": "planned",
                    "output_metrics": ["status"],
                }],
            }],
        }
        with patch.object(Path, "read_text", return_value=json.dumps(payload)):
            with self.assertRaisesRegex(ValueError, "credentials"):
                load_camera_registry(Path("unused.json"))

    def test_active_secondary_camera_is_offline_until_runtime_is_available(self):
        secondary = replace(CAMERAS[1], lifecycle="active")
        app = create_app(
            Settings(source="unused", model=Path("models/current-rack.pt")),
            self.service,
            camera_definitions=(CAMERAS[0], secondary),
        )
        with TestClient(app) as client:
            payload = client.get(f"/api/v1/cameras/{secondary.camera_id}/status").json()
        self.assertEqual(payload["camera_status"], "offline")
        self.assertEqual(payload["data_status"], "offline")
        self.assertEqual(payload["tasks"][0]["runtime_status"], "unavailable")

    def test_secondary_worker_heartbeat_makes_camera_live(self):
        helmet = next(task for task in CAMERAS[1].tasks if task.task_id == "ppe-helmet")
        active_task = replace(helmet, lifecycle="active")
        secondary = replace(CAMERAS[1], lifecycle="active", tasks=(active_task,))
        app = create_app(
            Settings(source="unused", model=Path("models/current-rack.pt")),
            self.service,
            camera_definitions=(CAMERAS[0], secondary),
        )
        heartbeat = {
            "camera_status": "online",
            "camera_fps": 15.0,
            "tasks": [{
                "task_id": active_task.task_id,
                "runtime_status": "running",
                "model_version": "helmet-v1.pt",
                "inference_fps": 9.5,
                "latest": {"people_count": 1, "helmet_pass": 1},
            }],
        }
        with TestClient(app) as client:
            response = client.put(f"/api/v1/workers/{secondary.camera_id}/heartbeat", json=heartbeat)
            self.assertEqual(response.status_code, 200)
            payload = client.get(f"/api/v1/cameras/{secondary.camera_id}/status").json()
        self.assertEqual(payload["camera_status"], "online")
        self.assertEqual(payload["data_status"], "live")
        self.assertEqual(payload["tasks"][0]["model_version"], "helmet-v1.pt")
        self.assertEqual(payload["tasks"][0]["latest"]["helmet_pass"], 1)

    def test_worker_heartbeat_rejects_unknown_task(self):
        active_task = replace(CAMERAS[1].tasks[0], lifecycle="active")
        secondary = replace(CAMERAS[1], lifecycle="active", tasks=(active_task,))
        app = create_app(
            Settings(source="unused", model=Path("models/current-rack.pt")),
            self.service,
            camera_definitions=(CAMERAS[0], secondary),
        )
        with TestClient(app) as client:
            response = client.put(f"/api/v1/workers/{secondary.camera_id}/heartbeat", json={
                "camera_status": "online",
                "tasks": [{"task_id": "wrong-task", "runtime_status": "running"}],
            })
        self.assertEqual(response.status_code, 422)

    def test_worker_heartbeat_rejects_unregistered_payload_fields(self):
        active_task = replace(CAMERAS[1].tasks[0], lifecycle="active")
        secondary = replace(CAMERAS[1], lifecycle="active", tasks=(active_task,))
        app = create_app(
            Settings(source="unused", model=Path("models/current-rack.pt")),
            self.service,
            camera_definitions=(CAMERAS[0], secondary),
        )
        with TestClient(app) as client:
            response = client.put(f"/api/v1/workers/{secondary.camera_id}/heartbeat", json={
                "camera_status": "online",
                "tasks": [{
                    "task_id": active_task.task_id,
                    "runtime_status": "running",
                    "latest": {"assessment_status": "compliant", "frame": "base64-image"},
                }],
            })
        self.assertEqual(response.status_code, 422)
        self.assertIn("unregistered metrics", response.json()["detail"])

    def test_worker_heartbeat_becomes_offline_after_timeout(self):
        now = [100.0]
        runtime = WorkerRuntimeRegistry(5, clock=lambda: now[0])
        active_task = replace(CAMERAS[1].tasks[0], lifecycle="active")
        secondary = replace(CAMERAS[1], lifecycle="active", tasks=(active_task,))
        runtime.update(secondary, {
            "camera_status": "online",
            "camera_fps": 12,
            "tasks": [{"task_id": active_task.task_id, "runtime_status": "running"}],
        })
        self.assertEqual(runtime.status(secondary)["data_status"], "live")
        now[0] += 6
        stale = runtime.status(secondary)
        self.assertEqual(stale["camera_status"], "offline")
        self.assertEqual(stale["data_status"], "offline")
        self.assertEqual(stale["tasks"][0]["runtime_status"], "unavailable")

    def test_system_links_exposes_configured_pcc_destination(self):
        app = create_app(
            Settings(source="unused", model=Path("models/current-rack.pt"), pcc_url="https://pcc.factory.test"),
            self.service,
        )
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/v1/system-links").json(), {"pcc": "https://pcc.factory.test"})

    def test_invalid_pcc_url_is_rejected(self):
        with self.assertRaises(ValueError):
            Settings(pcc_url="javascript:alert(1)")

    def test_current_camera_status_maps_legacy_counter(self):
        response = self.client.get("/api/v1/cameras/camera-09/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["camera_id"], "camera-09")
        self.assertEqual(payload["station_id"], "rack-infeed")
        self.assertEqual(payload["tasks"][0]["latest"]["rack_count"], 3)

    def test_station_contract_has_no_video_payload(self):
        response = self.client.get("/api/v1/stations/rack-infeed/ai-status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data_status"], "live")
        self.assertEqual(len(payload["cameras"]), 1)
        serialized = str(payload).lower()
        self.assertNotIn("jpeg", serialized)
        self.assertNotIn("preview", serialized)
        self.assertNotIn("frame_id", serialized)

    def test_final_pond_reports_only_the_pond_camera(self):
        response = self.client.get("/api/v1/stations/final-pond/ai-status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data_status"], "not_installed")
        # the separate work-status camera was removed from the registry on 2026-10-05
        self.assertEqual([item["camera_id"] for item in payload["cameras"]], ["final-pond-cam-01"])
        camera = payload["cameras"][0]
        self.assertEqual(camera["station_id"], "final-pond")
        self.assertEqual(camera["lifecycle"], "planned")
        self.assertEqual(camera["tasks"][0]["task_id"], "work-area-presence")
        self.assertEqual(camera["tasks"][0]["runtime_status"], "not_installed")

    def test_unknown_station_reports_no_camera(self):
        response = self.client.get("/api/v1/stations/unknown-station/ai-status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cameras"], [])

    def test_unknown_camera_is_404(self):
        self.assertEqual(self.client.get("/api/v1/cameras/missing/status").status_code, 404)

    def test_event_api_is_empty_when_service_has_no_journal(self):
        response = self.client.get("/api/v1/events?cursor=0&limit=25&station_id=rack-infeed")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [], "next_cursor": 0, "has_more": False})


if __name__ == "__main__":
    unittest.main()
