import assert from "node:assert/strict";
import test from "node:test";
import { parseSensorTelemetryBatch } from "./telemetry-contract.ts";
const valid = {
  measurement_id: "pond-gateway-01:1726700000:ph",
  site_id: "factory-01",
  line_id: "line-1",
  station_id: "final-pond",
  device_id: "pond-gateway-01",
  metric: "water_ph",
  value: 10.42,
  unit: "pH",
  measured_at: "2026-09-19T09:00:00.000Z",
  received_at: "2026-09-19T09:00:01.000Z",
  quality: "good",
  source_mode: "live",
};

test("accepts one item or a bounded batch", () => {
  assert.equal(parseSensorTelemetryBatch(valid).length, 1);
  assert.equal(parseSensorTelemetryBatch([valid, { ...valid, measurement_id: "second" }]).length, 2);
});

test("rejects malformed and oversized telemetry", () => {
  assert.throws(() => parseSensorTelemetryBatch({ ...valid, value: Number.NaN }));
  assert.throws(() => parseSensorTelemetryBatch({ ...valid, station_id: "bad station" }));
  assert.throws(() => parseSensorTelemetryBatch(Array.from({ length: 101 }, () => valid)));
});
