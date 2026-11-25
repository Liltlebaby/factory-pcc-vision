from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import unittest
import uuid

from pond_gateway.config import ConfigurationError, RegisterSpec, Settings
from pond_gateway.gateway import ModbusPondSource, TelemetrySpool, build_payload
from pond_gateway.main import _write_heartbeat, healthcheck


def settings(**overrides: str) -> Settings:
    values = {"PCC_TELEMETRY_TOKEN": "test-secret", "POND_GATEWAY_MODE": "mock", **overrides}
    return Settings.from_env(values)


class ConfigurationTests(unittest.TestCase):
    def test_register_mapping_is_configurable_and_decodes_signed_values(self) -> None:
        config = settings(POND_PH_SLAVE_ID="7", POND_PH_REGISTER_ADDRESS="12", POND_PH_SCALE="0.01")
        self.assertEqual(config.ph.slave_id, 7)
        self.assertEqual(config.ph.address, 12)
        signed = RegisterSpec("x", "x", 1, 0, "holding", 0.1, 0, True, -100, 100)
        self.assertEqual(signed.decode(0xFFF6), -1.0)

    def test_invalid_or_missing_safety_configuration_is_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"POND_GATEWAY_MODE": "modbus"})
        with self.assertRaises(ConfigurationError):
            settings(POND_PH_SLAVE_ID="0")
        with self.assertRaises(ConfigurationError):
            settings(POND_DEVICE_ID="invalid device id")
        with self.assertRaises(ConfigurationError):
            settings(PCC_TELEMETRY_URL="ftp://example.test/value")


class PayloadTests(unittest.TestCase):
    def test_payload_matches_pcc_contract_and_marks_mock_as_demo(self) -> None:
        measured = datetime(2026, 9, 22, 9, 30, tzinfo=UTC)
        payload = build_payload(settings(), {"water_ph": (10.42, "good"), "water_temperature": (32.1, "good")}, "demo", measured)
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["source_mode"], "demo")
        self.assertEqual(payload[0]["station_id"], "final-pond")
        self.assertTrue(str(payload[0]["measurement_id"]).endswith(":water_ph"))
        self.assertEqual(payload[1]["unit"], "°C")


class _Response:
    def __init__(self, raw: int, error: bool = False) -> None:
        self.registers = [raw]
        self._error = error

    def isError(self) -> bool:
        return self._error


class _FakeModbusClient:
    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[tuple[int, int, int]] = []
        self.closed = False

    def connect(self) -> bool:
        return True

    def read_holding_registers(self, address: int, *, count: int, device_id: int) -> _Response:
        self.calls.append((address, count, device_id))
        return _Response({0: 1042, 1: 321}[address])

    def read_input_registers(self, address: int, *, count: int, device_id: int) -> _Response:
        return self.read_holding_registers(address, count=count, device_id=device_id)

    def close(self) -> None:
        self.closed = True


class ModbusSourceTests(unittest.TestCase):
    def test_reads_each_configured_register_with_device_id_and_scale(self) -> None:
        clients: list[_FakeModbusClient] = []

        def factory(*args, **kwargs) -> _FakeModbusClient:
            client = _FakeModbusClient(*args, **kwargs)
            clients.append(client)
            return client

        source = ModbusPondSource(
            settings(POND_GATEWAY_MODE="modbus", POND_PH_SLAVE_ID="7", POND_TEMPERATURE_SLAVE_ID="8"),
            client_factory=factory,
        )
        values = source.read()
        self.assertEqual(values["water_ph"], (10.42, "good"))
        self.assertEqual(values["water_temperature"], (32.1, "good"))
        self.assertEqual(clients[0].calls, [(1, 1, 8), (0, 1, 7)])
        source.close()
        self.assertTrue(clients[0].closed)


class SpoolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_path = Path(__file__).parent / f".spool-{uuid.uuid4().hex}.sqlite3"
        self.spool = TelemetrySpool(str(self.database_path))

    def tearDown(self) -> None:
        self.spool.close()
        for suffix in ("", "-wal", "-shm"):
            Path(f"{self.database_path}{suffix}").unlink(missing_ok=True)

    def test_retry_keeps_same_payload_and_uses_backoff(self) -> None:
        payload = [{"measurement_id": "m-1"}]
        self.spool.enqueue(payload)
        item = self.spool.next_due(now=100)
        self.assertIsNotNone(item)
        assert item is not None
        self.spool.retry(item, "network down", now=100)
        self.assertIsNone(self.spool.next_due(now=101))
        retried = self.spool.next_due(now=102)
        self.assertEqual(retried.payload, payload)
        self.assertEqual(retried.attempts, 1)

    def test_permanent_error_moves_payload_to_dead_letter(self) -> None:
        self.spool.enqueue([{"measurement_id": "bad"}])
        item = self.spool.next_due(now=100)
        assert item is not None
        self.spool.dead_letter(item, "HTTP 400")
        self.assertEqual(self.spool.queue_depth(), 0)
        self.assertEqual(self.spool.dead_letter_depth(), 1)


class HeartbeatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path(__file__).parent / f".heartbeat-{uuid.uuid4().hex}.json"
        self.config = settings(POND_HEARTBEAT_PATH=str(self.path))

    def tearDown(self) -> None:
        self.path.unlink(missing_ok=True)

    def test_healthcheck_requires_fresh_ok_cycle(self) -> None:
        _write_heartbeat(self.config, status="ok", values=2, queue_depth=0, dead_letters=0)
        self.assertEqual(healthcheck(self.config), 0)
        _write_heartbeat(self.config, status="degraded", values=1, queue_depth=1, dead_letters=0, error="backlog")
        self.assertEqual(healthcheck(self.config), 1)


if __name__ == "__main__":
    unittest.main()
