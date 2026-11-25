"use client";

import Link from "next/link";
import { fmtCountdown, fmtTime } from "@/lib/format";
import { useStore } from "@/lib/store";
import { useStationAlerts } from "@/lib/use-station-alerts";
import type { StationAlertFeed } from "@/lib/telemetry";
import type { Incident } from "@/lib/types";
import type { PccRole } from "@/lib/access-control";
import { Panel, RuleTag } from "./ui";
import { StationAlertActions } from "./StationAlertActions";

const STATUS_STYLE: Record<Incident["status"], string> = {
  OPEN: "bg-red-50 text-red-700 ring-red-200",
  ACKNOWLEDGED: "bg-blue-50 text-blue-700 ring-blue-200",
  IN_PROGRESS: "bg-violet-50 text-violet-700 ring-violet-200",
  VERIFYING: "bg-amber-50 text-amber-700 ring-amber-200",
  CLOSED: "bg-emerald-50 text-emerald-700 ring-emerald-200",
};

const STATUS_TEXT: Record<Incident["status"], string> = {
  OPEN: "รอรับทราบ",
  ACKNOWLEDGED: "รออนุมัติ",
  IN_PROGRESS: "กำลังแก้ไข",
  VERIFYING: "รอตรวจผล",
  CLOSED: "ปิดแล้ว",
};

function impactText(incident: Incident) {
  return (
    [
      incident.impactQuality && "คุณภาพ",
      incident.impactSmell && "กลิ่น",
      incident.impactFail && "ของเสีย",
    ]
      .filter(Boolean)
      .join(" / ") || "—"
  );
}

