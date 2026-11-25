"""Count racks in a video file using the exact code path the live service uses.

Why this exists
---------------
``ai/rack_detector/offline_track_count.py`` counts with its own rules: it
anchors on the top edge, tests ``previous_y < line <= anchor_y`` and applies a
blanket cooldown. The live service counts through ``rack_ai/counter.py``, which
anchors on the centre by default, arms a track above the line and applies the
spatial duplicate guard. The two disagree, so a number produced by the legacy
script -- including every number in the existing Colab notebooks -- says
nothing about what the service will count.

This tool runs ``RackDetector`` + ``RackCounter``: the same objects, the same
settings, the same order. A count produced here is the count the service
produces, so it can be compared against a human count and used to pick
settings. It needs no lab database and no recording store, which is what makes
it usable on Colab.

Usage (from the project root, or anywhere the bundle was unpacked)::

    python -m rack_ai.tools.count_video --video clip.mp4 --model best.pt
    python -m rack_ai.tools.count_video --video clip.mp4 --expected 24 --annotate out.mp4
    python -m rack_ai.tools.count_video --video clip.mp4 --duration 600 --iou .70 --half off
"""
import argparse
import csv
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

from ..config import Settings
from ..counter import RackCounter
from ..preview_filter import select_preview_tracks


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--model', type=Path, default=None, help='defaults to RACK_MODEL_PATH')
    parser.add_argument('--csv', type=Path, default=Path('rack_events.csv'))
    parser.add_argument('--annotate', type=Path, default=None,
                        help='also write an annotated video (slower, needs disk)')
    parser.add_argument('--json', type=Path, default=None, help='write a machine-readable report')
    parser.add_argument('--start', type=float, default=0.0)
    parser.add_argument('--duration', type=float, default=0.0, help='0 = to the end of the clip')
    parser.add_argument('--sample-fps', type=float, default=None, help='defaults to INFERENCE_FPS')
    parser.add_argument('--expected', type=int, default=None,
                        help='human count for this window; prints the error')
    # Overrides for the settings worth sweeping. Anything omitted comes from .env.
    parser.add_argument('--conf', type=float, default=None)
    parser.add_argument('--iou', type=float, default=None)
    parser.add_argument('--imgsz', type=int, default=None)
    parser.add_argument('--line', type=float, default=None)
    parser.add_argument('--anchor', choices=['center', 'top', 'bottom'], default=None)
    parser.add_argument('--movement', type=float, default=None)
    parser.add_argument('--cooldown', type=float, default=None)
    parser.add_argument('--dedupe', choices=['spatial', 'global'], default=None)
    parser.add_argument('--duplicate-iou', type=float, default=None)
    parser.add_argument('--half', choices=['auto', 'off'], default=None,
                        help="off keeps a GPU run comparable to the CPU service")
    parser.add_argument('--quiet', action='store_true')
    return parser.parse_args(argv)


def apply_overrides(settings, args):
    changes = {}
    for name, field in (('conf', 'confidence'), ('iou', 'iou'), ('imgsz', 'imgsz'),
                        ('line', 'line'), ('anchor', 'anchor'), ('movement', 'movement'),
                        ('cooldown', 'cooldown'), ('dedupe', 'dedupe'),
                        ('duplicate_iou', 'duplicate_iou'), ('half', 'half')):
        value = getattr(args, name, None)
        if value is not None:
            changes[field] = value
    if args.model:
        changes['model'] = args.model
    return replace(settings, **changes) if changes else settings


