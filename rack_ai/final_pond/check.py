"""วัดว่าโมเดลตรวจคนและตรวจหมวกทำงานได้แค่ไหนกับภาพจากกล้องตัวนี้จริง

ทำไมต้องวัดก่อนใช้
------------------
ตัวเลขความแม่นที่ผู้ทำโมเดลประกาศไว้ วัดจากภาพชุดของเขา ไม่ใช่ภาพจากกล้อง
มุมนี้ แสงนี้ ระยะนี้ การเอามาใช้โดยไม่วัดคือการเชื่อตัวเลขที่ไม่เกี่ยวกับงานเรา

เครื่องมือนี้รันโมเดลกับเฟรมที่เก็บไว้แล้ว วาดกล่องทับให้ดูด้วยตา และสรุปเป็น
ตัวเลขว่าเจอคนกี่คนต่อเฟรม ตัดสินเรื่องหมวกได้กี่คน ไม่ได้กี่คน

สิ่งที่เครื่องมือนี้ตอบไม่ได้
-----------------------------
มันไม่รู้ว่าคำตอบที่ถูกคืออะไร จึงบอกได้แค่ว่าโมเดล "เห็นอะไร" ไม่ใช่ "ถูกไหม"
การตัดสินว่าถูกหรือผิดต้องให้คนดูภาพที่วาดกล่องแล้วเทียบเอง ซึ่งเร็วกว่ามาก
เมื่อมีภาพวาดกล่องให้ดูอยู่ตรงหน้า
"""
import argparse
import csv
import sys
from pathlib import Path

from .vision import (
    BARE_HEAD_NAMES, HELMET_NAMES, PASS, UNDECIDED, VIOLATION,
    observe_frame, summarise,
)

COLOURS = {PASS: (60, 200, 60), VIOLATION: (60, 60, 230), UNDECIDED: (160, 160, 160)}


def report(rows: list[dict]) -> dict:
    """สรุปผลทั้งชุด — แยกออกมาเพื่อให้ทดสอบได้โดยไม่ต้องมีโมเดล"""
    if not rows:
        return {'frames': 0, 'people_total': 0, 'people_per_frame': 0.0,
                'decided': 0, 'undecided': 0, 'decided_ratio': None, 'empty_frames': 0}
    people = sum(row['people'] for row in rows)
    decided = sum(row['helmet_pass'] + row['no_helmet'] for row in rows)
    undecided = sum(row['undecided'] for row in rows)
    return {
        'frames': len(rows),
        'people_total': people,
        'people_per_frame': round(people / len(rows), 2),
        'decided': decided,
        'undecided': undecided,
        # ตัดสินได้กี่เปอร์เซ็นต์ของคนที่เจอ ถ้าต่ำมากแปลว่าโมเดลหมวกใช้กับมุมนี้ไม่ได้
        'decided_ratio': round(decided / people, 3) if people else None,
        'empty_frames': sum(1 for row in rows if row['people'] == 0),
    }


