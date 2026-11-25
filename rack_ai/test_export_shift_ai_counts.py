import json
import shutil
import sqlite3
import unittest
import uuid
from contextlib import closing
from datetime import timedelta
from pathlib import Path

from rack_ai.shifts import midnight
from rack_ai.runtime import CountJournal
from rack_ai.tools.export_shift_ai_counts import ExportError, build_export, export_csv, read_count_events
from rack_ai.tools.validate_shift_count import file_sha256


class ExportShiftAiCountsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / f".shift-export-fixture-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.database = self.root / "lab.sqlite3"
        self.model = self.root / "rack.pt"
        self.model.write_bytes(b"model weights")
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("CREATE TABLE ai_events(cursor INTEGER PRIMARY KEY, event_id TEXT, camera_id TEXT, task_id TEXT, station_id TEXT, event_type TEXT, occurred_at REAL, data TEXT)")
            db.commit()

    def tearDown(self):
        shutil.rmtree(self.root)

    def insert(self, cursor, moment, *, camera="camera-09", event_type="rack_counted",
               model="rack.pt", model_hash="current"):
        payload = {"event_id": f"event-{cursor}", "model_version": model}
        if model_hash is not None:
            payload["model_sha256"] = file_sha256(self.model) if model_hash == "current" else model_hash
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("INSERT INTO ai_events VALUES (?,?,?,?,?,?,?,?)", (
                cursor, payload["event_id"], camera, "rack-counting", "rack-infeed", event_type,
                moment.timestamp(), json.dumps(payload),
            ))
            db.commit()

    def test_reads_only_selected_camera_shift_and_excludes_end_boundary(self):
        base = midnight("2026-09-23")
        self.insert(1, base + timedelta(hours=7))
        self.insert(2, base + timedelta(hours=8), event_type="rubber_counted")
        self.insert(3, base + timedelta(hours=18))
        self.insert(4, base + timedelta(hours=9), camera="camera-10")
        events = read_count_events(self.database, start=base + timedelta(hours=7),
                                   end=base + timedelta(hours=18), camera_id="camera-09",
                                   station_id="rack-infeed")
        rows, metadata = build_export(events, date_key="2026-09-23", shift="day",
                                      camera_id="camera-09", station_id="rack-infeed", model_path=self.model)
        self.assertEqual([row["ai_count"] for row in rows], [1, 1] + [0] * 9)
        self.assertEqual(metadata["event_count"], 2)
        self.assertEqual(metadata["first_cursor"], 1)
        self.assertTrue(metadata["model_identity_verified"])
        self.assertTrue(all(row["human_count"] == "" and row["camera_coverage_confirmed"] == "" for row in rows))

    def test_model_hash_mismatch_blocks_export(self):
        base = midnight("2026-09-23")
        self.insert(1, base + timedelta(hours=7), model_hash="0" * 64)
        events = read_count_events(self.database, start=base + timedelta(hours=7),
                                   end=base + timedelta(hours=18), camera_id="camera-09",
                                   station_id="rack-infeed")
        with self.assertRaisesRegex(ExportError, "SHA-256 differs"):
            build_export(events, date_key="2026-09-23", shift="day", camera_id="camera-09",
                         station_id="rack-infeed", model_path=self.model)

    def test_legacy_events_are_marked_unverified(self):
        base = midnight("2026-09-23")
        self.insert(1, base + timedelta(hours=7), model_hash=None)
        events = read_count_events(self.database, start=base + timedelta(hours=7),
                                   end=base + timedelta(hours=18), camera_id="camera-09",
                                   station_id="rack-infeed")
        _, metadata = build_export(events, date_key="2026-09-23", shift="day",
                                   camera_id="camera-09", station_id="rack-infeed", model_path=self.model)
        self.assertFalse(metadata["model_identity_verified"])
        self.assertIn("legacy", metadata["model_identity_limit"])

    def test_invalid_model_hash_payload_is_reported_cleanly(self):
        base = midnight("2026-09-23")
        self.insert(1, base + timedelta(hours=7), model_hash=None)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("UPDATE ai_events SET data = ? WHERE cursor = 1", (
                json.dumps({"model_version": "rack.pt", "model_sha256": ["invalid"]}),
            ))
            db.commit()
        with self.assertRaisesRegex(ExportError, "invalid model SHA-256 at cursor 1"):
            read_count_events(self.database, start=base + timedelta(hours=7),
                              end=base + timedelta(hours=18), camera_id="camera-09",
                              station_id="rack-infeed")

    def test_count_journal_event_preserves_model_fingerprint(self):
        fingerprint = file_sha256(self.model)
        event = CountJournal._event({"last_event": {
            "timestamp": midnight("2026-09-23").timestamp(), "trackId": 3, "rackNumber": 1,
            "confidence": 0.9, "model_version": "rack.pt", "model_sha256": fingerprint,
        }})
        self.assertEqual(event["model_sha256"], fingerprint)

    def test_model_mismatch_blocks_export(self):
        base = midnight("2026-09-23")
        self.insert(1, base + timedelta(hours=7), model="other.pt")
        events = read_count_events(self.database, start=base + timedelta(hours=7),
                                   end=base + timedelta(hours=18), camera_id="camera-09",
                                   station_id="rack-infeed")
        with self.assertRaisesRegex(ExportError, "model version mismatch"):
            build_export(events, date_key="2026-09-23", shift="day", camera_id="camera-09",
                         station_id="rack-infeed", model_path=self.model)

    def test_existing_review_csv_is_never_overwritten(self):
        rows, metadata = build_export([], date_key="2026-09-23", shift="day",
                                      camera_id="camera-09", station_id="rack-infeed", model_path=self.model)
        target = self.root / "review.csv"
        target.write_text("human review", encoding="utf-8")
        with self.assertRaisesRegex(ExportError, "already exists"):
            export_csv(rows, metadata, target)
        self.assertEqual(target.read_text(encoding="utf-8"), "human review")

    def test_existing_provenance_is_never_overwritten(self):
        rows, metadata = build_export([], date_key="2026-09-23", shift="day",
                                      camera_id="camera-09", station_id="rack-infeed", model_path=self.model)
        target = self.root / "review.csv"
        provenance = self.root / "review.provenance.json"
        provenance.write_text("previous evidence", encoding="utf-8")
        with self.assertRaisesRegex(ExportError, "already exists"):
            export_csv(rows, metadata, target)
        self.assertFalse(target.exists())
        self.assertEqual(provenance.read_text(encoding="utf-8"), "previous evidence")

    def test_export_before_shift_end_is_marked_draft(self):
        rows, metadata = build_export([], date_key="2026-09-23", shift="day",
                                      camera_id="camera-09", station_id="rack-infeed", model_path=self.model,
                                      exported_at=midnight("2026-09-23") + timedelta(hours=10))
        self.assertFalse(metadata["shift_complete"])
        self.assertEqual(metadata["ai_total"], 0)
        self.assertEqual(len(rows), 11)


if __name__ == "__main__":
    unittest.main()
