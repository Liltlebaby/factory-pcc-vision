import "server-only";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type { RackAIPersistentEvent, RackEvent } from "@/lib/rack";

const CAMERA_ID = "Camera09";

/**
 * เหตุการณ์นับเก๊ะหนึ่งครั้งที่อ่านกลับมาจากฐานข้อมูล
 *
 * เดิมชนิดนี้อยู่ใน lib/rack-report.ts ซึ่งเป็นโมดูลของรายงานตัวเก่าที่สะสมยอด
 * ใน localStorage ของเบราว์เซอร์ พอเลิกใช้รายงานตัวนั้นแล้ว (แทนด้วย
 * RackHourlyReport ที่อ่านยอดจากฝั่งเซิร์ฟเวอร์) ชนิดนี้จึงย้ายมาอยู่กับ
 * readRackEvents ซึ่งเป็นที่เดียวที่ใช้มันจริง
 */
export type RackCountEvent = {
  at: number;
  quantity: number;
};

type RackCountRow = {
  occurred_at: string;
  quantity: number;
};

let client: SupabaseClient | null = null;
let lastPersistedKey = "";

function credentials() {
  const url = process.env.SUPABASE_URL;
  const secret =
    process.env.SUPABASE_SECRET_KEY ?? process.env.SUPABASE_SERVICE_ROLE_KEY;
  return url && secret ? { url, secret } : null;
}

export function rackDatabaseConfigured() {
  return credentials() !== null;
}

function database() {
  const values = credentials();
  if (!values) return null;

  client ??= createClient(values.url, values.secret, {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
      detectSessionInUrl: false,
    },
  });
  return client;
}

function schemaMissing(error: { code?: string; message?: string } | null) {
  return Boolean(
    error &&
      (["42P01", "42703", "PGRST204", "PGRST205"].includes(error.code ?? "") ||
        /does not exist|schema cache|column/i.test(error.message ?? "")),
  );
}

function eventDate(timestamp: number) {
  const milliseconds = timestamp < 1_000_000_000_000 ? timestamp * 1000 : timestamp;
  const date = new Date(milliseconds);
  return Number.isFinite(date.getTime()) ? date : null;
}

/** Store one Camera 09 crossing. Duplicate status polls are ignored safely. */
export async function persistRackEvent(event: RackEvent | null) {
  const db = database();
  if (!db || !event) return;

  const occurredAt = eventDate(event.timestamp);
  if (!occurredAt) return;
  const key = `${occurredAt.toISOString()}:${event.trackId}`;
  if (key === lastPersistedKey) return;

  const { error } = await db.from("rack_count_events").upsert(
    {
      camera_id: CAMERA_ID,
      rack_number: event.rackNumber,
      track_id: event.trackId,
      quantity: 1,
      confidence: event.confidence,
      occurred_at: occurredAt.toISOString(),
    },
    {
      onConflict: "camera_id,occurred_at,track_id",
      ignoreDuplicates: true,
    },
  );

  if (error) throw new Error(`rack_event_insert_failed: ${error.message}`);
  lastPersistedKey = key;
}

export async function readRackEvents(since: Date): Promise<RackCountEvent[]> {
  const db = database();
  if (!db) return [];

  const { data, error } = await db
    .from("rack_count_events")
    .select("occurred_at,quantity")
    .eq("camera_id", CAMERA_ID)
    .gte("occurred_at", since.toISOString())
    .order("occurred_at", { ascending: true });

  if (error) throw new Error(`rack_event_query_failed: ${error.message}`);

  return ((data ?? []) as RackCountRow[]).flatMap((row) => {
    const at = Date.parse(row.occurred_at);
    return Number.isFinite(at) && row.quantity > 0
      ? [{ at, quantity: row.quantity }]
      : [];
  });
}

const VISION_INTEGRATION_ID = "vision-monitor";

