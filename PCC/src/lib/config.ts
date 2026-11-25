import type { Status } from "./types";

/** ค่าคงที่ของ Prototype — ในระบบจริงค่าเหล่านี้มาจากตาราง config ต่อเตา/ต่อเกรด */

export const FURNACE = {
  id: "FUR-A",
  name: "เตา A",
  line: "LINE-1",
  grade: "AJ2",
  workOrderId: "WO-2026-0904-01",
};

export const WEIGHT_SPEC = {
  lsl: 17.0,
  usl: 18.0,
  target: 17.5,
  warningBand: 0.25,
  unit: "kg",
  /** ค่านอกช่วงนี้ถือว่าเซ็นเซอร์ผิดปกติ ไม่ใช่ของเสียจากกระบวนการ */
  sensorMin: 5,
  sensorMax: 30,
  /** เฉลี่ย 10 ก้อนห่าง Target เกินค่านี้ → Escalate */
  meanEscalate: 0.3,
};

export const TEMP_SPEC = {
  target: 180.5,
  greenLimit: 1,
  yellowLimit: 2,
  swingWindowMinutes: 15,
  swingLimit: 2,
  unit: "°C",
};

export const POND_SPEC = {
  name: "บ่อสุดท้าย",
  max: 35,
  warningMargin: 1,
  sensorMin: 0,
  sensorMax: 80,
  unit: "°C",
};

/** เกณฑ์ pH น้ำบ่อสุดท้ายตามข้อกำหนดหน้างาน (รวมค่าขอบ 10 และ 11) */
export const POND_PH_SPEC = {
  min: 10,
  max: 11,
};

/**
 * เวลาในเดโม: 1 รอบ = 5 วินาทีในเวลากระบวนการ เดินทุก 1.5 วินาทีจริง (เร็วกว่าจริง ~3.3 เท่า)
 * เลือกอัตรานี้เพื่อให้ SLA 5–15 นาทีนับถอยหลังทันให้คนกดปุ่มในเดโม
 */
/**
 * ข้อมูลจำลองของจุดที่ยังไม่มีเซ็นเซอร์จริง ปิดไว้ = หน้าจอแสดง "ยังไม่ติดตั้ง" แทนตัวเลขปลอม
 * ถ้ามี telemetry จริงส่งเข้ามา ค่าจริงจะแสดงเสมอไม่ว่าตั้งค่านี้อย่างไร
 */
export const DEMO_SENSORS = {
  weight: false,
  furnace: false,
} as const;

export const TICK_MS = 1500;
export const SECONDS_PER_TICK = 5;
/** ชั่งน้ำหนัก 1 ก้อนทุก 3 รอบ = ทุก 15 วินาทีในเวลากระบวนการ */
export const WEIGHT_TICKS_PER_SAMPLE = 3;
export const SERIES_LIMIT = 200;

/**
 * ลำดับความรุนแรงของกฎในแหล่งเดียวกัน
 * ใช้กันไม่ให้เหตุเดียวเปิด Incident ซ้อนหลายใบ — ใบที่รุนแรงกว่าจะรวบใบเดิมเข้ามา
 */
export const RULE_PRIORITY: Record<string, number> = {
  W_SENSOR: 40,
  W_RED3: 30,
  W_MEAN10: 20,
  W_HIGH: 10,
  W_LOW: 10,
  TEMP_R3X3: 30,
  TEMP_R3: 10,
  POND_SENSOR: 40,
  POND_HIGH: 20,
};

export const OWNERS = {
  spray: "หอโรยยาง",
  burner: "ช่าง Burner",
  sprayAndBurner: "หอโรยยาง + ช่าง Burner",
  maintenance: "ช่างซ่อมบำรุง",
  supervisor: "หัวหน้ากะ",
  pond: "ฝ่ายผลิต + QC",
};

export interface RulePlaybook {
  issue: string;
  owner: string;
  task: string;
  slaMinutes: number;
  severity: "WARNING" | "CRITICAL";
  requiresApproval: boolean;
  impactQuality: boolean;
  impactSmell: boolean;
  impactFail: boolean;
  aiSuggestion: string[];
}

