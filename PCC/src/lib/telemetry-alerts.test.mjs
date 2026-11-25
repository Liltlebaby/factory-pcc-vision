import assert from "node:assert/strict";
import test from "node:test";
import { buildStationAlertMutations } from "./telemetry-alerts.ts";

function evaluation(overrides = {}) {
  return {
    station_id: "final-pond",
    site_id: "factory-01",
    line_id: "line-1",
    rule_key: "POND_PH",
    rule_code: "POND_PH_LOW",
    source_measurement_id: "pond:ph:1",
    metric: "water_ph",
    process_status: "RED",
    severity: "CRITICAL",
    is_violation: true,
    title: "ค่า pH บ่อสุดท้าย",
    message: "ค่า pH ต่ำกว่าเกณฑ์",
    owner: "ฝ่ายผลิต + QC",
    recommended_action: "เติมปูนขาวแล้ววัดซ้ำ",
    evaluated_at: "2026-09-21T01:00:00.000Z",
    ...overrides,
  };
}

test("opens one alert and keeps retry idempotent", () => {
  const first = buildStationAlertMutations([evaluation()], [], "2026-09-21T01:00:01.000Z");
  assert.equal(first.alerts[0].state, "OPEN");
  assert.equal(first.alerts[0].workflow_state, "OPEN");
  assert.equal(first.alerts[0].occurrence_count, 1);
  assert.equal(first.events[0].transition, "OPEN");

  const retry = buildStationAlertMutations([evaluation()], [first.alerts[0]], "2026-09-21T01:00:02.000Z");
  assert.equal(retry.alerts[0].occurrence_count, 1);
  assert.equal(retry.events[0].transition, "OBSERVED");
  assert.equal(retry.events[0].event_key, first.events[0].event_key);
});

test("closes an active alert when the same rule family returns to normal", () => {
  const opened = buildStationAlertMutations([evaluation()], [], "2026-09-21T01:00:01.000Z").alerts[0];
  const normal = evaluation({
    rule_code: "POND_PH_OK",
    source_measurement_id: "pond:ph:2",
    process_status: "GREEN",
    severity: null,
    is_violation: false,
    message: "ค่า pH อยู่ในเกณฑ์",
    evaluated_at: "2026-09-21T01:05:00.000Z",
  });
  const result = buildStationAlertMutations([normal], [opened], "2026-09-21T01:05:01.000Z");
  assert.equal(result.alerts[0].state, "CLOSED");
  assert.equal(result.alerts[0].workflow_state, "CLOSED");
  assert.equal(result.alerts[0].closed_at, normal.evaluated_at);
  assert.equal(result.events[0].transition, "CLOSED");
});

test("reopening a closed alert increments its occurrence count", () => {
  const opened = buildStationAlertMutations([evaluation()], [], "2026-09-21T01:00:01.000Z").alerts[0];
  const closed = { ...opened, state: "CLOSED", closed_at: "2026-09-21T01:05:00.000Z" };
  const again = evaluation({ source_measurement_id: "pond:ph:3", evaluated_at: "2026-09-21T02:00:00.000Z" });
  const result = buildStationAlertMutations([again], [closed], "2026-09-21T02:00:01.000Z");
  assert.equal(result.alerts[0].state, "OPEN");
  assert.equal(result.alerts[0].workflow_state, "OPEN");
  assert.equal(result.alerts[0].occurrence_count, 2);
  assert.equal(result.alerts[0].opened_at, again.evaluated_at);
  assert.equal(result.events[0].transition, "OPEN");
});
