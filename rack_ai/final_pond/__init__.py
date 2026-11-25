"""งาน AI ของกล้องบ่อสุดท้าย — ตรวจหมวกนิรภัยต่อเนื่อง และรอบตรวจแม่เหล็กรายชั่วโมง

โครงสร้างตั้งใจให้ตรรกะของโรงงานแยกออกจากงานวิชั่นอย่างชัดเจน

    lever.py   แปลงค่าตำแหน่งคันโยกเป็นเหตุการณ์การยกคันโยก
    weight.py  ตัดสินว่าน้ำหนักบนตาชั่งนิ่งแล้ว
    rounds.py  รวมคันโยก น้ำหนัก และเวลา ให้เป็นรอบตรวจที่ตรวจย้อนหลังได้

สามไฟล์นี้ไม่ import กล้อง โมเดล หรือไลบรารีภาพใด ๆ จึงทดสอบได้ครบทุกกรณี
ก่อนที่กล้อง โมเดลหมวก และตาชั่งจะพร้อม ซึ่งเป็นเหตุผลที่เริ่มจากส่วนนี้
"""
from .lever import LeverAbandoned, LeverActivation, LeverStateMachine
from .rounds import Inspection, RoundLedger, round_key_of, summarise
from .weight import StableWeight, WeightReading

__all__ = [
    'LeverAbandoned', 'LeverActivation', 'LeverStateMachine',
    'Inspection', 'RoundLedger', 'round_key_of', 'summarise',
    'StableWeight', 'WeightReading',
]
