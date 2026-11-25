"""เก็บภาพนิ่งจากกล้องเพื่อทำ dataset — ไม่ต้องดาวน์โหลดวิดีโอ

ทำไมไม่ต้องโหลดวิดีโอ
----------------------
Roboflow กับเครื่องมือตีกรอบทุกตัวรับ "ภาพนิ่ง" ไม่ใช่วิดีโอ ต่อให้อัปโหลดวิดีโอ
ได้ มันก็แค่ไปแตกเป็นเฟรมให้อยู่ดี เราดึงเฟรมจาก RTSP ได้โดยตรงอยู่แล้ว
จึงข้ามปัญหาสิทธิ์ดาวน์โหลดของ DVR ไปทั้งหมด

เครื่องมือนี้ต่อ playback ทีละช่วงเวลา ดึงเฟรมออกมาเป็น .jpg แล้วเขียนลงโฟลเดอร์
เดียว พร้อมชื่อที่บอกวันและเวลา ลากทั้งโฟลเดอร์เข้า Roboflow ได้เลย

หัวใจคือความหลากหลาย ไม่ใช่จำนวน
----------------------------------
ภาพ 500 ใบจากช่วงสิบนาทีเดียวกันสอนโมเดลได้น้อยกว่าภาพ 200 ใบจากคนละชั่วโมง
คนละวัน คนละแสง เพราะโมเดลจะเห็นแต่สถานการณ์เดียว เครื่องมือนี้จึงทำสองอย่าง

    รับหลายช่วงเวลาในครั้งเดียว   เพื่อให้ได้ทั้งเช้า สาย บ่าย และกลางคืน
    ตัดภาพที่ซ้ำกับที่เก็บไปแล้ว   เพื่อไม่ให้ได้ภาพนิ่ง ๆ เหมือนกันร้อยใบ

การตัดภาพซ้ำสำคัญกว่าที่คิด เพราะถ้าไม่ทำ งานตีกรอบส่วนใหญ่จะหมดไปกับภาพที่
แทบไม่ต่างกัน ซึ่งเสียทั้งเวลาคนและโควตาของ Roboflow ไปเปล่า ๆ
"""
import argparse
import sys
import time
from pathlib import Path
from urllib.parse import quote

import numpy as np

# ขนาดภาพย่อที่ใช้เทียบความต่าง เล็กพอให้เร็วและไม่สนใจรายละเอียดจุกจิก
THUMB = (64, 36)


def thumbnail(frame_gray_small: np.ndarray) -> np.ndarray:
    return frame_gray_small.astype(np.float32) / 255.0


def difference(a: np.ndarray, b: np.ndarray) -> float:
    """ความต่างเฉลี่ยของสองภาพย่อ 0 = เหมือนกันเป๊ะ"""
    if a.shape != b.shape:
        raise ValueError('ภาพย่อต้องขนาดเท่ากัน')
    return float(np.abs(a - b).mean())


def is_new(candidate: np.ndarray, kept: list, threshold: float) -> bool:
    """ภาพนี้ต่างจากทุกภาพที่เก็บไว้แล้วมากพอจะคุ้มค่าตีกรอบไหม"""
    return all(difference(candidate, other) >= threshold for other in kept)


def windows_from(text: str) -> list[tuple[str, str]]:
    """แปลง '2026-09-19 08:00,2026-09-19 14:00' เป็นรายการช่วงเวลา"""
    found = []
    for piece in text.split(','):
        piece = piece.strip()
        if not piece:
            continue
        try:
            moment = time.strptime(piece, '%Y-%m-%d %H:%M')
        except ValueError as exc:
            raise ValueError(f'รูปแบบเวลาไม่ถูก ต้องเป็น "YYYY-MM-DD HH:MM": {piece}') from exc
        found.append((time.strftime('%Y_%m_%d_%H_%M_00', moment),
                      time.strftime('%Y%m%d_%H%M', moment)))
    if not found:
        raise ValueError('ต้องระบุอย่างน้อยหนึ่งช่วงเวลา')
    return found


def credentials_in(base: str, user: str | None, password: str | None) -> str:
    """ใส่ชื่อผู้ใช้และรหัสผ่านลง URL โดยเข้ารหัสอักขระพิเศษให้ถูกต้อง

    ทำไมต้องมีตัวนี้
    ----------------
    รหัสผ่านที่มี @ : / # ? & หรือช่องว่าง ทำให้ URL ถูกแยกส่วนผิด ตัวอย่างชัดสุด
    คือ @ — `rtsp://user:p@ss@host` ถูกตัดที่ @ ตัวแรก กลายเป็นผู้ใช้ "user:p"
    รหัส "ss" และโฮสต์ "host" ผลคือ 401 ทุกครั้งโดยไม่มีอะไรบอกว่าเพราะอะไร

    เป็นกับดักที่เจอบ่อยหลังเปลี่ยนรหัสผ่านให้แข็งแรงขึ้น เพราะรหัสที่แข็งแรง
    มักมีอักขระพิเศษพอดี
    """
    if not user and not password:
        return base
    scheme, _, rest = base.partition('://')
    if not rest:
        raise ValueError('base ต้องขึ้นต้นด้วย rtsp://')
    if '@' in rest:
        raise ValueError('ใส่ --user/--password แล้วอย่าใส่รหัสผ่านใน --base ซ้ำอีก')
    # safe='' บังคับให้เข้ารหัสทุกอักขระที่มีความหมายพิเศษใน URL
    return f"{scheme}://{quote(user or '', safe='')}:{quote(password or '', safe='')}@{rest}"


