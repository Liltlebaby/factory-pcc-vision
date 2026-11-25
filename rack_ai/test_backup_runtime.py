import json
import shutil
import sqlite3
import unittest
import uuid
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from rack_ai.tools.backup_runtime import (
    BackupError,
    create_backup,
    prune_backups,
    restore_backup,
    verify_archive,
)


class RuntimeBackupTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / f".backup-fixture-{uuid.uuid4().hex}"
        self.source = self.root / "source"
        self.output = self.root / "output"
        runtime = self.source / "recordings" / "runtime"
        runtime.mkdir(parents=True)
        database = runtime / "lab.sqlite3"
        with closing(sqlite3.connect(database)) as db:
            db.execute("CREATE TABLE events(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("INSERT INTO events(value) VALUES ('rack-counted')")
            db.commit()
        metadata = self.source / "recordings" / "clip.json"
        metadata.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
        media = self.source / "recordings" / "raw.mp4"
        media.write_bytes(b"video-bytes")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def create(self, *, include_media=False):
        return create_backup(
            self.source,
            self.output,
            include_media=include_media,
            created_at=datetime(2026, 9, 23, 1, 2, 3, tzinfo=timezone.utc),
        )

    def test_backup_uses_manifest_and_excludes_media_by_default(self):
        archive = self.create()
        manifest = verify_archive(archive)
        paths = {item["path"] for item in manifest["files"]}
        self.assertIn("recordings/runtime/lab.sqlite3", paths)
        self.assertIn("recordings/clip.json", paths)
        self.assertNotIn("recordings/raw.mp4", paths)
        self.assertTrue(all(len(item["sha256"]) == 64 for item in manifest["files"]))

    def test_media_can_be_included_explicitly(self):
        manifest = verify_archive(self.create(include_media=True))
        self.assertIn("recordings/raw.mp4", {item["path"] for item in manifest["files"]})

    def test_restore_recovers_queryable_database(self):
        archive = self.create()
        target = self.root / "restored"
        restore_backup(archive, target)
        with closing(sqlite3.connect(target / "recordings" / "runtime" / "lab.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT value FROM events").fetchone(), ("rack-counted",))

    def test_restore_refuses_nonempty_target(self):
        archive = self.create()
        target = self.root / "live-runtime"
        target.mkdir()
        (target / "do-not-overwrite.txt").write_text("live", encoding="utf-8")
        with self.assertRaisesRegex(BackupError, "never restore over live"):
            restore_backup(archive, target)

    def test_tampered_payload_fails_checksum(self):
        archive = self.create()
        tampered = self.output / "runtime-backup-tampered.zip"
        with zipfile.ZipFile(archive, "r") as source, zipfile.ZipFile(tampered, "w") as output:
            for name in source.namelist():
                value = source.read(name)
                output.writestr(name, b"tampered" if name.endswith("clip.json") else value)
        with self.assertRaisesRegex(BackupError, "checksum mismatch"):
            verify_archive(tampered)

    def test_path_traversal_archive_is_rejected(self):
        archive = self.output / "runtime-backup-unsafe.zip"
        self.output.mkdir(parents=True)
        manifest = {
            "format": "factory-runtime-backup-v1",
            "file_count": 1,
            "files": [{"path": "../outside.json", "kind": "metadata", "size": 2, "sha256": "0" * 64}],
        }
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("manifest.json", json.dumps(manifest))
            bundle.writestr("../outside.json", "{}")
        with self.assertRaisesRegex(BackupError, "unsafe archive path"):
            verify_archive(archive)

    def test_windows_backslash_traversal_archive_is_rejected(self):
        archive = self.output / "runtime-backup-windows-unsafe.zip"
        self.output.mkdir(parents=True)
        manifest = {
            "format": "factory-runtime-backup-v1",
            "file_count": 1,
            "files": [{"path": "..\\outside.json", "kind": "metadata", "size": 2, "sha256": "0" * 64}],
        }
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("manifest.json", json.dumps(manifest))
            bundle.writestr("..\\outside.json", "{}")
        with self.assertRaisesRegex(BackupError, "unsafe archive path"):
            verify_archive(archive)

    def test_retention_only_removes_matching_old_archives(self):
        self.output.mkdir(parents=True)
        backups = []
        for index in range(4):
            path = self.output / f"runtime-backup-2026092{index}-000000Z.zip"
            path.write_bytes(str(index).encode())
            backups.append(path)
        unrelated = self.output / "manual-export.zip"
        unrelated.write_bytes(b"keep")
        removed = prune_backups(self.output, 2)
        self.assertEqual(len(removed), 2)
        self.assertTrue(unrelated.exists())
        self.assertEqual(sum(path.exists() for path in backups), 2)


if __name__ == "__main__":
    unittest.main()
