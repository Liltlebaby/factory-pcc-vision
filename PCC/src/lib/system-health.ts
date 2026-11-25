export type DependencyProbe = {
  ok: boolean;
  ready?: boolean;
  latency_ms: number;
  reason?: string;
};

export type SystemReadiness = {
  ready: boolean;
  status: "ready" | "degraded" | "not_ready";
  dependencies: {
    database: DependencyProbe;
    vision_monitor: DependencyProbe;
  };
};

export type EventSyncHealth = {
  data_status: "live" | "stale" | "offline";
  last_cursor: number | null;
  last_success_at: string | null;
  last_error: string | null;
  updated_at: string | null;
};

export type SystemStatusSnapshot = SystemReadiness & {
  service: "pcc";
  timestamp: string;
  deployment: string;
  policy: { vision_monitor_required: boolean };
  event_sync: EventSyncHealth;
};

export function deriveSystemReadiness(
  database: DependencyProbe,
  visionMonitor: DependencyProbe,
  requireVision: boolean,
): SystemReadiness {
  const databaseReady = database.ok;
  const visionReady = visionMonitor.ok && visionMonitor.ready !== false;
  const ready = databaseReady && (!requireVision || visionReady);
  const status = !ready
    ? "not_ready"
    : visionReady
      ? "ready"
      : "degraded";

  return {
    ready,
    status,
    dependencies: {
      database,
      vision_monitor: visionMonitor,
    },
  };
}