def draw(frame, tracks, line_y, count, second, label):
    import cv2
    cv2.line(frame, (0, int(line_y)), (frame.shape[1], int(line_y)), (255, 0, 255), 3)
    for track in select_preview_tracks(tracks, line_y):
        x1, y1, x2, y2 = (int(v) for v in track['bbox'])
        color = (0, 0, 255) if track['counted'] else (0, 220, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
        cv2.putText(frame, f"rack ID:{track['track_id']} {track['confidence']:.2f}",
                    (x1, max(28, y1-8)), cv2.FONT_HERSHEY_SIMPLEX, .75, color, 2)
    cv2.putText(frame, f'RACK OUT: {count}', (24, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.15, (0, 255, 255), 3)
    cv2.putText(frame, f'{second:.1f}s | {label}', (24, 78), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 255, 255), 2)
    return frame


def main(argv=None):
    import cv2
    from ..detector import RackDetector

    args = parse_args(argv)
    settings = apply_overrides(Settings(), args)
    if not Path(args.video).is_file():
        sys.exit(f'video not found: {args.video}')
    if not settings.model.is_file():
        sys.exit(f'model not found: {settings.model}  (set RACK_MODEL_PATH or pass --model)')

    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        sys.exit(f'cannot open {args.video}')
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps <= 0 or total <= 0 or width <= 0 or height <= 0:
        capture.release()
        sys.exit('unreadable video metadata')

    sample_fps = args.sample_fps or settings.inference_fps
    stride = max(1, round(fps/sample_fps))
    first = round(args.start*fps)
    last = min(total, round((args.start+args.duration)*fps)) if args.duration else total
    if first >= last:
        capture.release()
        sys.exit('empty interval')
    capture.set(cv2.CAP_PROP_POS_FRAMES, first)

    detector = RackDetector(settings)
    counter = RackCounter(settings)
    writer = None
    if args.annotate:
        Path(args.annotate).parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(args.annotate), cv2.VideoWriter_fourcc(*'mp4v'),
                                 fps/stride, (width, height))
        if not writer.isOpened():
            capture.release()
            sys.exit('cannot open the annotated-video writer')

    label = f'{Path(settings.model).name} conf={settings.confidence} iou={settings.iou}'
    if not args.quiet:
        print(f'video     {args.video}  {width}x{height} @ {fps:.2f} fps')
        print(f'model     {settings.model}  device={detector.device} half={detector.half}')
        print(f'counting  line={settings.line} anchor={settings.anchor} movement={settings.movement} '
              f'cooldown={settings.cooldown} dedupe={settings.dedupe}')
        print(f'sampling  {sample_fps} fps (every {stride} frames)\n')

    events = []
    processed = 0
    began = time.time()
    try:
        for index in range(first, last):
            if not capture.grab():
                break
            if (index-first) % stride:
                continue
            ok, frame = capture.retrieve()
            if not ok:
                raise SystemExit('decode failed part-way through the clip')
            second = index/fps
            before = counter.count
            tracks = counter.update(detector.infer(frame), height, second)
            if counter.count != before:
                events.append(dict(counter.last_event, video_second=round(second, 3)))
            if writer is not None:
                writer.write(draw(frame, tracks, height*settings.line, counter.count, second, label))
            processed += 1
            if not args.quiet and processed % 100 == 0:
                rate = processed/max(1e-9, time.time()-began)
                print(f'  {processed} frames  {rate:.1f} fps  count={counter.count}', flush=True)
    finally:
        capture.release()
        if writer is not None:
            writer.release()
    if not processed:
        sys.exit('no frames processed')

    if args.annotate:
        # OpenCV can open an mp4v writer and still emit an unplayable stub when the
        # codec is missing, which only surfaces later as an ffmpeg ENOENT-style error.
        written = Path(args.annotate)
        if not written.is_file() or written.stat().st_size < 2048:
            print(f'WARNING: {written} is empty or unusable '
                  f'({written.stat().st_size if written.is_file() else 0} bytes). '
                  'The mp4v encoder is unavailable here; the count and the CSV below are '
                  'still correct. Re-run without --annotate, or install a working '
                  'OpenCV build, if you need the video.', file=sys.stderr)

    Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
    with open(args.csv, 'w', newline='', encoding='utf-8-sig') as handle:
        output = csv.DictWriter(handle, fieldnames=['rack_number', 'track_id', 'video_second', 'confidence'])
        output.writeheader()
        for event in events:
            output.writerow(dict(rack_number=event['rackNumber'], track_id=event['trackId'],
                                 video_second=event['video_second'],
                                 confidence=round(float(event['confidence']), 4)))

    elapsed = time.time()-began
    report = dict(video=str(args.video), model=str(settings.model), device=str(detector.device),
                  half=bool(detector.half), count=counter.count, events=len(events),
                  suppressed_duplicates=counter.suppressed, frames=processed,
                  start_seconds=args.start, window_seconds=round(processed*stride/fps, 2),
                  sample_fps=sample_fps, elapsed_seconds=round(elapsed, 1),
                  inference_fps=round(processed/max(1e-9, elapsed), 2),
                  settings=dict(confidence=settings.confidence, iou=settings.iou, imgsz=settings.imgsz,
                                line=settings.line, anchor=settings.anchor, movement=settings.movement,
                                cooldown=settings.cooldown, dedupe=settings.dedupe,
                                duplicate_iou=settings.duplicate_iou))
    if args.expected is not None:
        error = abs(counter.count-args.expected)
        report.update(expected=args.expected, absolute_error=error,
                      percentage_error=round(100*error/args.expected, 2) if args.expected else None)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'\ncount {counter.count} racks in {processed} frames '
          f'({elapsed:.0f}s, {report["inference_fps"]} fps)')
    if counter.suppressed:
        print(f'{counter.suppressed} crossings suppressed as duplicate boxes of a rack already counted')
    if args.expected is not None:
        print(f'human count {args.expected}  ->  off by {report["absolute_error"]} '
              f'({report["percentage_error"]}%)')
    print(f'events  {args.csv}')
    if args.annotate:
        print(f'video   {args.annotate}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