/** playbook ต่อ rule — คนตัดสินใจ AI แค่เสนอทางเลือก */
export const PLAYBOOK: Record<string, RulePlaybook> = {
  W_HIGH: {
    issue: "น้ำหนัก Biscuit สูงเกิน USL",
    owner: OWNERS.spray,
    task: "ลดปริมาณโรย 1 ระดับ แล้วรอตรวจก้อนถัดไป",
    slaMinutes: 5,
    severity: "CRITICAL",
    requiresApproval: false,
    impactQuality: true,
    impactSmell: false,
    impactFail: true,
    aiSuggestion: [
      "ลดปริมาณโรยยาง 1 ระดับ (ทางเลือกที่ระบบเสนอเป็นอันดับแรก)",
      "ตรวจความสม่ำเสมอของการป้อนยางเข้าเครื่องโรย",
      "ตรวจสอบการสอบเทียบตาชั่งหน้าเตา หากค่าสูงต่อเนื่องทั้งกะ",
    ],
  },
  W_LOW: {
    issue: "น้ำหนัก Biscuit ต่ำกว่า LSL",
    owner: OWNERS.sprayAndBurner,
    task: "ประสานหอโรยยางเพิ่มปริมาณโรย และให้ช่าง Burner ตรวจอุณหภูมิเตา",
    slaMinutes: 5,
    severity: "CRITICAL",
    requiresApproval: false,
    impactQuality: true,
    impactSmell: true,
    impactFail: true,
    aiSuggestion: [
      "ตรวจอุณหภูมิ Burner ก่อนปรับปริมาณโรย เพราะน้ำหนักต่ำมักมาจากการอบเกิน",
      "เพิ่มปริมาณโรยยาง 1 ระดับ หากอุณหภูมิปกติ",
      "ตรวจความชื้นยางก้อนก่อนเข้าเตา",
    ],
  },
  W_SENSOR: {
    issue: "ตาชั่งหน้าเตาส่งค่าผิดธรรมชาติ",
    owner: OWNERS.maintenance,
    task: "ตรวจตาชั่ง / Load Cell / สาย Gateway",
    slaMinutes: 10,
    severity: "CRITICAL",
    requiresApproval: false,
    impactQuality: false,
    impactSmell: false,
    impactFail: false,
    aiSuggestion: [
      "ตรวจสาย Load Cell และการต่อ Gateway",
      "ระหว่างซ่อมให้ชั่งมือและบันทึกด้วยแบบฟอร์มสำรอง",
      "ห้ามใช้ค่านี้ตัดสินคุณภาพ Lot จนกว่าจะสอบเทียบเสร็จ",
    ],
  },
  W_DRIFT: {
    issue: "น้ำหนักเคลื่อนทิศทางเดียวกัน 5 ก้อนติด (Drift)",
    owner: OWNERS.spray,
    task: "เฝ้าระวังและเตรียมปรับปริมาณโรย",
    slaMinutes: 15,
    severity: "WARNING",
    requiresApproval: false,
    impactQuality: true,
    impactSmell: false,
    impactFail: false,
    aiSuggestion: [
      "ยังไม่หลุดเกณฑ์ แต่แนวโน้มชัด ควรปรับก่อนหลุด",
      "ตรวจว่าอุณหภูมิเตาเปลี่ยนไปพร้อมกันหรือไม่",
    ],
  },
  W_PROC: {
    issue: "2 ใน 3 ก้อนอยู่โซนเหลืองด้านเดียวกัน (Process Warning)",
    owner: OWNERS.spray,
    task: "ตรวจกระบวนการโรยยางและความสม่ำเสมอการป้อน",
    slaMinutes: 15,
    severity: "WARNING",
    requiresApproval: false,
    impactQuality: true,
    impactSmell: false,
    impactFail: false,
    aiSuggestion: [
      "กระบวนการเริ่มเบี่ยงไปด้านเดียว ควรปรับเล็กน้อยก่อนหลุดเกณฑ์",
    ],
  },
  W_MEAN10: {
    issue: "เฉลี่ย 10 ก้อนห่าง Target เกิน 0.30 kg",
    owner: OWNERS.supervisor,
    task: "ทบทวน Set Point การโรยยาง และอนุมัติการปรับ",
    slaMinutes: 20,
    severity: "CRITICAL",
    requiresApproval: true,
    impactQuality: true,
    impactSmell: false,
    impactFail: true,
    aiSuggestion: [
      "ค่าเฉลี่ยเบี่ยงทั้งช่วง ไม่ใช่ก้อนเดียว → ควรปรับ Set Point ไม่ใช่แก้เฉพาะจุด",
      "ต้องมีผู้อนุมัติก่อนเปลี่ยน Set Point (Set Point Authorization)",
    ],
  },
  W_RED3: {
    issue: "น้ำหนักหลุดเกณฑ์ (แดง) 3 ก้อนติด",
    owner: OWNERS.supervisor,
    task: "หยุดปล่อยของ ตรวจสอบสาเหตุ และกักของช่วงที่ผิด",
    slaMinutes: 10,
    severity: "CRITICAL",
    requiresApproval: true,
    impactQuality: true,
    impactSmell: true,
    impactFail: true,
    aiSuggestion: [
      "กักของช่วงที่ผิดเกณฑ์เพื่อรอตรวจ",
      "ตรวจทั้งการโรยยางและอุณหภูมิเตาพร้อมกัน",
      "ต้องมีผู้อนุมัติก่อนเดินต่อ",
    ],
  },
  TEMP_R3: {
    issue: "อุณหภูมิเทียบค่าจริงคลาดเคลื่อนเกิน ±2°C",
    owner: OWNERS.burner,
    task: "ตรวจ Burner / Sensor และแก้ไขให้กลับเข้าเกณฑ์",
    slaMinutes: 15,
    severity: "CRITICAL",
    requiresApproval: false,
    impactQuality: true,
    impactSmell: true,
    impactFail: false,
    aiSuggestion: [
      "ตรวจ Thermocouple ของ Burner ก่อน เพราะค่าเบี่ยงจาก Actual มากที่สุด",
      "เทียบกับ Recorder เพื่อแยกว่าเป็นปัญหาเซ็นเซอร์หรือกระบวนการ",
      "ถ้าทั้ง Burner และ Recorder เบี่ยงตรงกัน แปลว่าอุณหภูมิจริงเปลี่ยน ไม่ใช่เซ็นเซอร์",
    ],
  },
  TEMP_R3X3: {
    issue: "อุณหภูมิเกิน ±2°C ต่อเนื่อง 3 ครั้ง",
    owner: OWNERS.burner,
    task: "เข้าตรวจ Burner ทันที และบันทึกผลก่อน/หลังแก้",
    slaMinutes: 15,
    severity: "CRITICAL",
    requiresApproval: false,
    impactQuality: true,
    impactSmell: true,
    impactFail: true,
    aiSuggestion: [
      "ไม่ใช่ค่าแกว่งชั่วคราว ต้องเข้าตรวจหน้างาน",
      "ตรวจหัวเผาและแรงดันเชื้อเพลิงร่วมกับเซ็นเซอร์",
    ],
  },
  TEMP_SWING: {
    issue: "อุณหภูมิแกว่งเกิน 2°C ใน 15 นาที (Stability Warning)",
    owner: OWNERS.burner,
    task: "เฝ้าระวังการแกว่งของอุณหภูมิ และตรวจการควบคุมหัวเผา",
    slaMinutes: 30,
    severity: "WARNING",
    requiresApproval: false,
    impactQuality: true,
    impactSmell: false,
    impactFail: false,
    aiSuggestion: [
      "ค่าปัจจุบันยังไม่เกินเกณฑ์ แต่กระบวนการเริ่มไม่นิ่ง",
      "ตรวจการทำงานของวาล์วควบคุมและ PID ของ Burner",
    ],
  },
  POND_HIGH: {
    issue: "อุณหภูมิบ่อสุดท้ายสูงเกิน 35°C",
    owner: OWNERS.pond,
    task: "ตรวจระบบหมุนเวียนน้ำและลดอุณหภูมิให้ไม่เกิน 35°C",
    slaMinutes: 10,
    severity: "CRITICAL",
    requiresApproval: false,
    impactQuality: true,
    impactSmell: false,
    impactFail: true,
    aiSuggestion: [
      "ตรวจปั๊มและการไหลเวียนของน้ำในบ่อสุดท้าย",
      "ตรวจระบบระบายความร้อนและเติมน้ำตามมาตรฐานหน้างาน",
      "ยืนยันอุณหภูมิด้วยเครื่องวัดสำรองก่อนปล่อยกระบวนการต่อ",
    ],
  },
  POND_SENSOR: {
    issue: "เซ็นเซอร์อุณหภูมิบ่อสุดท้ายผิดปกติ",
    owner: OWNERS.maintenance,
    task: "ตรวจหัววัด สายสัญญาณ และ Gateway ของบ่อสุดท้าย",
    slaMinutes: 10,
    severity: "CRITICAL",
    requiresApproval: false,
    impactQuality: false,
    impactSmell: false,
    impactFail: false,
    aiSuggestion: [
      "ตรวจการเชื่อมต่อหัววัดและสายสัญญาณ",
      "ใช้เครื่องวัดอุณหภูมิสำรองระหว่างตรวจซ่อม",
      "ห้ามใช้ค่าที่ผิดธรรมชาติตัดสินสถานะกระบวนการ",
    ],
  },
};

export const STATUS_META: Record<
  Status,
  {
    label: string;
    dot: string;
    text: string;
    bg: string;
    border: string;
    /** สีสำหรับกราฟ/จุดชี้ตำแหน่ง ที่ต้องส่งเป็นค่าสีจริง ไม่ใช่คลาส */
    hex: string;
  }
> = {
  GREEN: {
    label: "NORMAL",
    dot: "bg-emerald-500",
    text: "text-emerald-600",
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    hex: "#059669",
  },
  YELLOW: {
    label: "WARNING",
    dot: "bg-amber-500",
    text: "text-amber-600",
    bg: "bg-amber-50",
    border: "border-amber-200",
    hex: "#d97706",
  },
  RED: {
    label: "CRITICAL",
    dot: "bg-red-500",
    text: "text-red-600",
    bg: "bg-red-50",
    border: "border-red-200",
    hex: "#dc2626",
  },
  SENSOR_ERROR: {
    label: "SENSOR ERROR",
    dot: "bg-sky-500",
    text: "text-sky-600",
    bg: "bg-sky-50",
    border: "border-sky-200",
    hex: "#0284c7",
  },
};
