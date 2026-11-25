import "server-only";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type { SensorTelemetry, StationAlert, StationAlertFeed, StationTelemetry } from "@/lib/telemetry";
import { buildStationAlertMutations } from "@/lib/telemetry-alerts";
import { evaluateStationTelemetry } from "@/lib/telemetry-rule-engine";
import type { IncidentAction } from "@/lib/incident-action-contract";
import type { PccRole } from "@/lib/access-control";
import { listChangedAuditFields, shortActorId, type PccAuditFeed } from "@/lib/audit-log";

let telemetryClient: SupabaseClient | null = null;

function database() {
  const url = process.env.SUPABASE_URL;
  const secret = process.env.SUPABASE_SECRET_KEY ?? process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !secret) return null;
  telemetryClient ??= createClient(url, secret, {
    auth: { autoRefreshToken: false, persistSession: false, detectSessionInUrl: false },
  });
  return telemetryClient;
}

export function telemetryDatabaseConfigured() {
  return database() !== null;
}

const MISSING_TABLE_CODES = ["42P01", "PGRST205"];
const MEMORY_HOURS = 24;
const MEMORY_MAX_ROWS = 20_000;

/**
 * ที่เก็บสำรองในหน่วยความจำ ใช้เมื่อยังไม่ได้ตั้ง Supabase หรือยังไม่ได้ apply migration
 * ค่าจากเซ็นเซอร์จริงจึงยังแสดงบน PCC ได้ แต่จะหายเมื่อ restart และไม่มีประวัติ alert
 * เก็บไว้บน globalThis เพื่อให้อยู่รอดตอน dev server โหลดโมดูลใหม่
 */
const memory = ((globalThis as { __pccTelemetryMemory?: { rows: SensorTelemetry[]; warned: boolean } }).__pccTelemetryMemory ??= { rows: [], warned: false });

function rememberTelemetry(items: SensorTelemetry[], reason: string) {
  if (!memory.warned) {
    console.warn(`Telemetry is kept in memory only (${reason}); apply the Supabase migrations to persist it`);
    memory.warned = true;
  }
  const known = new Set(memory.rows.map((row) => row.measurement_id));
  const cutoff = Date.now() - MEMORY_HOURS * 60 * 60 * 1000;
  memory.rows = [...memory.rows, ...items.filter((item) => !known.has(item.measurement_id))]
    .filter((row) => Date.parse(row.measured_at) >= cutoff)
    .sort((a, b) => Date.parse(b.measured_at) - Date.parse(a.measured_at))
    .slice(0, MEMORY_MAX_ROWS);
  return items.length;
}

function readMemoryStations(ids: string[], since: string, limitPerStation: number, generatedAt: Date, freshnessSeconds: number) {
  const sinceMs = Date.parse(since);
  return Object.fromEntries(ids.map((stationId) => [
    stationId,
    summarizeStation(
      stationId,
      memory.rows.filter((row) => row.station_id === stationId && Date.parse(row.measured_at) >= sinceMs).slice(0, limitPerStation),
      generatedAt,
      freshnessSeconds,
    ),
  ]));
}

export type DatabaseProbe = {
  ok: boolean;
  reason?: "not_configured" | "schema_unavailable" | "unreachable";
  code?: string;
};

/**
 * Verify the production-critical schema without reading business data.
 * Error messages are deliberately omitted so credentials and database details
 * never leak through the public readiness endpoint.
 */
export async function probePccDatabase(): Promise<DatabaseProbe> {
  const db = database();
  if (!db) return { ok: false, reason: "not_configured" };

  const checks = await Promise.all([
    db.from("sensor_telemetry").select("measurement_id", { head: true }).limit(1),
    db.from("station_alerts").select("alert_key", { head: true }).limit(1),
    db.from("rack_count_events").select("id", { head: true }).limit(1),
    db.from("integration_sync_state").select("integration_id", { head: true }).limit(1),
  ]);
  const failed = checks.find((result) => result.error)?.error;
  if (!failed) return { ok: true };

  const code = failed.code || undefined;
  const schemaUnavailable = ["42P01", "42703", "PGRST204", "PGRST205"].includes(code ?? "");
  return {
    ok: false,
    reason: schemaUnavailable ? "schema_unavailable" : "unreachable",
    ...(code ? { code } : {}),
  };
}

