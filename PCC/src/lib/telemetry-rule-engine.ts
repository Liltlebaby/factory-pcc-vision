import { POND_PH_SPEC, POND_SPEC, TEMP_SPEC, WEIGHT_SPEC } from "./config";
import { classifyPondTemp, classifyTemp, classifyWeight, compareTemp } from "./engine";
import type { SensorTelemetry, StationTelemetry, TelemetryRuleEvaluation } from "@/lib/telemetry";
import type { Status } from "@/lib/types";

const STATUS_RANK: Record<Status, number> = {
  GREEN: 0,
  YELLOW: 1,
  RED: 2,
  SENSOR_ERROR: 3,
};

type RuleInput = Omit<TelemetryRuleEvaluation, "station_id" | "site_id" | "line_id" | "source_measurement_id" | "evaluated_at">;

function buildRule(reading: SensorTelemetry, input: RuleInput): TelemetryRuleEvaluation {
  return {
    station_id: reading.station_id,
    site_id: reading.site_id,
    line_id: reading.line_id,
    source_measurement_id: reading.measurement_id,
    evaluated_at: reading.measured_at,
    ...input,
  };
}

function qualityRule(reading: SensorTelemetry, ruleKey: string, title: string, owner: string): TelemetryRuleEvaluation | null {
  if (reading.quality === "good") return null;
  const sensorError = reading.quality === "bad" || reading.quality === "stale";
  return buildRule(reading, {
    rule_key: ruleKey,
    rule_code: `${ruleKey}_${sensorError ? "QUALITY_ERROR" : "QUALITY_UNCERTAIN"}`,
    metric: reading.metric,
    process_status: sensorError ? "SENSOR_ERROR" : "YELLOW",
    severity: sensorError ? "CRITICAL" : "WARNING",
    is_violation: true,
    title,
    message: `คุณภาพข้อมูล ${reading.metric} เป็น ${reading.quality}`,
    owner,
    recommended_action: "ตรวจหัววัด การสอบเทียบ สายสัญญาณ และ Gateway ก่อนใช้ค่าตัดสินกระบวนการ",
  });
}

function unitError(reading: SensorTelemetry, ruleKey: string, expected: string, title: string, owner: string) {
  return buildRule(reading, {
    rule_key: ruleKey,
    rule_code: `${ruleKey}_UNIT_ERROR`,
    metric: reading.metric,
    process_status: "SENSOR_ERROR",
    severity: "CRITICAL",
    is_violation: true,
    title,
    message: `หน่วยของ ${reading.metric} เป็น ${reading.unit} แต่ระบบกำหนดให้เป็น ${expected}`,
    owner,
    recommended_action: "แก้ mapping หน่วยที่ Gateway และตรวจ configuration ก่อนส่งข้อมูลรอบถัดไป",
  });
}

function pondTemperature(reading: SensorTelemetry): TelemetryRuleEvaluation {
  const title = "อุณหภูมิบ่อสุดท้าย";
  const owner = "ฝ่ายผลิต + QC";
  const quality = qualityRule(reading, "POND_TEMP", title, owner);
  if (quality) return quality;
  if (reading.unit !== "°C") return unitError(reading, "POND_TEMP", "°C", title, owner);
  const verdict = classifyPondTemp(reading.value);
  const status = verdict.status;
  return buildRule(reading, {
    rule_key: "POND_TEMP",
    rule_code: verdict.ruleCode,
    metric: reading.metric,
    process_status: status,
    severity: status === "RED" || status === "SENSOR_ERROR" ? "CRITICAL" : status === "YELLOW" ? "WARNING" : null,
    is_violation: status !== "GREEN",
    title,
    message: status === "GREEN"
      ? `อุณหภูมิ ${reading.value.toFixed(1)}°C อยู่ในเกณฑ์`
      : status === "YELLOW"
        ? `อุณหภูมิ ${reading.value.toFixed(1)}°C ใกล้ขีดจำกัด ${POND_SPEC.max}°C`
        : status === "RED"
          ? `อุณหภูมิ ${reading.value.toFixed(1)}°C สูงกว่าเกณฑ์ ${POND_SPEC.max}°C`
          : `อุณหภูมิ ${reading.value.toFixed(1)}°C อยู่นอกช่วงที่เซ็นเซอร์รองรับ`,
    owner,
    recommended_action: status === "GREEN"
      ? "ติดตามค่าตามรอบปกติ"
      : "ตรวจปั๊มและการไหลเวียนของน้ำ พร้อมยืนยันค่าด้วยเครื่องวัดสำรอง",
  });
}