def main(argv=None) -> int:
    import cv2

    from .vision import YoloVision

    parser = argparse.ArgumentParser(description='วัดผลโมเดลกับเฟรมที่เก็บไว้')
    parser.add_argument('--frames', required=True, help='โฟลเดอร์ที่มีไฟล์ .jpg')
    parser.add_argument('--out', required=True, help='โฟลเดอร์ผลลัพธ์')
    parser.add_argument('--person-model', default='yolo11n.pt',
                        help='โมเดลตรวจคน ค่าเริ่มต้นดาวน์โหลดเองอัตโนมัติ')
    parser.add_argument('--ppe-model', default=None,
                        help='โมเดลตรวจหมวก ไม่ใส่ก็ได้ ทุกคนจะเป็น UNDECIDED')
    parser.add_argument('--imgsz', type=int, default=960)
    parser.add_argument('--confidence', type=float, default=0.35)
    parser.add_argument('--min-height-ratio', type=float, default=0.08,
                        help='คนที่เล็กกว่านี้ถือว่าตัดสินเรื่องหมวกไม่ได้')
    args = parser.parse_args(argv)

    frames = sorted(Path(args.frames).glob('*.jpg'))
    if not frames:
        print(f'ไม่พบไฟล์ .jpg ใน {args.frames}', file=sys.stderr)
        return 2
    out = Path(args.out)
    (out / 'annotated').mkdir(parents=True, exist_ok=True)

    vision = YoloVision(args.person_model, args.ppe_model,
                        imgsz=args.imgsz, confidence=args.confidence)

    if vision.ppe is not None:
        # ชื่อคลาสของแต่ละชุดน้ำหนักไม่เหมือนกัน ถ้าเราไม่รู้จักชื่อที่มันใช้
        # ทุกคนจะออกมาเป็น UNDECIDED โดยที่โมเดลทำงานถูกต้องทุกอย่าง
        # ซึ่งเป็นอาการที่หาสาเหตุยากมากถ้าไม่พิมพ์ชื่อคลาสออกมาดู
        names = [str(value).strip().lower() for value in vision.ppe.names.values()]
        known = [name for name in names if name in HELMET_NAMES or name in BARE_HEAD_NAMES]
        print('คลาสของโมเดล PPE:', ', '.join(sorted(set(names))))
        print('คลาสที่ระบบรู้จัก:', ', '.join(sorted(set(known))) or '(ไม่มีเลย)')
        if not known:
            print('\n*** ไม่รู้จักชื่อคลาสของโมเดลนี้เลย ทุกคนจะเป็น UNDECIDED ***',
                  file=sys.stderr)
            print('    ส่งรายชื่อคลาสข้างบนมาให้ผม แล้วผมเพิ่มให้ใน vision.py',
                  file=sys.stderr)
        print()

    rows = []
    for index, path in enumerate(frames, 1):
        frame = cv2.imread(str(path))
        if frame is None:
            print(f'อ่านไม่ได้ ข้ามไป: {path.name}', file=sys.stderr)
            continue
        people = vision.people(frame)
        detections = vision.ppe_boxes(frame)
        observations = observe_frame(frame.shape[0], people, detections)
        totals = summarise(observations)

        canvas = frame.copy()
        for found in observations:
            box = found.box
            colour = COLOURS[found.helmet_status]
            # คนที่เล็กเกินเกณฑ์วาดเส้นบาง เพื่อให้เห็นด้วยตาว่าทำไมถูกข้าม
            thin = found.height_ratio < args.min_height_ratio
            cv2.rectangle(canvas, (int(box.x1), int(box.y1)), (int(box.x2), int(box.y2)),
                          colour, 1 if thin else 3)
            label = f'#{found.track_id} {found.helmet_status} {found.height_ratio:.2f}'
            cv2.putText(canvas, label, (int(box.x1), max(14, int(box.y1) - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1, cv2.LINE_AA)
        cv2.imwrite(str(out / 'annotated' / path.name), canvas)

        rows.append({'frame': path.name, **totals})
        if index % 10 == 0:
            print(f'{index}/{len(frames)} เฟรม')

    with (out / 'people.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    totals = report(rows)
    print('\n--- สรุป ---')
    print(f"เฟรมทั้งหมด            {totals['frames']}")
    print(f"เฟรมที่ไม่เจอคนเลย      {totals['empty_frames']}")
    print(f"เจอคนรวม               {totals['people_total']}  ({totals['people_per_frame']} คน/เฟรม)")
    print(f"ตัดสินเรื่องหมวกได้     {totals['decided']}")
    print(f"ตัดสินไม่ได้            {totals['undecided']}")
    if totals['decided_ratio'] is not None:
        print(f"สัดส่วนที่ตัดสินได้     {totals['decided_ratio']:.1%}")
    if args.ppe_model is None:
        print('\nยังไม่ได้ใส่ --ppe-model ทุกคนจึงเป็น UNDECIDED ซึ่งถูกต้องแล้ว')
        print('ตอนนี้ดูแค่ว่ากล่องคนตรงตัวคนจริงไหม และเจอครบทุกคนในภาพหรือเปล่า')
    print(f"\nภาพวาดกล่องอยู่ใน {out / 'annotated'} — เปิดดูแล้วเทียบกับภาพจริง")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
