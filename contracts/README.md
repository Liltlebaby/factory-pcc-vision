# Factory Monitoring Contracts

สัญญาข้อมูลกลางระหว่าง Vision Monitor, PCC และอุปกรณ์หน้างาน รุ่น `v1`.

- `ai-event.v1.schema.json` — เหตุการณ์ AI ที่บันทึกถาวรและส่งซ้ำได้โดยไม่เพิ่มรายการซ้ำ
- `station-ai-status.v1.schema.json` — สถานะล่าสุดที่ PCC อ่านจาก Vision Monitor โดยไม่มีภาพหรือ credential
- `sensor-telemetry.v1.schema.json` — ค่าจาก gateway/PLC/เซ็นเซอร์เข้า PCC

หลักสำคัญ:

1. เก็บเวลาเป็น ISO 8601 UTC และแสดงผล Asia/Bangkok ที่ UI
2. `event_id` และ `measurement_id` ต้องไม่ซ้ำและคงเดิมเมื่อ retry
3. ไม่ใช้เลข `0` แทน “ไม่มีข้อมูล”
4. แยก `process_status` ออกจาก `data_status`
5. สัญญาเหล่านี้ไม่มี RTSP URL, token, password, ภาพ หรือวิดีโอ

