"""ตรวจว่า FPS กล้องนับเก๊ะที่แกว่ง เกิดจากกล้อง/DVR หรือจากเครื่องที่รันระบบ

วิธีคิด
-------
ภาพทุกเฟรมที่ DVR ส่งมามี "เวลาในสตรีม" (PTS) ติดมาด้วย ซึ่ง DVR เป็นคนใส่
ตอนเข้ารหัส ส่วน "เวลาที่มาถึง" คือตอนที่เครื่องเราอ่านได้ สองค่านี้แยกปัญหาได้

    PTS ขาดหาย (ข้ามไปหลายเฟรม)      DVR/กล้องไม่ได้ส่งเฟรมนั้นมาเลย  → ฝั่งกล้อง
    PTS ต่อเนื่อง แต่มาถึงเป็นก้อน      เฟรมครบแต่มาช้าแล้วทะลักทีเดียว  → เครือข่าย
                                                                   หรือเครื่องเรา
    ตัวนี้อ่านได้เรียบ แต่ระบบนับตก      กล้องปกติ ระบบนับอ่านไม่ทันเอง   → ระบบ

เครื่องมือนี้เปิดสตรีมเดียวกับระบบนับเป็นโปรเซสแยก อ่านทุกเฟรม และในเวลาเดียวกัน
ถาม FPS ที่ระบบนับเห็นจาก /api/status เทียบกันวินาทีต่อวินาที พร้อมวัดการเคลื่อนไหว
ในภาพ เพื่อดูว่าตอนเก๊ะเลื่อนมีอะไรเปลี่ยน

ข้อควรรู้: เปิดสตรีมเพิ่มอีกหนึ่งตัวชั่วคราว DVR รับได้ แต่ไม่ควรเปิดทิ้งไว้
"""
import argparse
import csv
import json
import os
import statistics
import sys
import threading
import time
import urllib.request
from pathlib import Path


def analyse(frames: list[tuple[float, float]], nominal_fps: float) -> dict:
    """สรุปผลจากรายการ (เวลามาถึง, PTS มิลลิวินาที) — แยกไว้ให้ทดสอบได้โดยไม่ต้องมีกล้อง

    เฟรมหาย = PTS กระโดดเกิน 1.5 เท่าของระยะปกติ
    มาช้า   = PTS ต่อเนื่อง แต่ห่างจากเฟรมก่อนหน้าเกิน 300 มิลลิวินาทีตามเวลาจริง
    """
    step = 1000.0 / nominal_fps
    missing = late = 0
    worst_gap = 0.0
    for (arrive_a, pts_a), (arrive_b, pts_b) in zip(frames, frames[1:]):
        pts_gap = pts_b - pts_a
        arrive_gap = (arrive_b - arrive_a) * 1000
        worst_gap = max(worst_gap, arrive_gap)
        if pts_gap > step * 1.5:
            missing += round(pts_gap / step) - 1
        elif arrive_gap > 300:
            late += 1
    duration = frames[-1][0] - frames[0][0] if len(frames) > 1 else 0
    return {
        'frames': len(frames),
        'seconds': round(duration, 1),
        'fps': round((len(frames) - 1) / duration, 2) if duration else 0,
        'missing_frames': missing,
        'late_bursts': late,
        'worst_gap_ms': round(worst_gap),
    }


def verdict(summary: dict, service_low_seconds: int, reader_low_seconds: int, seconds: int) -> str:
    """แปลตัวเลขเป็นคำตอบ — เกณฑ์ตั้งไว้หลวม ๆ ให้ชี้ทิศ ไม่ใช่ตัดสินเด็ดขาด"""
    if seconds == 0:
        return 'ไม่มีข้อมูลพอ'
    if summary['missing_frames'] > summary['frames'] * 0.02:
        return ('ฝั่งกล้อง/DVR: เฟรมหายตั้งแต่ต้นทาง (PTS ขาดช่วง) '
                'มักเกิดจาก bitrate ของช่องนี้ตั้งไว้ต่ำ พอภาพเคลื่อนไหวมากก็เข้ารหัสไม่ทัน')
    if reader_low_seconds > seconds * 0.1:
        return ('เครือข่ายหรือเครื่องนี้: เฟรมครบแต่มาถึงเป็นก้อน ทั้งตัวตรวจและระบบนับเห็นเหมือนกัน '
                'ดู CPU ของเครื่องในช่วงเดียวกัน ถ้า CPU ไม่เต็ม ให้สงสัยสาย LAN/สวิตช์')
    if service_low_seconds > seconds * 0.1:
        return ('ฝั่งระบบ: กล้องส่งมาเรียบ แต่ระบบนับอ่านไม่ทันเอง '
                'เครื่องไม่ว่างพอ เช่น มีงาน AI อื่นหรือสคริปต์อื่นรันพร้อมกัน')
    return 'ปกติ: ช่วงที่วัดไม่พบ FPS ตกทั้งฝั่งกล้องและฝั่งระบบ ลองวัดตอนเก๊ะเลื่อนผ่านจริง'


