/**
 * ฟอร์แมตวันเวลาแบบคำนวณเองที่ offset +07:00
 * ไม่ใช้ Intl/toLocaleString เพราะผลลัพธ์ของ locale th-TH ต่างกันระหว่าง Node กับเบราว์เซอร์
 * แล้วทำให้ React hydration ไม่ตรงกัน
 */

const TZ_OFFSET_MS = 7 * 60 * 60 * 1000;

const THAI_MONTHS = [
  "ม.ค.",
  "ก.พ.",
  "มี.ค.",
  "เม.ย.",
  "พ.ค.",
  "มิ.ย.",
  "ก.ค.",
  "ส.ค.",
  "ก.ย.",
  "ต.ค.",
  "พ.ย.",
  "ธ.ค.",
];

function pad(value: number) {
  return String(value).padStart(2, "0");
}

function shifted(at: number) {
  return new Date(at + TZ_OFFSET_MS);
}

export function fmtTime(at: number) {
  const d = shifted(at);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

export function fmtDateTime(at: number) {
  const d = shifted(at);
  return `${d.getUTCDate()} ${THAI_MONTHS[d.getUTCMonth()]} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

/** นับถอยหลัง SLA เป็นข้อความอ่านง่าย */
export function fmtCountdown(deadline: number, now: number) {
  const remaining = deadline - now;
  if (remaining < 0) {
    const over = Math.abs(remaining);
    return `เกินกำหนด ${Math.floor(over / 60_000)}:${pad(Math.floor((over % 60_000) / 1000))}`;
  }
  return `เหลือ ${Math.floor(remaining / 60_000)}:${pad(Math.floor((remaining % 60_000) / 1000))}`;
}
