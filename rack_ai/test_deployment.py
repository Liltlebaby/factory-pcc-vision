import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent


class ProductionComposeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = yaml.safe_load((ROOT / 'docker-compose.production.yml').read_text(encoding='utf-8'))
        cls.services = cls.compose['services']

    def test_required_services_restart_automatically(self):
        self.assertEqual(set(self.services), {'vision-monitor', 'pcc', 'rack-event-sync', 'pond-gateway'})
        for service in self.services.values():
            self.assertEqual(service['restart'], 'unless-stopped')

    def test_web_ports_are_bound_to_loopback_only(self):
        for name in ('vision-monitor', 'pcc'):
            ports = self.services[name]['ports']
            self.assertTrue(ports)
            self.assertTrue(all(str(port).startswith('127.0.0.1:') for port in ports))

    def test_model_mount_is_read_only_and_runtime_data_is_persistent(self):
        volumes = self.services['vision-monitor']['volumes']
        self.assertTrue(any(str(volume).endswith('/models/rack-production.pt:ro') for volume in volumes))
        self.assertIn('rack_ai_data:/app/rack_ai/data', volumes)
        self.assertIn('rack_ai_data', self.compose['volumes'])

    def test_secrets_are_scoped_to_services_that_need_them(self):
        vision_environment = self.services['vision-monitor']['environment']
        pcc_environment = self.services['pcc']['environment']
        sync_environment = self.services['rack-event-sync']['environment']
        self.assertNotIn('SUPABASE_SECRET_KEY', vision_environment)
        self.assertNotIn('CAMERA_RTSP_AI', pcc_environment)
        self.assertEqual(set(sync_environment), {'PCC_SYNC_TOKEN', 'SYNC_INTERVAL_SECONDS'})

    def test_healthchecks_and_startup_dependencies_exist(self):
        self.assertIn('healthcheck', self.services['vision-monitor'])
        self.assertIn('healthcheck', self.services['pcc'])
        self.assertIn('healthcheck', self.services['rack-event-sync'])
        self.assertEqual(
            self.services['pcc']['depends_on']['vision-monitor']['condition'],
            'service_healthy',
        )
        self.assertEqual(
            self.services['rack-event-sync']['depends_on']['pcc']['condition'],
            'service_healthy',
        )

    def test_sync_job_uses_dedicated_worker_with_logged_results(self):
        sync = self.services['rack-event-sync']
        self.assertEqual(sync['build']['context'], './deploy')
        self.assertEqual(sync['build']['dockerfile'], 'Dockerfile.sync')
        self.assertNotIn('entrypoint', sync)
        self.assertEqual(sync['healthcheck']['test'], ['CMD', 'node', 'rack-sync.mjs', '--healthcheck'])
        script = (ROOT / 'deploy' / 'rack-sync.mjs').read_text(encoding='utf-8')
        self.assertIn('rack_sync_complete', script)
        self.assertIn('rack_sync_failed', script)
        self.assertIn('rack_sync_unreachable', script)


if __name__ == '__main__':
    unittest.main()
