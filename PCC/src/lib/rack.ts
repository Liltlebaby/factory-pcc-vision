/**
 * ตัวเชื่อมไปยัง Rack Monitor (rack_ai) ที่รันอยู่คนละ process
 *
 * ทำไมต้องผ่าน route handler ของ Next แทนที่จะให้เบราว์เซอร์ยิงไป 8011 ตรง ๆ
 * ---------------------------------------------------------------------------
 * 1. CORS — rack_ai อนุญาตเฉพาะ origin ที่ตั้งไว้ใน PCC_ORIGINS ซึ่งตอนนี้มี
 *    8011 กับ localhost:3001 เท่านั้น ไม่มี localhost:3000 ที่ Next ใช้เป็น
 *    ค่าเริ่มต้น ถ้ายิงตรงจากเบราว์เซอร์จะโดนบล็อก
 * 2. โทเคน — ถ้าวันหนึ่งตั้ง RACK_API_TOKEN ขึ้นมา โทเคนจะอยู่ฝั่งเซิร์ฟเวอร์
 *    ไม่หลุดไปอยู่ใน JavaScript ที่เบราว์เซอร์โหลดได้
 * 3. เบราว์เซอร์คุยกับ origin เดียว ทำให้ย้ายเครื่องหรือเปลี่ยนพอร์ตภายหลัง
 *    แก้ที่ตัวแปรสภาพแวดล้อมจุดเดียว
 */

/** ที่อยู่ของ service — แก้ได้ที่ .env.local ถ้าย้ายเครื่องหรือเปลี่ยนพอร์ต */
export const RACK_API = process.env.RACK_API_URL ?? "http://127.0.0.1:8011";

/** ว่างไว้ได้ rack_ai ไม่บังคับโทเคนเมื่อ RACK_API_TOKEN ไม่ได้ตั้ง */
const TOKEN = process.env.RACK_API_TOKEN ?? "";

export function rackHeaders(): HeadersInit {
  return TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {};
}

export type RackEvent = {
  rackNumber: number;
  trackId: number;
  timestamp: number;
  confidence: number;
};

export type RackTrack = {
  track_id: number;
  confidence: number;
  bbox: [number, number, number, number];
  counted: boolean;
};

/** รูปร่างของ /api/status ตามที่ rack_ai/service.py snapshot() คืนมา */
export type RackStatus = {
  running: boolean;
  error: string | null;
  count: number;
  rack_count: number;
  frame_id: number;
  timestamp?: string;
  tracks: RackTrack[];
  active_tracks: number;
  total_detections: number;
  inference_fps: number;
  lastEvent: RackEvent | null;
  width?: number;
  height?: number;
  model?: string;
  device?: string;
  uptime: number;
  result_age_seconds: number | null;
  fps: { camera: number; inference: number };
  camera: { connected: boolean; stale: boolean; fps: number };
  recording?: { active: boolean };
  /** ไม่ใช่ null เมื่อเขียนยอดสะสมลงไฟล์ไม่สำเร็จ — ยอดจะหายเมื่อรีสตาร์ท */
  counter_storage_error?: string | null;
};

/** สถานะที่ใช้ตัดสินใจว่าจะแสดงผลแบบไหน */
export type RackHealth = "live" | "stale" | "offline";

export type RackAIDataStatus = "live" | "pilot" | "offline" | "not_installed";

export type RackAITaskStatus = {
  task_id: string;
  name: string;
  task_type: string;
  station_id: string;
  lifecycle: "active" | "planned" | "disabled";
  output_metrics: string[];
  runtime_status: "running" | "pilot" | "waiting" | "unavailable" | "not_installed";
  model_version: string | null;
  inference_fps: number;
  latest: {
    rack_count?: number;
    /** ชื่อเดิมก่อนแยกงานนับเก๊ะออกจากงานนับก้อนยาง — อ่านไว้เผื่อ rack_ai ยังไม่อัปเดต */
    rubber_count?: number;
    active_tracks?: number;
    last_event?: RackEvent | null;
    assessment_status?: string;
    event_count?: number;
    people_count?: number;
    helmet_pass?: number;
    no_helmet?: number;
    undecided?: number;
    filtered_out?: number;
    workers_in_pond?: number;
    workers_in_zone?: number;
    presence_status?: string;
    seconds_since_person?: number | null;
    unattended_alerts?: number;
    camera_online?: boolean;
    inference_fps?: number;
    inference_ms?: number;
  } | null;
};

