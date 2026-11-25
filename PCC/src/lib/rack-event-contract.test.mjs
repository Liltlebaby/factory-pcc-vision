import assert from "node:assert/strict";
import test from "node:test";
import { parseRackAIEventPage } from "./rack-event-contract.ts";

function event(cursor) {
  return {
    cursor,
    event_id: `camera-09:rubber-counting:${cursor}`,
    camera_id: "camera-09",
    task_id: "rubber-counting",
    station_id: "checker-infeed",
    type: "rubber_counted",
    occurred_at: "2026-09-19T02:30:00Z",
    model_version: "best.pt",
    rule_version: "rack-count-v1",
    payload: { rubber_count: cursor, track_id: cursor, confidence: 0.9 },
  };
}

test("accepts a page only when its cursor advances", () => {
  const page = parseRackAIEventPage(
    { items: [event(11), event(12)], next_cursor: 12, has_more: false },
    10,
  );
  assert.equal(page.items.length, 2);
  assert.equal(page.next_cursor, 12);
});

test("rejects malformed events and a stuck cursor", () => {
  assert.throws(
    () => parseRackAIEventPage({ items: [event(10)], next_cursor: 10, has_more: true }, 10),
    /event_cursor_did_not_advance/,
  );
  assert.throws(
    () => parseRackAIEventPage({ items: [{ ...event(11), occurred_at: "bad" }], next_cursor: 11, has_more: false }, 10),
    /invalid_event_page/,
  );
  assert.throws(
    () => parseRackAIEventPage({ items: [{ ...event(11), payload: { track_id: 11 } }], next_cursor: 11, has_more: false }, 10),
    /invalid_event_page/,
  );
});