def fit_to_now(start: str, minutes: float, now: float) -> float | None:
    """ตัดช่วงเวลาให้ไม่เลยเวลาปัจจุบัน

    DVR ยังไม่มีภาพของเวลาที่ยังมาไม่ถึง ถ้าขอไปจะได้ 404 Not Found ซึ่งดูเหมือน
    ต่อกล้องไม่ติด ทั้งที่แค่ยังไม่ถึงเวลา — เจอจริงตอนใส่ 13:00 ของวันนี้ไว้ล่วงหน้า

    คืน None ถ้าช่วงนั้นยังไม่เริ่ม คืนจำนวนนาทีที่ดึงได้จริงถ้าเพิ่งผ่านไปบางส่วน
    เผื่อไว้หนึ่งนาที เพราะ DVR เขียนไฟล์ช้ากว่าเวลาจริงเล็กน้อย
    """
    begin = time.mktime(time.strptime(start, '%Y_%m_%d_%H_%M_%S'))
    available = (now - 60 - begin) / 60
    if available < 1:
        return None
    return min(minutes, available)


def spread_every(minutes: float, every: float, max_per_window: int) -> float:
    """ระยะห่างระหว่างภาพ ที่ทำให้ภาพกระจายเต็มช่วงเวลา ไม่ไปกองอยู่ต้นช่วง

    ถ้าเก็บทุก 2 วินาทีแต่จำกัด 60 ภาพ ภาพจะครบตั้งแต่นาทีที่ 2 แล้วหยุด
    อีก 28 นาทีที่เหลือไม่ได้ใช้เลย — เจอจริงกับช่วง 13:00–15:00 ของวันที่ 19
    จึงยืดระยะให้ภาพสุดท้ายตกใกล้ท้ายช่วงพอดี
    """
    if max_per_window <= 0:
        return every
    return max(every, minutes * 60 / max_per_window)


def playback_url(base: str, channel: int, start: str, minutes: float) -> str:
    """สร้าง URL ของ Dahua/imou สำหรับช่วงเวลาที่ขอ"""
    finish = time.strftime('%Y_%m_%d_%H_%M_%S',
                           time.localtime(time.mktime(time.strptime(start, '%Y_%m_%d_%H_%M_%S'))
                                          + minutes * 60))
    return (f'{base.rstrip("/")}/cam/playback?channel={channel}'
            f'&starttime={start}&endtime={finish}')


