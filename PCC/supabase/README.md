# Supabase setup for PCC

PCC ใช้ Supabase PostgreSQL เป็นพื้นที่เก็บข้อมูลฝั่ง Server สำหรับ Telemetry,
Rack Event, Rule Engine, Incident Workflow และ Audit Log ส่วน Supabase Auth ใช้
ยืนยันตัวตนและส่ง Role ผ่าน `app_metadata.pcc_role`

> ห้ามนำ Secret/Service Role Key ไปใส่ใน Client Component หรือ Environment
> ที่ขึ้นต้นด้วย `NEXT_PUBLIC_`

## Migration ที่ต้องมี

Migration ต้องถูก Apply ตามลำดับชื่อไฟล์ทั้งหมดใน `supabase/migrations/`

1. `202609160001_initial_schema.sql`
2. `20260919092314_rack_ai_event_sync.sql`
3. `20260919093110_station_telemetry.sql`
4. `20260919171034_server_telemetry_rules.sql`
5. `20260922014313_pcc_auth_rbac_audit.sql`

ไฟล์สุดท้ายเพิ่ม Login/RBAC catalogue, Incident Workflow, Atomic Incident
Action และ Immutable Audit Event โดย Function สำคัญเป็น `SECURITY INVOKER` และ
อนุญาต Execute เฉพาะ `service_role`

## ขั้นตอนสำหรับ Staging

1. สร้าง Supabase Project สำหรับ Staging ใน Region ที่ใกล้โรงงาน
2. ติดตั้ง Supabase CLI รุ่นที่ทีมอนุมัติและ Pin Version ให้แน่นอน
3. ตรวจคำสั่งปัจจุบันด้วย `supabase --help` และ `supabase db --help`
4. Link โฟลเดอร์นี้กับ Staging Project ตามคู่มือ CLI รุ่นที่ใช้งาน
5. Apply Migration ทั้งชุดผ่าน Migration Workflow ของ Supabase CLI
6. ตรวจ Security/Performance Advisor และแก้รายการระดับ Error ก่อนทดสอบ
7. สร้างผู้ใช้ทดสอบ Admin, Operator และ Viewer ผ่าน Admin-controlled flow
8. กำหนด Role ให้ตรงกันทั้งสองตำแหน่ง:
   - `auth.users.raw_app_meta_data.pcc_role`
   - `public.pcc_user_profiles.role` พร้อม `active = true`
9. ตั้งค่า `.env.local` จาก `env.example` แล้ว Restart PCC
10. เปิด `PCC_AUTH_REQUIRED=true` เฉพาะหลังจากทดสอบบัญชี Admin แล้ว

## Environment ที่ต้องตั้ง

- `NEXT_PUBLIC_SUPABASE_URL` — Project URL สำหรับ Auth Client
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` — Publishable Key สำหรับ Browser/SSR Auth
- `SUPABASE_URL` — Project URL ฝั่ง Server
- `SUPABASE_SECRET_KEY` — Secret Key ฝั่ง Server เท่านั้น
- `SUPABASE_SERVICE_ROLE_KEY` — รองรับ Legacy Project เท่านั้น
- `PCC_AUTH_REQUIRED=true` — บังคับ Login ใน Production

ควรใช้ Secret รูปแบบ `sb_secret_...` เมื่อ Project รองรับ และไม่ควรตั้ง
`SUPABASE_SECRET_KEY` หรือ `SUPABASE_SERVICE_ROLE_KEY` เป็น `NEXT_PUBLIC_*`

## Test Matrix ก่อนขึ้น Production

- Viewer เปิด Dashboard/Report/Incident ได้ แต่ปุ่มดำเนินการถูกปิด
- Operator รับทราบ Incident และบันทึกสิ่งที่แก้ไขได้
- Admin ทำทุก Action ของ Operator และเข้าถึงงานจัดการระบบได้
- Role ใน JWT ไม่ตรงกับ Active Profile ต้องถูกปฏิเสธ
- ผู้ใช้ที่ `active = false` ต้องดำเนินการ Incident ไม่ได้
- การกดซ้ำด้วย Idempotency Key เดิมต้องไม่สร้าง Action/Audit ซ้ำ
- `ACKNOWLEDGE` ใช้ได้เฉพาะ Workflow `OPEN`
- `RESOLVE` ใช้ได้เฉพาะ Workflow `ACKNOWLEDGED` และต้องมี Note
- Rule กลับเข้าเกณฑ์ต้องเปลี่ยน Workflow เป็น `CLOSED`
- Rule เปิดซ้ำต้องเริ่ม Workflow ใหม่และล้างข้อมูลผู้ดำเนินการรอบก่อน
- `anon` และ `authenticated` ต้องเข้าถึงตารางภายใน/Audit โดยตรงไม่ได้
- API ที่ไม่มี Session ต้องตอบ `401`; Viewer ต้องตอบ `403`
- ตรวจว่า Audit Event ระบุ Actor, Role, Before/After State และ Request ID ครบ

## Production gate

ก่อน Apply Migration ไป Production ต้อง:

1. สำรองฐานข้อมูลและยืนยันขั้นตอน Restore
2. ทดสอบ Migration ชุดเดียวกันบน Staging สำเร็จ
3. ผ่าน Test Matrix ด้านบนครบ
4. ได้รับอนุมัติจากผู้ดูแลระบบ/IT
5. มี Rollback หรือ Recovery Plan หาก Migration หยุดกลางทาง

สถานะปัจจุบัน: Migration ถูกสร้างใน Workspace แล้ว แต่ **ยังไม่ได้ Apply ไปยัง
Staging หรือ Production** เพราะยังไม่มี Project Credential และเครื่องพัฒนาไม่มี
Docker/Supabase Local Stack
