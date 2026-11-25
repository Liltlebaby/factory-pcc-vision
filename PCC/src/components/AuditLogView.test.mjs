import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AuditAccessState, AuditLogView } from "./AuditLogView.tsx";

test("audit log renders action, actor and safe changed-field summary", () => {
  const html = renderToStaticMarkup(createElement(AuditLogView, { feed: {
    dataStatus: "live",
    generatedAt: "2026-09-22T09:00:00.000Z",
    records: [{ id: 1, action: "incident.acknowledge", entityType: "station_alert", entityId: "final-pond:POND_PH", actorId: "actor-1", actorName: "สมชาย Operator", actorRole: "operator", requestId: "req-001", occurredAt: "2026-09-22T08:00:00.000Z", changedFields: ["workflow_state"] }],
  }}));
  assert.match(html, /บันทึกการใช้งานระบบ/);
  assert.match(html, /รับทราบเหตุการณ์/);
  assert.match(html, /สมชาย Operator/);
  assert.match(html, /workflow_state/);
  assert.doesNotMatch(html, /before_state|after_state/);
});

test("audit access state explains that demo data is never substituted", () => {
  const html = renderToStaticMarkup(createElement(AuditAccessState, { state: "not_configured" }));
  assert.match(html, /ยังไม่ได้เชื่อมระบบบัญชี/);
  assert.match(html, /ไม่แสดงข้อมูลตัวอย่างแทน Audit จริง/);
});
