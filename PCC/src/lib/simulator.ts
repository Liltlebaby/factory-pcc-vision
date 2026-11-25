import { POND_PH_SPEC, POND_SPEC, TEMP_SPEC, WEIGHT_SPEC } from "./config";

/**
 * ตัวจำลองสัญญาณจากหน้างานสำหรับ Prototype
 * ในระบบจริงส่วนนี้จะถูกแทนด้วย Gateway ของตาชั่ง และตัวดึงข้อมูลจาก Recorder เดิม
 */

export type Scenario =
  | "NORMAL"
  | "WEIGHT_HIGH"
  | "WEIGHT_LOW_DRIFT"
  | "TEMP_DEVIATION"
  | "TEMP_SWING"
  | "POND_HIGH"
  | "SENSOR_ERROR"
  | "CORRELATION";

export const SCENARIOS: { id: Scenario; label: string; hint: string }[] = [
  { id: "NORMAL", label: "เดินปกติ", hint: "ทุกค่าอยู่ในเกณฑ์" },
  {
    id: "WEIGHT_HIGH",
    label: "น้ำหนักสูงเกิน",
    hint: "ไล่ขึ้นจนหลุด USL 18.00 kg → แจ้งหอโรยยาง SLA 5 นาที",
  },
  {
    id: "WEIGHT_LOW_DRIFT",
    label: "น้ำหนักดริฟท์ลง",
    hint: "ลดต่อเนื่องทีละก้อน → Drift Warning ก่อนหลุด LSL",
  },
  {
    id: "TEMP_DEVIATION",
    label: "อุณหภูมิเพี้ยน",
    hint: "Burner เบี่ยงจากค่าจริงเกิน ±2°C → แจ้งช่าง Burner SLA 15 นาที",
  },
  {
    id: "TEMP_SWING",
    label: "อุณหภูมิแกว่ง",
    hint: "ค่าปัจจุบันยังไม่เกิน ±2°C แต่ Recorder แกว่งเกิน 2°C ใน 15 นาที",
  },
  {
    id: "POND_HIGH",
    label: "บ่อสุดท้ายร้อน",
    hint: "อุณหภูมิค่อย ๆ สูงเกิน 35°C → แจ้งฝ่ายผลิตและ QC",
  },
  {
    id: "SENSOR_ERROR",
    label: "ตาชั่งเสีย",
    hint: "ค่าผิดธรรมชาติ → แจ้งช่างซ่อมบำรุง ไม่นับเป็นของเสีย",
  },
  {
    id: "CORRELATION",
    label: "น้ำหนักตก + อุณหภูมิแกว่ง",
    hint: "เกิดพร้อมกัน → ระบบเสนอให้ตรวจ Burner ก่อนปรับปริมาณโรย",
  },
];

function noise(amplitude: number) {
  return (Math.random() * 2 - 1) * amplitude;
}

export function nextWeight(
  scenario: Scenario,
  ticksInScenario: number,
  previous: number,
): number {
  const { target, usl, lsl } = WEIGHT_SPEC;

  switch (scenario) {
    case "WEIGHT_HIGH": {
      const ramp = Math.min(ticksInScenario * 0.16, 1.2);
      return round2(target + ramp + noise(0.05));
    }
    case "WEIGHT_LOW_DRIFT":
    case "CORRELATION": {
      const base = previous > 0 ? previous : target;
      const stepped = base - 0.11 - Math.random() * 0.02;
      return round2(Math.max(stepped, lsl - 0.7));
    }
    case "SENSOR_ERROR": {
      if (ticksInScenario % 3 === 1) return 0;
      if (ticksInScenario % 3 === 2) return round2(112.4 + noise(2));
      return round2(target + noise(0.1));
    }
    default: {
      const pulled = target + noise(0.18);
      return round2(Math.min(Math.max(pulled, lsl + 0.02), usl - 0.02));
    }
  }
}

export function nextTemp(
  scenario: Scenario,
  ticksInScenario: number,
): { actual: number; burner: number; recorder: number } {
  const actual = round1(TEMP_SPEC.target + noise(0.2));

  switch (scenario) {
    case "TEMP_DEVIATION": {
      const drift = Math.min(1.2 + ticksInScenario * 0.25, 2.9);
      return {
        actual,
        burner: round1(actual + drift + noise(0.15)),
        recorder: round1(actual + noise(0.4)),
      };
    }
    case "TEMP_SWING":
    case "CORRELATION": {
      // แกว่งกว้างแต่แต่ละจุดยังไม่เกิน ±2°C — จับได้จาก Swing เท่านั้น
      const swing = 1.35 * Math.sin(ticksInScenario * 0.35);
      return {
        actual,
        burner: round1(actual + swing * 0.7 + noise(0.2)),
        recorder: round1(actual + swing + noise(0.15)),
      };
    }
    default:
      return {
        actual,
        burner: round1(actual + noise(0.45)),
        recorder: round1(actual + noise(0.35)),
      };
  }
}

export function nextPondTemp(
  scenario: Scenario,
  ticksInScenario: number,
): number {
  if (scenario === "POND_HIGH") {
    const ramp = Math.min(ticksInScenario * 0.18, 4.2);
    return round1(32.2 + ramp + noise(0.12));
  }
  return round1(POND_SPEC.max - 3 + noise(0.45));
}

/** Prototype reading only; replace with a calibrated water pH probe feed. */
export function nextPondPh(tick: number): number {
  return round2(
    (POND_PH_SPEC.min + POND_PH_SPEC.max) / 2 +
      0.24 * Math.sin(tick * 0.11) +
      noise(0.025),
  );
}

function round1(v: number) {
  return Math.round(v * 10) / 10;
}

function round2(v: number) {
  return Math.round(v * 100) / 100;
}