def poll_service(url: str, token: str, stop: threading.Event, out: dict):
    """เก็บ FPS กล้องที่ระบบนับเห็น แยกตามวินาที"""
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    while not stop.is_set():
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=2) as response:
                data = json.loads(response.read())
            out[int(time.monotonic())] = (float((data.get('fps') or {}).get('camera') or 0),
                                          float(data.get('inference_fps') or 0))
        except Exception:
            out.setdefault(int(time.monotonic()), (None, None))
        stop.wait(0.5)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='ตรวจ FPS กล้องนับเก๊ะ แยกปัญหากล้องกับระบบ')
    parser.add_argument('--seconds', type=int, default=120, help='วัดนานกี่วินาที ควรครอบช่วงที่เก๊ะเลื่อน')
    parser.add_argument('--status', default='http://127.0.0.1:8011/api/status')
    parser.add_argument('--transport', choices=('default', 'tcp', 'udp'), default='default',
                        help='default = แบบเดียวกับระบบนับตอนนี้')
    parser.add_argument('--out', default='rack_ai/data/diagnostics')
    args = parser.parse_args(argv)

    source = os.getenv('CAMERA_RTSP_AI', '')
    if not source:
        print('ไม่พบ CAMERA_RTSP_AI ให้รันผ่าน check_camera09_fps.ps1', file=sys.stderr)
        return 2
    if args.transport != 'default':
        # ต้องตั้งก่อน import cv2 ไม่งั้น OpenCV ไม่อ่านค่านี้
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = f'rtsp_transport;{args.transport}'
    import cv2
    import numpy as np

    capture = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
    if not capture.isOpened():
        # ห้ามพิมพ์ source เพราะมีรหัสผ่านอยู่ใน URL
        print('เปิดสตรีมกล้องไม่ได้', file=sys.stderr)
        return 2
    nominal = capture.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f'เปิดสตรีมได้ {width}x{height} ประกาศไว้ {nominal:.0f} FPS  transport={args.transport}')
    print(f'วัด {args.seconds} วินาที ระหว่างนี้ให้มีเก๊ะเลื่อนผ่านสักสองสามตัว\n')

    service: dict[int, tuple] = {}
    stop = threading.Event()
    token = os.getenv('RACK_API_TOKEN', '')
    poller = threading.Thread(target=poll_service, args=(args.status, token, stop, service), daemon=True)
    poller.start()

    frames: list[tuple[float, float]] = []
    per_second: dict[int, dict] = {}
    previous = None
    began = time.monotonic()
    index = 0
    try:
        while time.monotonic() - began < args.seconds:
            if not capture.grab():
                print('สตรีมขาดระหว่างวัด', file=sys.stderr)
                break
            now = time.monotonic()
            pts = capture.get(cv2.CAP_PROP_POS_MSEC)
            frames.append((now, pts))
            second = int(now)
            bucket = per_second.setdefault(second, {'frames': 0, 'motion': 0.0})
            bucket['frames'] += 1
            index += 1
            if index % 5 == 0:
                ok, frame = capture.retrieve()
                if ok:
                    small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (96, 108)).astype(np.float32)
                    if previous is not None:
                        bucket['motion'] = max(bucket['motion'], float(np.abs(small - previous).mean()))
                    previous = small
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        capture.release()

    if len(frames) < 2:
        print('ได้เฟรมไม่พอวิเคราะห์', file=sys.stderr)
        return 2

    summary = analyse(frames, nominal)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d_%H%M%S')
    table = out / f'camera09_fps_{stamp}.csv'
    rows = []
    low_reader = low_service = 0
    seconds = sorted(per_second)[1:-1]   # ตัดวินาทีแรกและสุดท้ายที่ไม่เต็ม
    for second in seconds:
        cam_service, ai = service.get(second, (None, None))
        reader = per_second[second]['frames']
        low_reader += reader < nominal * 0.6
        low_service += cam_service is not None and cam_service < nominal * 0.6
        rows.append({'second': second - seconds[0], 'reader_fps': reader,
                     'service_camera_fps': cam_service, 'service_ai_fps': ai,
                     'motion': round(per_second[second]['motion'], 2)})
    with table.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['second'])
        writer.writeheader()
        writer.writerows(rows)

    moving = [row for row in rows if row['motion'] >= 4]
    still = [row for row in rows if row['motion'] < 4]
    mean = lambda items, key: round(statistics.mean([r[key] for r in items if r[key] is not None]), 1) \
        if [r for r in items if r[key] is not None] else None

    print('--- ผลวัด ---')
    print(f"ตัวตรวจอ่านได้          {summary['fps']} FPS  ({summary['frames']} เฟรม ใน {summary['seconds']} วิ)")
    print(f"เฟรมหายจากต้นทาง       {summary['missing_frames']}  (PTS ขาดช่วง = DVR ไม่ได้ส่งมา)")
    print(f"เฟรมมาเป็นก้อน          {summary['late_bursts']} ครั้ง  ช่องว่างนานสุด {summary['worst_gap_ms']} ms")
    print(f"วินาทีที่ตัวตรวจได้ต่ำ     {low_reader} / {len(rows)}")
    print(f"วินาทีที่ระบบนับได้ต่ำ     {low_service} / {len(rows)}")
    print(f"ตอนภาพนิ่ง   ตัวตรวจ {mean(still, 'reader_fps')}  ระบบนับ {mean(still, 'service_camera_fps')} FPS")
    print(f"ตอนมีการเคลื่อนไหว ตัวตรวจ {mean(moving, 'reader_fps')}  ระบบนับ {mean(moving, 'service_camera_fps')} FPS"
          f"  ({len(moving)} วินาที)")
    print(f"\nสรุป: {verdict(summary, low_service, low_reader, len(rows))}")
    print(f'\nรายวินาทีอยู่ที่ {table}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
