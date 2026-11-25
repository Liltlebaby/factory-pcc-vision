import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { StationAlertActions } from "./StationAlertActions.tsx";

function alert(overrides = {}) {
  return {
    alert_key: "final-pond:POND_PH",
    site_id: "factory-01",
    line_id: "line-1",
    station_id: "final-pond",
    rule_key: "POND_PH",
    rule_code: "POND_PH_LOW",
    source_measurement_id: "pond:ph:1",
    state: "OPEN",
    workflow_state: "OPEN",
    process_status: "RED",
    severity: "CRITICAL",
    title: "ค่า pH ต่ำกว่าเกณฑ์",
    message: "pH 9.8",
    owner: "ฝ่ายผลิต + QC",
    recommended_action: "เติมปูนขาวแล้ววัดซ้ำ",
    opened_at: "2026-09-22T01:00:00.000Z",
    last_observed_at: "2026-09-22T01:05:00.000Z",
    closed_at: null,
    occurrence_count: 1,
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
    resolution_note: null,
    ...overrides,
  };
}

test("operator can acknowledge an open live alert", () => {
  const html = renderToStaticMarkup(createElement(StationAlertActions, { alert: alert(), role: "operator" }));
  const button = html.match(/<button[^>]*>รับทราบเหตุการณ์<\/button>/)?.[0];
  assert.ok(button);
  assert.doesNotMatch(button, /\sdisabled=""/);
});

test("viewer sees the workflow but cannot acknowledge", () => {
  const html = renderToStaticMarkup(createElement(StationAlertActions, { alert: alert(), role: "viewer" }));
  const button = html.match(/<button[^>]*>รับทราบเหตุการณ์<\/button>/)?.[0];
  assert.ok(button);
  assert.match(button, /disabled=""/);
});

test("acknowledged alert asks an operator for a resolution note", () => {
  const html = renderToStaticMarkup(createElement(StationAlertActions, {
    alert: alert({ workflow_state: "ACKNOWLEDGED", acknowledged_at: "2026-09-22T01:06:00.000Z" }),
    role: "operator",
  }));
  assert.match(html, /สิ่งที่ดำเนินการแก้ไข/);
  assert.match(html, /บันทึกว่าแก้ไขแล้ว/);
  assert.match(html, /เติมน้ำและตรวจวัด pH ซ้ำแล้ว/);
});