function pondPh(reading: SensorTelemetry): TelemetryRuleEvaluation {
  const title = "ค่า pH บ่อสุดท้าย";
  const owner = "ฝ่ายผลิต + QC";
  const quality = qualityRule(reading, "POND_PH", title, owner);
  if (quality) return quality;
  if (reading.unit !== "pH") return unitError(reading, "POND_PH", "pH", title, owner);
  const low = reading.value < POND_PH_SPEC.min;
  const high = reading.value > POND_PH_SPEC.max;
  const status: Status = low || high ? "RED" : "GREEN";
  return buildRule(reading, {
    rule_key: "POND_PH",
    rule_code: low ? "POND_PH_LOW" : high ? "POND_PH_HIGH" : "POND_PH_OK",
    metric: reading.metric,
    process_status: status,
    severity: status === "RED" ? "CRITICAL" : null,
    is_violation: status !== "GREEN",
    title,
    message: status === "GREEN"
      ? `ค่า pH ${reading.value.toFixed(2)} อยู่ในเกณฑ์ ${POND_PH_SPEC.min}–${POND_PH_SPEC.max}`
      : `ค่า pH ${reading.value.toFixed(2)} ${low ? "ต่ำกว่า" : "สูงกว่า"}เกณฑ์ ${POND_PH_SPEC.min}–${POND_PH_SPEC.max}`,
    owner,
    recommended_action: low
      ? "เติมปูนขาวตาม WI แล้ววัด pH ซ้ำอย่างสม่ำเสมอ"
      : high
        ? "เติมน้ำเพื่อเจือจางแบบ Overflow แล้ววัด pH ซ้ำอย่างสม่ำเสมอ"
        : "ตรวจปั๊มน้ำไหลกลับบ่อเหล็ก AJ1 และติดตามค่าตามรอบปกติ",
  });
}

function rubberWeight(reading: SensorTelemetry): TelemetryRuleEvaluation {
  const title = "น้ำหนักก้อนยาง";
  const owner = "หอโรยยาง";
  const quality = qualityRule(reading, "RUBBER_WEIGHT", title, owner);
  if (quality) return quality;
  if (reading.unit !== "kg") return unitError(reading, "RUBBER_WEIGHT", "kg", title, owner);
  const verdict = classifyWeight(reading.value);
  const status = verdict.status;
  return buildRule(reading, {
    rule_key: "RUBBER_WEIGHT",
    rule_code: verdict.ruleCode,
    metric: reading.metric,
    process_status: status,
    severity: status === "RED" || status === "SENSOR_ERROR" ? "CRITICAL" : status === "YELLOW" ? "WARNING" : null,
    is_violation: status !== "GREEN",
    title,
    message: status === "GREEN"
      ? `น้ำหนัก ${reading.value.toFixed(2)} kg อยู่ในเกณฑ์`
      : `น้ำหนัก ${reading.value.toFixed(2)} kg เบี่ยงจากเป้าหมาย ${WEIGHT_SPEC.target.toFixed(2)} kg`,
    owner: status === "SENSOR_ERROR" ? "ช่างซ่อมบำรุง" : owner,
    recommended_action: status === "SENSOR_ERROR"
      ? "ตรวจ Load Cell สายสัญญาณ และ Gateway"
      : status === "GREEN"
        ? "ติดตามค่าตามรอบปกติ"
        : "ตรวจปริมาณโรยยางและยืนยันน้ำหนักด้วยตาชั่งสำรอง",
  });
}

