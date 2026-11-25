import { POND_SPEC, TEMP_SPEC, WEIGHT_SPEC } from "./config";
import type {
  PondSample,
  Signal,
  Status,
  TempSample,
  WeightSample,
} from "./types";

/** ---------- Function 01: Weight ---------- */

export function classifyWeight(value: number): {
  status: Status;
  ruleCode: string;
} {
  const { lsl, usl, target, warningBand, sensorMin, sensorMax } = WEIGHT_SPEC;

  if (!Number.isFinite(value) || value < sensorMin || value > sensorMax) {
    return { status: "SENSOR_ERROR", ruleCode: "W_SENSOR" };
  }
  if (value > usl) return { status: "RED", ruleCode: "W_HIGH" };
  if (value < lsl) return { status: "RED", ruleCode: "W_LOW" };

  const deviation = value - target;
  if (Math.abs(deviation) > warningBand) {
    return { status: "YELLOW", ruleCode: deviation > 0 ? "W_HIGH" : "W_LOW" };
  }
  return { status: "GREEN", ruleCode: "W_OK" };
}

/**
 * กฎเชิงทำนายของน้ำหนัก ทำงานบน series ที่เรียงเก่า→ใหม่
 * คืนเฉพาะสัญญาณที่ "เพิ่งเกิด" จากก้อนล่าสุด เพื่อไม่ให้แจ้งซ้ำทุก tick
 */
export function weightSignals(series: WeightSample[]): Signal[] {
  const signals: Signal[] = [];
  if (series.length === 0) return signals;

  const last = series[series.length - 1];
  const statusOf = (s: WeightSample) => s.comparison.status;

  if (statusOf(last) === "SENSOR_ERROR") {
    return [
      {
        ruleCode: "W_SENSOR",
        severity: "CRITICAL",
        message: `ตาชั่งส่งค่า ${last.measurement.value.toFixed(2)} kg ซึ่งอยู่นอกช่วงที่เป็นไปได้`,
        opensIncident: true,
      },
    ];
  }

  // แดง 3 ก้อนติด → เปิด Incident
  const last3 = series.slice(-3);
  if (last3.length === 3 && last3.every((s) => statusOf(s) === "RED")) {
    signals.push({
      ruleCode: "W_RED3",
      severity: "CRITICAL",
      message: `หลุดเกณฑ์ 3 ก้อนติด (${last3
        .map((s) => s.measurement.value.toFixed(2))
        .join(" / ")} kg)`,
      opensIncident: true,
    });
  }

  // ก้อนล่าสุดหลุด LSL/USL
  if (statusOf(last) === "RED") {
    signals.push({
      ruleCode: last.deviation > 0 ? "W_HIGH" : "W_LOW",
      severity: "CRITICAL",
      message: `ก้อนที่ ${last.lotNo} ชั่งได้ ${last.measurement.value.toFixed(2)} kg (${
        last.deviation > 0 ? "สูงเกิน" : "ต่ำกว่า"
      }เกณฑ์ ${Math.abs(last.deviation).toFixed(2)} kg จาก Target)`,
      opensIncident: true,
    });
  }

  // เฉลี่ย 10 ก้อนห่าง Target > 0.30 kg → Escalate
  const last10 = series.slice(-10);
  if (last10.length === 10) {
    const mean =
      last10.reduce((sum, s) => sum + s.measurement.value, 0) / last10.length;
    const gap = mean - WEIGHT_SPEC.target;
    if (Math.abs(gap) > WEIGHT_SPEC.meanEscalate) {
      signals.push({
        ruleCode: "W_MEAN10",
        severity: "CRITICAL",
        message: `เฉลี่ย 10 ก้อนล่าสุด ${mean.toFixed(2)} kg ห่าง Target ${gap > 0 ? "+" : ""}${gap.toFixed(2)} kg`,
        opensIncident: true,
      });
    }
  }

  // 5 ก้อนเคลื่อนไปทิศทางเดียวกัน → Drift Warning
  const last5 = series.slice(-5);
  if (last5.length === 5) {
    const diffs = last5
      .slice(1)
      .map((s, i) => s.measurement.value - last5[i].measurement.value);
    const allUp = diffs.every((d) => d > 0);
    const allDown = diffs.every((d) => d < 0);
    if (allUp || allDown) {
      signals.push({
        ruleCode: "W_DRIFT",
        severity: "WARNING",
        message: `น้ำหนัก ${allUp ? "เพิ่ม" : "ลด"}ต่อเนื่อง 5 ก้อน (${last5[0].measurement.value.toFixed(2)} → ${last.measurement.value.toFixed(2)} kg)`,
        opensIncident: false,
      });
    }
  }

  // 2 ใน 3 ก้อนอยู่โซนเหลืองด้านเดียวกัน → Process Warning
  if (last3.length === 3) {
    const yellowHigh = last3.filter(
      (s) => statusOf(s) === "YELLOW" && s.deviation > 0,
    ).length;
    const yellowLow = last3.filter(
      (s) => statusOf(s) === "YELLOW" && s.deviation < 0,
    ).length;
    if (yellowHigh >= 2 || yellowLow >= 2) {
      signals.push({
        ruleCode: "W_PROC",
        severity: "WARNING",
        message: `2 ใน 3 ก้อนอยู่โซนเหลืองด้าน${yellowHigh >= 2 ? "สูง" : "ต่ำ"}`,
        opensIncident: false,
      });
    }
  }

  return signals;
}

