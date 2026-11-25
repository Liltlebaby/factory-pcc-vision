# Rack AI รุ่นแยกบริการ — Phase 1–8

อัปเดต Phase 4–8: ดู [PHASE4_8_TH.md](../docs/rack-ai/PHASE4_8_TH.md) สำหรับหน้า `/dataset`,
คัดภาพดิบ ตรวจกรอบ สร้างชุดข้อมูล เทรนรุ่นใหม่ และเปรียบเทียบโมเดล
สถานะนี้หมายถึงมี workflow แล้ว ไม่ได้หมายถึงเทรนโมเดลใหม่หรือรับรองความแม่นยำแล้ว

อัปเดต Phase 3: ดู [PHASE3_TH.md](../docs/rack-ai/PHASE3_TH.md) สำหรับตั้งเวลา, event recording,
stream-copy/fallback, คลิป annotated แยกไฟล์ และดาวน์โหลดประวัติ
รายละเอียด Phase 3 ใหม่นี้แทนข้อจำกัดของระบบบันทึกขั้นต้นในบันทึกเดิมด้านล่าง

## สถานะและขอบเขต

รุ่นนี้เป็นต้นแบบที่ทดสอบในเครื่อง ไม่ใช่รุ่นที่รับรอง production หรือความแม่นยำ 90%
เก็บ `best.pt` และสคริปต์เดิมไว้ ไม่เทรนทับ ไม่แทนบริการ PCC อัตโนมัติ

- Phase 1: ตัวอ่าน RTSP เจ้าของเดียวต่อสตรีม, บัฟเฟอร์ภาพล่าสุด, reconnect, ตรวจภาพเก่า, YOLO + ByteTrack
- Phase 2: FastAPI, WebSocket metadata, MJPEG, หน้าจอเฝ้าดู, token และ allowlist origin
- Phase 3 ขั้นต้น: เริ่ม/หยุดคลิปดิบ 10/15 นาทีหรือระบุเอง, SQLite + JSON, ประวัติและ archive กู้คืนได้
- Phase 3 เพิ่มแล้ว: FFmpeg stream-copy/fallback, ตารางเวลาครั้งเดียว, event recording แบบ opt-in,
  annotated แยกไฟล์, สถิติในช่วงเวลา, และทำเครื่องหมาย interrupted หลังรีสตาร์ต
- ยังต้องทดสอบระยะยาว/กล้อง main-stream จริง; ไม่มี pre-roll หรือการซ่อมไฟล์ที่เสียจากไฟดับอัตโนมัติ
- Phase 4–7: คัดภาพ active learning แบบ heuristic, auto-label รอตรวจ, หน้าแก้กรอบ,
  split ตามคลิป/session, ชุดข้อมูลเป็นรุ่นแยก, retraining และ model comparison
- Phase 8: งานหนักแยก process ครั้งละหนึ่งงาน, graceful cancellation/recovery,
  ล็อก launcher กันเปิดซ้ำ, เก็บยอดนับใน SQLite และตรวจ origin ของคำสั่งแก้ข้อมูล
  ยังต้องทดสอบโหลดต่อเนื่อง ความแม่นยำจริง และการสำรองข้อมูลก่อน production

## สิ่งที่นำกลับมาใช้และสิ่งที่แยกออก

นำ `best.pt`, ByteTrack และ `filter_racks` จาก `ai/rack_detector/offline_track_count.py` กลับมาใช้
แยกการอ่านกล้องออกจาก inference และแยกส่งภาพ/metadata ออกจากงาน AI
ไม่มีการลบไฟล์เดิม การ polling เดิมของ PCC ยังอยู่จนกว่าจะทดสอบและย้าย frontend นั้นโดยตรง
ชุดข้อมูล auto-label เดิมยังไม่ถือเป็น ground truth; ต้องตรวจทุกเก๊ะและกล่องที่รวมสองเก๊ะก่อนใช้ฝึก

