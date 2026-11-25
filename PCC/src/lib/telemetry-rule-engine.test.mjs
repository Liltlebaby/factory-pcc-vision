import assert from "node:assert/strict";
import test from "node:test";
import { evaluateStationTelemetry } from "./telemetry-rule-engine.ts";

function reading({ station, metric, value, unit = "°C", quality = "good", id = metric }) {
  return {
    measurement_id: id,
    site_id: "factory-01",
    line_id: "line-1",
    station_id: station,
    device_id: "gateway-01",
    metric,
    value,
    unit,
    measured_at: "2026-09-20T01:00:00.000Z",
    received_at: "2026-09-20T01:00:01.000Z",
    quality,
    source_mode: "live",
  };
}

function station(stationId, readings, dataStatus = "live") {
  return {
    station_id: stationId,
    data_status: dataStatus,
    generated_at: "2026-09-20T01:00:02.000Z",
    latest: Object.fromEntries(readings.map((item) => [item.metric, item])),
    history: readings,
    process_status: "SENSOR_ERROR",
    rules: [],
  };
}

test("final pond evaluates temperature and low pH on the server", () => {
  const result = evaluateStationTelemetry(station("final-pond", [
    reading({ station: "final-pond", metric: "water_temperature", value: 32.1 }),
    reading({ station: "final-pond", metric: "water_ph", value: 9.7, unit: "pH" }),
  ]));
  assert.equal(result.process_status, "RED");
  assert.equal(result.rules.length, 2);
  assert.equal(result.rules.find((rule) => rule.rule_key === "POND_PH")?.rule_code, "POND_PH_LOW");
  assert.match(result.rules.find((rule) => rule.rule_key === "POND_PH")?.recommended_action ?? "", /ปูนขาว/);
});

test("final pond flags a near-limit temperature as warning", () => {
  const result = evaluateStationTelemetry(station("final-pond", [
    reading({ station: "final-pond", metric: "water_temperature", value: 34.4 }),
    reading({ station: "final-pond", metric: "water_ph", value: 10.5, unit: "pH" }),
  ]));
  assert.equal(result.process_status, "YELLOW");
  assert.equal(result.rules.find((rule) => rule.rule_key === "POND_TEMP")?.rule_code, "POND_NEAR");
});

test("missing furnace channel is a sensor error", () => {
  const result = evaluateStationTelemetry(station("furnace-temperature", [
    reading({ station: "furnace-temperature", metric: "furnace_temperature", value: 180.5 }),
    reading({ station: "furnace-temperature", metric: "furnace_burner_temperature", value: 180.8 }),
  ]));
  assert.equal(result.process_status, "SENSOR_ERROR");
  assert.equal(result.rules[0].rule_code, "FURNACE_INCOMPLETE");
});

test("furnace comparison uses the digital thermometer as reference", () => {
  const result = evaluateStationTelemetry(station("furnace-temperature", [
    reading({ station: "furnace-temperature", metric: "furnace_temperature", value: 180.5 }),
    reading({ station: "furnace-temperature", metric: "furnace_burner_temperature", value: 183.0 }),
    reading({ station: "furnace-temperature", metric: "furnace_recorder_temperature", value: 180.8 }),
  ]));
  assert.equal(result.process_status, "RED");
  assert.equal(result.rules[0].rule_code, "TEMP_R3");
});

test("wrong units never become a normal process reading", () => {
  const result = evaluateStationTelemetry(station("rubber-scale", [
    reading({ station: "rubber-scale", metric: "rubber_weight", value: 17.5, unit: "g" }),
  ]));
  assert.equal(result.process_status, "SENSOR_ERROR");
  assert.equal(result.rules[0].rule_code, "RUBBER_WEIGHT_UNIT_ERROR");
});
