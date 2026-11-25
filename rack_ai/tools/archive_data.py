"""Archive all stable rack_ai/data files while taking online SQLite snapshots."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from rack_ai.tools.backup_runtime import DATABASE_SUFFIXES, SKIP_SUFFIXES, snapshot_sqlite


SKIP_NAMES = {".service.lock", "pond-gateway-heartbeat.json"}
SKIP_PREFIXES = (".upload_part_",)
STORED_SUFFIXES = {".mp4", ".avi", ".mkv", ".mov", ".jpg", ".jpeg", ".png", ".webp", ".zip", ".pt"}


def skipped(path: Path) -> bool:
    name = path.name.casefold()
    return (
        name in SKIP_NAMES
        or name.startswith(SKIP_PREFIXES)
        or any(name.endswith(suffix) for suffix in SKIP_SUFFIXES)
    )


def build_archive(source: Path, output: Path) -> tuple[Path, int, int]:
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise ValueError(f"Not a directory: {source}")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    archive = output / f"rack_ai-data-{stamp}.zip"
    if archive.exists():
        raise FileExistsError(archive)
    partial = archive.with_suffix(".partial.zip")
    files = sorted((p for p in source.rglob("*") if p.is_file() and not p.is_symlink() and not skipped(p)), key=lambda p: p.relative_to(source).as_posix())
    manifest: list[dict[str, object]] = []
    snapshots = output / f".rack-ai-sqlite-{uuid.uuid4().hex}"
    snapshots.mkdir()
    try:
            with zipfile.ZipFile(partial, "w", allowZip64=True) as bundle:
                for index, path in enumerate(files, 1):
                    relative = path.relative_to(source).as_posix()
                    if path.suffix.casefold() in DATABASE_SUFFIXES:
                        to_store = snapshots / relative
                        to_store.parent.mkdir(parents=True, exist_ok=True)
                        snapshot_sqlite(path, to_store)
                    else:
                        to_store = path
                    before = to_store.stat()
                    method = zipfile.ZIP_STORED if path.suffix.casefold() in STORED_SUFFIXES else zipfile.ZIP_DEFLATED
                    bundle.write(to_store, f"rack_ai/data/{relative}", compress_type=method, compresslevel=1 if method == zipfile.ZIP_DEFLATED else None)
                    after = to_store.stat()
                    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
                        raise RuntimeError(f"File changed during archive; retry after stopping service: {relative}")
                    manifest.append({"path": relative, "bytes": after.st_size, "sqlite_snapshot": path.suffix.casefold() in DATABASE_SUFFIXES})
                    if index % 100 == 0:
                        print(f"Archived {index}/{len(files)} files", flush=True)
                bundle.writestr("archive-manifest.json", json.dumps({"source": "rack_ai/data", "created_at": datetime.now(timezone.utc).isoformat(), "files": manifest}, ensure_ascii=False))
            with zipfile.ZipFile(partial, "r") as bundle:
                bad = bundle.testzip()
                if bad:
                    raise RuntimeError(f"ZIP integrity check failed: {bad}")
            os.replace(partial, archive)
    finally:
        partial.unlink(missing_ok=True)
        shutil.rmtree(snapshots, ignore_errors=True)
    return archive, len(files), sum(int(item["bytes"]) for item in manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive, count, size = build_archive(args.source, args.output)
    digest = hashlib.sha256()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    print(f"ARCHIVE={archive}")
    print(f"FILES={count} SOURCE_BYTES={size} ZIP_BYTES={archive.stat().st_size}")
    print(f"SHA256={digest.hexdigest()}")


if __name__ == "__main__":
    main()