## เริ่มใช้งาน Windows

เปิด PowerShell ที่โฟลเดอร์โครงการ `C:\Factory\123`

```powershell
python -m pip install -r rack_ai/requirements.txt
powershell -ExecutionPolicy Bypass -File rack_ai/start_camera09.ps1
```

launcher ใช้ค่ากล้องจาก `.env.camera.local` เดิมโดยไม่พิมพ์รหัสผ่าน
เปิด http://127.0.0.1:8011 แล้วกดเชื่อมต่อ ถ้าตั้ง RACK_API_TOKEN ให้กรอก token
อย่าเปิด uvicorn หลาย workers หรือ --reload เพราะจะเปิดตัวอ่านกล้องซ้ำ
กด Ctrl+C เพื่อปิดอย่างสุภาพ อย่าเปิด launcher ใหม่ซ้อนตัวเก่าบนพอร์ตเดียวกัน

การตั้งเครื่องใหม่: คัดลอก `.env.example` เป็น `.env` ใน rack_ai และกรอกค่าเฉพาะเครื่อง แล้วรัน:

```powershell
python -m rack_ai.run
```

ห้าม commit/share `.env` และไม่ใส่รหัสกล้องใน source code
ค่า CAMERA_RTSP_AI ใช้สตรีม AI; CAMERA_RTSP_RECORD ว่างหรือเหมือนกันจะใช้ reader เดียวกัน
หากกำหนดสตรีมบันทึกต่างกันจะมี reader หนึ่งตัวต่อสตรีม (รวมสองตัว ไม่แชร์ VideoCapture)
ตรวจ channel/substream จริงกับ DVR ก่อนเปลี่ยน ไม่มีการแก้ค่ากล้องให้อัตโนมัติ

กล้องบ่อสุดท้ายช่อง 11 บน DVR `192.168.1.64` แสดงภาพสดใน Vision Monitor ผ่าน
`FINAL_POND_RTSP` (Dahua substream `/cam/realmonitor?channel=11&subtype=1` ใน launcher ของเครื่องนี้)
หาก DVR ใช้บัญชีคนละชุดกับกล้องนับเก๊ะ ให้ตั้งค่า `FINAL_POND_RTSP` ก่อนรัน launcher
โดยมีตัวอ่านภาพแยกและส่ง JPEG preview ตาม substream ของ DVR (วัดได้ 15 FPS)
เมื่อมีโมเดล PEE จะเชื่อมกล้องต่อเนื่องแม้ไม่มีผู้ชม (เตรียมภาพสูงสุด 10 FPS เพื่อให้ AI มีภาพใหม่พอสำหรับเป้า 5 FPS)
ภาพนี้เป็น preview ไม่ใช่ผล AI:
งานตรวจหมวกและรอบแม่เหล็กยังแสดงเป็น planned จนกว่าจะทดสอบโมเดล/กฎและเปิด worker จริง
URL RTSP และรหัสผ่านอยู่ฝั่งบริการเท่านั้น ไม่ส่งไปหน้าเว็บหรือ Camera Registry

### ทดลองโมเดล PEE บน VISION MONITOR (อ่านอย่างเดียว)

