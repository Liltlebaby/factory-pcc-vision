"""ตรวจและแปลงเหตุการณ์ที่ worker ส่งเข้ามา ก่อนบันทึกลง ai_events

ทำไมแยกจาก app.py
-----------------
ส่วนนี้คือกฎว่าอะไรบันทึกได้บ้าง ซึ่งเป็นจุดที่ข้อมูลจากภายนอกเข้าสู่ฐานข้อมูล
จึงควรทดสอบได้ครบโดยไม่ต้องยก FastAPI ขึ้นมาทั้งตัว ตัว handler ใน app.py
เหลือหน้าที่แค่แปลง ValueError เป็น HTTP 422

หลักที่ยึด
----------
worker บอกได้เฉพาะสิ่งที่มันรู้ คือ task ของมัน ชนิดเหตุการณ์ เวลา และ payload
ส่วน station_id มาจากทะเบียนกล้องฝั่งเซิร์ฟเวอร์เสมอ ไม่ใช่จาก worker ไม่งั้น
worker ที่ตั้งค่าผิด (หรือถูกแก้) จะเขียนเหตุการณ์ลงสถานีอื่นได้
"""
from datetime import datetime, timezone

# ชนิดเหตุการณ์ที่ยอมรับ แยกตามชนิดงานในทะเบียน — ตั้งใจให้แคบ
# พิมพ์ชนิดผิดจะถูกปฏิเสธทันที ดีกว่าปล่อยให้เกิดชนิดใหม่เงียบ ๆ
# แล้วรายงานย้อนหลังนับไม่เจอโดยไม่มีใครรู้ว่าทำไม
EVENT_TYPES_BY_TASK_TYPE = {
    # เฝ้าพื้นที่ออกคู่ของการหายออกจากพื้นที่นานเกินกำหนดกับการกลับเข้ามา
    # ส่วนงานหมวกออกเฉพาะเรื่องหมวก — สองงานนี้แยกกันในทะเบียนแล้ว
    'area_presence': ('station_unattended', 'station_attended'),
    'ppe_compliance': ('ppe_violation', 'ppe_resolved'),
    'hourly_inspection': ('magnet_inspection',),
    'line_crossing_count': ('rack_counted',),
    'activity_assessment': ('activity_assessed',),
}

MAX_EVENTS = 50
MAX_COVERAGE = 50
# เผื่อนาฬิกาของ worker คลาดจากเซิร์ฟเวอร์ได้เล็กน้อย แต่ไม่ให้เขียนอนาคตไกล ๆ
# เพราะเหตุการณ์ที่ลงอนาคตจะไปโผล่ในรายงานของวันที่ยังไม่มาถึง แล้วลบออกยาก
FUTURE_TOLERANCE_SECONDS = 300
MAX_AGE_SECONDS = 7 * 24 * 3600


def _timestamp(value) -> float:
    if isinstance(value, (int, float)):
        moment = float(value)
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        except ValueError as exc:
            raise ValueError('occurred_at ต้องเป็น ISO-8601 หรือ unix timestamp') from exc
    else:
        raise ValueError('occurred_at ต้องเป็น ISO-8601 หรือ unix timestamp')
    if moment != moment or moment in (float('inf'), float('-inf')):
        raise ValueError('occurred_at ไม่ใช่ตัวเลขที่ใช้ได้')
    return moment


