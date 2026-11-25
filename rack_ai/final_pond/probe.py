"""วัดสัญญาณตำแหน่งคันโยกจากกล้องจริง เพื่อตั้งค่า LeverStateMachine จากข้อมูล ไม่ใช่จากการเดา

ทำไมต้องมีเครื่องมือนี้
------------------------
`lever.py` ต้องการค่า `rest_below` กับ `check_above` ซึ่งขึ้นกับมุมกล้อง ระยะชัก
ของคันโยกจริง และแสงในโรงงาน ค่าเริ่มต้นที่ใส่ไว้เป็นเพียงจุดตั้งต้น ถ้าเอาไป
ใช้เลยโดยไม่วัด ระบบจะพลาดการตรวจจริงหรือรายงานการตรวจที่ไม่มีอยู่ ซึ่งแย่กว่า
ไม่มีระบบ เครื่องมือนี้บันทึกสัญญาณดิบลง CSV ให้เอามาดูว่าตอนคนยกคันโยกจริง
ตัวเลขขึ้นไปถึงเท่าไร แล้วค่อยตั้งเกณฑ์

วัดหลายสัญญาณพร้อมกันโดยตั้งใจ
------------------------------
ยังไม่รู้ว่าสัญญาณไหนแยกการยกคันโยกออกจากคนเดินผ่านได้ดีที่สุด จึงบันทึกทุกตัว
ในรอบเดียว แล้วเลือกทีหลังจากข้อมูลจริง เก็บใหม่รอบสองแพงกว่าเก็บเกินไว้ก่อนมาก
เพราะต้องรอให้มีคนมาตรวจแม่เหล็กอีกครั้ง

    diff_ratio  สัดส่วนพิกเซลใน ROI ที่ต่างจากภาพตอนคันโยกอยู่นิ่ง
    rise        ความสูงที่การเปลี่ยนแปลงขึ้นไปถึงใน ROI (0 = ล่างสุด, 1 = บนสุด)
    roi_mean    ความสว่างเฉลี่ยของ ROI ใช้ดูว่าแสงเปลี่ยนไปจนอ้างอิงเดิมใช้ไม่ได้แล้วไหม

ผลจากการวัดจริง 19 ก.ย. 2026 กล้องบ่อสุดท้าย
--------------------------------------------
ตอนออกแบบคิดว่า `rise` จะเป็นตัวหลักเพราะตรงกับ position ที่ state machine ต้องการ
ข้อมูลจริงบอกตรงข้าม: `rise` ดูแค่แถวบนสุดที่เปลี่ยน คนเดินไกล ๆ ที่ขอบบนของกรอบ
จึงดันมันขึ้นเต็ม 1.00 ได้ด้วยพิกเซลไม่กี่สิบจุด ส่วนคนที่มายืนทำงานที่คันโยกจริง
กลับได้แค่ 0.59 เพราะการเปลี่ยนแปลงกระจุกอยู่กลางกรอบ ไม่ถึงขอบบน

`diff_ratio` แยกสองกรณีนี้ได้ชัด คนทำงานที่คันโยก 0.21 ส่วนพื้นหลังรบกวน 0.02-0.07
ต่างกัน 3-10 เท่า จึงเปลี่ยนมาใช้ diff_ratio เป็นตัวจับช่วงน่าสนใจแทน และปิด rise
ไว้เป็นค่าเริ่มต้น ส่วน rise ยังบันทึกลง CSV ต่อไปเพราะเมื่อบีบ ROI ให้เหลือเฉพาะ
คันโยกแล้ว มันอาจกลับมาใช้ได้ — แต่ต้องพิสูจน์ด้วยข้อมูล ไม่ใช่ด้วยการสันนิษฐาน

ภาพอ้างอิง "คันโยกอยู่นิ่ง"
--------------------------
ใช้ค่ามัธยฐานของเฟรมในช่วงอุ่นเครื่อง ไม่ใช่เฟรมแรกเฟรมเดียว เพราะถ้าเฟรมแรก
บังเอิญมีคนยืนบังอยู่ ภาพอ้างอิงจะผิดทั้งรอบการวัด มัธยฐานทนต่อคนเดินผ่านได้
ตราบใดที่ส่วนใหญ่ของช่วงนั้นคันโยกอยู่นิ่งจริง
"""
import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np

