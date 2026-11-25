from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
import math
from pathlib import Path
import random
import sqlite3
import time
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import RegisterSpec, Settings

LOGGER = logging.getLogger("pcc.pond_gateway")


class SensorReadError(RuntimeError):
    pass


class PublishError(RuntimeError):
    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


class SensorSource(Protocol):
    source_mode: str

    def read(self) -> dict[str, tuple[float, str]]: ...
    def close(self) -> None: ...


class MockPondSource:
    source_mode = "demo"

    def __init__(self, seed: int = 42) -> None:
        self._random = random.Random(seed)
        self._tick = 0

    def read(self) -> dict[str, tuple[float, str]]:
        self._tick += 1
        temperature = 32.0 + math.sin(self._tick / 8) * 0.35 + self._random.uniform(-0.08, 0.08)
        ph = 10.45 + math.sin(self._tick / 11) * 0.12 + self._random.uniform(-0.025, 0.025)
        return {"water_temperature": (round(temperature, 2), "good"), "water_ph": (round(ph, 2), "good")}

    def close(self) -> None:
        return None


class ModbusPondSource:
    source_mode = "live"

    def __init__(self, settings: Settings, client_factory: Callable[..., object] | None = None) -> None:
        if client_factory is None:
            try:
                from pymodbus.client import ModbusSerialClient
            except ImportError as exc:  # pragma: no cover - depends on production extra
                raise SensorReadError("pymodbus is not installed") from exc
            client_factory = ModbusSerialClient
        self._specs = (settings.temperature, settings.ph)
        self._client = client_factory(
            settings.serial_port,
            baudrate=settings.baudrate,
            bytesize=settings.bytesize,
            parity=settings.parity,
            stopbits=settings.stopbits,
            timeout=settings.serial_timeout_seconds,
            retries=2,
        )

    def _read_one(self, spec: RegisterSpec) -> tuple[float, str]:
        method = self._client.read_holding_registers if spec.register_type == "holding" else self._client.read_input_registers
        result = method(spec.address, count=1, device_id=spec.slave_id)
        if result is None or result.isError() or not getattr(result, "registers", None):
            raise SensorReadError(f"modbus read failed for {spec.metric}")
        value = spec.decode(int(result.registers[0]))
        quality = "good" if spec.physical_min <= value <= spec.physical_max else "bad"
        return value, quality

    def read(self) -> dict[str, tuple[float, str]]:
        try:
            connected = self._client.connect()
        except Exception as exc:
            raise SensorReadError(f"cannot connect to Modbus serial bus: {exc}") from exc
        if not connected:
            raise SensorReadError("cannot connect to Modbus serial bus")
        values: dict[str, tuple[float, str]] = {}
        errors: list[str] = []
        for spec in self._specs:
            try:
                values[spec.metric] = self._read_one(spec)
            except Exception as exc:  # keep the other sensor online
                errors.append(f"{spec.metric}: {exc}")
        if not values:
            raise SensorReadError("; ".join(errors) or "no sensor values")
        if errors:
            LOGGER.warning("partial_modbus_read errors=%s", errors)
        return values

    def close(self) -> None:
        self._client.close()


@dataclass(frozen=True)
class QueueItem:
    id: int
    payload: list[dict[str, object]]
    attempts: int