function furnaceTemperature(station: StationTelemetry): TelemetryRuleEvaluation[] {
  const actual = station.latest.furnace_temperature;
  const burner = station.latest.furnace_burner_temperature;
  const recorder = station.latest.furnace_recorder_temperature;
  const source = actual ?? burner ?? recorder;
  if (!source) return [];
  const title = "อุณหภูมิเตา";
  const owner = "ช่าง Burner";
  if (!actual || !burner || !recorder) {
    return [buildRule(source, {
      rule_key: "FURNACE_COMPARE",
      rule_code: "FURNACE_INCOMPLETE",
      metric: "furnace_temperature",
      process_status: "SENSOR_ERROR",
      severity: "CRITICAL",
      is_violation: true,
      title,
      message: "ข้อมูล Digital Thermometer, Burner หรือ Recorder มาไม่ครบ",
      owner,
      recommended_action: "ตรวจสายสัญญาณและ mapping ของอุปกรณ์ทั้ง 3 จุด",
    })];
  }
  const affected = [actual, burner, recorder].find((item) => item.quality !== "good");
  if (affected) return [qualityRule(affected, "FURNACE_COMPARE", title, owner)!];
  const wrongUnit = [actual, burner, recorder].find((item) => item.unit !== "°C");
  if (wrongUnit) return [unitError(wrongUnit, "FURNACE_COMPARE", "°C", title, owner)];
  const comparison = compareTemp(actual.value, burner.value, recorder.value);
  const verdict = classifyTemp(comparison.worstError);
  const status = verdict.status;
  return [buildRule(actual, {
    rule_key: "FURNACE_COMPARE",
    rule_code: verdict.ruleCode,
    metric: actual.metric,
    process_status: status,
    severity: status === "RED" ? "CRITICAL" : status === "YELLOW" ? "WARNING" : null,
    is_violation: status !== "GREEN",
    title,
    message: status === "GREEN"
      ? `ค่าคลาดเคลื่อนสูงสุด ${comparison.worstError.toFixed(1)}°C อยู่ในเกณฑ์`
      : `ค่าคลาดเคลื่อนสูงสุด ${comparison.worstError.toFixed(1)}°C เทียบ Digital Thermometer ${actual.value.toFixed(1)}°C`,
    owner,
    recommended_action: status === "GREEN"
      ? "ติดตามค่าตามรอบปกติ"
      : `ตรวจ Burner และ Recorder ให้คลาดเคลื่อนไม่เกิน ±${TEMP_SPEC.greenLimit}°C`,
  })];
}

export function evaluateStationTelemetry(station: StationTelemetry): StationTelemetry {
  let rules: TelemetryRuleEvaluation[] = [];
  if (station.station_id === "final-pond") {
    const temperature = station.latest.water_temperature;
    const ph = station.latest.water_ph;
    if (temperature) rules.push(pondTemperature(temperature));
    if (ph) rules.push(pondPh(ph));
  } else if (station.station_id === "rubber-scale") {
    const weight = station.latest.rubber_weight;
    if (weight) rules.push(rubberWeight(weight));
  } else if (station.station_id === "furnace-temperature") {
    rules = furnaceTemperature(station);
  }

  const missingRequired =
    (station.station_id === "final-pond" && (!station.latest.water_temperature || !station.latest.water_ph)) ||
    (station.station_id === "rubber-scale" && !station.latest.rubber_weight) ||
    (station.station_id === "furnace-temperature" && rules.length === 0);
  const processStatus: Status = station.data_status === "offline" || station.data_status === "stale" || missingRequired
    ? "SENSOR_ERROR"
    : rules.reduce<Status>((worst, rule) => STATUS_RANK[rule.process_status] > STATUS_RANK[worst] ? rule.process_status : worst, "GREEN");
  return { ...station, process_status: processStatus, rules };
}
