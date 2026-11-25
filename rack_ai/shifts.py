"""สรุปยอดนับเก๊ะเป็นรายชั่วโมงและรายกะ

ทำไมรายชั่วโมงเป็นตัวตั้ง
-------------------------
นิยามกะของโรงงานมีชั่วโมงที่ไม่อยู่ในกะไหนเลย (18:00–20:00) ถ้าเขียนโค้ดโดยรวม
ยอดเข้ากะตรง ๆ เก๊ะที่ผ่านช่วงนั้นจะหายไปเงียบ ๆ และไม่มีใครรู้ว่าหายเพราะอะไร
โมดูลนี้จึงนับเป็นรายชั่วโมงก่อนเสมอ แล้วให้กะเป็นแค่การจัดกลุ่มของชั่วโมง
ผลคือทุกชั่วโมงปรากฏที่เดียวเสมอ ยอดรวมของกลุ่มจึงเท่ากับยอดรวมของวันเสมอ

ขอบเขตของ "วันรายงาน"
---------------------
วันรายงานของวันที่ D เริ่ม 07:00 ของวัน D และจบ 08:00 ของวัน D+1 รวม 25 ชั่วโมง
ซึ่งตรงกับที่ PCC/src/lib/rack-report.ts ใช้อยู่แล้ว ทั้งสองระบบจึงได้ตัวเลขตรงกัน

    กะเช้า  07:00–18:00 ของวัน D        11 ชั่วโมง
    นอกกะ   18:00–20:00 ของวัน D         2 ชั่วโมง
    กะดึก   20:00 วัน D – 08:00 วัน D+1  12 ชั่วโมง
                                        ----------
                                         25 ชั่วโมง

ข้อควรรู้: ชั่วโมง 07:00–08:00 ของวัน D+1 เป็นชั่วโมงสุดท้ายของกะดึกวัน D และเป็น
ชั่วโมงแรกของกะเช้าวัน D+1 ด้วย ถ้าเอายอดหลายวันรายงานมาบวกกันตรง ๆ ชั่วโมงนั้นจะ
ถูกนับสองครั้ง — เป็นผลจากนิยามกะของโรงงานเอง ไม่ใช่ข้อบกพร่องของการคำนวณ
"""
from datetime import datetime, timedelta, timezone

# เวลาโรงงานเป็นเวลาไทย ไม่พึ่ง timezone ของเครื่องที่รันเพราะเซิร์ฟเวอร์อาจตั้งเป็น UTC
BANGKOK = timezone(timedelta(hours=7))

DAY_START_HOUR = 7
DAY_END_HOUR = 18
NIGHT_START_HOUR = 20
NIGHT_END_HOUR = 32  # 08:00 ของวันถัดไป นับต่อเนื่องจากเที่ยงคืนวันเดียวกัน

REPORT_HOURS = 25  # 07:00 ถึง 08:00 ของวันถัดไป

GROUPS = (
    ('day', 'กะเช้า', DAY_START_HOUR, DAY_END_HOUR),
    ('outside', 'นอกกะ', DAY_END_HOUR, NIGHT_START_HOUR),
    ('night', 'กะดึก', NIGHT_START_HOUR, NIGHT_END_HOUR),
)


def midnight(date_key: str) -> datetime:
    """เที่ยงคืนตามเวลาไทยของวันที่ที่ขอ — ใช้เป็นจุดอ้างอิงของทุกการคำนวณ"""
    return datetime.strptime(date_key, '%Y-%m-%d').replace(tzinfo=BANGKOK)


def report_window(date_key: str) -> tuple[float, float]:
    """ช่วงเวลา unix ของวันรายงาน: 07:00 วัน D ถึง 08:00 วัน D+1"""
    base = midnight(date_key)
    start = base + timedelta(hours=DAY_START_HOUR)
    return start.timestamp(), (base + timedelta(hours=NIGHT_END_HOUR)).timestamp()


def today_key(now: float | None = None) -> str:
    """วันรายงานที่ครอบเวลาปัจจุบัน — ก่อน 07:00 ยังถือว่าเป็นวันรายงานของเมื่อวาน"""
    moment = datetime.fromtimestamp(now, BANGKOK) if now is not None else datetime.now(BANGKOK)
    if moment.hour < DAY_START_HOUR:
        moment -= timedelta(days=1)
    return moment.strftime('%Y-%m-%d')


def hourly(timestamps, date_key: str) -> list[dict]:
    """แจกแจงเวลาที่นับได้ลงช่องรายชั่วโมงของวันรายงาน"""
    base = midnight(date_key)
    buckets = []
    for index in range(REPORT_HOURS):
        offset = DAY_START_HOUR + index
        start = base + timedelta(hours=offset)
        buckets.append({
            'hour': offset % 24,
            'label': f'{offset % 24:02d}:00',
            'start': start.timestamp(),
            'end': (start + timedelta(hours=1)).timestamp(),
            'count': 0,
            # ชั่วโมงที่ล้นไปวันถัดไป ต้องบอกให้ชัด ไม่งั้น 07:00 สองอันจะดูเหมือนกัน
            'next_day': offset >= 24,
        })
    for moment in timestamps:
        index = int((moment - buckets[0]['start']) // 3600)
        if 0 <= index < REPORT_HOURS:
            buckets[index]['count'] += 1
    return buckets


def shifts(buckets: list[dict]) -> list[dict]:
    """จัดกลุ่มชั่วโมงเป็นกะ — ทุกชั่วโมงเข้ากลุ่มเดียว ยอดรวมจึงไม่มีทางเพี้ยน"""
    base_hour = DAY_START_HOUR
    groups = []
    for key, name, start_hour, end_hour in GROUPS:
        chosen = [
            bucket for index, bucket in enumerate(buckets)
            if start_hour <= base_hour + index < end_hour
        ]
        groups.append({
            'key': key,
            'name': name,
            'label': f'{start_hour % 24:02d}:00–{end_hour % 24:02d}:00',
            'count': sum(bucket['count'] for bucket in chosen),
            'hours': len(chosen),
            'start': chosen[0]['start'] if chosen else None,
            'end': chosen[-1]['end'] if chosen else None,
        })
    return groups


def summarise(timestamps, date_key: str, now: float | None = None) -> dict:
    """รูปแบบเดียวที่ทั้ง API และหน้าจอใช้ร่วมกัน"""
    buckets = hourly(timestamps, date_key)
    groups = shifts(buckets)
    moment = now if now is not None else datetime.now(BANGKOK).timestamp()
    for bucket in buckets:
        # แยก "ยังไม่ถึงเวลา" ออกจาก "ถึงเวลาแล้วแต่นับได้ศูนย์" — สองอย่างนี้ไม่เหมือนกัน
        bucket['pending'] = bucket['start'] > moment
    for group in groups:
        group['current'] = bool(
            group['start'] is not None and group['start'] <= moment < group['end']
        )
    start, end = report_window(date_key)
    return {
        'date': date_key,
        'start': start,
        'end': end,
        'total': sum(bucket['count'] for bucket in buckets),
        'hours': buckets,
        'shifts': groups,
    }