/** ---------- Function 02: Temperature ---------- */

export function classifyTemp(worstError: number): {
  status: Status;
  ruleCode: string;
} {
  const abs = Math.abs(worstError);
  if (abs <= TEMP_SPEC.greenLimit) return { status: "GREEN", ruleCode: "T_OK" };
  if (abs <= TEMP_SPEC.yellowLimit)
    return { status: "YELLOW", ruleCode: "TEMP_Y2" };
  return { status: "RED", ruleCode: "TEMP_R3" };
}

/** Digital Thermometer = Reference, Worst Error = MAX(|Δ Burner|, |Δ Recorder|) */
export function compareTemp(actual: number, burner: number, recorder: number) {
  const deltaBurner = burner - actual;
  const deltaRecorder = recorder - actual;
  const worstError =
    Math.abs(deltaBurner) >= Math.abs(deltaRecorder)
      ? deltaBurner
      : deltaRecorder;
  return { deltaBurner, deltaRecorder, worstError };
}

/** Swing = MAX - MIN ของ Recorder ในหน้าต่างเวลา (ค่าจาก Recorder เดิม ไม่ต้องซื้อใหม่) */
export function recorderSwing(series: TempSample[], windowTicks: number) {
  const window = series.slice(-windowTicks);
  if (window.length < 2) return 0;
  const values = window.map((s) => s.recorder);
  return Math.max(...values) - Math.min(...values);
}

export function tempSignals(series: TempSample[]): Signal[] {
  const signals: Signal[] = [];
  if (series.length === 0) return signals;
  const last = series[series.length - 1];

  const last3 = series.slice(-3);
  if (last3.length === 3 && last3.every((s) => s.status === "RED")) {
    signals.push({
      ruleCode: "TEMP_R3X3",
      severity: "CRITICAL",
      message: `คลาดเคลื่อนเกิน ±${TEMP_SPEC.yellowLimit}°C ต่อเนื่อง 3 ครั้ง (ล่าสุด ${fmtDelta(last.worstError)}°C)`,
      opensIncident: true,
    });
  }

  if (last.status === "RED") {
    signals.push({
      ruleCode: "TEMP_R3",
      severity: "CRITICAL",
      message: `Δ ${fmtDelta(last.worstError)}°C เทียบค่าจริง ${last.actual.toFixed(1)}°C (Burner ${fmtDelta(last.deltaBurner)} / Recorder ${fmtDelta(last.deltaRecorder)})`,
      opensIncident: true,
    });
  }

  if (last.swing15 > TEMP_SPEC.swingLimit) {
    signals.push({
      ruleCode: "TEMP_SWING",
      severity: "WARNING",
      message: `Recorder แกว่ง ${last.swing15.toFixed(1)}°C ใน ${TEMP_SPEC.swingWindowMinutes} นาที`,
      opensIncident: false,
    });
  }

  return signals;
}

/** ---------- Function 03: Final pond temperature ---------- */

export function classifyPondTemp(value: number): {
  status: Status;
  ruleCode: string;
} {
  if (
    !Number.isFinite(value) ||
    value < POND_SPEC.sensorMin ||
    value > POND_SPEC.sensorMax
  ) {
    return { status: "SENSOR_ERROR", ruleCode: "POND_SENSOR" };
  }
  if (value > POND_SPEC.max) {
    return { status: "RED", ruleCode: "POND_HIGH" };
  }
  if (value > POND_SPEC.max - POND_SPEC.warningMargin) {
    return { status: "YELLOW", ruleCode: "POND_NEAR" };
  }
  return { status: "GREEN", ruleCode: "POND_OK" };
}

export function pondSignals(series: PondSample[]): Signal[] {
  if (series.length === 0) return [];
  const last = series[series.length - 1];

  if (last.status === "SENSOR_ERROR") {
    return [
      {
        ruleCode: "POND_SENSOR",
        severity: "CRITICAL",
        message: `เซ็นเซอร์บ่อสุดท้ายส่งค่า ${last.value.toFixed(1)}°C ซึ่งอยู่นอกช่วงที่เป็นไปได้`,
        opensIncident: true,
      },
    ];
  }
  if (last.status === "RED") {
    return [
      {
        ruleCode: "POND_HIGH",
        severity: "CRITICAL",
        message: `อุณหภูมิบ่อสุดท้าย ${last.value.toFixed(1)}°C สูงกว่าเกณฑ์ ${POND_SPEC.max.toFixed(0)}°C`,
        opensIncident: true,
      },
    ];
  }
  if (last.status === "YELLOW") {
    return [
      {
        ruleCode: "POND_NEAR",
        severity: "WARNING",
        message: `อุณหภูมิบ่อสุดท้าย ${last.value.toFixed(1)}°C ใกล้ขีดจำกัด ${POND_SPEC.max.toFixed(0)}°C`,
        opensIncident: false,
      },
    ];
  }
  return [];
}

export function fmtDelta(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}

/** ---------- Process Health ---------- */

export function healthPercent(statuses: Status[]) {
  if (statuses.length === 0) return 100;
  const good = statuses.filter((s) => s === "GREEN").length;
  const warn = statuses.filter((s) => s === "YELLOW").length;
  return ((good + warn * 0.5) / statuses.length) * 100;
}
