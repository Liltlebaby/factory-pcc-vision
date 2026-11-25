"""Export hourly AI rack counts from the Vision Monitor event journal.

The exported CSV leaves human counts and camera coverage empty for a reviewer.
It never edits the event journal or overwrites a completed review CSV.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rack_ai.lab.store import LabStore
from rack_ai.tools.validate_shift_count import SHIFT_LABELS, ai_series_sha256, expected_shift_window, file_sha256


class ExportError(ValueError):
    pass


def read_count_events(
    database_path: Path,
    *,
    start: datetime,
    end: datetime,
    camera_id: str,
    station_id: str,
) -> list[dict]:
    database_path = database_path.resolve()
    if not database_path.is_file():
        raise ExportError(f"event journal not found: {database_path}")
    query = """
        SELECT cursor, event_id, occurred_at, data
        FROM ai_events
        WHERE occurred_at >= ? AND occurred_at < ?
          AND camera_id = ? AND station_id = ? AND task_id = 'rack-counting'
          AND event_type IN (?, ?)
        ORDER BY occurred_at, cursor
    """
    try:
        with closing(sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True, timeout=10)) as db:
            db.execute("BEGIN")
            rows = db.execute(query, (start.timestamp(), end.timestamp(), camera_id, station_id,
                                      *LabStore.COUNT_EVENT_TYPES)).fetchall()
    except sqlite3.Error as exc:
        raise ExportError(f"cannot read event journal: {exc}") from exc
    events = []
    for cursor, event_id, occurred_at, data in rows:
        try:
            payload = json.loads(data)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ExportError(f"invalid event payload at cursor {cursor}") from exc
        if not isinstance(payload, dict):
            raise ExportError(f"invalid event payload at cursor {cursor}")
        recorded_hash = payload.get("model_sha256")
        if recorded_hash is not None and not isinstance(recorded_hash, str):
            raise ExportError(f"invalid model SHA-256 at cursor {cursor}")
        events.append({
            "cursor": int(cursor),
            "event_id": str(event_id),
            "occurred_at": float(occurred_at),
            "model_version": payload.get("model_version"),
            "model_sha256": recorded_hash,
        })
    return events


def build_export(
    events: list[dict],
    *,
    date_key: str,
    shift: str,
    camera_id: str,
    station_id: str,
    model_path: Path,
    recorded_model_name: str | None = None,
    exported_at: datetime | None = None,
) -> tuple[list[dict], dict]:
    start, end = expected_shift_window(date_key, shift)
    if model_path.suffix.casefold() != ".pt" or not model_path.is_file():
        raise ExportError(f"model must be an existing .pt file: {model_path}")
    expected_model = recorded_model_name or model_path.name
    versions = sorted({str(item.get("model_version") or "") for item in events})
    if events and versions != [expected_model]:
        raise ExportError(
            f"journal model version mismatch: expected {expected_model}, found {versions}; "
            "check model deployment before acceptance"
        )
    model_hash = file_sha256(model_path)
    recorded_hashes = {item.get("model_sha256") for item in events}
    if any(value is not None and value != model_hash for value in recorded_hashes):
        raise ExportError("journal model SHA-256 differs from the supplied model file")
    model_identity_verified = bool(events) and recorded_hashes == {model_hash}
    rows = []
    for hour in range(int((end - start).total_seconds() // 3600)):
        window_start = start + timedelta(hours=hour)
        window_end = window_start + timedelta(hours=1)
        rows.append({
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "human_count": "",
            "ai_count": sum(window_start.timestamp() <= item["occurred_at"] < window_end.timestamp()
                            for item in events),
            "camera_coverage_confirmed": "",
            "notes": "",
        })
    digest = hashlib.sha256()
    for event in events:
        digest.update(f"{event['cursor']}|{event['event_id']}|{event['occurred_at']:.6f}\n".encode("utf-8"))
    export_moment = (exported_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    metadata = {
        "schema_version": 1,
        "exported_at": export_moment.isoformat().replace("+00:00", "Z"),
        "shift_complete": export_moment >= end.astimezone(timezone.utc),
        "date": date_key,
        "shift": shift,
        "camera_id": camera_id,
        "station_id": station_id,
        "model_file": model_path.name,
        "model_sha256_at_export": model_hash,
        "recorded_model_name": expected_model,
        "model_identity_verified": model_identity_verified,
        "model_identity_limit": (
            None if model_identity_verified else
            "No rack count events were recorded; model use cannot be attested."
            if not events else
            "One or more journal events lack the model SHA-256 recorded at inference startup; "
            "this legacy export cannot prove the deployed weights."
        ),
        "event_count": len(events),
        "first_cursor": min((item["cursor"] for item in events), default=None),
        "last_cursor": max((item["cursor"] for item in events), default=None),
        "selected_event_sha256": digest.hexdigest(),
        "ai_series_sha256": ai_series_sha256(
            (row["window_start"], row["window_end"], row["ai_count"]) for row in rows
        ),
        "ai_total": sum(row["ai_count"] for row in rows),
        "review_required": ["human_count", "camera_coverage_confirmed"],
    }
    return rows, metadata


def export_csv(rows: list[dict], metadata: dict, output_path: Path) -> tuple[Path, Path]:
    output_path = output_path.resolve()
    provenance_path = output_path.with_name(output_path.stem + ".provenance.json")
    if output_path.exists() or provenance_path.exists():
        raise ExportError("output CSV or provenance file already exists; choose a new name")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    created_csv = False
    created_provenance = False
    try:
        with output_path.open("x", newline="", encoding="utf-8-sig") as handle:
            created_csv = True
            writer = csv.DictWriter(handle, fieldnames=(
                "window_start", "window_end", "human_count", "ai_count",
                "camera_coverage_confirmed", "notes",
            ))
            writer.writeheader()
            writer.writerows(rows)
        with provenance_path.open("x", encoding="utf-8") as handle:
            created_provenance = True
            json.dump(metadata, handle, ensure_ascii=False, indent=2)
    except Exception:
        if created_csv:
            output_path.unlink(missing_ok=True)
        if created_provenance:
            provenance_path.unlink(missing_ok=True)
        raise
    return output_path, provenance_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True, help="recordings/runtime/lab.sqlite3")
    parser.add_argument("--date", required=True, help="report day YYYY-MM-DD")
    parser.add_argument("--shift", choices=sorted(SHIFT_LABELS), required=True)
    parser.add_argument("--camera-id", default="camera-09")
    parser.add_argument("--station-id", default="rack-infeed")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--recorded-model-name", default=None, help="journal model name if the deployed filename differs")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        start, end = expected_shift_window(args.date, args.shift)
        events = read_count_events(args.database, start=start, end=end,
                                   camera_id=args.camera_id, station_id=args.station_id)
        rows, metadata = build_export(events, date_key=args.date, shift=args.shift,
                                      camera_id=args.camera_id, station_id=args.station_id,
                                      model_path=args.model,
                                      recorded_model_name=args.recorded_model_name)
        csv_path, provenance_path = export_csv(rows, metadata, args.output)
    except (ExportError, OSError, ValueError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"AI events={metadata['event_count']} total={metadata['ai_total']} across {len(rows)} hours")
    print(f"CSV: {csv_path}")
    print(f"Provenance: {provenance_path}")
    if not metadata["shift_complete"]:
        print("DRAFT: the shift has not ended; export again after the shift for acceptance.")
    print("Fill human_count and camera_coverage_confirmed after reviewing the camera footage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