โมเดล `best_PEE_V1.pt` มีคลาส `bare_head`, `helmet`, `worker` เท่านั้น ยังไม่มี
`magnet_lever` และยังไม่ยืนยันการโยกคันโยกจากวิดีโอ ไฟล์โมเดลอยู่ที่
`models/best_PEE_V1.pt` และ launcher ตั้ง `FINAL_POND_PPE_MODEL` ให้โดยอัตโนมัติ
เปิด `http://127.0.0.1:8011/#/` หรือหน้ากล้องบ่อสุดท้ายใน VISION MONITOR:
ภาพสดและตัวเลขคน/หมวกมาจากโมเดล PEE ในระบบเดียวกัน ไม่มีบริการพอร์ต 8012
ตัวตรวจเริ่มทำงานเบื้องหลังพร้อมบริการ ไม่ต้องเปิดหน้าเว็บ ใช้ JPEG จากตัวอ่านกล้องช่อง 11 เดิม
ไม่ได้ต่อ RTSP ซ้ำ หน้าเว็บอ่านผล AI ล่าสุดที่ประมวลผลไว้แล้ว งานตรวจหมวกยังเป็น pilot และยังไม่แจ้งเตือนเรื่องหมวก แต่ระบบเฝ้าคนในพื้นที่บ่อสุดท้ายจะบันทึกเหตุการณ์ `station_unattended` เมื่อไม่พบคนครบ 5 นาที (และ `station_attended` เมื่อกลับมา) โดยไม่จับเวลาตอนกล้องขาดภาพ
พื้นที่บ่อใช้ polygon เริ่มต้นจากมุมกล้อง 11 และนับเฉพาะจุดเท้าของกรอบคนที่อยู่ใน polygon; ควรยืนยันขอบเขตกับหน้างานและทดสอบคลิปต่างวันก่อนใช้เหตุการณ์เป็นหลักฐานจริง แจ้งเตือนแสดงใน Vision Monitor/ประวัติเหตุการณ์เท่านั้น ยังไม่ได้เชื่อม WhatsApp
ตั้งเป้า AI เป็น 5 FPS ผ่าน `FINAL_POND_PPE_FPS=5` (ค่าเริ่มต้น); ค่า `inference_fps` ในสถานะกล้องคือความเร็วที่วัดได้จริง ซึ่งอาจต่ำกว่าเป้าหมายเมื่อ CPU ทำงานหนัก
ผล `UNKNOWN` หมายถึงโมเดลยังตัดสินเรื่องหมวกไม่ได้ ไม่ใช่ไม่สวมหมวก
ข้อมูลใน PCC และงานรอบแม่เหล็กยังไม่ถือว่า live จาก pilot นี้
ผลจาก 59 ภาพคลิปเดียวต้องตรวจด้วยคลิปต่างวันโดยคนก่อนเปิดกฎจริง

## วิธีทำงาน

camera.py อ่านภาพต่อเนื่อง เก็บเพียงภาพล่าสุดพร้อม frame_id/timestamp/generation
ผู้บริโภคได้สำเนาภาพ จึงไม่ฝังกรอบลงในภาพดิบโดยไม่ตั้งใจ
detector.py รัน best.pt และ ByteTrack ใน inference thread เดียว ตรวจ CUDA อัตโนมัติ
counter.py ใช้ center ข้ามเส้นลง, เคยเห็นเหนือเส้น, ระยะเคลื่อนขั้นต่ำและ cooldown
COUNT_ANCHOR เลือก center/top/bottom ได้ ต้องทดสอบกับคลิปที่นับโดยคนก่อนใช้จริง
service.py ประกอบผลล่าสุดและ JPEG; client ช้าไม่ทำให้ AI รอ และไม่มีคิวภาพสะสม
WebSocket ส่งเฉพาะ metadata ไม่ส่งวิดีโอ หน้า monitor ใช้ภาพ JPEG snapshot ที่มี authentication;
MJPEG endpoint ยังพร้อมให้ PCC/proxy ใช้งาน

ยอดนับล่าสุดบันทึกลง SQLite แบบเบื้องหลังและอ่านคืนเมื่อเริ่มบริการ;
ไฟดับก่อนบันทึกสำเร็จอาจสูญเสียเหตุการณ์ล่าสุด ไม่ใช่การรับรอง exactly-once
reconnect/รีสตาร์ตยังรีเซ็ต track history จึงต้องตรวจเหตุการณ์บริเวณรอยต่อ
การเปลี่ยน ID หรือกรอบรวมสองเก๊ะยังทำให้นับผิดได้ ไม่มีการแยกกรอบรวมแบบเดาสองชิ้น
cooldown รวมอาจทำให้เก๊ะที่ผ่านใกล้กันพลาด ต้องประเมินค่าจากเหตุการณ์จริง