# ต่างจากภาพอ้างอิงเกินเท่านี้ (0-255) จึงนับว่าพิกเซลนั้น "เปลี่ยน"
# ต่ำกว่านี้คือสัญญาณรบกวนของเซ็นเซอร์กับการบีบอัดวิดีโอ
CHANGE_THRESHOLD = 25
# แถวหนึ่งต้องมีพิกเซลเปลี่ยนเกินสัดส่วนนี้ จึงนับว่าการเปลี่ยนแปลงขึ้นมาถึงแถวนั้น
# กันไม่ให้พิกเซลหลงเพียงไม่กี่จุดที่ขอบบนดัน rise ขึ้นไปสุด
ROW_OCCUPANCY = 0.15


def stride_for(source_fps: float, target_fps: float) -> int:
    """อ่านทุกกี่เฟรมจึงจะได้ประมาณ target_fps ตัวอย่างต่อวินาทีของวิดีโอ

    ใช้เฉพาะโหมดอ่านไฟล์หรือ playback ที่เฟรมไหลมาเร็วกว่าเวลาจริง การ sleep
    แบบโหมดสดใช้ไม่ได้ เพราะมันคุมเวลานาฬิกา ไม่ใช่เวลาในวิดีโอ
    """
    if not source_fps or source_fps <= 0:
        return 1
    return max(1, round(source_fps / max(0.1, target_fps)))


def parse_roi(text: str) -> tuple[float, float, float, float]:
    """แปลง 'x1,y1,x2,y2' แบบ 0..1 — ใช้ค่าปกติเพื่อให้เปลี่ยนความละเอียดแล้วไม่ต้องแก้"""
    try:
        x1, y1, x2, y2 = (float(part) for part in text.split(','))
    except ValueError as exc:
        raise ValueError('ROI ต้องเป็น x1,y1,x2,y2 แบบ 0..1') from exc
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise ValueError('ROI ต้องอยู่ในช่วง 0..1 และ x1<x2, y1<y2')
    return x1, y1, x2, y2


def crop(frame: np.ndarray, roi) -> np.ndarray:
    """ตัด ROI ออกจากเฟรม รับได้ทั้งภาพสีและภาพเทา"""
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = roi
    left, right = int(x1 * width), max(int(x1 * width) + 1, int(x2 * width))
    top, bottom = int(y1 * height), max(int(y1 * height) + 1, int(y2 * height))
    return frame[top:bottom, left:right]


def position_signals(roi_gray: np.ndarray, reference: np.ndarray) -> dict:
    """สัญญาณทั้งหมดของหนึ่งเฟรม — numpy ล้วน ทดสอบได้โดยไม่ต้องมีกล้อง"""
    if roi_gray.shape != reference.shape:
        raise ValueError('ROI กับภาพอ้างอิงต้องมีขนาดเท่ากัน')
    delta = roi_gray.astype(np.int16) - reference.astype(np.int16)
    # กล้องปรับแสงอัตโนมัติตลอดเวลา ทั้งภาพจึงสว่างขึ้นหรือมืดลงพร้อมกันโดยไม่มีอะไรขยับ
    # ถ้าไม่หักส่วนนี้ออก ทุกพิกเซลจะถูกนับว่า "เปลี่ยน" ทีเดียวทั้งกรอบ
    # ใช้มัธยฐานเพราะทนต่อบริเวณที่เปลี่ยนจริง ตราบใดที่มันไม่เกินครึ่งหนึ่งของกรอบ
    delta = delta - int(np.median(delta))
    difference = np.abs(delta)
    changed = difference > CHANGE_THRESHOLD
    rows, _ = changed.shape
    per_row = changed.mean(axis=1)
    occupied = np.flatnonzero(per_row >= ROW_OCCUPANCY)
    # แถว 0 คือบนสุดของ ROI จึงกลับด้านให้ค่ามาก = ยกสูง ตรงกับที่ state machine คาด
    rise = 0.0 if occupied.size == 0 else float((rows - 1 - occupied[0]) / max(1, rows - 1))
    return {
        'diff_ratio': round(float(changed.mean()), 5),
        'rise': round(rise, 5),
        'roi_mean': round(float(roi_gray.mean()), 2),
    }