class TelemetrySpool:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.execute("pragma journal_mode=wal")
        self._db.executescript(
            """
            create table if not exists telemetry_queue (
              id integer primary key autoincrement,
              payload text not null,
              attempts integer not null default 0,
              next_attempt_at real not null default 0,
              last_error text,
              created_at text not null
            );
            create table if not exists telemetry_dead_letter (
              id integer primary key autoincrement,
              payload text not null,
              error text not null,
              failed_at text not null
            );
            """
        )
        self._db.commit()

    def enqueue(self, payload: list[dict[str, object]]) -> None:
        self._db.execute(
            "insert into telemetry_queue(payload, created_at) values (?, ?)",
            (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), datetime.now(UTC).isoformat()),
        )
        self._db.commit()

    def next_due(self, now: float | None = None) -> QueueItem | None:
        row = self._db.execute(
            "select id, payload, attempts from telemetry_queue where next_attempt_at <= ? order by id limit 1",
            (time.time() if now is None else now,),
        ).fetchone()
        return QueueItem(row[0], json.loads(row[1]), row[2]) if row else None

    def acknowledge(self, item_id: int) -> None:
        self._db.execute("delete from telemetry_queue where id = ?", (item_id,))
        self._db.commit()

    def retry(self, item: QueueItem, error: str, now: float | None = None) -> None:
        attempts = item.attempts + 1
        delay = min(300, 2 ** min(attempts, 8))
        self._db.execute(
            "update telemetry_queue set attempts = ?, next_attempt_at = ?, last_error = ? where id = ?",
            (attempts, (time.time() if now is None else now) + delay, error[:500], item.id),
        )
        self._db.commit()

    def dead_letter(self, item: QueueItem, error: str) -> None:
        with self._db:
            self._db.execute(
                "insert into telemetry_dead_letter(payload, error, failed_at) values (?, ?, ?)",
                (json.dumps(item.payload, ensure_ascii=False), error[:500], datetime.now(UTC).isoformat()),
            )
            self._db.execute("delete from telemetry_queue where id = ?", (item.id,))

    def queue_depth(self) -> int:
        return int(self._db.execute("select count(*) from telemetry_queue").fetchone()[0])

    def dead_letter_depth(self) -> int:
        return int(self._db.execute("select count(*) from telemetry_dead_letter").fetchone()[0])

    def close(self) -> None:
        self._db.close()


class PccTelemetryClient:
    def __init__(self, url: str, token: str, timeout: float) -> None:
        self.url = url
        self.token = token
        self.timeout = timeout

    def publish(self, payload: list[dict[str, object]]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(
            self.url,
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    raise PublishError(f"PCC returned HTTP {response.status}", permanent=400 <= response.status < 500)
        except HTTPError as exc:
            permanent = 400 <= exc.code < 500 and exc.code not in {408, 429}
            raise PublishError(f"PCC returned HTTP {exc.code}", permanent=permanent) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise PublishError(f"PCC unavailable: {exc}") from exc


def build_payload(settings: Settings, values: dict[str, tuple[float, str]], source_mode: str, measured_at: datetime | None = None) -> list[dict[str, object]]:
    measured = measured_at or datetime.now(UTC)
    measured_iso = measured.isoformat().replace("+00:00", "Z")
    received_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    units = {"water_temperature": settings.temperature.unit, "water_ph": settings.ph.unit}
    timestamp_id = int(measured.timestamp() * 1000)
    return [
        {
            "measurement_id": f"{settings.device_id}:{timestamp_id}:{metric}",
            "site_id": settings.site_id,
            "line_id": settings.line_id,
            "station_id": settings.station_id,
            "device_id": settings.device_id,
            "metric": metric,
            "value": value,
            "unit": units[metric],
            "measured_at": measured_iso,
            "received_at": received_iso,
            "quality": quality,
            "source_mode": source_mode,
        }
        for metric, (value, quality) in values.items()
    ]


class PondGateway:
    def __init__(self, settings: Settings, source: SensorSource, spool: TelemetrySpool, client: PccTelemetryClient) -> None:
        self.settings = settings
        self.source = source
        self.spool = spool
        self.client = client

    def sample(self) -> list[dict[str, object]]:
        payload = build_payload(self.settings, self.source.read(), self.source.source_mode)
        self.spool.enqueue(payload)
        return payload

    def flush(self, limit: int = 100) -> int:
        sent = 0
        for _ in range(limit):
            item = self.spool.next_due()
            if item is None:
                break
            try:
                self.client.publish(item.payload)
            except PublishError as exc:
                if exc.permanent:
                    self.spool.dead_letter(item, str(exc))
                    LOGGER.error("telemetry_dead_letter queue_id=%s error=%s", item.id, exc)
                    continue
                self.spool.retry(item, str(exc))
                LOGGER.warning("telemetry_retry queue_id=%s attempts=%s error=%s", item.id, item.attempts + 1, exc)
                break
            self.spool.acknowledge(item.id)
            sent += 1
        return sent

    def close(self) -> None:
        self.source.close()
        self.spool.close()
