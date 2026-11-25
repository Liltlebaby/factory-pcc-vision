"""Small SDK used by out-of-process camera AI workers."""

import importlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

log = logging.getLogger('vision.worker')
HeartbeatProvider = Callable[[], dict]


@dataclass(frozen=True)
class WorkerClientSettings:
    api_url: str = field(default_factory=lambda: os.getenv('VISION_API_URL', 'http://127.0.0.1:8011'))
    camera_id: str = field(default_factory=lambda: os.getenv('VISION_CAMERA_ID', ''))
    token: str = field(default_factory=lambda: os.getenv('VISION_API_TOKEN', ''))
    interval_seconds: float = field(default_factory=lambda: float(os.getenv('VISION_HEARTBEAT_SECONDS', '5')))
    timeout_seconds: float = field(default_factory=lambda: float(os.getenv('VISION_HEARTBEAT_TIMEOUT_SECONDS', '5')))

    def __post_init__(self):
        parsed = urlparse(self.api_url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ValueError('VISION_API_URL must be an absolute http(s) URL')
        if not self.camera_id or not all(character.isalnum() or character in '-_' for character in self.camera_id):
            raise ValueError('VISION_CAMERA_ID must contain only letters, numbers, hyphens, or underscores')
        if not 1 <= self.interval_seconds <= 60 or not 1 <= self.timeout_seconds <= 30:
            raise ValueError('invalid worker heartbeat timing')


class WorkerHeartbeatClient:
    def __init__(self, settings: WorkerClientSettings):
        self.settings = settings

    def publish(self, heartbeat: dict) -> dict:
        endpoint = (
            f"{self.settings.api_url.rstrip('/')}/api/v1/workers/"
            f"{quote(self.settings.camera_id, safe='')}/heartbeat"
        )
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.settings.token:
            headers['Authorization'] = f'Bearer {self.settings.token}'
        request = Request(
            endpoint,
            data=json.dumps(heartbeat, ensure_ascii=False, separators=(',', ':')).encode('utf-8'),
            headers=headers,
            method='PUT',
        )
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                return json.loads(response.read().decode('utf-8'))
        except HTTPError as exc:
            raise RuntimeError(f'heartbeat rejected with HTTP {exc.code}') from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError('Vision Monitor heartbeat endpoint is unavailable') from exc

    def run(self, provider: HeartbeatProvider, stop: threading.Event, once: bool = False):
        while not stop.is_set():
            try:
                response = self.publish(provider())
                log.info(
                    'worker_heartbeat camera_id=%s data_status=%s',
                    self.settings.camera_id,
                    response.get('data_status'),
                )
            except Exception as exc:
                log.warning(
                    'worker_heartbeat_failed camera_id=%s error_type=%s',
                    self.settings.camera_id,
                    type(exc).__name__,
                )
            if once:
                return
            stop.wait(self.settings.interval_seconds)


def load_provider(specification: str) -> HeartbeatProvider:
    """Load `package.module:function`; the function must return a heartbeat dict."""
    module_name, separator, attribute_name = specification.partition(':')
    if not separator or not module_name or not attribute_name:
        raise ValueError('VISION_WORKER_PROVIDER must use package.module:function')
    provider = getattr(importlib.import_module(module_name), attribute_name, None)
    if not callable(provider):
        raise ValueError('VISION_WORKER_PROVIDER target must be callable')
    return provider