def normalise_events(camera, events, now: float) -> list[dict]:
    """แปลงเหตุการณ์จาก worker เป็นรูปแบบที่ LabStore.append_event รับได้"""
    if not isinstance(events, list) or not events:
        raise ValueError('ต้องมีอย่างน้อยหนึ่งเหตุการณ์')
    if len(events) > MAX_EVENTS:
        raise ValueError(f'ส่งได้ครั้งละไม่เกิน {MAX_EVENTS} เหตุการณ์')

    task_by_id = {task.task_id: task for task in camera.tasks}
    prepared = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('เหตุการณ์ต้องเป็น object')
        task = task_by_id.get(event.get('task_id'))
        if task is None:
            raise ValueError(f"task_id ไม่อยู่ในทะเบียนของกล้องนี้: {event.get('task_id')}")
        allowed = EVENT_TYPES_BY_TASK_TYPE.get(task.task_type)
        if allowed is None:
            raise ValueError(f'ยังไม่รองรับการบันทึกเหตุการณ์ของงานชนิด {task.task_type}')
        if event.get('type') not in allowed:
            raise ValueError(f"ชนิดเหตุการณ์ของ {task.task_id} ต้องเป็นหนึ่งใน {list(allowed)}")

        occurred_at = _timestamp(event.get('occurred_at'))
        if occurred_at > now + FUTURE_TOLERANCE_SECONDS:
            raise ValueError('occurred_at อยู่ในอนาคตไกลเกินไป ตรวจนาฬิกาของเครื่อง worker')
        if occurred_at < now - MAX_AGE_SECONDS:
            raise ValueError('occurred_at เก่าเกินกว่าที่จะรับย้อนหลัง')

        payload = event.get('payload')
        if payload is not None and not isinstance(payload, dict):
            raise ValueError('payload ต้องเป็น object หรือ null')

        # ไม่มี event_id มาก็สร้างจากข้อมูลที่กำหนดผลแน่นอน เพื่อให้ส่งซ้ำแล้วไม่เกิดแถวซ้ำ
        # แต่ผู้ส่งควรกำหนดเองจะดีกว่า เพราะรู้ว่าอะไรคือตัวแยกเหตุการณ์ที่แท้จริง
        event_id = event.get('event_id') or (
            f"{camera.camera_id}:{task.task_id}:{event['type']}:{int(occurred_at * 1_000_000)}"
        )
        prepared.append({
            'event_id': str(event_id),
            'camera_id': camera.camera_id,
            'task_id': task.task_id,
            # มาจากทะเบียนฝั่งเซิร์ฟเวอร์เสมอ ไม่รับจาก worker
            'station_id': camera.station_id,
            'type': event['type'],
            'occurred_at': datetime.fromtimestamp(occurred_at, timezone.utc)
                                   .isoformat().replace('+00:00', 'Z'),
            'model_version': event.get('model_version'),
            'rule_version': event.get('rule_version'),
            'payload': payload or {},
        })

    identities = [item['event_id'] for item in prepared]
    if len(identities) != len(set(identities)):
        raise ValueError('event_id ซ้ำกันภายในชุดเดียว')
    return prepared


def normalise_coverage(entries, now: float) -> list[tuple[str, float]]:
    """ตรวจรายการเวลาที่กล้องเห็นภาพจริง ก่อนนำไปบวกสะสมรายรอบ"""
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise ValueError('coverage ต้องเป็น array')
    if len(entries) > MAX_COVERAGE:
        raise ValueError(f'ส่ง coverage ได้ครั้งละไม่เกิน {MAX_COVERAGE} รอบ')
    prepared = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('รายการ coverage ต้องเป็น object')
        key = entry.get('round_key')
        try:
            datetime.strptime(str(key), '%Y-%m-%dT%H')
        except (TypeError, ValueError) as exc:
            raise ValueError('round_key ต้องอยู่ในรูปแบบ YYYY-MM-DDTHH') from exc
        seconds = entry.get('seconds')
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
            raise ValueError('seconds ต้องเป็นตัวเลข')
        seconds = float(seconds)
        # หนึ่งรอบยาวหนึ่งชั่วโมง จะเห็นภาพเกินนั้นไม่ได้ ค่าที่เกินแปลว่าฝั่ง worker
        # นับผิด ถ้าปล่อยผ่านจะทำให้รอบที่กล้องดับไปครึ่งหนึ่งดูเหมือนเห็นครบ
        if not 0 <= seconds <= 3600:
            raise ValueError('seconds ต้องอยู่ระหว่าง 0 ถึง 3600')
        prepared.append((str(key), seconds))
    keys = [key for key, _ in prepared]
    if len(keys) != len(set(keys)):
        raise ValueError('round_key ซ้ำกันภายในชุดเดียว')
    return prepared
