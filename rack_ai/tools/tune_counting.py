"""Find the counting settings that match a human count, with evidence.

Why this exists
---------------
The live service ships several numbers that were chosen by hand and never
measured against a real count: the NMS overlap threshold, the count line ratio,
the anchor, the movement threshold and the cooldown. Changing any of them by
feel is guesswork, and the failure they interact with -- two racks travelling
touching -- is exactly the case where a wrong value silently drops a rack.

How it works
------------
Detection is the expensive step, so it runs once per ``(conf, iou)`` pair and
every tracked detection is cached to disk. The counter is then replayed over
that cache for every combination of the cheap settings. A grid that would take
hours of inference finishes in one inference pass per detector setting.

The score is the absolute difference between the count and the human count,
summed over every clip given. Ties are broken towards the settings closest to
what is deployed today, so the tool never recommends churn for nothing.

Usage (from the project root)::

    # one clip, counted by eye over the whole file
    python -m rack_ai.tools.tune_counting --video path\\to\\clip.mp4 --expected 24

    # a clip already registered with tools/register_benchmark.py
    python -m rack_ai.tools.tune_counting --benchmark benchmark_ab12...

    # several clips at once, and a faster first look at a 10 minute window
    python -m rack_ai.tools.tune_counting --video a.mp4 --expected 12 \\
        --video b.mp4 --expected 9 --duration 600

    # re-sweep the cheap settings without re-running any inference
    python -m rack_ai.tools.tune_counting --video a.mp4 --expected 12 --from-cache
"""
import argparse
import csv
import itertools
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

from ..config import Settings
from ..counter import RackCounter
from ..lab.store import LabStore, sha256


DETECTOR_GRID = dict(conf=[.45, .55], iou=[.35, .70])
COUNTER_GRID = dict(line=[.55, .60, .65], anchor=['center', 'top', 'bottom'],
                    movement=[6, 10, 16], cooldown=[.0, .8, 1.5, 2.5],
                    dedupe=['spatial', 'global'], duplicate_iou=[.40, .55, .70])
DEPLOYED = dict(line=.60, anchor='center', movement=10, cooldown=1.5,
                dedupe='global', duplicate_iou=.55)


# ----------------------------------------------------------------- arguments

class PairAction(argparse.Action):
    """Collect --video/--expected as ordered pairs."""
    def __call__(self, parser, namespace, values, option_string=None):
        pairs = getattr(namespace, 'pairs', None) or []
        if option_string == '--video':
            pairs.append([Path(values), None])
        else:
            if not pairs or pairs[-1][1] is not None:
                parser.error('--expected must follow a --video')
            pairs[-1][1] = int(values)
        namespace.pairs = pairs


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--video', action=PairAction, help='clip file; repeatable')
    parser.add_argument('--expected', action=PairAction, help='human count for the preceding --video')
    parser.add_argument('--benchmark', action='append', default=[],
                        help='benchmark id registered with register_benchmark; repeatable')
    parser.add_argument('--model', type=Path, default=None, help='defaults to RACK_MODEL_PATH')
    parser.add_argument('--lab-root', type=Path, default=None)
    parser.add_argument('--record-root', type=Path, default=None)
    parser.add_argument('--cache-dir', type=Path, default=Path('rack_ai/data/lab/tuning'))
    parser.add_argument('--start', type=float, default=0.0, help='seconds into the clip')
    parser.add_argument('--duration', type=float, default=0.0, help='0 = to the end of the clip')
    parser.add_argument('--sample-fps', type=float, default=5.0, help='match INFERENCE_FPS')
    parser.add_argument('--conf', type=float, action='append', default=None)
    parser.add_argument('--iou', type=float, action='append', default=None)
    parser.add_argument('--from-cache', action='store_true',
                        help='fail instead of running inference for a missing cache')
    parser.add_argument('--csv', type=Path, default=Path('tuning_results.csv'))
    parser.add_argument('--top', type=int, default=15)
    args = parser.parse_args(argv)
    args.pairs = getattr(args, 'pairs', None) or []
    if any(expected is None for _, expected in args.pairs):
        parser.error('every --video needs a following --expected')
    return args


# ------------------------------------------------------------------ caching

def cache_key(model_hash, clip_hash, conf, iou, imgsz, sample_fps, start, duration):
    parts = (model_hash[:16], clip_hash[:16], f'{conf:.3f}', f'{iou:.3f}',
             str(imgsz), f'{sample_fps:.3f}', f'{start:.1f}', f'{duration:.1f}')
    return 'det_'+'_'.join(parts)+'.jsonl'