function StatusPill({ status }: { status: Incident["status"] }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[11px] font-bold ring-1 ${STATUS_STYLE[status]}`}
    >
      {STATUS_TEXT[status]}
    </span>
  );
}

function sourceLabel(source: Incident["source"], compact = false) {
  if (source === "WEIGHT") return compact ? "⚖️ Weight" : "⚖️";
  if (source === "POND") return compact ? "🌊 Final Pond" : "🌊";
  return compact ? "🌡️ Temp" : "🌡️";
}

export function IncidentList({
  initialStationAlerts,
  currentRole,
}: {
  initialStationAlerts: StationAlertFeed;
  currentRole: PccRole | null;
}) {
  const { incidents, now, hydrated } = useStore();
  const stationAlerts = useStationAlerts(initialStationAlerts);

  if (stationAlerts.data_status === "live") {
    return (
      <Panel
        title="Alert จาก Rule Engine ฝั่งเซิร์ฟเวอร์"
        icon="🛡️"
        action={<span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-bold text-emerald-700 ring-1 ring-emerald-200">LIVE · {stationAlerts.alerts.length} รายการ</span>}
        bodyClassName="p-3 sm:p-5"
      >
        {stationAlerts.alerts.length === 0 ? (
          <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 px-4 py-8 text-center">
            <p className="text-sm font-bold text-emerald-800">ไม่มี Alert จากเซ็นเซอร์ที่ยังเปิดอยู่</p>
            <p className="mt-1 text-xs text-emerald-600">Rule Engine ประเมินผลบนเซิร์ฟเวอร์และตรวจซ้ำทุกครั้งที่ Gateway ส่งข้อมูล</p>
          </div>
        ) : (
          <ul className="space-y-3">
            {stationAlerts.alerts.map((alert) => (
              <li key={alert.alert_key} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`size-2.5 rounded-full ${alert.severity === "CRITICAL" ? "bg-red-500" : "bg-amber-500"}`} />
                      <h3 className="font-extrabold text-slate-900">{alert.title}</h3>
                      <RuleTag code={alert.rule_code} />
                    </div>
                    <p className="mt-2 text-sm text-slate-700">{alert.message}</p>
                    <p className="mt-2 text-xs leading-relaxed text-blue-700"><strong>แนวทาง:</strong> {alert.recommended_action}</p>
                  </div>
                  <div className="shrink-0 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-500 sm:text-right">
                    <p><strong className="text-slate-700">ผู้รับผิดชอบ:</strong> {alert.owner}</p>
                    <p className="mt-1">พบล่าสุด {fmtTime(Date.parse(alert.last_observed_at))}</p>
                    <p className="mt-1">เกิดซ้ำ {alert.occurrence_count} รอบ</p>
                  </div>
                </div>
                <StationAlertActions alert={alert} role={currentRole} />
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-[10px] leading-relaxed text-slate-500">การรับทราบและบันทึกการแก้ไขต้องใช้บัญชี Operator หรือ Admin ทุกคำสั่งมี Idempotency Key และถูกบันทึกใน Audit Log ฝั่งเซิร์ฟเวอร์</p>
      </Panel>
    );
  }

  return (
    <Panel
      title="Incident — Single Source of Truth"
      icon="🗂️"
      action={
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-500">
          ข้อมูลจำลอง · รอ migration/ฐานข้อมูล
        </span>
      }
      bodyClassName="p-3 sm:p-5"
    >
      {incidents.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-400">
          {hydrated
            ? "ยังไม่มี Incident — ลองเลือกโหมดจำลองที่หน้า Control Center"
            : "กำลังกู้คืนข้อมูลจำลอง…"}
        </p>
      ) : (
        <>
          {/* มือถือ: การ์ดอ่านง่ายแทนตาราง */}
          <ul className="space-y-2.5 lg:hidden">
            {incidents.map((incident) => (
              <li
                key={incident.id}
                className="rounded-xl border border-slate-200 bg-white p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="font-mono text-[11px] font-semibold text-slate-400">
                    {incident.id}
                  </span>
                  <StatusPill status={incident.status} />
                </div>
                <p className="mt-1 flex items-center gap-1.5 text-sm font-bold text-slate-900">
                  <span aria-hidden>
                    {sourceLabel(incident.source)}
                  </span>
                  {incident.issue}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
                  <RuleTag code={incident.ruleCode} />
                  <span>👤 {incident.owner}</span>
                  <span
                    className={
                      incident.status !== "CLOSED" && incident.deadline < now
                        ? "font-bold text-red-600"
                        : ""
                    }
                  >
                    ⏱{" "}
                    {incident.status === "CLOSED"
                      ? `SLA ${incident.slaMinutes} นาที`
                      : fmtCountdown(incident.deadline, now)}
                  </span>
                </div>
                <div className="mt-2.5 flex items-center justify-between gap-2 border-t border-slate-100 pt-2.5">
                  <span className="text-[11px] text-slate-400">
                    ผลกระทบ: {impactText(incident)}
                  </span>
                  <Link
                    href={`/incidents/${incident.id}`}
                    className="text-[11px] font-bold text-blue-600 hover:underline"
                  >
                    เปิด →
                  </Link>
                </div>
              </li>
            ))}
          </ul>

          {/* จอใหญ่: ตารางเต็ม */}
          <div className="hidden lg:block">
            <table className="w-full text-left text-xs">
              <thead className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
                <tr className="border-b border-slate-200">
                  <th className="py-2.5 pr-3">ID</th>
                  <th className="py-2.5 pr-3">Source</th>
                  <th className="py-2.5 pr-3">Issue</th>
                  <th className="py-2.5 pr-3">Rule</th>
                  <th className="py-2.5 pr-3">Owner</th>
                  <th className="py-2.5 pr-3">SLA</th>
                  <th className="py-2.5 pr-3">Status</th>
                  <th className="py-2.5 pr-3">Impact</th>
                  <th className="py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {incidents.map((incident) => (
                  <tr key={incident.id} className="transition hover:bg-blue-50/40">
                    <td className="py-2.5 pr-3 font-mono text-slate-400">
                      {incident.id}
                    </td>
                    <td className="py-2.5 pr-3 whitespace-nowrap text-slate-600">
                      {sourceLabel(incident.source, true)}
                    </td>
                    <td className="py-2.5 pr-3 font-medium text-slate-800">
                      {incident.issue}
                    </td>
                    <td className="py-2.5 pr-3">
                      <RuleTag code={incident.ruleCode} />
                    </td>
                    <td className="py-2.5 pr-3 whitespace-nowrap text-slate-600">
                      {incident.owner}
                    </td>
                    <td className="py-2.5 pr-3 whitespace-nowrap tabular-nums">
                      {incident.status === "CLOSED" ? (
                        <span className="text-slate-400">
                          {incident.slaMinutes} นาที
                        </span>
                      ) : (
                        <span
                          className={
                            incident.deadline < now
                              ? "font-bold text-red-600"
                              : "text-slate-600"
                          }
                        >
                          {fmtCountdown(incident.deadline, now)}
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 pr-3">
                      <StatusPill status={incident.status} />
                    </td>
                    <td className="py-2.5 pr-3 text-slate-500">
                      {impactText(incident)}
                    </td>
                    <td className="py-2.5">
                      <Link
                        href={`/incidents/${incident.id}`}
                        className="font-semibold text-blue-600 hover:underline"
                      >
                        เปิด
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="mt-3 text-[10px] leading-relaxed text-slate-400">
            ตรวจพบล่าสุด {fmtTime(incidents[0].detectedAt)} ·
            ทุกแถวย้อนกลับได้ว่า เกิดอะไรขึ้น → ใครได้รับแจ้ง → ใครรับผิดชอบ →
            แก้อะไร → ผลเป็นอย่างไร → ใครอนุมัติ
          </p>
        </>
      )}
    </Panel>
  );
}
