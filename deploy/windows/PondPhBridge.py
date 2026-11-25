"""Forward calibrated ESP32 pond readings to the local PCC telemetry API.

The board is polled directly; the former server is never used as a source.
Only fresh Modbus readings are queued. No substitute values are generated.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


BOARD_URL = os.getenv("POND_BOARD_URL", "http://192.168.1.9/status")
PCC_URL = os.getenv("POND_PCC_URL", "http://127.0.0.1:3000/api/v1/telemetry")
ENV_FILE = Path(os.getenv("POND_PCC_ENV_FILE", r"C:\Factory\123\PCC\.env.local"))
STATE_DIR = Path(os.getenv("POND_BRIDGE_STATE_DIR", r"C:\Factory\123\service_state"))
DB_PATH = STATE_DIR / "pond_ph_bridge.sqlite3"
LOG_PATH = STATE_DIR / "pond_ph_bridge.log"
INTERVAL = 10
LOGGER = logging.getLogger("pond_ph_bridge")


def configure_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOGGER.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)


def read_token() -> str:
    matches = []
    for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("PCC_TELEMETRY_TOKEN="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            matches.append(value)
    if len(matches) != 1 or not matches[0]:
        raise RuntimeError("PCC_TELEMETRY_TOKEN is missing or duplicated")
    return matches[0]


def board_status() -> dict:
    with urlopen(Request(BOARD_URL, headers={"Accept": "application/json"}), timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"board returned HTTP {response.status}")
        status = json.load(response)
    if not isinstance(status, dict):
        raise RuntimeError("board status is not an object")
    return status


def validated_sample(status: dict) -> tuple[str, int, int, int, float, float]:
    if status.get("device_id") != "pond-esp32-01" or status.get("station_id") != "final-pond":
        raise RuntimeError("unexpected board identity")
    if status.get("fresh") is not True or status.get("ph_valid") is not True:
        raise RuntimeError("board measurement is stale or invalid")
    if status.get("pcc", {}).get("source_mode") != "live":
        raise RuntimeError("board is not in calibrated live mode")
    if status.get("modbus", {}).get("error") is not None:
        raise RuntimeError("board reports a Modbus error")
    age_ms = status.get("age_ms")
    reads = status.get("modbus", {}).get("reads")
    uptime_ms = status.get("diagnostic", {}).get("uptime_ms")
    ph = status.get("ph")
    temperature = status.get("temperature_c")
    if any(type(value) is not int for value in (age_ms, reads, uptime_ms)):
        raise RuntimeError("board timing or read count is invalid")
    if not 0 <= age_ms <= 10_000 or reads < 1 or uptime_ms < 0:
        raise RuntimeError("board measurement age or read count is invalid")
    if any(type(value) not in (int, float) for value in (ph, temperature)):
        raise RuntimeError("board pH or temperature is not numeric")
    if not 0 <= ph <= 14 or not -10 <= temperature <= 100:
        raise RuntimeError("board pH or temperature is outside physical limits")
    return status["device_id"], reads, uptime_ms, age_ms, float(ph), float(temperature)


def open_db() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.execute("pragma journal_mode=wal")
    db.executescript(
        """
        create table if not exists state (
          id integer primary key check(id = 1),
          boot_id text not null,
          last_reads integer not null,
          last_uptime_ms integer not null
        );
        create table if not exists pending (
          id integer primary key autoincrement,
          payload text not null,
          created_at text not null
        );
        """
    )
    db.commit()
    return db


def queue_sample(db: sqlite3.Connection, sample: tuple[str, int, int, int, float, float]) -> bool:
    device, reads, uptime_ms, age_ms, ph, temperature = sample
    row = db.execute("select boot_id, last_reads, last_uptime_ms from state where id = 1").fetchone()
    if row is None or uptime_ms < row[2] or reads < row[1]:
        boot_id = uuid4().hex[:12]
    else:
        boot_id = row[0]
        if reads == row[1]:
            return False
    if db.execute("select count(*) from pending").fetchone()[0] >= 10_000:
        raise RuntimeError("telemetry queue is full; oldest readings were preserved")
    received = datetime.now(timezone.utc)
    measured = received - timedelta(milliseconds=age_ms)
    common = {
        "site_id": "factory-01", "line_id": "line-1", "station_id": "final-pond",
        "device_id": device, "measured_at": measured.isoformat().replace("+00:00", "Z"),
        "received_at": received.isoformat().replace("+00:00", "Z"),
        "quality": "good", "source_mode": "live",
    }
    payload = [
        {**common, "measurement_id": f"{device}:{boot_id}:{reads}:water_ph", "metric": "water_ph", "value": ph, "unit": "pH"},
        {**common, "measurement_id": f"{device}:{boot_id}:{reads}:water_temperature", "metric": "water_temperature", "value": temperature, "unit": "°C"},
    ]
    with db:
        db.execute("insert into pending(payload, created_at) values (?, ?)", (json.dumps(payload, separators=(",", ":")), received.isoformat()))
        db.execute(
            "insert into state(id, boot_id, last_reads, last_uptime_ms) values (1, ?, ?, ?) "
            "on conflict(id) do update set boot_id=excluded.boot_id, last_reads=excluded.last_reads, last_uptime_ms=excluded.last_uptime_ms",
            (boot_id, reads, uptime_ms),
        )
    return True


def flush(db: sqlite3.Connection, limit: int = 20) -> int:
    token = read_token()
    sent = 0
    for row_id, payload in db.execute("select id, payload from pending order by id limit ?", (limit,)).fetchall():
        request = Request(PCC_URL, data=payload.encode("utf-8"), method="POST", headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json",
        })
        try:
            with urlopen(request, timeout=10) as response:
                if response.status != 202:
                    raise RuntimeError(f"PCC returned HTTP {response.status}")
                body = json.load(response)
                if not isinstance(body.get("accepted"), int):
                    raise RuntimeError("PCC response did not confirm ingestion")
        except HTTPError as exc:
            raise RuntimeError(f"PCC returned HTTP {exc.code}; queued measurement retained") from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError("PCC unreachable; queued measurement retained") from exc
        with db:
            db.execute("delete from pending where id = ?", (row_id,))
        sent += 1
    return sent


def cycle(db: sqlite3.Connection) -> tuple[bool, int, int]:
    status = board_status()
    queued = queue_sample(db, validated_sample(status))
    sent = flush(db)
    depth = db.execute("select count(*) from pending").fetchone()[0]
    return queued, sent, depth


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--check-board", action="store_true")
    args = parser.parse_args()
    configure_logging()
    if args.check_board:
        validated_sample(board_status())
        print("Calibrated live pH board is reachable with a fresh reading.")
        return 0
    db = open_db()
    try:
        while True:
            try:
                queued, sent, depth = cycle(db)
                LOGGER.info("cycle queued=%s sent=%s pending=%s", queued, sent, depth)
                if args.once:
                    print(f"Pond pH bridge: queued={queued}, sent={sent}, pending={depth}")
                    return 0 if depth == 0 else 1
            except Exception as exc:
                LOGGER.error("cycle failed: %s", exc)
                if args.once:
                    print(f"Pond pH bridge failed: {exc}")
                    return 1
            time.sleep(INTERVAL)
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