def run_detection(video, settings, conf, iou, start, duration, sample_fps, destination):
    """Run the real detector once and store every tracked detection."""
    import cv2
    from ..detector import RackDetector

    detector = RackDetector(replace(settings, confidence=conf, iou=iou))
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise SystemExit(f'cannot open {video}')
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps <= 0 or total <= 0 or height <= 0:
        capture.release()
        raise SystemExit(f'unreadable video metadata: {video}')
    stride = max(1, round(fps/sample_fps))
    first = round(start*fps)
    last = min(total, round((start+duration)*fps)) if duration else total
    capture.set(cv2.CAP_PROP_POS_FRAMES, first)

    temporary = destination.with_suffix('.partial')
    temporary.parent.mkdir(parents=True, exist_ok=True)
    processed = 0
    began = time.time()
    try:
        with temporary.open('w', encoding='utf-8') as handle:
            handle.write(json.dumps(dict(kind='header', height=height, fps=fps,
                                         stride=stride, conf=conf, iou=iou))+'\n')
            for index in range(first, last):
                if not capture.grab():
                    break
                if (index-first) % stride:
                    continue
                ok, frame = capture.retrieve()
                if not ok:
                    raise SystemExit('decode failed part-way through the clip')
                detections = [dict(track_id=int(d['track_id']), confidence=float(d['confidence']),
                                   bbox=[float(v) for v in d['bbox']])
                              for d in detector.infer(frame)]
                handle.write(json.dumps(dict(second=index/fps, detections=detections))+'\n')
                processed += 1
                if processed % 100 == 0:
                    rate = processed/max(1e-9, time.time()-began)
                    print(f'    {processed} frames  {rate:.1f} fps', flush=True)
    finally:
        capture.release()
    if not processed:
        raise SystemExit('no frames processed')
    temporary.replace(destination)
    print(f'    cached {processed} frames in {time.time()-began:.0f}s -> {destination.name}')


def load_cache(path):
    header, frames = None, []
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            value = json.loads(line)
            if value.get('kind') == 'header':
                header = value
            else:
                frames.append(value)
    return header, frames


# ------------------------------------------------------------------ sweeping

def replay(frames, height, options, base):
    """Replay the counter over cached detections. No inference here."""
    counter = RackCounter(replace(base, **options))
    for record in frames:
        counter.update([dict(track_id=d['track_id'], confidence=d['confidence'],
                             bbox=list(d['bbox'])) for d in record['detections']],
                       height, record['second'])
    return counter.count, counter.suppressed


def counter_options():
    keys = list(COUNTER_GRID)
    seen = set()
    for values in itertools.product(*(COUNTER_GRID[k] for k in keys)):
        option = dict(zip(keys, values))
        if option['dedupe'] == 'global':
            option['duplicate_iou'] = DEPLOYED['duplicate_iou']   # unused in this mode
        if option['cooldown'] == 0:
            option['dedupe'] = 'spatial'                          # no window, mode is moot
            option['duplicate_iou'] = DEPLOYED['duplicate_iou']
        marker = tuple(sorted(option.items()))
        if marker in seen:
            continue
        seen.add(marker)
        yield option


def distance_from_deployed(option, conf, iou, settings):
    """Small number = close to what is running today. Used only to break ties."""
    score = 0.0
    score += abs(option['line']-DEPLOYED['line'])*10
    score += 0 if option['anchor'] == DEPLOYED['anchor'] else 1
    score += abs(option['movement']-DEPLOYED['movement'])/10
    score += abs(option['cooldown']-DEPLOYED['cooldown'])
    score += abs(conf-settings.confidence)*2
    score += abs(iou-0.70)*2        # the corrected default
    return score


# ---------------------------------------------------------------------- main

def resolve_clips(args, settings):
    clips = [(path, expected, sha256(path)) for path, expected in args.pairs]
    if args.benchmark:
        store = LabStore(args.lab_root or settings.lab_root)
        root = Path(args.record_root or settings.record_root)
        for key in args.benchmark:
            record = store.get('benchmark', key)
            raw = root/'raw'/(record['clip_id']+'.mp4')
            if not raw.is_file():
                sys.exit(f'benchmark {key} points at a missing clip: {raw}')
            clips.append((raw, int(record['expected_count']), sha256(raw)))
    for path, _, _ in clips:
        if not Path(path).is_file():
            sys.exit(f'clip not found: {path}')
    return clips