def reference_frame(samples: list[np.ndarray]) -> np.ndarray:
    """ภาพอ้างอิงตอนคันโยกนิ่ง — มัธยฐานทนคนเดินผ่านได้ดีกว่าค่าเฉลี่ย"""
    if not samples:
        raise ValueError('ไม่มีเฟรมสำหรับสร้างภาพอ้างอิง')
    return np.median(np.stack(samples), axis=0).astype(np.uint8)


def main(argv=None) -> int:
    import cv2  # นำเข้าตรงนี้เพื่อให้ทดสอบส่วนคำนวณได้โดยไม่ต้องมี OpenCV

    parser = argparse.ArgumentParser(description='วัดสัญญาณตำแหน่งคันโยกจาก RTSP หรือไฟล์วิดีโอ')
    parser.add_argument('--source', required=True, help='RTSP URL หรือพาธไฟล์วิดีโอ')
    parser.add_argument('--roi', required=True, help='x1,y1,x2,y2 แบบ 0..1')
    parser.add_argument('--out', required=True, help='โฟลเดอร์ผลลัพธ์')
    parser.add_argument('--minutes', type=float, default=20, help='วัดนานกี่นาที')
    parser.add_argument('--fps', type=float, default=5, help='วัดกี่เฟรมต่อวินาที')
    parser.add_argument('--warmup-seconds', type=float, default=60,
                        help='เก็บภาพอ้างอิงนานกี่วินาทีก่อนเริ่มวัด')
    parser.add_argument('--snapshot-seconds', type=float, default=30,
                        help='บันทึกภาพ ROI ทุกกี่วินาที ใส่ 0 เพื่อไม่บันทึก')
    parser.add_argument('--full-frames', action='store_true',
                        help='บันทึกทั้งเฟรมด้วย สำหรับเอาไปทำ dataset หมวกนิรภัย')
    parser.add_argument('--playback', action='store_true',
                        help='อ่านวิดีโอย้อนหลังหรือไฟล์ ไม่ใช่กล้องสด '
                             'เวลาในผลลัพธ์จะนับจากเวลาในวิดีโอ ไม่ใช่นาฬิกาเครื่อง')
    parser.add_argument('--diff-threshold', type=float, default=0.15,
                        help='เก็บภาพเมื่อสัดส่วนพิกเซลที่เปลี่ยนถึงค่านี้ ใส่ 0 เพื่อปิด '
                             'วัดจากของจริงแล้วตัวนี้แยกคนทำงานที่คันโยกออกจากพื้นหลังได้ดีกว่า rise')
    parser.add_argument('--rise-threshold', type=float, default=0,
                        help='เก็บภาพเมื่อ rise ถึงค่านี้ ปิดไว้เป็นค่าเริ่มต้นเพราะ rise ดูแค่แถว '
                             'บนสุดที่เปลี่ยน คนเดินไกล ๆ ที่ขอบบนกรอบจึงดัน rise ขึ้นเต็มได้')
    parser.add_argument('--rise-cooldown', type=float, default=20,
                        help='หลังเก็บภาพจากเหตุการณ์หนึ่งแล้ว เว้นกี่วินาทีจึงเก็บครั้งต่อไป')
    parser.add_argument('--preview', action='store_true',
                        help='ดึงเฟรมเดียวมาวาดกรอบ ROI แล้วจบ ใช้ตรวจว่ากรอบตรงคันโยกจริง '
                             'ก่อนจะเสียเวลาวัดเป็นชั่วโมง')
    parser.add_argument('--start-clock', default=None,
                        help='เวลาจริงของวินาทีแรกในวิดีโอ เช่น "2026-09-19 10:00:00" '
                             'ใส่แล้วคอลัมน์ clock จะตรงกับไทม์ไลน์ของ DVR')
    args = parser.parse_args(argv)

    roi = parse_roi(args.roi)
    out = Path(args.out)
    (out / 'roi').mkdir(parents=True, exist_ok=True)
    if args.full_frames:
        (out / 'frames').mkdir(parents=True, exist_ok=True)

    capture = cv2.VideoCapture(args.source)
    if not capture.isOpened():
        print('เปิดกล้องหรือไฟล์ไม่ได้ ตรวจ URL และรหัสผ่านอีกครั้ง', file=sys.stderr)
        return 2

    if args.preview:
        # เฟรมแรก ๆ ของ RTSP มักยังถอดรหัสไม่ครบ อ่านทิ้งไปหลายเฟรมก่อนแล้วเอาเฟรมล่าสุด
        frame = None
        for _ in range(20):
            ok, candidate = capture.read()
            if ok:
                frame = candidate
        capture.release()
        if frame is None:
            print('ต่อกล้องได้แต่ยังไม่ได้ภาพ ลองใหม่อีกครั้ง', file=sys.stderr)
            return 2
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = roi
        box = (int(x1 * width), int(y1 * height), int(x2 * width), int(y2 * height))
        annotated = frame.copy()
        cv2.rectangle(annotated, box[:2], box[2:], (0, 0, 255), 3)
        piece = crop(frame, roi)
        zoom = cv2.resize(piece, (piece.shape[1] * 4, piece.shape[0] * 4), interpolation=cv2.INTER_LANCZOS4)
        cv2.imwrite(str(out / 'frame.png'), frame)
        cv2.imwrite(str(out / 'roi_preview.png'), annotated)
        cv2.imwrite(str(out / 'roi_zoom.png'), zoom)
        print(f'ขนาดเฟรมจริง {width} x {height}  อัตราส่วน {width / height:.3f}')
        print(f'กรอบ ROI ในพิกเซล x {box[0]}-{box[2]}  y {box[1]}-{box[3]} '
              f'({box[2] - box[0]} x {box[3] - box[1]})')
        print(f'บันทึกไว้ที่ {out} — เปิด roi_preview.png ดูว่ากรอบแดงครอบคันโยกไหม')
        return 0

    interval = 1.0 / args.fps
    started = time.time()
    samples, reference = [], None
    last_snapshot = 0.0
    last_rise_snapshot = -1e9
    rise_hits = 0
    (out / 'candidates').mkdir(parents=True, exist_ok=True)
    written = 0

    source_fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    stride = stride_for(source_fps, args.fps) if args.playback else 1
    origin = None
    if args.start_clock:
        try:
            origin = time.mktime(time.strptime(args.start_clock, '%Y-%m-%d %H:%M:%S'))
        except ValueError:
            print('--start-clock ต้องเป็น "YYYY-MM-DD HH:MM:SS"', file=sys.stderr)
            return 2
    if args.playback:
        if not source_fps:
            print('อ่าน fps ของวิดีโอไม่ได้ จะถือว่า 25 fps '
                  'ถ้าเวลาในผลลัพธ์เพี้ยน ให้ระบุ --fps ให้ตรงกับของจริง', file=sys.stderr)
            source_fps = 25.0
            stride = stride_for(source_fps, args.fps)
        print(f'โหมดย้อนหลัง: วิดีโอ {source_fps:.1f} fps อ่านทุก {stride} เฟรม')
    read_index, misses = 0, 0
    elapsed_playback = 0.0

    with (out / 'signals.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['time', 'clock', 'diff_ratio', 'rise', 'roi_mean'])
        writer.writeheader()
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    if args.playback:
                        # อ่านไม่ได้ติดกันนาน ๆ จึงถือว่าจบวิดีโอ
                        #
                        # เดิมตั้งไว้ 30 ครั้งแบบไม่หน่วงเลย ซึ่งอันตราย: ใน playback เฟรมมา
                        # ทางเครือข่าย ถ้าสะดุดแม้เสี้ยววินาที ลูปจะยิงครบ 30 ครั้งในพริบตา
                        # แล้วสรุปว่าจบวิดีโอทั้งที่ยังไม่จบ
                        #
                        # ยังไม่เคยเกิดขึ้นจริงเท่าที่วัดมา (19 ก.ย. อ่านต่อเนื่องได้ 20 นาที
                        # จนผู้ใช้กดหยุดเอง) แต่กันไว้เพราะถ้าเกิดจริงมันเงียบสนิท
                        # ข้อมูลหายโดยไม่มีอะไรเตือน
                        misses += 1
                        if misses > 150:
                            print(f'อ่านไม่ได้ติดกัน {misses} ครั้ง ถือว่าจบวิดีโอ '
                                  f'(อ่านมาได้ {elapsed_playback / 60:.1f} นาที)')
                            break
                        time.sleep(0.2)
                        continue
                    # สตรีมสดสะดุดเป็นเรื่องปกติของ RTSP รอแล้วลองต่อ ไม่ใช่จบการวัด
                    time.sleep(0.5)
                    continue
                misses = 0
                read_index += 1
                if args.playback and read_index % stride:
                    continue

                # เวลาในวิดีโอ ไม่ใช่เวลานาฬิกา ไม่งั้นคลิปหนึ่งชั่วโมงที่อ่านจบใน
                # สองนาทีจะถูกบันทึกว่ากินเวลาสองนาที แล้วเทียบกับไทม์ไลน์ DVR ไม่ได้
                elapsed = read_index / source_fps if args.playback else time.time() - started
                elapsed_playback = elapsed
                if elapsed >= args.minutes * 60:
                    break
                now = (origin + elapsed) if origin is not None else time.time()
                grey = cv2.cvtColor(crop(frame, roi), cv2.COLOR_BGR2GRAY)

                if reference is None:
                    samples.append(grey)
                    if elapsed >= args.warmup_seconds:
                        reference = reference_frame(samples)
                        cv2.imwrite(str(out / 'reference.png'), reference)
                        print(f'ภาพอ้างอิงพร้อม จาก {len(samples)} เฟรม เริ่มวัดแล้ว')
                    if not args.playback:
                        time.sleep(interval)
                    continue

                signals = position_signals(grey, reference)
                writer.writerow({
                    'time': round(elapsed, 3),
                    'clock': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)),
                    **signals,
                })
                written += 1
                if written % 100 == 0:
                    handle.flush()
                    print(f'{written} เฟรม  rise ล่าสุด {signals["rise"]:.3f}  diff {signals["diff_ratio"]:.3f}')

                # เก็บ "ช่วงที่น่าสนใจ" ให้อัตโนมัติ คนจะได้ไม่ต้องไล่ดูวิดีโอทั้งชั่วโมงเอง
                # ตั้งใจเก็บทั้งภาพ ROI และเฟรมเต็ม เพราะเฟรมเต็มเป็นตัวบอกว่าที่ขยับคือ
                # คันโยกจริง หรือเป็นคนเดินผ่านหน้ากล้อง ซึ่ง rise อย่างเดียวแยกไม่ได้
                triggered = (
                    (args.diff_threshold and signals['diff_ratio'] >= args.diff_threshold)
                    or (args.rise_threshold and signals['rise'] >= args.rise_threshold)
                )
                if triggered and elapsed - last_rise_snapshot >= args.rise_cooldown:
                    last_rise_snapshot = elapsed
                    rise_hits += 1
                    stamp = time.strftime('%H%M%S', time.localtime(now))
                    name = f'{stamp}_diff{signals["diff_ratio"]:.2f}_rise{signals["rise"]:.2f}'
                    cv2.imwrite(str(out / 'candidates' / f'{name}_roi.jpg'), crop(frame, roi))
                    cv2.imwrite(str(out / 'candidates' / f'{name}_full.jpg'), frame)
                    print(f'  พบช่วงน่าสนใจ {stamp}  diff {signals["diff_ratio"]:.2f}  rise {signals["rise"]:.2f}')

                if args.snapshot_seconds and elapsed - last_snapshot >= args.snapshot_seconds:
                    last_snapshot = elapsed
                    stamp = time.strftime('%H%M%S', time.localtime(now))
                    cv2.imwrite(str(out / 'roi' / f'{stamp}_{signals["rise"]:.3f}.jpg'),
                                crop(frame, roi))
                    if args.full_frames:
                        cv2.imwrite(str(out / 'frames' / f'{stamp}.jpg'), frame)
                if not args.playback:
                    time.sleep(interval)
        except KeyboardInterrupt:
            print('หยุดตามคำสั่ง')
        finally:
            capture.release()

    print(f'เสร็จแล้ว บันทึก {written} แถวไว้ที่ {out / "signals.csv"}')
    if args.diff_threshold or args.rise_threshold:
        print(f'ช่วงที่น่าสนใจ {rise_hits} ช่วง เก็บภาพไว้ใน {out / "candidates"} '
              f'(diff >= {args.diff_threshold})')
        if rise_hits == 0:
            print('  ไม่พบเลย แปลว่าชั่วโมงนี้ไม่มีใครมาทำงานที่คันโยก หรือเกณฑ์ตั้งสูงไป '
                  'ลองลด --diff-threshold แล้วรันซ้ำ ไม่ต้องดึงวิดีโอใหม่')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
