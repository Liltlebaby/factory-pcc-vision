import type { SensorTelemetry } from "@/lib/telemetry";

const ID = /^[A-Za-z0-9_-]{1,100}$/;
const METRIC = /^[A-Za-z0-9_.:-]{1,100}$/;
const QUALITIES = new Set(["good", "uncertain", "bad", "stale"]);
const SOURCE_MODES = new Set(["live", "demo"]);

function validDateTime(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

export function parseSensorTelemetry(value: unknown): SensorTelemetry {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("invalid_sensor_telemetry");
  }
  const item = value as Partial<SensorTelemetry>;
  const valid =
    typeof item.measurement_id === "string" &&
    item.measurement_id.length > 0 &&
    item.measurement_id.length <= 160 &&
    typeof item.site_id === "string" && ID.test(item.site_id) &&
    typeof item.line_id === "string" && ID.test(item.line_id) &&
    typeof item.station_id === "string" && ID.test(item.station_id) &&
    typeof item.device_id === "string" && ID.test(item.device_id) &&
    typeof item.metric === "string" && METRIC.test(item.metric) &&
    typeof item.value === "number" && Number.isFinite(item.value) &&
    typeof item.unit === "string" && item.unit.length > 0 && item.unit.length <= 40 &&
    validDateTime(item.measured_at) &&
    validDateTime(item.received_at) &&
    typeof item.quality === "string" && QUALITIES.has(item.quality) &&
    typeof item.source_mode === "string" && SOURCE_MODES.has(item.source_mode);
  if (!valid) throw new Error("invalid_sensor_telemetry");
  return item as SensorTelemetry;
}

export function parseSensorTelemetryBatch(value: unknown): SensorTelemetry[] {
  const values = Array.isArray(value) ? value : [value];
  if (values.length === 0 || values.length > 100) {
    throw new Error("invalid_sensor_telemetry_batch");
  }
  return values.map(parseSensorTelemetry);
}
