"""Create, verify, and restore consistent Rack Monitor runtime backups.

SQLite databases are copied with SQLite's online backup API, not with a raw
filesystem copy. Every stored file is recorded in a SHA-256 manifest. Restore
only targets a new or empty directory so a failed drill cannot overwrite the
live runtime by accident.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import uuid
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable


ARCHIVE_PREFIX = "runtime-backup-"
ARCHIVE_SUFFIX = ".zip"
DATABASE_SUFFIXES = {".sqlite3", ".sqlite", ".db"}
METADATA_SUFFIXES = {".json", ".jsonl", ".csv", ".yaml", ".yml"}
MEDIA_SUFFIXES = {".mp4", ".avi", ".mkv", ".mov", ".jpg", ".jpeg", ".png", ".webp"}
SKIP_SUFFIXES = {".sqlite3-wal", ".sqlite3-shm", ".sqlite-wal", ".sqlite-shm", ".db-wal", ".db-shm"}
SKIP_NAMES = {".service.lock", "pond-gateway-heartbeat.json"}


class BackupError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_archive_name(name: str) -> PurePosixPath:
    if (
        not name
        or "\\" in name
        or "\x00" in name
        or re.match(r"^[A-Za-z]:", name)
    ):
        raise BackupError(f"unsafe archive path: {name}")
    candidate = PurePosixPath(name)
    if candidate.is_absolute() or not candidate.parts or any(
        part in {".", ".."} or ":" in part for part in candidate.parts
    ):
        raise BackupError(f"unsafe archive path: {name}")
    if candidate.parts[0] == "manifest.json" and len(candidate.parts) > 1:
        raise BackupError(f"invalid manifest path: {name}")
    return candidate


def _kind(path: Path) -> str | None:
    lowered = path.name.casefold()
    if path.name in SKIP_NAMES or any(lowered.endswith(suffix) for suffix in SKIP_SUFFIXES):
        return None
    if path.suffix.casefold() in DATABASE_SUFFIXES:
        return "sqlite"
    if path.suffix.casefold() in METADATA_SUFFIXES:
        return "metadata"
    if path.suffix.casefold() in MEDIA_SUFFIXES:
        return "media"
    return None


def discover_files(source: Path, *, include_media: bool) -> list[tuple[Path, Path, str]]:
    source = source.resolve()
    if not source.is_dir():
        raise BackupError(f"source directory not found: {source}")
    result: list[tuple[Path, Path, str]] = []
    for path in source.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(source)
        except ValueError as exc:
            raise BackupError(f"file escapes source directory: {path}") from exc
        kind = _kind(path)
        if kind is None or (kind == "media" and not include_media):
            continue
        result.append((resolved, relative, kind))
    return sorted(result, key=lambda item: item[1].as_posix())


def _quick_check(path: Path) -> None:
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=10)) as database:
            result = database.execute("PRAGMA quick_check").fetchone()
    except sqlite3.Error as exc:
        raise BackupError(f"SQLite check failed for {path.name}: {exc}") from exc
    if result != ("ok",):
        raise BackupError(f"SQLite quick_check failed for {path.name}: {result}")


def snapshot_sqlite(source: Path, destination: Path) -> None:
    _quick_check(source)
    source_uri = source.resolve().as_uri() + "?mode=ro"
    try:
        with closing(sqlite3.connect(source_uri, uri=True, timeout=10)) as source_db:
            with closing(sqlite3.connect(destination, timeout=10)) as destination_db:
                source_db.backup(destination_db)
    except sqlite3.Error as exc:
        raise BackupError(f"SQLite online backup failed for {source.name}: {exc}") from exc
    _quick_check(destination)


def _timestamp(value: datetime | None = None) -> tuple[str, str]:
    moment = (value or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return moment.strftime("%Y%m%d-%H%M%SZ"), moment.isoformat().replace("+00:00", "Z")


def create_backup(
    source: Path,
    output_directory: Path,
    *,
    include_media: bool = False,
    created_at: datetime | None = None,
    source_label: str = "rack-ai-runtime",
) -> Path:
    source = source.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    stamp, created_iso = _timestamp(created_at)
    archive = output_directory / f"{ARCHIVE_PREFIX}{stamp}.zip"
    if archive.exists():
        archive = output_directory / f"{ARCHIVE_PREFIX}{stamp}-{uuid.uuid4().hex[:8]}.zip"
    partial = archive.with_suffix(".partial.zip")
    stage = output_directory / f".{archive.stem}.stage-{uuid.uuid4().hex}"
    stage.mkdir()
    manifest_files: list[dict] = []
    try:
        files = discover_files(source, include_media=include_media)
        if not files:
            raise BackupError("no runtime database or metadata files were found")
        for original, relative, kind in files:
            staged = stage / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            if kind == "sqlite":
                snapshot_sqlite(original, staged)
            else:
                shutil.copy2(original, staged)
            manifest_files.append(
                {
                    "path": relative.as_posix(),
                    "kind": kind,
                    "size": staged.stat().st_size,
                    "sha256": sha256_file(staged),
                }
            )
        manifest = {
            "format": "factory-runtime-backup-v1",
            "created_at": created_iso,
            "source_label": source_label,
            "include_media": include_media,
            "file_count": len(manifest_files),
            "files": manifest_files,
        }
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for entry in manifest_files:
                bundle.write(stage / Path(entry["path"]), entry["path"])
        os.replace(partial, archive)
        verify_archive(archive)
        return archive
    finally:
        partial.unlink(missing_ok=True)
        shutil.rmtree(stage, ignore_errors=True)


def _load_manifest(bundle: zipfile.ZipFile) -> dict:
    names = bundle.namelist()
    if len(names) != len(set(names)):
        raise BackupError("archive contains duplicate paths")
    for name in names:
        _safe_archive_name(name)
    if names.count("manifest.json") != 1:
        raise BackupError("archive must contain exactly one manifest.json")
    try:
        manifest = json.loads(bundle.read("manifest.json"))
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BackupError("manifest.json is missing or invalid") from exc
    if manifest.get("format") != "factory-runtime-backup-v1":
        raise BackupError("unsupported backup format")
    files = manifest.get("files")
    if not isinstance(files, list) or manifest.get("file_count") != len(files):
        raise BackupError("manifest file list is invalid")
    expected = {"manifest.json"}
    for entry in files:
        if not isinstance(entry, dict) or not {"path", "kind", "size", "sha256"}.issubset(entry):
            raise BackupError("manifest file entry is invalid")
        if not isinstance(entry["path"], str) or entry["path"] == "manifest.json":
            raise BackupError("manifest file path is invalid")
        if entry["kind"] not in {"sqlite", "metadata", "media"}:
            raise BackupError("manifest file kind is invalid")
        if type(entry["size"]) is not int or entry["size"] < 0:
            raise BackupError("manifest file size is invalid")
        if not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise BackupError("manifest checksum is invalid")
        _safe_archive_name(entry["path"])
        expected.add(entry["path"])
    if len(expected) != len(files) + 1:
        raise BackupError("manifest contains duplicate paths")
    if set(names) != expected:
        raise BackupError("archive contents do not match manifest")
    return manifest


def verify_archive(archive: Path) -> dict:
    archive = archive.resolve()
    if not archive.is_file():
        raise BackupError(f"backup archive not found: {archive}")
    with zipfile.ZipFile(archive, "r") as bundle:
        manifest = _load_manifest(bundle)
        for entry in manifest["files"]:
            name = entry["path"]
            digest = hashlib.sha256()
            size = 0
            with bundle.open(name, "r") as stored:
                for chunk in iter(lambda: stored.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
            if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                raise BackupError(f"checksum mismatch: {name}")
            if entry["kind"] == "sqlite":
                temporary_path: Path | None = None
                try:
                    with tempfile.NamedTemporaryFile(
                        prefix="runtime-backup-check-",
                        suffix=Path(name).suffix,
                        dir=archive.parent,
                        delete=False,
                    ) as temporary:
                        temporary.write(bundle.read(name))
                        temporary_path = Path(temporary.name)
                    _quick_check(temporary_path)
                finally:
                    if temporary_path is not None:
                        temporary_path.unlink(missing_ok=True)
        return manifest


def restore_backup(archive: Path, target: Path) -> dict:
    archive = archive.resolve()
    target = target.resolve()
    if target.exists() and any(target.iterdir()):
        raise BackupError("restore target must be new or empty; never restore over live runtime data")
    manifest = verify_archive(archive)
    target.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        with zipfile.ZipFile(archive, "r") as bundle:
            for entry in manifest["files"]:
                relative = _safe_archive_name(entry["path"])
                destination = target.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(entry["path"], "r") as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
                created.append(destination)
        for entry in manifest["files"]:
            restored = target.joinpath(*PurePosixPath(entry["path"]).parts)
            if sha256_file(restored) != entry["sha256"]:
                raise BackupError(f"restored checksum mismatch: {entry['path']}")
            if entry["kind"] == "sqlite":
                _quick_check(restored)
        return manifest
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise


def prune_backups(directory: Path, keep: int) -> list[Path]:
    if keep < 1:
        raise BackupError("keep must be at least 1")
    directory = directory.resolve()
    candidates = sorted(
        (
            path
            for path in directory.glob(f"{ARCHIVE_PREFIX}*{ARCHIVE_SUFFIX}")
            if path.is_file() and path.parent.resolve() == directory
        ),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    removed = candidates[keep:]
    for path in removed:
        path.unlink()
    return removed


def _print_manifest(manifest: dict, archive: Path, action: str) -> None:
    total = sum(item["size"] for item in manifest["files"])
    sqlite_count = sum(item["kind"] == "sqlite" for item in manifest["files"])
    print(f"{action}: {archive}")
    print(f"files={manifest['file_count']} sqlite={sqlite_count} bytes={total}")
    print(f"created_at={manifest['created_at']} media={manifest['include_media']}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="create and verify a new backup")
    create.add_argument("--source", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--include-media", action="store_true")
    create.add_argument("--keep", type=int, default=0, help="retain newest N archives after success; 0 disables pruning")
    verify = commands.add_parser("verify", help="verify checksums and SQLite integrity")
    verify.add_argument("archive", type=Path)
    restore = commands.add_parser("restore", help="restore into a new or empty directory")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--target", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "create":
            archive = create_backup(args.source, args.output, include_media=args.include_media)
            manifest = verify_archive(archive)
            removed: Iterable[Path] = prune_backups(args.output, args.keep) if args.keep else ()
            _print_manifest(manifest, archive, "created")
            if removed:
                print(f"pruned={len(list(removed))}")
        elif args.command == "verify":
            manifest = verify_archive(args.archive)
            _print_manifest(manifest, args.archive.resolve(), "verified")
        else:
            manifest = restore_backup(args.archive, args.target)
            _print_manifest(manifest, args.target.resolve(), "restored")
    except (BackupError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