export async function persistSensorTelemetry(items: SensorTelemetry[]) {
  const db = database();
  if (!db) return rememberTelemetry(items, "database not configured");
  const rows = items.map((item) => ({ ...item, source_payload: item }));
  const { error } = await db.from("sensor_telemetry").upsert(rows, {
    onConflict: "measurement_id",
    ignoreDuplicates: true,
  });
  if (error && MISSING_TABLE_CODES.includes(error.code ?? "")) return rememberTelemetry(items, "sensor_telemetry table missing");
  if (error) throw new Error(`sensor_telemetry_insert_failed: ${error.message}`);
  return rows.length;
}

export async function readStationTelemetry(
  stationId: string,
  options: { hours?: number; limit?: number; freshnessSeconds?: number } = {},
): Promise<StationTelemetry> {
  const stations = await readStationsTelemetry([stationId], options);
  return stations[stationId];
}

function emptyStation(stationId: string, generatedAt: Date): StationTelemetry {
  return {
    station_id: stationId,
    data_status: "offline",
    generated_at: generatedAt.toISOString(),
    latest: {},
    history: [],
    process_status: "SENSOR_ERROR",
    rules: [],
  };
}

function summarizeStation(
  stationId: string,
  descending: SensorTelemetry[],
  generatedAt: Date,
  freshnessSeconds: number,
): StationTelemetry {
  const latest: Record<string, SensorTelemetry> = {};
  for (const item of descending) latest[item.metric] ??= item;
  const newest = descending[0];
  const ageMs = newest ? generatedAt.getTime() - Date.parse(newest.measured_at) : Number.POSITIVE_INFINITY;
  const stale = ageMs > freshnessSeconds * 1000 || newest?.quality === "stale" || newest?.quality === "bad";
  const dataStatus: StationTelemetry["data_status"] = !newest
    ? "offline"
    : newest.source_mode === "demo"
      ? "demo"
      : stale
        ? "stale"
        : "live";
  return evaluateStationTelemetry({
    station_id: stationId,
    data_status: dataStatus,
    generated_at: generatedAt.toISOString(),
    latest,
    history: [...descending].reverse(),
    process_status: "SENSOR_ERROR",
    rules: [],
  });
}

export async function readStationsTelemetry(
  stationIds: string[],
  options: { hours?: number; limit?: number; freshnessSeconds?: number } = {},
): Promise<Record<string, StationTelemetry>> {
  const generatedAt = new Date();
  const ids = [...new Set(stationIds)].slice(0, 20);
  const empty = Object.fromEntries(ids.map((id) => [id, emptyStation(id, generatedAt)]));
  if (ids.length === 0) return empty;
  const db = database();
  const requestedHours = Number.isFinite(options.hours) ? Number(options.hours) : 2;
  const requestedLimit = Number.isFinite(options.limit) ? Number(options.limit) : 500;
  const hours = Math.min(24, Math.max(1, requestedHours));
  const limitPerStation = Math.floor(Math.min(1000, Math.max(1, requestedLimit)));
  const since = new Date(generatedAt.getTime() - hours * 60 * 60 * 1000).toISOString();
  const freshnessSeconds = options.freshnessSeconds ?? 120;
  if (!db) return readMemoryStations(ids, since, limitPerStation, generatedAt, freshnessSeconds);
  const results = await Promise.all(ids.map(async (stationId) => {
    const { data, error } = await db
      .from("sensor_telemetry")
      .select("measurement_id,site_id,line_id,station_id,device_id,metric,value,unit,measured_at,received_at,quality,source_mode")
      .eq("station_id", stationId)
      .gte("measured_at", since)
      .order("measured_at", { ascending: false })
      .limit(limitPerStation);
    return { stationId, data: (data ?? []) as SensorTelemetry[], error };
  }));
  const missingTable = results.some(({ error }) => MISSING_TABLE_CODES.includes(error?.code ?? ""));
  if (missingTable) return readMemoryStations(ids, since, limitPerStation, generatedAt, freshnessSeconds);
  const failed = results.find(({ error }) => error);
  if (failed?.error) throw new Error(`sensor_telemetry_query_failed: ${failed.error.message}`);
  return Object.fromEntries(results.map(({ stationId, data }) => [
    stationId,
    summarizeStation(stationId, data, generatedAt, freshnessSeconds),
  ]));
}

