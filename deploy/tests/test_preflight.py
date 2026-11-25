from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path


DEPLOY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPLOY_DIR))

from preflight import parse_env, summarize, validate_config  # noqa: E402


class PreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).parent
        self.created_files: list[Path] = []
        model = self.root / f"fixture-rack-{uuid.uuid4().hex}.pt"
        model.write_bytes(b"weights")
        self.created_files.append(model)
        self.env = {
            "PUBLIC_VISION_MONITOR_URL": "https://vision.factory.local",
            "PCC_PUBLIC_URL": "https://pcc.factory.local",
            "PCC_ORIGINS": "https://pcc.factory.local,https://vision.factory.local",
            "RACK_MODEL_FILE": model.name,
            "SUPABASE_URL": "https://factory.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_" + "a" * 40,
            "NEXT_PUBLIC_SUPABASE_URL": "https://factory.supabase.co",
            "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_" + "b" * 40,
            "RACK_API_TOKEN": "c" * 40,
            "PCC_SYNC_TOKEN": "d" * 40,
            "PCC_TELEMETRY_TOKEN": "e" * 40,
            "CAMERA_RTSP_AI": "rtsp://camera-user:secret@nvr.local:554/camera09",
            "PCC_AUTH_REQUIRED": "true",
        }

    def tearDown(self) -> None:
        for path in self.created_files:
            path.unlink(missing_ok=True)

    def codes(self, *, with_pond: bool = False) -> list[str]:
        return [item.code for item in validate_config(self.env, project_root=self.root, with_pond=with_pond)]

    def test_valid_base_configuration_passes(self) -> None:
        self.assertEqual(self.codes(), [])

    def test_parser_supports_comments_export_and_quotes(self) -> None:
        path = self.root / f"fixture-{uuid.uuid4().hex}.env"
        self.created_files.append(path)
        path.write_text("# note\nexport ALPHA='one'\nBETA=two=three\n", encoding="utf-8")
        self.assertEqual(parse_env(path), {"ALPHA": "one", "BETA": "two=three"})

    def test_parser_rejects_malformed_lines(self) -> None:
        path = self.root / f"fixture-{uuid.uuid4().hex}.env"
        self.created_files.append(path)
        path.write_text("NOT_AN_ASSIGNMENT\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "line 1"):
            parse_env(path)

    def test_placeholders_weak_and_reused_secrets_fail(self) -> None:
        self.env["RACK_API_TOKEN"] = "replace-me"
        self.env["PCC_SYNC_TOKEN"] = self.env["PCC_TELEMETRY_TOKEN"]
        codes = self.codes()
        self.assertIn("placeholder", codes)
        self.assertIn("weak_secret", codes)
        self.assertIn("reused_secret", codes)

    def test_insecure_public_url_and_disabled_auth_fail(self) -> None:
        self.env["PCC_PUBLIC_URL"] = "http://pcc.factory.local"
        self.env["PCC_AUTH_REQUIRED"] = "false"
        codes = self.codes()
        self.assertIn("invalid_url", codes)
        self.assertIn("auth_disabled", codes)

    def test_invalid_local_health_port_fails_before_network_check(self) -> None:
        self.env["PCC_PORT"] = "80@outside.example"
        self.assertIn("invalid_port", self.codes())

    def test_missing_model_and_supabase_mismatch_fail(self) -> None:
        self.env["RACK_MODEL_FILE"] = "models/missing.pt"
        self.env["NEXT_PUBLIC_SUPABASE_URL"] = "https://other.supabase.co"
        codes = self.codes()
        self.assertIn("model_missing", codes)
        self.assertIn("supabase_mismatch", codes)

    def test_valid_pond_configuration_passes_on_windows(self) -> None:
        self.env.update(
            {
                "POND_PH_SLAVE_ID": "1",
                "POND_PH_REGISTER_TYPE": "holding",
                "POND_PH_REGISTER_ADDRESS": "0",
                "POND_PH_SCALE": "0.01",
                "POND_TEMPERATURE_SLAVE_ID": "1",
                "POND_TEMPERATURE_REGISTER_TYPE": "input",
                "POND_TEMPERATURE_REGISTER_ADDRESS": "1",
                "POND_TEMPERATURE_SCALE": "0.1",
                "POND_SERIAL_DEVICE_HOST": "COM3" if sys.platform == "win32" else str(self.root),
            }
        )
        self.assertEqual(self.codes(with_pond=True), [])

    def test_invalid_pond_registers_are_rejected(self) -> None:
        self.env.update(
            {
                "POND_PH_SLAVE_ID": "0",
                "POND_PH_REGISTER_TYPE": "coil",
                "POND_PH_REGISTER_ADDRESS": "40001",
                "POND_PH_SCALE": "0",
                "POND_TEMPERATURE_SLAVE_ID": "248",
                "POND_TEMPERATURE_REGISTER_TYPE": "input",
                "POND_TEMPERATURE_REGISTER_ADDRESS": "not-a-number",
                "POND_TEMPERATURE_SCALE": "nan",
                "POND_SERIAL_DEVICE_HOST": "",
            }
        )
        codes = self.codes(with_pond=True)
        self.assertIn("pond_slave", codes)
        self.assertIn("pond_register_type", codes)
        self.assertIn("pond_register", codes)
        self.assertIn("pond_scale", codes)
        self.assertIn("pond_serial", codes)

    def test_summary_does_not_include_secret_values(self) -> None:
        self.env["RACK_API_TOKEN"] = "short"
        findings = validate_config(self.env, project_root=self.root)
        self.assertEqual(summarize(findings)["errors"], len(findings))
        rendered = " ".join(item.message for item in findings)
        self.assertNotIn("short", rendered)


if __name__ == "__main__":
    unittest.main()
