import type { PccRole } from "@/lib/access-control";

export type AuditDataStatus = "live" | "offline";
export type AuditOfflineReason = "not_configured" | "schema_unavailable" | "unreachable";

export type PccAuditRecord = {
  id: number;
  action: string;
  entityType: string;
  entityId: string;
  actorId: string | null;
  actorName: string;
  actorRole: PccRole | "system" | null;
  requestId: string | null;
  occurredAt: string;
  changedFields: string[];
};

export type PccAuditFeed = {
  dataStatus: AuditDataStatus;
  reason?: AuditOfflineReason;
  generatedAt: string;
  records: PccAuditRecord[];
};

const IGNORED_CHANGE_FIELDS = new Set(["updated_at"]);

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export function listChangedAuditFields(beforeState: unknown, afterState: unknown) {
  const before = objectRecord(beforeState);
  const after = objectRecord(afterState);
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  return [...keys]
    .filter((key) => !IGNORED_CHANGE_FIELDS.has(key))
    .filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]))
    .sort()
    .slice(0, 12);
}

export function shortActorId(actorId: string | null) {
  if (!actorId) return "ระบบอัตโนมัติ";
  return `ผู้ใช้ ${actorId.slice(0, 8)}`;
}

export function auditActionLabel(action: string) {
  const labels: Record<string, string> = {
    "incident.acknowledge": "รับทราบเหตุการณ์",
    "incident.resolve": "ส่งตรวจสอบหลังแก้ไข",
    "incident.note": "เพิ่มบันทึกเหตุการณ์",
    "incident.reopen": "เปิดเหตุการณ์อีกครั้ง",
  };
  return labels[action] ?? action.replaceAll(".", " · ");
}

export function auditEntityLabel(entityType: string) {
  const labels: Record<string, string> = {
    station_alert: "เหตุการณ์สถานี",
    user: "บัญชีผู้ใช้",
    device: "อุปกรณ์",
    system: "ระบบ",
  };
  return labels[entityType] ?? entityType.replaceAll("_", " ");
}