def main(argv=None) -> int:
    import cv2

    parser = argparse.ArgumentParser(description='เก็บภาพนิ่งจากกล้องเพื่อทำ dataset')
    parser.add_argument('--base', required=True,
                        help='เช่น rtsp://USER:PASS@192.168.1.64:554')
    parser.add_argument('--channel', type=int, default=11)
    parser.add_argument('--windows', required=True,
                        help='ช่วงเวลาคั่นด้วยคอมมา เช่น "2026-09-19 08:00,2026-09-19 14:00"')
    parser.add_argument('--minutes', type=float, default=10, help='ดึงช่วงละกี่นาที')
    parser.add_argument('--every', type=float, default=3.0, help='พิจารณาเฟรมทุกกี่วินาทีของวิดีโอ')
    parser.add_argument('--out', required=True)
    parser.add_argument('--min-difference', type=float, default=0.035,
                        help='ต่างจากภาพที่เก็บแล้วน้อยกว่านี้ถือว่าซ้ำ ข้ามไป')
    parser.add_argument('--max-per-window', type=int, default=60)
    parser.add_argument('--retries', type=int, default=3,
                        help='ลองต่อใหม่กี่ครั้งต่อหนึ่งช่วงเวลา ก่อนจะข้ามไป')
    parser.add_argument('--user', default=None,
                        help='ชื่อผู้ใช้ DVR ใส่แยกแบบนี้ปลอดภัยกว่าใส่ใน --base')
    parser.add_argument('--password', default=None,
                        help='รหัสผ่าน DVR ระบบจะเข้ารหัสอักขระพิเศษให้เอง')
    args = parser.parse_args(argv)

    try:
        windows = windows_from(args.windows)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    # ลืมกรอกรหัสผ่านแล้วได้ 401 ทุกช่วง เป็นอาการที่ดูเหมือนปัญหาเครือข่าย
    # ทั้งที่เป็นเรื่องกรอกค่าไม่ครบ ตรวจให้ชัดตั้งแต่ก่อนเริ่มดีกว่า
    for placeholder in ('USER', 'PASS'):
        if f'{placeholder}:' in args.base or f':{placeholder}@' in args.base:
            print(f'ยังไม่ได้แก้ {placeholder} ใน --base กรอกชื่อผู้ใช้และรหัสผ่านจริงก่อน',
                  file=sys.stderr)
            return 2
    try:
        base = credentials_in(args.base, args.user, args.password)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    kept_thumbs: list[np.ndarray] = []
    saved = skipped = 0
    not_yet: list[str] = []
    failed: list[str] = []

    for start, label in windows:
        print(f'\n=== {label} ===')
        minutes = fit_to_now(start, args.minutes, time.time())
        if minutes is None:
            print('  ยังไม่ถึงเวลานี้ DVR ยังไม่มีภาพ ข้ามไป')
            not_yet.append(label)
            continue
        if minutes < args.minutes:
            print(f'  ช่วงนี้เพิ่งผ่านไป {minutes:.0f} นาที ดึงเท่าที่มี')
        url = playback_url(base, args.channel, start, minutes)
        # DVR ตัวนี้ตอบ 401 ในการเชื่อมต่อครั้งแรกเป็นครั้งคราว แล้วครั้งถัดไปผ่าน
        # เคยเจอมาแล้วสองครั้งตอนทดสอบ จึงลองซ้ำก่อนจะยอมแพ้และข้ามช่วงนั้นไป
        capture = None
        for attempt in range(1, args.retries + 1):
            capture = cv2.VideoCapture(url)
            if capture.isOpened():
                break
            capture.release()
            capture = None
            if attempt < args.retries:
                print(f'  ต่อไม่ติด ลองใหม่ครั้งที่ {attempt + 1}')
                time.sleep(2.0)
        if capture is None:
            print(f'  ต่อไม่ได้หลังลอง {args.retries} ครั้ง ข้ามช่วงนี้', file=sys.stderr)
            print('  ถ้าขึ้น 404 แปลว่า DVR ไม่มีไฟล์บันทึกของช่วงนี้ เช่น เก่าเกินที่เก็บไว้', file=sys.stderr)
            failed.append(label)
            continue
        source_fps = capture.get(cv2.CAP_PROP_FPS) or 20.0
        every = spread_every(minutes, args.every, args.max_per_window)
        if every > args.every:
            print(f'  เก็บทุก {every:.0f} วินาที ให้ภาพกระจายครบ {minutes:.0f} นาที')
        stride = max(1, int(source_fps * every))
        index = misses = taken = seen = duplicates = 0
        while taken < args.max_per_window:
            ok, frame = capture.read()
            if not ok:
                misses += 1
                if misses > 150:
                    break
                time.sleep(0.2)
                continue
            misses = 0
            index += 1
            if index % stride:
                continue
            seen += 1
            small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), THUMB)
            candidate = thumbnail(small)
            if not is_new(candidate, kept_thumbs, args.min_difference):
                skipped += 1
                duplicates += 1
                continue
            kept_thumbs.append(candidate)
            seconds = int(index / source_fps)
            name = f'{label}_{seconds // 60:02d}m{seconds % 60:02d}s.jpg'
            cv2.imwrite(str(out / name), frame)
            saved += 1
            taken += 1
        capture.release()
        print(f'  เก็บได้ {taken} ภาพ  (ดูไป {seen} เฟรม ซ้ำ {duplicates})')

    print(f'\nรวมเก็บได้ {saved} ภาพ  ข้ามภาพซ้ำ {skipped} ภาพ')
    print(f'อยู่ใน {out}')
    if not_yet:
        print(f"ยังไม่ถึงเวลา ข้ามไป: {', '.join(not_yet)}")
    if failed:
        print(f"ดึงไม่ได้: {', '.join(failed)}")
    if saved + skipped and skipped > saved * 10:
        # ฉากโรงงานนิ่งมาก คนตัวเล็กในภาพ ภาพทั้งเฟรมจึงต่างกันน้อย
        # เกณฑ์ที่สูงไปจะทิ้งภาพที่มีคนเดินอยู่ไปด้วย
        print(f'\nตัดภาพซ้ำไปเยอะ ({skipped} ต่อ {saved}) ลองลด --min-difference ลง เช่น 0.012')
    if saved < 150:
        print('\nจำนวนยังน้อยสำหรับเทรนโมเดล ควรเพิ่มช่วงเวลาให้หลากหลายกว่านี้')
        print('แนะนำให้ครอบทั้งกะเช้าและกะดึก และหลายวัน เพื่อให้ได้แสงที่ต่างกัน')
    print('ลากทั้งโฟลเดอร์เข้า Roboflow ได้เลย ไม่ต้องแปลงอะไรก่อน')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
