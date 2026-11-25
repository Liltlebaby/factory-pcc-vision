import type { Status } from "@/lib/types";

export const TELEMETRY_QUALITIES = ["good", "uncertain", "bad", "stale"] as const;
export const TELEMETRY_SOURCE_MODES = ["live", "demo"] as const;

export type TelemetryQuality = (typeof TELEMETRY_QUALITIES)[number];
export type TelemetrySourceMode = (typeof TELEMETRY_SOURCE_MODES)[number];

export type SensorTelemetry = {
  measurement_id: string;
  site_id: string;
  line_id: string;
  station_id: string;
  device_id: string;
  metric: string;
  value: number;
  unit: string;
  measured_at: string;
  received_at: string;
  quality: TelemetryQuality;
  source_mode: TelemetrySourceMode;
};

export type StationTelemetry = {
  station_id: string;
  data_status: "live" | "stale" | "demo" | "offline";
  generated_at: string;
  latest: Record<string, SensorTelemetry>;
  history: SensorTelemetry[];
  process_status: Status;
  rules: TelemetryRuleEvaluation[];
};

export type TelemetryRuleEvaluation = {
  station_id: string;
  site_id: string;
  line_id: string;
  rule_key: string;
  rule_code: string;
  source_measurement_id: string;
  metric: string;
  process_status: Status;
  severity: "WARNING" | "CRITICAL" | null;
  is_violation: boolean;
  title: string;
  message: string;
  owner: string;
  recommended_action: string;
  evaluated_at: string;
};

export type StationAlert = {
  alert_key: string;
  site_id: string;
  line_id: string;
  station_id: string;
  rule_key: string;
  rule_code: string;
  source_measurement_id: string | null;
  state: "OPEN" | "CLOSED";
  workflow_state: "OPEN" | "ACKNOWLEDGED" | "VERIFYING" | "CLOSED";
  process_status: Exclude<Status, "GREEN">;
  severity: "WARNING" | "CRITICAL";
  title: string;
  message: string;
  owner: string;
  recommended_action: string;
  opened_at: string;
  last_observed_at: string;
  closed_at: string | null;
  occurrence_count: number;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_note: string | null;
};

export type StationAlertFeed = {
  data_status: "live" | "offline";
  generated_at: string;
  alerts: StationAlert[];
};
