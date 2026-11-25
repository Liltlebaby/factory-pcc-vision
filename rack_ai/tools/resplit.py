#!/usr/bin/env python3
"""Re-split an exported YOLO dataset by source clip instead of at random.

A random split is wrong for fixed-camera footage: frames seconds apart are
nearly the same picture, so the same rack lands in train and in test and the
score measures memorisation. Holding out whole clips is the only split that
measures what happens on footage the model has not seen.

The export this was written for already held out two night clips, but every
daylight frame sat in train -- so its metrics could only ever describe night.
Sending one whole daylight clip to validation and another to test is what makes
a daylight number exist at all.
"""
import argparse
import collections
import json
import re
import shutil
import zipfile
from pathlib import Path


def source(name):
    """Which recording a frame came from, by filename."""
    if name.startswith('clip_'):
        return 'day_'+name.split('_')[1]
    found = re.search(r'_p(\d\d)_', name)
    return 'night_p'+found.group(1) if found else 'unknown'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--src', required=True, help='folder holding train/ valid/ test/')
    parser.add_argument('--out', required=True)
    parser.add_argument('--valid', required=True, help='comma separated source ids for validation')
    parser.add_argument('--test', required=True, help='comma separated source ids for test')
    parser.add_argument('--zip', default='')
    args = parser.parse_args()

    valid = {s.strip() for s in args.valid.split(',') if s.strip()}
    test = {s.strip() for s in args.test.split(',') if s.strip()}
    overlap = valid & test
    if overlap:
        raise SystemExit(f'a clip cannot be in both valid and test: {sorted(overlap)}')

    src = Path(args.src)
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    for split in ('train', 'valid', 'test'):
        (out/split/'images').mkdir(parents=True, exist_ok=True)
        (out/split/'labels').mkdir(parents=True, exist_ok=True)

    moved = collections.defaultdict(collections.Counter)
    boxes = collections.Counter()
    for split in ('train', 'valid', 'test'):
        for image in sorted((src/split/'images').glob('*')):
            origin = source(image.name)
            target = 'valid' if origin in valid else 'test' if origin in test else 'train'
            shutil.copy2(image, out/target/'images'/image.name)
            label = src/split/'labels'/(image.stem+'.txt')
            if label.is_file():
                shutil.copy2(label, out/target/'labels'/label.name)
                boxes[target] += sum(1 for line in label.read_text().splitlines() if line.strip())
            moved[target][origin] += 1

    (out/'data.yaml').write_text(
        'train: ../train/images\nval: ../valid/images\ntest: ../test/images\n\n'
        'nc: 1\nnames: [\'rack\']\n', encoding='utf-8')

    report = {}
    for split in ('train', 'valid', 'test'):
        count = sum(moved[split].values())
        day = sum(v for k, v in moved[split].items() if k.startswith('day'))
        report[split] = dict(images=count, boxes=boxes[split], day=day, night=count-day,
                             sources=dict(sorted(moved[split].items())))
        print(f'{split:6s} {count:4d} ภาพ  {boxes[split]:5d} กล่อง  '
              f'(กลางวัน {day}, กลางคืน {count-day})')
        print(f'       {dict(sorted(moved[split].items()))}')

    everywhere = collections.Counter()
    for split in ('train', 'valid', 'test'):
        for origin in moved[split]:
            everywhere[origin] += 1
    spread = [k for k, v in everywhere.items() if v > 1]
    print('\nคลิปที่อยู่มากกว่าหนึ่ง split:', spread or 'ไม่มี — สะอาด')
    report['clips_in_more_than_one_split'] = spread
    (out/'split_report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                         encoding='utf-8')

    if args.zip:
        with zipfile.ZipFile(args.zip, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(out.rglob('*')):
                if path.is_file():
                    archive.write(path, path.relative_to(out))
        print(f'\n{args.zip}  {Path(args.zip).stat().st_size/1e6:.1f} MB')


if __name__ == '__main__':
    main()
