import assert from "node:assert/strict";
import test from "node:test";
import { parseIncidentActionInput } from "./incident-action-contract.ts";

test("accepts acknowledgement without a note", () => {
  assert.deepEqual(parseIncidentActionInput({ action: "ACKNOWLEDGE" }), {
    ok: true,
    value: { action: "ACKNOWLEDGE", note: null },
  });
});

test("requires and trims a resolution note", () => {
  assert.deepEqual(parseIncidentActionInput({ action: "RESOLVE", note: "  ล้างหัววัดแล้ว  " }), {
    ok: true,
    value: { action: "RESOLVE", note: "ล้างหัววัดแล้ว" },
  });
  assert.deepEqual(parseIncidentActionInput({ action: "RESOLVE", note: "  " }), {
    ok: false,
    error: "resolution_note_required",
  });
  assert.deepEqual(parseIncidentActionInput({ action: "RESOLVE", note: "ok" }), {
    ok: false,
    error: "resolution_note_too_short",
  });
});

test("rejects unknown actions and oversized notes", () => {
  assert.deepEqual(parseIncidentActionInput({ action: "DELETE" }), {
    ok: false,
    error: "invalid_action",
  });
  assert.deepEqual(parseIncidentActionInput({ action: "RESOLVE", note: "x".repeat(1001) }), {
    ok: false,
    error: "resolution_note_too_long",
  });
});