/**
 * ผลที่ rack_ai ถาม DVR ว่าช่องกล้องนี้ยังมีสัญญาณเข้าอยู่ไหม
 *
 * ต้องอ่านแยกจาก camera_status เสมอ เพราะสองค่านี้ขัดกันได้:
 * เมื่อสายกล้องอนาล็อกหลุด DVR ไม่ได้หยุดส่งสตรีม แต่ส่งภาพดำที่เขียนว่า NO VIDEO
 * ออกมาแทน camera_status จึงยังเป็น online และเฟรมยังไหลเข้ามาปกติ
 * ทั้งที่ระบบมองไม่เห็นอะไรเลย
 */
export type CameraSourceSignal = {
  checked_at: string | null;
  reachable: boolean;
  channel: number | null;
  signal: "ok" | "no_video" | "unknown";
  resolution: string | null;
  error: string | null;
};

/** ok = เห็นภาพจริง · blind = กล้องตาบอด · unknown = ถาม DVR ไม่ได้ หรือ rack_ai ยังไม่อัปเดต */
export type SignalVerdict = "ok" | "blind" | "unknown";

/** แยกให้ชัดว่า "ไม่มีเก๊ะผ่าน" กับ "กล้องตาบอด" ไม่ใช่เรื่องเดียวกัน */
export function signalVerdict(signal?: CameraSourceSignal | null): SignalVerdict {
  if (!signal || !signal.reachable) return "unknown";
  if (signal.signal === "no_video") return "blind";
  if (signal.signal === "ok") return "ok";
  return "unknown";
}

export type RackAICameraStatus = {
  camera_id: string;
  name: string;
  station_id: string;
  location: string;
  lifecycle: "active" | "planned" | "disabled";
  camera_status: "online" | "offline" | "not_installed";
  /** ไม่มีค่าเมื่อ rack_ai ยังเป็นเวอร์ชันก่อนเพิ่มการถาม DVR */
  source_signal?: CameraSourceSignal | null;
  data_status: RackAIDataStatus;
  updated_at: string | null;
  camera_fps: number;
  tasks: RackAITaskStatus[];
};

/** หนึ่งชั่วโมงในวันรายงาน — ดูรายละเอียดนิยามได้ที่ rack_ai/shifts.py */
export type RackHourBucket = {
  hour: number;
  label: string;
  start: number;
  end: number;
  count: number;
  /** ชั่วโมงที่ล้นไปวันถัดไป (หลังเที่ยงคืนของกะดึก) */
  next_day: boolean;
  /** ยังมาไม่ถึง — ต่างจากชั่วโมงที่ผ่านไปแล้วและนับได้ศูนย์ */
  pending: boolean;
};

export type RackShiftBucketReport = {
  key: "day" | "outside" | "night";
  name: string;
  label: string;
  count: number;
  hours: number;
  start: number | null;
  end: number | null;
  current: boolean;
};

/**
 * ยอดนับเก๊ะของวันรายงานหนึ่งวัน สรุปฝั่ง Vision Monitor จากเหตุการณ์ที่บันทึกไว้จริง
 *
 * ต่างจากการสะสมยอดในเบราว์เซอร์ตรงที่ตัวเลขไม่ขึ้นกับว่ามีใครเปิดหน้าจอค้างไว้ไหม
 * และทุกเครื่องที่เปิดดูจะเห็นตัวเลขชุดเดียวกัน
 */
export type RackDailyReport = {
  date: string;
  start: number;
  end: number;
  total: number;
  hours: RackHourBucket[];
  shifts: RackShiftBucketReport[];
  storage?: "ok" | "unavailable";
};

export type StationAIStatus = {
  station_id: string;
  data_status: RackAIDataStatus;
  cameras: RackAICameraStatus[];
};

export type RackAIPersistentEvent = {
  cursor: number;
  event_id: string;
  camera_id: string;
  task_id: string;
  station_id: string;
  type: string;
  occurred_at: string;
  model_version: string | null;
  rule_version: string;
  payload: {
    rack_count?: number;
    /** เหตุการณ์ที่บันทึกไว้ก่อนเปลี่ยนชื่อยังใช้คีย์นี้ */
    rubber_count?: number;
    track_id?: number;
    confidence?: number;
    [key: string]: unknown;
  };
};

export type RackAIEventPage = {
  items: RackAIPersistentEvent[];
  next_cursor: number;
  has_more: boolean;
};

export function healthOf(status: RackStatus | null): RackHealth {
  if (!status) return "offline";
  if (!status.running || status.error) return "offline";
  // ภาพค้างเกินสองวินาทีถือว่าไม่สด แม้ service จะยังตอบอยู่
  if ((status.result_age_seconds ?? 0) > 2) return "stale";
  return "live";
}
