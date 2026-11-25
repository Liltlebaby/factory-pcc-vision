"use client";

import Link from "next/link";
import { FURNACE } from "@/lib/config";
import { fmtCountdown, fmtTime } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { Incident } from "@/lib/types";
import { IncidentActions } from "./IncidentActions";
import { Panel, RuleTag } from "./ui";

const STATUS_LABEL: Record<Incident["status"], string> = {
  OPEN: "เปิดใหม่ · รอรับทราบ",
  ACKNOWLEDGED: "รับทราบแล้ว · รออนุมัติ",
  IN_PROGRESS: "กำลังแก้ไข",
  VERIFYING: "รอตรวจผลหลังแก้",
  CLOSED: "ปิดแล้ว",
};

export function AlertPanel() {
  const { activeIncidents, now } = useStore();

  return (
    <Panel
      title="Active Alert"
      icon="🚨"
      action={
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-500">
          ค้าง {activeIncidents.length} รายการ
        </span>
      }
    >
      {activeIncidents.length === 0 ? (
        <div className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-5">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-emerald-500/15 text-lg">
            🟢
          </span>
          <div>
            <p className="text-sm font-bold text-emerald-700">
              ไม่มีการแจ้งเตือนค้าง
            </p>
            <p className="text-[11px] text-emerald-600/80">
              ทุกค่าอยู่ในเกณฑ์ ทั้งน้ำหนัก อุณหภูมิเตา และบ่อสุดท้าย
            </p>
          </div>
        </div>
      ) : (
        <ul className="space-y-3">
          {activeIncidents.map((incident) => {
            const overdue = incident.deadline < now;
            const critical = incident.severity === "CRITICAL";
            return (
              <li
                key={incident.id}
                className={`overflow-hidden rounded-xl border ${
                  critical
                    ? "border-red-200 bg-red-50/50"
                    : "border-amber-200 bg-amber-50/50"
                }`}
              >
                <div
                  className={`h-1 w-full ${critical ? "bg-red-500" : "bg-amber-400"}`}
                />
                <div className="p-3 sm:p-4">
                  <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
                    <p className="flex min-w-0 items-center gap-2 text-sm font-bold text-slate-900">
                      <span aria-hidden>{critical ? "🔴" : "🟡"}</span>
                      <span className="min-w-0">{incident.issue}</span>
                      <RuleTag code={incident.ruleCode} />
                    </p>
                    <span
                      className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold tabular-nums ring-1 ${
                        overdue
                          ? "bg-red-100 text-red-700 ring-red-200"
                          : "bg-white text-slate-700 ring-slate-200"
                      }`}
                    >
                      SLA {incident.slaMinutes} น. ·{" "}
                      {fmtCountdown(incident.deadline, now)}
                    </span>
                  </div>

                  <p className="mt-1.5 text-[11px] text-slate-500">
                    {FURNACE.name} ·{" "}
                    {incident.source === "WEIGHT"
                      ? "ตาชั่งหน้าเตา"
                      : incident.source === "POND"
                        ? "เซ็นเซอร์บ่อสุดท้าย"
                        : "Burner / Recorder"}{" "}
                    · ตรวจพบ {fmtTime(incident.detectedAt)}
                  </p>

                  <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
                    <div className="rounded-lg bg-white/80 px-2.5 py-1.5 ring-1 ring-slate-200/70">
                      <dt className="text-[10px] font-semibold tracking-wide text-slate-400 uppercase">
                        ผู้รับผิดชอบ
                      </dt>
                      <dd className="flex flex-wrap items-center gap-1.5 font-semibold text-slate-800">
                        {incident.owner}
                        {incident.escalated && (
                          <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[9px] font-bold text-amber-700">
                            ESCALATED
                          </span>
                        )}
                      </dd>
                    </div>
                    <div className="rounded-lg bg-white/80 px-2.5 py-1.5 ring-1 ring-slate-200/70">
                      <dt className="text-[10px] font-semibold tracking-wide text-slate-400 uppercase">
                        สถานะ
                      </dt>
                      <dd className="font-semibold text-slate-800">
                        {STATUS_LABEL[incident.status]}
                      </dd>
                    </div>
                    <div className="rounded-lg bg-white/80 px-2.5 py-1.5 ring-1 ring-slate-200/70 sm:col-span-2">
                      <dt className="text-[10px] font-semibold tracking-wide text-slate-400 uppercase">
                        งานที่ต้องทำ
                      </dt>
                      <dd className="text-slate-700">{incident.task}</dd>
                    </div>
                    <div className="rounded-lg bg-white/80 px-2.5 py-1.5 ring-1 ring-slate-200/70 sm:col-span-2">
                      <dt className="text-[10px] font-semibold tracking-wide text-slate-400 uppercase">
                        ค่าที่ตรวจพบ
                      </dt>
                      <dd className="font-mono text-[11px] break-words text-slate-600">
                        {incident.snapshot}
                      </dd>
                    </div>
                  </dl>

                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200/70 pt-3">
                    <IncidentActions incident={incident} />
                    <Link
                      href={`/incidents/${incident.id}`}
                      className="text-[11px] font-semibold text-blue-600 hover:underline"
                    >
                      รายละเอียด / Audit Log →
                    </Link>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
