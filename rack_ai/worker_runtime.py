"""In-memory health/result registry for independent camera AI workers.

The primary rack counter still runs in-process. Future PPE/activity workers can run
as separate processes or containers and publish a small heartbeat here. Video and
stream credentials never pass through this contract.
"""

import copy
import math
import threading
import time
from datetime import datetime, timezone

from .registry import CameraDefinition, unavailable_camera_status


class WorkerRuntimeRegistry:
    def __init__(self, stale_seconds: float, clock=time.monotonic):
        if stale_seconds <= 0:
            raise ValueError('worker stale timeout must be positive')
        self.stale_seconds = stale_seconds
        self.clock = clock
        self.lock = threading.Lock()
        self._heartbeats: dict[str, dict] = {}

    def update(self, camera: CameraDefinition, heartbeat: dict) -> dict:
        task_by_id = {task.task_id: task for task in camera.tasks}
        task_ids = set(task_by_id)
        supplied = [task.get('task_id') for task in heartbeat.get('tasks', [])]
        if len(supplied) != len(set(supplied)):
            raise ValueError('heartbeat task_id values must be unique')
        if set(supplied) != task_ids:
            raise ValueError('heartbeat tasks must exactly match the camera registry')
        for reported in heartbeat.get('tasks', []):
            latest = reported.get('latest')
            if latest is None:
                continue
            if not isinstance(latest, dict):
                raise ValueError('task latest result must be an object or null')
            definition = task_by_id[reported['task_id']]
            unexpected = set(latest) - set(definition.output_metrics)
            if unexpected:
                raise ValueError(f'task latest contains unregistered metrics: {sorted(unexpected)}')
            for metric, metric_value in latest.items():
                if not isinstance(metric_value, (str, int, float, bool, type(None))):
                    raise ValueError(f'task metric {metric} must be a scalar value')
                if isinstance(metric_value, float) and not math.isfinite(metric_value):
                    raise ValueError(f'task metric {metric} must be finite')
        value = copy.deepcopy(heartbeat)
        value['_received_monotonic'] = self.clock()
        value['updated_at'] = datetime.now(timezone.utc).isoformat()
        with self.lock:
            self._heartbeats[camera.camera_id] = value
        return self.status(camera)

    def status(self, camera: CameraDefinition) -> dict:
        with self.lock:
            heartbeat = copy.deepcopy(self._heartbeats.get(camera.camera_id))
        if heartbeat is None:
            return unavailable_camera_status(camera)

        age = max(0.0, self.clock() - heartbeat.pop('_received_monotonic'))
        fresh = age <= self.stale_seconds
        task_by_id = {task['task_id']: task for task in heartbeat.get('tasks', [])}
        tasks = []
        for task in camera.tasks:
            reported = task_by_id.get(task.task_id, {})
            tasks.append({
                **task.public(),
                'runtime_status': reported.get('runtime_status', 'unavailable') if fresh else 'unavailable',
                'model_version': reported.get('model_version'),
                'inference_fps': float(reported.get('inference_fps') or 0) if fresh else 0,
                'latest': reported.get('latest'),
            })

        online = fresh and heartbeat.get('camera_status') == 'online'
        running = online and any(task['runtime_status'] == 'running' for task in tasks)
        return {
            'camera_id': camera.camera_id,
            'name': camera.name,
            'station_id': camera.station_id,
            'location': camera.location,
            'lifecycle': camera.lifecycle,
            'camera_status': 'online' if online else 'offline',
            'data_status': 'live' if running else 'offline',
            'updated_at': heartbeat.get('updated_at'),
            'camera_fps': float(heartbeat.get('camera_fps') or 0) if online else 0,
            'heartbeat_age_seconds': round(age, 2),
            'tasks': tasks,
        }

    def summary(self, cameras: tuple[CameraDefinition, ...]) -> dict:
        statuses = [self.status(camera) for camera in cameras if camera.lifecycle == 'active']
        return {
            'registered': len(statuses),
            'online': sum(status['camera_status'] == 'online' for status in statuses),
            'live': sum(status['data_status'] == 'live' for status in statuses),
        }
