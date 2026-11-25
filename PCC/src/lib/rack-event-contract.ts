import type { RackAIEventPage, RackAIPersistentEvent } from "@/lib/rack";

function validEvent(value: unknown): value is RackAIPersistentEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Partial<RackAIPersistentEvent>;
  const validEnvelope = (
    Number.isSafeInteger(event.cursor) &&
    Number(event.cursor) > 0 &&
    typeof event.event_id === "string" &&
    typeof event.camera_id === "string" &&
    typeof event.task_id === "string" &&
    typeof event.station_id === "string" &&
    typeof event.type === "string" &&
    typeof event.occurred_at === "string" &&
    Number.isFinite(Date.parse(event.occurred_at)) &&
    typeof event.rule_version === "string" &&
    Boolean(event.payload && typeof event.payload === "object")
  );
  if (!validEnvelope) return false;
  if (event.type !== "rubber_counted") return true;
  const payload = event.payload as Record<string, unknown>;
  return (
    Number.isSafeInteger(payload.rubber_count) &&
    Number(payload.rubber_count) >= 0 &&
    Number.isSafeInteger(payload.track_id) &&
    typeof payload.confidence === "number" &&
    Number.isFinite(payload.confidence) &&
    payload.confidence >= 0 &&
    payload.confidence <= 1
  );
}

export function parseRackAIEventPage(value: unknown, currentCursor: number): RackAIEventPage {
  if (!value || typeof value !== "object") throw new Error("invalid_event_page");
  const page = value as Partial<RackAIEventPage>;
  if (
    !Array.isArray(page.items) ||
    !page.items.every(validEvent) ||
    !Number.isSafeInteger(page.next_cursor) ||
    Number(page.next_cursor) < currentCursor ||
    typeof page.has_more !== "boolean"
  ) {
    throw new Error("invalid_event_page");
  }
  if (page.items.length > 0 && Number(page.next_cursor) <= currentCursor) {
    throw new Error("event_cursor_did_not_advance");
  }
  return page as RackAIEventPage;
}
