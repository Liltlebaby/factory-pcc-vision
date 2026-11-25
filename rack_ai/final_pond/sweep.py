"""ลองหลายค่าตั้งกับเฟรมชุดเดียวกัน แล้วบอกว่าค่าไหนเจอคนได้ดีที่สุด

ทำไมต้องกวาดแทนการเดา
----------------------
รอบแรกใช้ yolo11n ที่ imgsz=960 conf=0.35 แล้วพลาดคนที่ยืนชัดกลางภาพ
การเดาว่า "น่าจะเพราะโมเดลเล็กไป" หรือ "น่าจะเพราะภาพถูกย่อมากไป" ไม่ช่วยอะไร
เพราะเดาผิดหนึ่งครั้งก็เสียเวลาอีกรอบ กวาดทีเดียวแล้ววัดจากผลจริงเร็วกว่า

กล้องมุมสูงมองลงมาในโรงงานเป็นมุมที่ชุดข้อมูล COCO มีน้อย โมเดลเล็กจึงพลาดง่าย
กว่าที่ตัวเลขความแม่นบนเว็บบอกไว้มาก

ข้อควรระวังในการอ่านผล
-----------------------
"เจอคนมากกว่า" ไม่ได้แปลว่า "ดีกว่า" เสมอไป เพราะอาจเป็นกล่องหลอกที่เพิ่มขึ้น
เครื่องมือนี้จึงเซฟภาพวาดกล่องของค่าที่ดีที่สุดไว้ให้ดูด้วยตาเสมอ ตัวเลขใช้
คัดตัวเลือก แต่คนต้องเป็นคนตัดสินว่ากล่องนั้นคือคนจริง
"""
import argparse
import sys
import time
from pathlib import Path

DEFAULT_MODELS = ('yolo11n.pt', 'yolo11s.pt', 'yolo11m.pt')
DEFAULT_SIZES = (960, 1280)
DEFAULT_CONFIDENCE = (0.25,)


def rank(results: list[dict]) -> list[dict]:
    """เรียงผลจากดีไปแย่ — แยกออกมาเพื่อทดสอบได้โดยไม่ต้องมีโมเดล

    เรียงตามจำนวนคนที่เจอก่อน แล้วค่อยดูเวลาที่ใช้ เพราะตอนนี้ปัญหาคือหาคนไม่เจอ
    ไม่ใช่ช้าเกินไป ถ้าวันหนึ่งกลายเป็นเจอมากเกินจริง ต้องเปลี่ยนวิธีเรียง
    """
    return sorted(results, key=lambda row: (-row['people'], row['seconds']))


def main(argv=None) -> int:
    import cv2

    from .vision import YoloVision, observe_frame, summarise

    parser = argparse.ArgumentParser(description='กวาดหาค่าตั้งที่ตรวจคนได้ดีที่สุด')
    parser.add_argument('--frames', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--models', nargs='+', default=list(DEFAULT_MODELS))
    parser.add_argument('--sizes', nargs='+', type=int, default=list(DEFAULT_SIZES))
    parser.add_argument('--confidence', nargs='+', type=float, default=list(DEFAULT_CONFIDENCE))
    parser.add_argument('--limit', type=int, default=0, help='ใช้กี่เฟรม 0 = ทั้งหมด')
    args = parser.parse_args(argv)

    frames = sorted(Path(args.frames).glob('*.jpg'))
    if args.limit:
        frames = frames[:args.limit]
    if not frames:
        print(f'ไม่พบไฟล์ .jpg ใน {args.frames}', file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    images = [cv2.imread(str(path)) for path in frames]
    images = [image for image in images if image is not None]
    print(f'ใช้ {len(images)} เฟรม  ขนาด {images[0].shape[1]}x{images[0].shape[0]}\n')

    results = []
    for model in args.models:
        for size in args.sizes:
            for conf in args.confidence:
                label = f'{model} imgsz={size} conf={conf}'
                try:
                    vision = YoloVision(model, None, imgsz=size, confidence=conf)
                except Exception as exc:
                    print(f'{label:<34} โหลดไม่ได้: {type(exc).__name__}', file=sys.stderr)
                    continue
                began = time.monotonic()
                people = empty = 0
                for image in images:
                    found = observe_frame(image.shape[0], vision.people(image), [])
                    totals = summarise(found)
                    people += totals['people']
                    empty += 1 if totals['people'] == 0 else 0
                seconds = time.monotonic() - began
                results.append({'label': label, 'model': model, 'imgsz': size,
                                'confidence': conf, 'people': people, 'empty': empty,
                                'seconds': round(seconds, 1)})
                print(f'{label:<34} เจอคน {people:>4}   เฟรมว่าง {empty:>3}/{len(images)}'
                      f'   {seconds:>5.1f} วิ')

    if not results:
        print('ไม่มีค่าตั้งไหนรันได้เลย', file=sys.stderr)
        return 2

    ordered = rank(results)
    best = ordered[0]
    print('\n--- เรียงจากเจอคนมากที่สุด ---')
    for row in ordered:
        print(f"  {row['label']:<34} {row['people']:>4} คน   {row['seconds']:>5.1f} วิ")

    print(f"\nดีที่สุด: {best['label']}  เจอ {best['people']} คน "
          f"เฟรมว่าง {best['empty']}/{len(images)}")
    print('กำลังเซฟภาพวาดกล่องของค่านี้ไว้ให้ดูด้วยตา...')

    vision = YoloVision(best['model'], None, imgsz=best['imgsz'], confidence=best['confidence'])
    (out / 'best').mkdir(exist_ok=True)
    for path, image in zip(frames, images):
        canvas = image.copy()
        for found in observe_frame(image.shape[0], vision.people(image), []):
            box = found.box
            cv2.rectangle(canvas, (int(box.x1), int(box.y1)), (int(box.x2), int(box.y2)),
                          (60, 200, 60), 3)
            cv2.putText(canvas, f'#{found.track_id} {found.confidence:.2f} h{found.height_ratio:.2f}',
                        (int(box.x1), max(14, int(box.y1) - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (60, 200, 60), 2, cv2.LINE_AA)
        cv2.imwrite(str(out / 'best' / path.name), canvas)

    print(f"เสร็จแล้ว ดูภาพใน {out / 'best'}")
    print('ตัวเลขบอกได้แค่ว่าเจอมากกว่า คนต้องดูเองว่ากล่องนั้นคือคนจริงหรือกล่องหลอก')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
