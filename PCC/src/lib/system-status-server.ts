import "server-only";

import { RACK_API, rackHeaders } from "@/lib/rack";
import { readRackSyncState } from "@/lib/rack-database";
import { probePccDatabase } from "@/lib/telemetry-database";
import {
  deriveSystemReadiness,
  type DependencyProbe,
  type EventSyncHealth,
  type SystemStatusSnapshot,
} from "@/lib/system-health";

async function measure<T>(task: () => Promise<T>) {
  const start = performance.now();
  try {
    return { value: await task(), latency_ms: Math.round(performance.now() - start) };
  } catch {
    return { value: null, latency_ms: Math.round(performance.now() - start) };
  }
}

async function probeVisionMonitor(): Promise<DependencyProbe> {
  const measured = await measure(async () => {
    const response = await fetch(`${RACK_API}/health`, {
      headers: rackHeaders(),
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    if (!response.ok) return null;
    return (await response.json()) as { alive?: boolean; ready?: boolean };
  });
  if (!measured.value?.alive) {
    return { ok: false, ready: false, latency_ms: measured.latency_ms, reason: "unreachable" };
  }
  return {
    ok: true,
    ready: measured.value.ready === true,
    latency_ms: measured.latency_ms,
    ...(measured.value.ready === true ? {} : { reason: "camera_not_ready" }),
  };
}

function summarizeSync(
  row: Awaited<ReturnType<typeof readRackSyncState>>,
  now: Date,
): EventSyncHealth {
  if (!row) {
    return {
      data_status: "offline",
      last_cursor: null,
      last_success_at: null,
      last_error: null,
      updated_at: null,
    };
  }
  const updated = Date.parse(row.updated_at);
  const stale = !Number.isFinite(updated) || now.getTime() - updated > 60_000;
  return {
    data_status: row.last_error ? "offline" : stale ? "stale" : "live",
    last_cursor: Number(row.last_cursor),
    last_success_at: row.last_success_at,
    last_error: row.last_error,
    updated_at: row.updated_at,
  };
}

export async function readSystemStatus(): Promise<SystemStatusSnapshot> {
  const now = new Date();
  const [databaseResult, visionMonitor, syncResult] = await Promise.all([
    measure(probePccDatabase),
    probeVisionMonitor(),
    measure(readRackSyncState),
  ]);
  const database: DependencyProbe = databaseResult.value
    ? {
        ok: databaseResult.value.ok,
        latency_ms: databaseResult.latency_ms,
        ...(databaseResult.value.reason ? { reason: databaseResult.value.reason } : {}),
      }
    : { ok: false, latency_ms: databaseResult.latency_ms, reason: "unreachable" };
  const requireVision = process.env.PCC_REQUIRE_VISION_READY === "true";
  const readiness = deriveSystemReadiness(database, visionMonitor, requireVision);

  return {
    service: "pcc",
    ...readiness,
    policy: { vision_monitor_required: requireVision },
    event_sync: summarizeSync(syncResult.value, now),
    timestamp: now.toISOString(),
    deployment: process.env.DEPLOYMENT_VERSION ?? "local",
  };
}
