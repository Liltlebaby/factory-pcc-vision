# Final Pond IoT Gateway

Gateway นี้อ่านเซ็นเซอร์ pH และอุณหภูมิน้ำผ่าน RS485/Modbus RTU แล้วส่งข้อมูลเข้า `POST /api/v1/telemetry` ของ PCC ทุกค่ามี Measurement ID คงที่สำหรับ Retry และมี SQLite Spool ป้องกันข้อมูลหายเมื่อเครือข่ายหรือ PCC หยุดชั่วคราว

## หลักความปลอดภัยของข้อมูล

- `mock` ถูกส่งเป็น `source_mode=demo` เสมอ
- `modbus` เท่านั้นที่ส่งเป็น `source_mode=live`
- อ่าน Sensor ไม่ได้จะไม่สร้างค่าทดแทน
- HTTP 5xx/Network Error จะ Retry ด้วย Exponential Backoff
- HTTP 4xx ที่แก้ด้วยการ Retry ไม่ได้จะย้ายไป Dead-letter Queue
- Token อยู่ใน Environment เท่านั้น ไม่ฝังใน Source Code/Firmware

## เริ่มทดสอบโดยไม่ต่ออุปกรณ์

```powershell
cd PCC\integrations\pond_gateway
python -m venv .venv
.\.venv\Scripts\python -m pip install --requirement requirements.txt
$env:PCC_TELEMETRY_TOKEN="local-test-token"
$env:POND_GATEWAY_MODE="mock"
.\.venv\Scripts\python -m pond_gateway.main --dry-run
```

คำสั่งนี้พิมพ์ Payload และไม่ส่งเข้า PCC หากต้องการส่งจริงให้ตั้ง Token ให้ตรงกับ PCC แล้วใช้ `--once`

## การต่อ RS485

1. จ่ายไฟ Sensor ตามสเปกผู้ผลิต แยกจาก USB-RS485 หากอุปกรณ์กำหนด
2. ต่อ `A → A`, `B → B` และ Signal Ground ตามคู่มือ
3. ใช้ Terminator 120Ω เฉพาะปลาย Bus เมื่อสายยาว/มีสัญญาณสะท้อน
4. ตรวจ Baudrate, Parity, Stop bits และ Slave ID
5. อ่านคู่มือรุ่นจริงเพื่อยืนยัน Function Code, Register Address, Scale, Offset และ Signed/Unsigned
6. ทดสอบ `--dry-run` ก่อนเปลี่ยน `POND_GATEWAY_MODE=modbus`

> PyModbus ใช้ Register Address แบบ Zero-based หากคู่มือเขียน Register 1 อาจต้องตั้ง Address 0 ห้ามใช้ค่าตัวอย่างใน `env.example` กับ Production จนกว่าจะยืนยันจากคู่มืออุปกรณ์จริง

## ตรวจ Configuration และ Health

```powershell
python -m pond_gateway.main --check-config
python -m pond_gateway.main --healthcheck
python -m unittest discover -s tests -v
```

Heartbeat อยู่ที่ `POND_HEARTBEAT_PATH` และบอก Source Mode, เวลารอบล่าสุด, Queue Depth, Dead-letter Count และ Error ล่าสุด
Healthcheck จะผ่านเมื่ออ่านค่าครบทั้ง 2 ตัว, ส่ง PCC สำเร็จ, Queue ว่าง และไม่มี Dead-letter เท่านั้น

## เปิดใช้งานจริง

- Windows Edge PC: ติดตั้ง Python/Dependencies แล้วรันเป็น Windows Service โดยใช้ `COMx`
- Linux Edge PC: ใช้ `/dev/ttyUSB0` และกำหนดสิทธิ์ Serial ให้ Service Account
- Docker: ใช้ Profile `pond-iot` ใน Production Compose และ Map `/dev/ttyUSB0` เข้า Container

ก่อนเปิด Alert อัตโนมัติ ต้อง Calibration pH ด้วยสารมาตรฐาน ตรวจเทียบอุณหภูมิกับเครื่องอ้างอิง และให้ QC ลงนามยืนยันผล
