import type { Status } from "./types";

// เกณฑ์ H2S ของจุดตรวจกลิ่นยาง (SN-3002-H2S, ช่วงวัด 0–100 ppm, ละเอียด 0.1 ppm)
export type H2sLevelKey = "NORMAL" | "ODOR" | "HIGH" | "ABNORMAL" | "DANGER" | "IDLH";

export interface H2sLevel {
  key: H2sLevelKey;
  range: string;
  label: string;
  meaning: string;
  // สิ่งที่หน้างานต้องทำเมื่อถึงระดับนี้ (ตามที่โรงงานกำหนด)
  action?: string;
  status: Status;
  classes: string;
  dot: string;
}

const STOP_PRODUCTION = "หยุดการผลิตทุกประเภท หาสาเหตุและการแก้ไขกลิ่นภายใน 15 นาที";

// minPpm เรียงจากมากไปน้อย; ค่าแรกที่ ppm >= minPpm คือระดับนั้น
// ≥10 ppm สูงกว่าระดับแดง จึงใช้มาตรการเดียวกับ "สูงผิดปกติ" และเป็น Safety Alarm เพิ่ม
export const H2S_LEVELS: Array<H2sLevel & { minPpm: number }> = [
  { minPpm: 100, key: "IDLH", range: "≥ 100", label: "IDLH", meaning: "ระดับอันตรายต่อชีวิต/สุขภาพทันทีตาม NIOSH (ถึงเพดานช่วงวัดแล้ว ค่าจริงอาจสูงกว่า)", action: `${STOP_PRODUCTION} · Safety Alarm ระดับอันตรายต่อชีวิต`, status: "RED", classes: "bg-red-700 text-white ring-red-800", dot: "bg-white" },
  { minPpm: 10, key: "DANGER", range: "≥ 10", label: "อันตราย", meaning: "ใช้เป็น Safety Alarm ไม่ใช่แค่เรื่องกลิ่น", action: `${STOP_PRODUCTION} · Safety Alarm`, status: "RED", classes: "bg-red-600 text-white ring-red-700", dot: "bg-white" },
  { minPpm: 5, key: "ABNORMAL", range: "5.0 – 9.9", label: "สูงผิดปกติ", meaning: "ให้ PCC แจ้งเตือนและตรวจหน้างาน", action: STOP_PRODUCTION, status: "RED", classes: "bg-red-50 text-red-700 ring-red-200", dot: "bg-red-500" },
  { minPpm: 1, key: "HIGH", range: "1.0 – 4.9", label: "กลิ่นสูง", meaning: "ควรตรวจพื้นที่/แหล่งกำเนิด", action: "ลงโทษผู้รับผิดชอบและแก้ไขทันที ภายใน 15 นาที", status: "YELLOW", classes: "bg-orange-50 text-orange-700 ring-orange-200", dot: "bg-orange-500" },
  { minPpm: 0.5, key: "ODOR", range: "0.5 – 0.9", label: "เริ่มมีกลิ่น", meaning: "เริ่มถือว่ามีกลิ่น H₂S ชัดสำหรับระบบ", action: "หาสาเหตุ กำจัดกลิ่นภายใน 15 นาที", status: "YELLOW", classes: "bg-amber-50 text-amber-700 ring-amber-200", dot: "bg-amber-500" },
  { minPpm: 0, key: "NORMAL", range: "0 – 0.4", label: "ปกติ", meaning: "H₂S ต่ำ", status: "GREEN", classes: "bg-emerald-50 text-emerald-700 ring-emerald-200", dot: "bg-emerald-500" },
];

export function getH2sLevel(ppm: number | undefined): H2sLevel | undefined {
  if (ppm === undefined || !Number.isFinite(ppm)) return undefined;
  // ปัดเป็น 0.1 ppm ตามความละเอียดเซ็นเซอร์ ให้ 0.45 ไม่ตกอยู่ระหว่างช่อง 0.4 กับ 0.5
  const rounded = Math.round(ppm * 10) / 10;
  return H2S_LEVELS.find((level) => rounded >= level.minPpm);
}