export async function readRackSyncCursor() {
  const db = database();
  if (!db) return 0;
  const { data, error } = await db
    .from("integration_sync_state")
    .select("last_cursor")
    .eq("integration_id", VISION_INTEGRATION_ID)
    .maybeSingle();
  if (schemaMissing(error)) return 0;
  if (error) throw new Error(`rack_sync_cursor_read_failed: ${error.message}`);
  const cursor = Number(data?.last_cursor ?? 0);
  return Number.isSafeInteger(cursor) && cursor >= 0 ? cursor : 0;
}

type RackSyncStateRow = {
  last_cursor: number;
  last_success_at: string | null;
  last_error: string | null;
  updated_at: string;
};

export async function readRackSyncState(): Promise<RackSyncStateRow | null> {
  const db = database();
  if (!db) return null;
  const { data, error } = await db
    .from("integration_sync_state")
    .select("last_cursor,last_success_at,last_error,updated_at")
    .eq("integration_id", VISION_INTEGRATION_ID)
    .maybeSingle();
  if (schemaMissing(error)) return null;
  if (error) throw new Error(`rack_sync_state_read_failed: ${error.message}`);
  return data ? (data as RackSyncStateRow) : null;
}

export async function persistRackAIEvents(events: RackAIPersistentEvent[]) {
  const db = database();
  if (!db || events.length === 0) return 0;

  const rows = events.map((event) => ({
    source_event_id: event.event_id,
    source_cursor: event.cursor,
    camera_id: event.camera_id,
    task_id: event.task_id,
    station_id: event.station_id,
    // rack_count คือคีย์ปัจจุบัน rubber_count คือคีย์เดิมที่ยังอยู่ในเหตุการณ์เก่า
    rack_number: Math.max(0, Math.floor(Number(event.payload.rack_count ?? event.payload.rubber_count ?? 0))),
    track_id: Math.floor(Number(event.payload.track_id ?? 0)),
    quantity: 1,
    confidence:
      typeof event.payload.confidence === "number" ? event.payload.confidence : null,
    occurred_at: event.occurred_at,
    model_version: event.model_version,
    rule_version: event.rule_version,
    source_payload: event.payload,
  }));

  const { error } = await db.from("rack_count_events").upsert(rows, {
    onConflict: "source_event_id",
    ignoreDuplicates: true,
  });
  if (!error) return rows.length;
  if (!schemaMissing(error)) {
    throw new Error(`rack_event_insert_failed: ${error.message}`);
  }

  // Transitional fallback for a database that has not applied the v1 sync
  // migration yet. The legacy unique constraint still makes replay idempotent.
  const legacyRows = rows.map((row) => ({
    camera_id: row.camera_id,
    rack_number: row.rack_number,
    track_id: row.track_id,
    quantity: row.quantity,
    confidence: row.confidence,
    occurred_at: row.occurred_at,
  }));
  const { error: legacyError } = await db.from("rack_count_events").upsert(legacyRows, {
    onConflict: "camera_id,occurred_at,track_id",
    ignoreDuplicates: true,
  });
  if (legacyError) throw new Error(`rack_event_insert_failed: ${legacyError.message}`);
  return legacyRows.length;
}

export async function writeRackSyncCursor(cursor: number) {
  const db = database();
  if (!db) return false;
  const now = new Date().toISOString();
  const { error } = await db.from("integration_sync_state").upsert(
    {
      integration_id: VISION_INTEGRATION_ID,
      last_cursor: cursor,
      last_success_at: now,
      last_error: null,
      updated_at: now,
    },
    { onConflict: "integration_id" },
  );
  if (schemaMissing(error)) return false;
  if (error) throw new Error(`rack_sync_cursor_write_failed: ${error.message}`);
  return true;
}

export async function writeRackSyncFailure(cursor: number, reason: string) {
  const db = database();
  if (!db) return false;
  const now = new Date().toISOString();
  const { error } = await db.from("integration_sync_state").upsert(
    {
      integration_id: VISION_INTEGRATION_ID,
      last_cursor: Math.max(0, cursor),
      last_error: reason.slice(0, 160),
      updated_at: now,
    },
    { onConflict: "integration_id" },
  );
  if (schemaMissing(error)) return false;
  if (error) throw new Error(`rack_sync_failure_write_failed: ${error.message}`);
  return true;
}