## API

- GET /health: alive กับ ready (alive ไม่เท่ากับกล้องทำงาน)
- GET /api/status และ /api/rack-counter/status: metadata ล่าสุด
- WS /ws/rack-counter: ส่ง JSON {"token":"..."} เป็นข้อความแรกหากเปิด token
- GET /api/live/stream และ /api/rack-counter/stream: MJPEG
- GET /api/live/frame: JPEG ล่าสุด
- GET /api/v1/cameras/final-pond-cam-01/frame: JPEG preview ช่อง 11 (503 ระหว่างรอสตรีมหรือไม่ได้ตั้งค่า)
- POST /api/recordings/start: {"duration_minutes":15,"name":"morning_shift_01"}
- POST /api/recordings/stop
- GET /api/recordings: ล่าสุดไม่เกิน 500 คลิป
- DELETE /api/recordings/{clip_id}: เปลี่ยนสถานะ archived ไม่ลบ bytes

HTTP ที่ป้องกันใช้ Authorization: Bearer <token> ไม่ใส่ token ใน URL
บริการ bind 127.0.0.1 เท่านั้น อย่าเปิด RTSP หรือ API ตรงสู่อินเทอร์เน็ต
ก่อนใช้ LAN จริงต้องมี authentication/TLS/reverse proxy และการจัดการสิทธิ์โดยฝ่าย IT

## การบันทึก

ไฟล์อยู่ `rack_ai/data/recordings/raw/` พร้อม JSON และ recordings.sqlite3
ใช้ OpenCV mp4v ที่ 10 FPS เป็น fallback รุ่นแรก ไม่ใช่ stream-copy และมีการบีบอัดซ้ำ
ใช้ได้ครั้งละหนึ่งคลิป แต่เก็บหลายคลิปต่อเนื่องกันได้
duration_minutes คือ **นาที**; 10=600 วินาที, 15=900 วินาที
ถ้าต้นทางต่ำกว่า 10 FPS อาจซ้ำภาพเพื่อคงเวลา; duplicate_frames ระบุไว้ใน metadata
หยุดและระบุ failed เมื่อภาพเก่า กล้อง reconnect/เปลี่ยนขนาด พื้นที่ต่ำ หรือ encoder ตามเวลาไม่ทัน
OpenCV ไม่รับรองแจ้ง write failure ทุกชนิด ต้องตรวจไฟล์หลังบันทึกและใช้ stream-copy ในเฟสถัดไป
ค่า rack_events/average_confidence เป็น null โดยเจตนา ยังไม่ได้เชื่อมเวลาระหว่างสองสตรีม
ห้ามใช้คลิป annotated หรือ screenshot ที่มีกรอบเป็นวัตถุดิบฝึก

## ทดสอบ

```powershell
python -m pip install -r rack_ai/requirements-dev.txt
python -m unittest rack_ai.test_pipeline rack_ai.test_recording -v
node --check rack_ai/frontend/monitor.js
Invoke-RestMethod http://127.0.0.1:8011/health
```

ทดสอบจำลองครอบคลุม latest-only/copy isolation, นับครั้งเดียว/ไม่นับย้อนขึ้น,
reconnect, auth, WebSocket สอง client, เขียนอ่านคลิปสั้น, metadata, stop, archive และ path traversal
การทดสอบคลิปสั้นไม่ทดแทน soak test 10/15 นาทีหรือการทดสอบ RTSP หลุดจริง
ทดสอบโมเดลเดิมกับคลิปจริงได้ JPEG และ metadata บน CPU; ยังไม่มีตัวเลข counting accuracy ที่ยืนยัน

