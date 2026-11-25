"""Register a human-counted clip so model comparison can judge counting.

Why this exists
---------------
``lab/evaluation.py`` already knows how to score counting: it runs the counter
over a clip and compares against ``expected_count``. It has never been used --
there is not one ``benchmark`` record in the lab database, so every comparison
carries ``"counting": []`` and the acceptance gate returns
``unseen_counting_benchmark_required``. Detection mAP says nothing about how
many racks the system counts.

A benchmark clip must never appear in any dataset split. ``evaluate()`` enforces
that by hash; this tool checks it up front so the mistake is caught before a
person spends an hour counting.

Usage (from the project root)::

    python -m rack_ai.tools.register_benchmark --list-clips
    python -m rack_ai.tools.register_benchmark --clip-id clip_1441... --expected 24 --actor tle
    python -m rack_ai.tools.register_benchmark --show
"""
import argparse
import json
import sys
from pathlib import Path

from ..config import Settings
from ..lab.store import LabStore, identity, sha256


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--lab-root', type=Path, default=None)
    parser.add_argument('--record-root', type=Path, default=None)
    parser.add_argument('--list-clips', action='store_true',
                        help='show clips and whether each is still unseen by every dataset')
    parser.add_argument('--show', action='store_true', help='show registered benchmarks')
    parser.add_argument('--clip-id')
    parser.add_argument('--expected', type=int, help='racks counted by a person over the WHOLE clip')
    parser.add_argument('--actor')
    parser.add_argument('--note', default='', help='free text, e.g. "night shift, two touching pairs"')
    return parser.parse_args(argv)


def used_source_hashes(store):
    """Every source clip hash that appears in any built dataset."""
    used = set()
    for dataset in store.list('dataset'):
        manifest = store.path(dataset['path'])/'manifest.json'
        if manifest.is_file():
            used.update(item['source_hash'] for item in json.loads(manifest.read_text(encoding='utf-8')))
    for frame in store.list('frame'):
        if frame.get('review_status') == 'approved':
            used.add(frame['source_hash'])      # approved frames will land in the next build
    return used


def clip_rows(store, clips_root):
    used = used_source_hashes(store)
    rows = []
    for sidecar in sorted(Path(clips_root).glob('clip_*.json')):
        clip = json.loads(sidecar.read_text(encoding='utf-8'))
        raw = Path(clips_root)/'raw'/(clip['clip_id']+'.mp4')
        if not raw.is_file():
            continue
        digest = sha256(raw)
        rows.append(dict(clip_id=clip['clip_id'], name=clip.get('name', ''),
                         status=clip.get('status', ''), size_mb=round(raw.stat().st_size/1e6, 1),
                         source_hash=digest, unseen=digest not in used, path=raw))
    return rows


def main(argv=None):
    args = parse_args(argv)
    settings = Settings()
    lab_root = args.lab_root or settings.lab_root
    record_root = args.record_root or settings.record_root
    if not Path(lab_root).is_dir():
        sys.exit(f'lab root not found: {lab_root}  (run from the project root, or pass --lab-root)')
    store = LabStore(lab_root)

    if args.show:
        rows = store.list('benchmark')
        if not rows:
            print('no benchmarks registered -- counting accuracy has never been measured')
            return 0
        for row in rows:
            print(f"  {row['id']}  clip={row['clip_id']}  expected={row['expected_count']}  by={row.get('actor','')}")
        return 0

    if args.list_clips:
        rows = clip_rows(store, record_root)
        if not rows:
            print(f'no finalized clips under {record_root}')
            return 0
        print(f'{"clip_id":40s} {"MB":>7} {"status":11s} usable as benchmark')
        for row in rows:
            mark = 'yes' if row['unseen'] else 'NO - frames from this clip are in a dataset'
            print(f'{row["clip_id"]:40s} {row["size_mb"]:7.1f} {row["status"]:11s} {mark}')
        print('\nPick a clip marked "yes", count the racks in it by eye, then run this tool')
        print('with --clip-id and --expected. Count the WHOLE clip: evaluation replays all of it.')
        return 0

    if not (args.clip_id and args.expected is not None and args.actor):
        sys.exit('need --clip-id, --expected and --actor (or use --list-clips / --show)')
    if args.expected < 0:
        sys.exit('--expected cannot be negative')

    rows = {row['clip_id']: row for row in clip_rows(store, record_root)}
    clip = rows.get(args.clip_id)
    if clip is None:
        sys.exit(f'clip not found or has no raw file: {args.clip_id}')
    if not clip['unseen']:
        sys.exit('this clip already contributed frames to a dataset, so it cannot measure\n'
                 'generalisation. Pick a clip listed as usable by --list-clips.')

    value = dict(id=identity('benchmark'), clip_id=args.clip_id, expected_count=args.expected,
                 actor=args.actor, note=args.note, source_hash=clip['source_hash'])
    store.put('benchmark', value)
    print(f'registered {value["id"]}  clip={args.clip_id}  expected={args.expected}')
    print('\nNext: evaluate a model against it, e.g. from the dataset page, or')
    print('POST /api/evaluate with {"model_id": "...", "benchmark_ids": ["%s"]}' % value['id'])
    print('The acceptance gate can only clear once at least one benchmark exists.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
