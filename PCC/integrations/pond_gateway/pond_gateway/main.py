from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import sys
import time

from .config import ConfigurationError, Settings
from .gateway import MockPondSource, ModbusPondSource, PccTelemetryClient, PondGateway, SensorReadError, TelemetrySpool, build_payload


def _write_heartbeat(settings: Settings, *, status: str, values: int, queue_depth: int, dead_letters: int, error: str | None = None) -> None:
    path = Path(settings.heartbeat_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "source_mode": "live" if settings.mode == "modbus" else "demo",
        "last_cycle_at": datetime.now(UTC).isoformat(),
        "values": values,
        "queue_depth": queue_depth,
        "dead_letters": dead_letters,
        "last_error": error,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def healthcheck(settings: Settings) -> int:
    try:
        payload = json.loads(Path(settings.heartbeat_path).read_text(encoding="utf-8"))
        last_cycle = datetime.fromisoformat(payload["last_cycle_at"])
        age = (datetime.now(UTC) - last_cycle).total_seconds()
        maximum_age = max(30.0, settings.sample_interval_seconds * 3)
        return 0 if age <= maximum_age and payload.get("status") == "ok" else 1
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return 1


def build_gateway(settings: Settings) -> PondGateway:
    source = ModbusPondSource(settings) if settings.mode == "modbus" else MockPondSource()
    spool = TelemetrySpool(settings.spool_path)
    client = PccTelemetryClient(settings.pcc_url, settings.telemetry_token, settings.request_timeout_seconds)
    return PondGateway(settings, source, spool, client)


def run_once(gateway: PondGateway, settings: Settings, *, dry_run: bool = False) -> int:
    try:
        if dry_run:
            payload = build_payload(settings, gateway.source.read(), gateway.source.source_mode)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            sent = 0
        else:
            payload = gateway.sample()
            sent = gateway.flush()
        queue_depth = gateway.spool.queue_depth()
        dead_letters = gateway.spool.dead_letter_depth()
        healthy = len(payload) == 2 and queue_depth == 0 and dead_letters == 0
        _write_heartbeat(
            settings,
            status="ok" if healthy else "degraded",
            values=len(payload),
            queue_depth=queue_depth,
            dead_letters=dead_letters,
            error=None if healthy else "partial_sensor_read_or_telemetry_backlog",
        )
        logging.getLogger("pcc.pond_gateway").info("cycle_%s values=%s sent_batches=%s queue_depth=%s dead_letters=%s", "ok" if healthy else "degraded", len(payload), sent, queue_depth, dead_letters)
        return 0
    except SensorReadError as exc:
        _write_heartbeat(
            settings,
            status="degraded",
            values=0,
            queue_depth=gateway.spool.queue_depth(),
            dead_letters=gateway.spool.dead_letter_depth(),
            error=str(exc),
        )
        logging.getLogger("pcc.pond_gateway").error("sensor_read_failed error=%s", exc)
        return 2


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="PCC final-pond RS485/Modbus gateway")
    parser.add_argument("--once", action="store_true", help="sample once and exit")
    parser.add_argument("--dry-run", action="store_true", help="print telemetry without sending to PCC")
    parser.add_argument("--check-config", action="store_true", help="validate environment and exit")
    parser.add_argument("--healthcheck", action="store_true", help="check heartbeat freshness")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        logging.error("invalid_configuration error=%s", exc)
        return 64
    if args.check_config:
        print(f"configuration_ok mode={settings.mode} station={settings.station_id} device={settings.device_id}")
        return 0
    if args.healthcheck:
        return healthcheck(settings)
    gateway = build_gateway(settings)
    try:
        if args.once or args.dry_run:
            return run_once(gateway, settings, dry_run=args.dry_run)
        while True:
            started = time.monotonic()
            run_once(gateway, settings)
            time.sleep(max(0.1, settings.sample_interval_seconds - (time.monotonic() - started)))
    except KeyboardInterrupt:
        return 0
    finally:
        gateway.close()


if __name__ == "__main__":
    sys.exit(main())
