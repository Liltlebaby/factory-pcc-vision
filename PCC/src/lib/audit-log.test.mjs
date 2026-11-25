import assert from "node:assert/strict";
import test from "node:test";
import { auditActionLabel, listChangedAuditFields, shortActorId } from "./audit-log.ts";

test("audit field summary only returns material changed fields", () => {
  assert.deepEqual(
    listChangedAuditFields(
      { workflow_state: "OPEN", occurrence_count: 1, updated_at: "old" },
      { workflow_state: "ACKNOWLEDGED", occurrence_count: 1, updated_at: "new" },
    ),
    ["workflow_state"],
  );
});

test("audit labels and actor fallback remain readable", () => {
  assert.equal(auditActionLabel("incident.resolve"), "ส่งตรวจสอบหลังแก้ไข");
  assert.equal(shortActorId(null), "ระบบอัตโนมัติ");
  assert.equal(shortActorId("12345678-aaaa-bbbb-cccc-123456789012"), "ผู้ใช้ 12345678");
});