def main(argv=None):
    args = parse_args(argv)
    settings = Settings()
    if args.model:
        settings = replace(settings, model=args.model)
    if not settings.model.is_file():
        sys.exit(f'model not found: {settings.model}  (set RACK_MODEL_PATH or pass --model)')

    clips = resolve_clips(args, settings)
    if not clips:
        sys.exit('give at least one --video/--expected pair or one --benchmark')
    if args.duration:
        print('NOTE: --duration is set, so every --expected must be the count for that window only.\n')

    confs = args.conf or DETECTOR_GRID['conf']
    ious = args.iou or DETECTOR_GRID['iou']
    model_hash = sha256(settings.model)
    total_expected = sum(expected for _, expected, _ in clips)
    print(f'model      {settings.model}  ({model_hash[:12]})')
    print(f'clips      {len(clips)}, human count {total_expected} racks in total')
    print(f'detector   conf={confs} iou={ious} imgsz={settings.imgsz} sample_fps={args.sample_fps}')
    print(f'counter    {sum(1 for _ in counter_options())} combinations replayed per detector setting\n')

    rows = []
    for conf, iou in itertools.product(confs, ious):
        streams = []
        for path, expected, clip_hash in clips:
            destination = args.cache_dir/cache_key(model_hash, clip_hash, conf, iou,
                                                   settings.imgsz, args.sample_fps,
                                                   args.start, args.duration)
            if not destination.is_file():
                if args.from_cache:
                    sys.exit(f'--from-cache given but {destination.name} is missing')
                print(f'  inference conf={conf} iou={iou} on {Path(path).name}')
                run_detection(path, settings, conf, iou, args.start, args.duration,
                              args.sample_fps, destination)
            header, frames = load_cache(destination)
            streams.append((header, frames, expected))

        for option in counter_options():
            error = 0
            counted = 0
            suppressed = 0
            for header, frames, expected in streams:
                count, dropped = replay(frames, header['height'], option, settings)
                error += abs(count-expected)
                counted += count
                suppressed += dropped
            rows.append(dict(conf=conf, iou=iou, **option, counted=counted,
                             expected=total_expected, absolute_error=error,
                             percentage_error=round(100*error/total_expected, 2) if total_expected else None,
                             suppressed=suppressed,
                             churn=round(distance_from_deployed(option, conf, iou, settings), 3)))
        print(f'  swept conf={conf} iou={iou}: best error so far '
              f'{min(r["absolute_error"] for r in rows)}')

    rows.sort(key=lambda r: (r['absolute_error'], r['churn']))
    with open(args.csv, 'w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f'\n{len(rows)} settings scored, full table in {args.csv}')
    print(f'\ntop {args.top} (human count = {total_expected})')
    header = f'{"err":>4} {"got":>4} {"conf":>5} {"iou":>5} {"line":>5} {"anchor":>7} {"move":>5} {"cool":>5} {"dedupe":>8} {"dupIoU":>7}'
    print(header)
    print('-'*len(header))
    for row in rows[:args.top]:
        print(f'{row["absolute_error"]:4d} {row["counted"]:4d} {row["conf"]:5.2f} {row["iou"]:5.2f} '
              f'{row["line"]:5.2f} {row["anchor"]:>7} {row["movement"]:5.0f} {row["cooldown"]:5.2f} '
              f'{row["dedupe"]:>8} {row["duplicate_iou"]:7.2f}')

    best = rows[0]
    print('\nbest settings:')
    print(f'  RACK_CONFIDENCE={best["conf"]}')
    print(f'  RACK_IOU={best["iou"]}')
    print(f'  COUNT_LINE_RATIO={best["line"]}')
    print(f'  COUNT_ANCHOR={best["anchor"]}')
    print(f'  MIN_DOWNWARD_PIXELS={best["movement"]}')
    print(f'  EVENT_COOLDOWN_SECONDS={best["cooldown"]}')
    print(f'  COUNT_DEDUPE={best["dedupe"]}')
    print(f'  COUNT_DUPLICATE_IOU={best["duplicate_iou"]}')
    print(f'\n  counted {best["counted"]} against {total_expected} counted by hand '
          f'({best["percentage_error"]}% off)')

    ties = sum(1 for row in rows if row['absolute_error'] == best['absolute_error'])
    if ties > 1:
        print(f'\n{ties} settings tie at this error. That usually means the clips are too short\n'
              'or too easy to separate them -- add a clip with racks travelling touching\n'
              'before trusting any single row.')
    if best['absolute_error'] == 0 and total_expected < 20:
        print('\nA perfect score on fewer than 20 racks is not evidence. Re-run with more clips.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