ผลตรวจวันที่ 11 กันยายน 2026: ผ่าน 9 tests, Camera09 สด 960x1080 ประมาณ 24.8 FPS,
AI บน CPU ประมาณ 4.3–4.9 FPS ในช่วงตรวจสั้น บันทึกภาพดิบจริง 6 วินาทีได้ 60 เฟรมที่ 10 FPS,
เปิดอ่าน MP4 สำเร็จ ไม่มีภาพซ้ำที่ recorder รายงาน และ AI ยังทำงานหลังบันทึก
ตัวเลขนี้ไม่ใช่ผลรับรองโหลดต่อเนื่องหรือความแม่นยำ

## ไฟล์ที่เพิ่ม

- config.py / .env.example: ค่าที่ปรับได้และตัวอย่างไม่มีรหัสผ่าน
- camera.py: RTSPReader, FrameBuffer, FramePacket
- detector.py / counter.py / service.py: โมเดล, track/count และ worker
- app.py / run.py / start_camera09.ps1: API และจุดเริ่มบริการ
- frontend/index.html / frontend/monitor.js: หน้า monitor แบบ local ใช้ WebSocket
- recording.py: recorder และ ClipStore ขั้นต้น
- test_pipeline.py / test_recording.py: regression tests
- requirements.txt / requirements-dev.txt: dependencies

ก่อนย้าย PCC: เปิดหน้าใหม่นับเทียบคนกลางวัน/กลางคืนและช่วงเก๊ะติดกัน,
บันทึก 10/15 นาที ตรวจความยาวและภาพดิบ, ทดสอบหลุดต่อใหม่ และผู้ชมหลายคน
จากนั้นค่อยย้าย PCC จาก polling ไป WebSocket โดยเก็บบริการเดิมสำหรับย้อนกลับ

## ตรวจรับความแม่นยำหนึ่งกะ

เมื่อกะสิ้นสุด ให้ส่งออกยอด AI จาก SQLite Event Journal โดยตรง คำสั่งนี้อ่านอย่างเดียวและไม่เขียนทับไฟล์ที่มีอยู่:

```powershell
python -m rack_ai.tools.export_shift_ai_counts `
  --database rack_ai/data/recordings/runtime/lab.sqlite3 `
  --date 2026-09-23 --shift day --model models/best_v3.pt `
  --camera-id camera-09 --output output/rack-review-2026-09-23-day.csv
```

ระบบจะสร้าง CSV และไฟล์ `.provenance.json` คู่กัน ยอด AI ถูกกรอกให้อัตโนมัติ ส่วน `human_count` ให้ผู้ตรวจกรอกตามการนับจริง และ `camera_coverage_confirmed` ให้กรอก `yes` เฉพาะชั่วโมงที่ตรวจแล้วว่าภาพกล้องครบและใช้งานได้ หากกล้องหลุดหรือยังไม่ตรวจให้เว้นว่างหรือกรอก `no` เวลา ISO ต้องมี `+07:00` และทุกช่วงต้องต่อกันครบกะ หากส่งออกก่อนกะจบ ไฟล์จะถูกระบุเป็น Draft และไม่ผ่านการตรวจหลักฐาน

สร้างรายงานตรวจรับ JSON และ HTML จาก CSV ที่ตรวจเสร็จ โดยแนบไฟล์หลักฐานจาก Event Journal:

```powershell
python -m rack_ai.tools.validate_shift_count `
  --input output/rack-review-2026-09-23-day.csv `
  --provenance output/rack-review-2026-09-23-day.provenance.json `
  --date 2026-09-23 --shift day `
  --model models/best_v3.pt --camera-id camera-09 `
  --reviewer "ชื่อผู้ตรวจนับ" `
  --html output/rack-validation-2026-09-23-day.html `
  --json output/rack-validation-2026-09-23-day.json
```

