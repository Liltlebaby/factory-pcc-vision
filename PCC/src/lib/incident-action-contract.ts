export const INCIDENT_ACTIONS = ["ACKNOWLEDGE", "RESOLVE"] as const;
export type IncidentAction = (typeof INCIDENT_ACTIONS)[number];

export type IncidentActionInput = {
  action: IncidentAction;
  note: string | null;
};

export type IncidentActionParseResult =
  | { ok: true; value: IncidentActionInput }
  | { ok: false; error: "invalid_body" | "invalid_action" | "resolution_note_required" | "resolution_note_too_short" | "resolution_note_too_long" };

export function parseIncidentActionInput(input: unknown): IncidentActionParseResult {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return { ok: false, error: "invalid_body" };
  }
  const body = input as Record<string, unknown>;
  if (!INCIDENT_ACTIONS.includes(body.action as IncidentAction)) {
    return { ok: false, error: "invalid_action" };
  }
  if (body.note !== undefined && body.note !== null && typeof body.note !== "string") {
    return { ok: false, error: "invalid_body" };
  }
  const note = typeof body.note === "string" ? body.note.trim() : null;
  if (body.action === "RESOLVE" && !note) {
    return { ok: false, error: "resolution_note_required" };
  }
  if (body.action === "RESOLVE" && note && note.length < 3) {
    return { ok: false, error: "resolution_note_too_short" };
  }
  if (note && note.length > 1000) {
    return { ok: false, error: "resolution_note_too_long" };
  }
  return { ok: true, value: { action: body.action as IncidentAction, note } };
}

export const ALERT_KEY_PATTERN = /^[A-Za-z0-9_.:-]{1,200}$/;
export const IDEMPOTENCY_KEY_PATTERN = /^[A-Za-z0-9_.:-]{8,100}$/;