export async function persistStationRuleEvaluations(stations: StationTelemetry[]) {
  const db = database();
  // ไม่มีฐานข้อมูล = ไม่มีที่บันทึก alert ค่าที่วัดยังประเมินเกณฑ์และแสดงบนหน้าจอได้ตามปกติ
  if (!db) return { observations: 0, alerts: 0 };
  const evaluations = stations
    .filter((station) => station.data_status === "live")
    .flatMap((station) => station.rules);
  if (evaluations.length === 0) return { observations: 0, alerts: 0 };

  const observationRows = evaluations.map((rule) => ({
    station_id: rule.station_id,
    rule_key: rule.rule_key,
    rule_code: rule.rule_code,
    source_measurement_id: rule.source_measurement_id,
    metric: rule.metric,
    process_status: rule.process_status,
    severity: rule.severity,
    is_violation: rule.is_violation,
    title: rule.title,
    message: rule.message,
    owner: rule.owner,
    recommended_action: rule.recommended_action,
    evaluated_at: rule.evaluated_at,
  }));
  const { error: observationError } = await db.from("station_rule_observations").upsert(observationRows, {
    onConflict: "source_measurement_id,rule_key",
    ignoreDuplicates: true,
  });
  if (observationError && MISSING_TABLE_CODES.includes(observationError.code ?? "")) return { observations: 0, alerts: 0 };
  if (observationError) throw new Error(`station_rule_observation_insert_failed: ${observationError.message}`);

  const alertKeys = evaluations.map((rule) => `${rule.station_id}:${rule.rule_key}`);
  const { data: existingRows, error: existingError } = await db
    .from("station_alerts")
    .select("alert_key,site_id,line_id,station_id,rule_key,rule_code,source_measurement_id,state,workflow_state,process_status,severity,title,message,owner,recommended_action,opened_at,last_observed_at,closed_at,occurrence_count,acknowledged_at,acknowledged_by,resolved_at,resolved_by,resolution_note")
    .in("alert_key", alertKeys);
  if (existingError) throw new Error(`station_alert_query_failed: ${existingError.message}`);
  const mutations = buildStationAlertMutations(
    evaluations,
    (existingRows ?? []) as StationAlert[],
    new Date().toISOString(),
  );
  const alertRows = mutations.alerts;
  const eventRows = mutations.events;

  if (alertRows.length > 0) {
    const { error } = await db.from("station_alerts").upsert(alertRows, { onConflict: "alert_key" });
    if (error) throw new Error(`station_alert_upsert_failed: ${error.message}`);
  }
  if (eventRows.length > 0) {
    const { error } = await db.from("station_alert_events").upsert(eventRows, {
      onConflict: "event_key",
      ignoreDuplicates: true,
    });
    if (error) throw new Error(`station_alert_event_insert_failed: ${error.message}`);
  }
  return { observations: observationRows.length, alerts: alertRows.length };
}

export async function readStationAlertFeed(
  options: { stationIds?: string[]; state?: "OPEN" | "CLOSED"; limit?: number } = {},
): Promise<StationAlertFeed> {
  const generatedAt = new Date().toISOString();
  const db = database();
  if (!db) return { data_status: "offline", generated_at: generatedAt, alerts: [] };
  const limit = Math.min(100, Math.max(1, options.limit ?? 30));
  let query = db
    .from("station_alerts")
    .select("alert_key,site_id,line_id,station_id,rule_key,rule_code,source_measurement_id,state,workflow_state,process_status,severity,title,message,owner,recommended_action,opened_at,last_observed_at,closed_at,occurrence_count,acknowledged_at,acknowledged_by,resolved_at,resolved_by,resolution_note")
    .eq("state", options.state ?? "OPEN")
    .order("last_observed_at", { ascending: false })
    .limit(limit);
  const stationIds = [...new Set(options.stationIds ?? [])].slice(0, 20);
  if (stationIds.length > 0) query = query.in("station_id", stationIds);
  const { data, error } = await query;
  if (error) {
    if (["42P01", "42703", "PGRST204", "PGRST205"].includes(error.code ?? "")) {
      return { data_status: "offline", generated_at: generatedAt, alerts: [] };
    }
    throw new Error(`station_alert_query_failed: ${error.message}`);
  }
  return { data_status: "live", generated_at: generatedAt, alerts: (data ?? []) as StationAlert[] };
}

