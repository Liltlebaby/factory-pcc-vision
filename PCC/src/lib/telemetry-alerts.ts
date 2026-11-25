import type { StationAlert, TelemetryRuleEvaluation } from "@/lib/telemetry";

export type StationAlertRow = StationAlert & { updated_at: string };

export type StationAlertEventRow = {
  event_key: string;
  alert_key: string;
  source_measurement_id: string;
  transition: "OPEN" | "OBSERVED" | "CLOSED";
  rule_code: string;
  process_status: TelemetryRuleEvaluation["process_status"];
  message: string;
  occurred_at: string;
  details: Record<string, string>;
};

export function buildStationAlertMutations(
  evaluations: TelemetryRuleEvaluation[],
  existingAlerts: StationAlert[],
  updatedAt: string,
) {
  const existing = new Map(existingAlerts.map((alert) => [alert.alert_key, alert]));
  const alerts: StationAlertRow[] = [];
  const events: StationAlertEventRow[] = [];

  for (const rule of evaluations) {
    const alertKey = `${rule.station_id}:${rule.rule_key}`;
    const current = existing.get(alertKey);
    if (rule.is_violation && rule.severity && rule.process_status !== "GREEN") {
      const transition = current?.state === "OPEN" ? "OBSERVED" : "OPEN";
      const continuing = current?.state === "OPEN";
      alerts.push({
        alert_key: alertKey,
        site_id: rule.site_id,
        line_id: rule.line_id,
        station_id: rule.station_id,
        rule_key: rule.rule_key,
        rule_code: rule.rule_code,
        source_measurement_id: rule.source_measurement_id,
        state: "OPEN",
        workflow_state: continuing ? current.workflow_state : "OPEN",
        process_status: rule.process_status,
        severity: rule.severity,
        title: rule.title,
        message: rule.message,
        owner: rule.owner,
        recommended_action: rule.recommended_action,
        opened_at: current?.state === "OPEN" ? current.opened_at : rule.evaluated_at,
        last_observed_at: rule.evaluated_at,
        closed_at: null,
        occurrence_count: current ? current.occurrence_count + (current.state === "CLOSED" ? 1 : 0) : 1,
        acknowledged_at: continuing ? current.acknowledged_at : null,
        acknowledged_by: continuing ? current.acknowledged_by : null,
        resolved_at: continuing ? current.resolved_at : null,
        resolved_by: continuing ? current.resolved_by : null,
        resolution_note: continuing ? current.resolution_note : null,
        updated_at: updatedAt,
      });
      events.push({
        event_key: `${rule.source_measurement_id}:${rule.rule_key}`,
        alert_key: alertKey,
        source_measurement_id: rule.source_measurement_id,
        transition,
        rule_code: rule.rule_code,
        process_status: rule.process_status,
        message: rule.message,
        occurred_at: rule.evaluated_at,
        details: { owner: rule.owner, recommended_action: rule.recommended_action },
      });
    } else if (current?.state === "OPEN") {
      alerts.push({
        ...current,
        source_measurement_id: rule.source_measurement_id,
        state: "CLOSED",
        workflow_state: "CLOSED",
        last_observed_at: rule.evaluated_at,
        closed_at: rule.evaluated_at,
        updated_at: updatedAt,
      });
      events.push({
        event_key: `${rule.source_measurement_id}:${rule.rule_key}`,
        alert_key: alertKey,
        source_measurement_id: rule.source_measurement_id,
        transition: "CLOSED",
        rule_code: rule.rule_code,
        process_status: rule.process_status,
        message: rule.message,
        occurred_at: rule.evaluated_at,
        details: { previous_rule_code: current.rule_code },
      });
    }
  }

  return { alerts, events };
}
