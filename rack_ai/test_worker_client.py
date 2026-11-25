import json
import threading
import unittest
from unittest.mock import patch

from rack_ai.worker_client import WorkerClientSettings, WorkerHeartbeatClient, load_provider


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return b'{"data_status":"live"}'


class WorkerClientTests(unittest.TestCase):
    def test_settings_reject_invalid_url_and_camera_id(self):
        with self.assertRaises(ValueError):
            WorkerClientSettings(api_url='not-a-url', camera_id='camera-1')
        with self.assertRaises(ValueError):
            WorkerClientSettings(api_url='https://vision.example', camera_id='../camera')

    def test_publish_uses_scoped_endpoint_and_bearer_token(self):
        settings = WorkerClientSettings(
            api_url='https://vision.example/base',
            camera_id='ppe-camera',
            token='secret-token',
        )
        client = WorkerHeartbeatClient(settings)
        heartbeat = {'camera_status': 'online', 'tasks': []}
        with patch('rack_ai.worker_client.urlopen', return_value=FakeResponse()) as opened:
            response = client.publish(heartbeat)
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, 'https://vision.example/base/api/v1/workers/ppe-camera/heartbeat')
        self.assertEqual(request.method, 'PUT')
        self.assertEqual(request.headers['Authorization'], 'Bearer secret-token')
        self.assertEqual(json.loads(request.data), heartbeat)
        self.assertEqual(response['data_status'], 'live')

    def test_once_publishes_exactly_one_heartbeat(self):
        client = WorkerHeartbeatClient(WorkerClientSettings(camera_id='worker-camera'))
        provider_calls = []
        with patch.object(client, 'publish', return_value={'data_status': 'live'}) as publish:
            client.run(lambda: provider_calls.append(True) or {'camera_status': 'online'}, threading.Event(), once=True)
        self.assertEqual(len(provider_calls), 1)
        publish.assert_called_once()

    def test_provider_loader_validates_specification(self):
        with self.assertRaises(ValueError):
            load_provider('missing-separator')
        provider = load_provider('json:dumps')
        self.assertTrue(callable(provider))


if __name__ == '__main__':
    unittest.main()