export class IncidentActionDatabaseError extends Error {
  constructor(
    public readonly code: string | undefined,
    message: string,
  ) {
    super(message);
    this.name = "IncidentActionDatabaseError";
  }
}

export async function applyStationIncidentAction(input: {
  alertKey: string;
  action: IncidentAction;
  note: string | null;
  actorUserId: string;
  actorRole: Extract<PccRole, "admin" | "operator">;
  idempotencyKey: string;
  requestId: string;
}): Promise<StationAlert> {
  const db = database();
  if (!db) throw new IncidentActionDatabaseError(undefined, "telemetry_database_not_configured");
  const actionKey = `${input.alertKey}:${input.action}:${input.idempotencyKey}`;
  const auditKey = `audit:${actionKey}`;
  const { data, error } = await db.rpc("pcc_apply_incident_action", {
    p_alert_key: input.alertKey,
    p_action: input.action,
    p_note: input.note,
    p_actor_user_id: input.actorUserId,
    p_actor_role: input.actorRole,
    p_action_key: actionKey,
    p_audit_key: auditKey,
    p_request_id: input.requestId,
  });
  if (error) throw new IncidentActionDatabaseError(error.code, error.message);
  return data as StationAlert;
}

type AuditRow = {
  id: number;
  actor_user_id: string | null;
  actor_role: PccRole | "system" | null;
  action: string;
  entity_type: string;
  entity_id: string;
  before_state: unknown;
  after_state: unknown;
  request_id: string | null;
  occurred_at: string;
};

export async function readPccAuditFeed(options: { limit?: number } = {}): Promise<PccAuditFeed> {
  const generatedAt = new Date().toISOString();
  const db = database();
  if (!db) return { dataStatus: "offline", reason: "not_configured", generatedAt, records: [] };
  const limit = Math.min(500, Math.max(1, Math.floor(options.limit ?? 100)));
  const { data, error } = await db
    .from("pcc_audit_events")
    .select("id,actor_user_id,actor_role,action,entity_type,entity_id,before_state,after_state,request_id,occurred_at")
    .order("occurred_at", { ascending: false })
    .limit(limit);
  if (error) {
    const schemaUnavailable = ["42P01", "42703", "PGRST204", "PGRST205"].includes(error.code ?? "");
    console.error("Unable to read PCC audit feed", { code: error.code });
    return { dataStatus: "offline", reason: schemaUnavailable ? "schema_unavailable" : "unreachable", generatedAt, records: [] };
  }
  const rows = (data ?? []) as AuditRow[];
  const actorIds = [...new Set(rows.flatMap((row) => row.actor_user_id ? [row.actor_user_id] : []))];
  const names = new Map<string, string>();
  if (actorIds.length > 0) {
    const profiles = await db.from("pcc_user_profiles").select("user_id,display_name").in("user_id", actorIds);
    if (!profiles.error) for (const profile of profiles.data ?? []) names.set(profile.user_id as string, profile.display_name as string);
  }
  return {
    dataStatus: "live",
    generatedAt,
    records: rows.map((row) => ({
      id: row.id,
      action: row.action,
      entityType: row.entity_type,
      entityId: row.entity_id,
      actorId: row.actor_user_id,
      actorName: row.actor_user_id ? (names.get(row.actor_user_id) ?? shortActorId(row.actor_user_id)) : shortActorId(null),
      actorRole: row.actor_role,
      requestId: row.request_id,
      occurredAt: row.occurred_at,
      changedFields: listChangedAuditFields(row.before_state, row.after_state),
    })),
  };
}
