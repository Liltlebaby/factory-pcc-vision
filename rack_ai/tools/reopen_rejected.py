"""Send rejected frames back to the review queue.

Why this exists
---------------
The review history shows 176 frames rejected with their auto-labels untouched
(mean 8.9 boxes in, 8.8 boxes out) against 55 approved frames that were edited
down (8.5 in, 2.6 out). Rejecting a frame because the model got it wrong removes
exactly the example the model needs: frames with many boxes are the frames where
racks travel touching.

This tool flips chosen rejected frames back to ``pending`` so they reappear in
the review UI, and can print the queue so the most useful ones are fixed first.
It never edits boxes and never approves anything -- a person still reviews each
frame.

Usage (from the project root)::

    python -m rack_ai.tools.reopen_rejected --list
    python -m rack_ai.tools.reopen_rejected --list --min-boxes 5
    python -m rack_ai.tools.reopen_rejected --actor tle --min-boxes 5 --limit 60
    python -m rack_ai.tools.reopen_rejected --actor tle --min-boxes 5 --csv queue.csv
"""
import argparse
import csv
import os
import sys
from collections import Counter
from pathlib import Path

from ..config import Settings
from ..lab.store import LabStore


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--lab-root', type=Path, default=None,
                        help='defaults to LAB_ROOT from the environment')
    parser.add_argument('--actor', default=None,
                        help='who is reopening these frames; required unless --list')
    parser.add_argument('--min-boxes', type=int, default=1,
                        help='only frames whose auto-label produced at least this many boxes')
    parser.add_argument('--max-boxes', type=int, default=10**6)
    parser.add_argument('--group', action='append', default=None,
                        help='restrict to a clip/session id; repeatable')
    parser.add_argument('--limit', type=int, default=None,
                        help='reopen at most this many frames, largest box count first')
    parser.add_argument('--csv', type=Path, default=None, help='write the queue to a CSV file')
    parser.add_argument('--list', action='store_true', help='show what would be reopened, change nothing')
    return parser.parse_args(argv)


def boxes_of(frame):
    """Boxes a reviewer would see: their edits if any, otherwise the auto-label."""
    return frame.get('boxes') or frame.get('auto_boxes') or []


def candidates(store, args):
    rows = []
    for frame in store.list('frame'):
        if frame.get('review_status') != 'rejected':
            continue
        if args.group and frame.get('group_id') not in args.group:
            continue
        count = len(boxes_of(frame))
        if not args.min_boxes <= count <= args.max_boxes:
            continue
        rows.append(dict(frame_id=frame['id'], group_id=frame.get('group_id', ''),
                         second=round(float(frame.get('second', 0)), 2),
                         boxes=count, auto_boxes=len(frame.get('auto_boxes') or []),
                         revision=frame.get('revision', 0),
                         brightness=round(float(frame.get('brightness', 0)), 1),
                         blur=round(float(frame.get('blur', 0)), 1),
                         reasons='|'.join(frame.get('reasons') or [])))
    # Most boxes first: those are the touching-rack frames worth fixing.
    rows.sort(key=lambda r: (-r['boxes'], r['group_id'], r['second']))
    return rows[:args.limit] if args.limit else rows


def summarise(rows):
    if not rows:
        print('no rejected frames matched')
        return
    print(f'matched {len(rows)} rejected frames')
    print('\nby clip/session:')
    for key, value in Counter(r['group_id'] for r in rows).most_common():
        print(f'   {value:4d}  {key}')
    print('\nby box count:')
    for key, value in sorted(Counter(r['boxes'] for r in rows).items()):
        print(f'   {key:3d} boxes  {value:4d} frames')
    dark = sum(1 for r in rows if r['brightness'] < 45)
    blurry = sum(1 for r in rows if r['blur'] < 50)
    print(f'\nlikely unusable (reject again): {dark} very dark, {blurry} blurry')
    print('everything else is a frame the model got wrong and should be corrected, not discarded')


def main(argv=None):
    args = parse_args(argv)
    root = args.lab_root or Settings().lab_root
    if not Path(root).is_dir():
        sys.exit(f'lab root not found: {root}  (run from the project root, or pass --lab-root)')
    store = LabStore(root)
    rows = candidates(store, args)
    summarise(rows)

    if args.csv and rows:
        with open(args.csv, 'w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f'\nqueue written to {args.csv}')

    if args.list:
        print('\n--list given, nothing was changed')
        return 0
    if not args.actor:
        sys.exit('--actor is required to reopen frames (or pass --list to preview)')
    if not rows:
        return 0

    reopened = failed = 0
    for row in rows:
        try:
            # action 'save' sets review_status back to pending without touching boxes.
            frame = store.get('frame', row['frame_id'])
            store.review(row['frame_id'], frame['revision'], 'save', args.actor)
            reopened += 1
        except Exception as error:      # a concurrent edit must not abort the batch
            failed += 1
            print(f'  skipped {row["frame_id"]}: {error}')
    print(f'\nreopened {reopened} frames as pending' + (f', {failed} skipped' if failed else ''))
    print('open the dataset page and review them: fix the boxes, then approve')
    print('reject only frames whose IMAGE is unusable (too dark, blurred, duplicate)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