เครื่องมือจะตรวจยอด AI และช่วงเวลาว่ายังตรงกับไฟล์ส่งออก ตรวจว่ากะสิ้นสุดแล้ว บันทึกชื่อและ SHA-256 ของไฟล์โมเดล ตรวจช่วงเวลาขาด/ซ้อน จำนวนตัวอย่างขั้นต่ำ ภาพกล้องที่ผู้ตรวจยืนยัน Total Error, WAPE และ False Positive ในชั่วโมงที่คนยืนยันว่านับได้ศูนย์ หากชื่อไฟล์ที่โมเดลใช้ใน Container เป็น `rack-production.pt` แต่ไฟล์ต้นฉบับชื่ออื่น ให้เพิ่ม `--recorded-model-name rack-production.pt` ตอนส่งออก Event Journal

บริการนับเก๊ะรุ่นใหม่บันทึก SHA-256 ของไฟล์โมเดลที่โหลดไว้ในทุกเหตุการณ์นับ และเครื่องมือส่งออกตรวจว่าตรงกับไฟล์ `.pt` ที่ใช้ทำรายงาน หาก Hash ไม่ตรงจะไม่ส่งออก; หากเหตุการณ์ใดในกะเป็นข้อมูลรุ่นเก่าที่ไม่มี Hash จะระบุ `model_identity_verified: false` และรายงานตรวจรับ **ไม่ผ่าน** จนกว่าจะมีหลักฐานรุ่นโมเดลที่ตรวจสอบได้ครบ การแก้โค้ดนี้มีผลกับเหตุการณ์ที่เกิดหลังรีสตาร์ตบริการเท่านั้น ไม่เติม Hash ย้อนหลังให้ข้อมูลเก่า และไม่ควรรีสตาร์ตระหว่างกะโดยไม่วางแผน หากต้องทดลองคลิปบางช่วงให้เพิ่ม `--allow-partial` แต่ผลดังกล่าวไม่ถือเป็นการตรวจรับหนึ่งกะเต็ม

ค่าเริ่มต้น Total Error ≤2%, WAPE ≤5%, ผิดพลาดไม่เกิน 2 เก๊ะต่อช่วง และยอดคนขั้นต่ำ 50 เก๊ะ เป็นเกณฑ์ทดลองทางวิศวกรรม ต้องให้ QC และ Production อนุมัติหรือกำหนดค่าใหม่ก่อนนำไปตัดสิน Production

## Backup และ Restore Runtime

สำรอง SQLite ขณะบริการทำงานพร้อม Metadata, Manifest และ SHA-256 โดยไม่รวมวิดีโอ/ภาพเป็นค่าเริ่มต้น:

```powershell
python -m rack_ai.tools.backup_runtime create --source rack_ai/data --output backups/rack_ai --keep 14
python -m rack_ai.tools.backup_runtime verify backups/rack_ai/runtime-backup-YYYYMMDD-HHMMSSZ.zip
python -m rack_ai.tools.backup_runtime restore backups/rack_ai/runtime-backup-YYYYMMDD-HHMMSSZ.zip --target backups/restore-drill-YYYYMMDD
```

Restore รับเฉพาะโฟลเดอร์ใหม่หรือว่างและจะตรวจฐานข้อมูลซ้ำหลังแตกไฟล์ จึงไม่เขียนทับ Runtime สดโดยตรง ใช้ `--include-media` เฉพาะเมื่อพื้นที่เพียงพอและต้องการเก็บคลิป/ภาพด้วย รายละเอียด Production และ Cron อยู่ใน `docs/operations/production-docker-runbook.md`

## อ้างอิงแนวทาง

- https://github.com/salvirezwan/Traffic-Video-Analytics-Project — การแยก capture/inference/API และ metadata
- https://github.com/SpectraCoreX/SpectraX — การแยกบริการและเหตุการณ์ CCTV
- https://docs.ultralytics.com/modes/predict/ — ตัวเลือก inference/precision

ใช้เป็นแนวทาง ไม่คัดลอกโค้ดทั้งระบบ ชื่อ repository อื่นในคำขอต้องยืนยัน URL ก่อนอ้างว่าใช้ตรงโครงการ
