"use client";

import Link from "next/link";
import { FURNACE } from "@/lib/config";
import { fmtCountdown, fmtDateTime, fmtTime } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { Incident } from "@/lib/types";
import { IncidentActions } from "./IncidentActions";
import { Panel, RuleTag } from "./ui";

const STEPS: { key: Incident["status"] | "APPROVAL"; label: string }[] = [
  { key: "OPEN", label: "ตรวจพบ / แจ้งเตือน" },
  { key: "ACKNOWLEDGED", label: "รับทราบ" },
  { key: "APPROVAL", label: "อนุมัติ" },
  { key: "IN_PROGRESS", label: "ดำเนินการแก้ไข" },
  { key: "VERIFYING", label: "ตรวจผลหลังแก้" },
  { key: "CLOSED", label: "ปิดงาน" },
];

function stepIndex(incident: Incident) {
  switch (incident.status) {
    case "OPEN":
      return 0;
    case "ACKNOWLEDGED":
      return 1;
    case "IN_PROGRESS":
      return 3;
    case "VERIFYING":
      return 4;
    case "CLOSED":
      return 5;
  }
}

function sourceLabel(source: Incident["source"]) {
  if (source === "WEIGHT") return "⚖️ ตาชั่งหน้าเตา";
  if (source === "POND") return "🌊 เซ็นเซอร์บ่อสุดท้าย";
  return "🌡️ Burner / Recorder";
}

export function IncidentDetail({ id }: { id: string }) {
  const { incidents, now, hydrated } = useStore();
  const incident = incidents.find((i) => i.id === id);

  if (!hydrated) {
    return (
      <Panel title="กำลังโหลด" icon="⏳">
        <p className="text-sm text-slate-400">กำลังกู้คืนข้อมูลจำลอง…</p>
      </Panel>
    );
  }

  if (!incident) {
    return (
      <Panel title="ไม่พบ Incident" icon="❓">
        <p className="text-sm text-slate-500">
          ไม่พบ Incident <span className="font-mono">{id}</span> — ข้อมูล
          Prototype จะหายเมื่อปิดแท็บ หรือเมื่อกด “ล้างข้อมูล”
        </p>
        <Link
          href="/incidents"
          className="mt-3 inline-block text-xs font-semibold text-blue-600 hover:underline"
        >
          ← กลับไปหน้ารายการ Incident
        </Link>
      </Panel>
    );
  }

  const current = stepIndex(incident);
  const approvalDone = Boolean(incident.approvedAt);
  const critical = incident.severity === "CRITICAL";
  const overdue = incident.status !== "CLOSED" && incident.deadline < now;

  return (
    <div className="space-y-3 sm:space-y-4">
      <Panel bodyClassName="p-0">
        <div
          className={`h-1.5 w-full rounded-t-2xl ${
            incident.status === "CLOSED"
              ? "bg-emerald-500"
              : critical
                ? "bg-red-500"
                : "bg-amber-400"
          }`}
        />
        <div className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
            <div className="min-w-0">
              <p className="font-mono text-[11px] font-semibold text-slate-400">
                {incident.id}
              </p>
              <h2 className="mt-1 flex flex-wrap items-center gap-2 text-base font-extrabold text-slate-900 sm:text-lg">
                <span aria-hidden>{critical ? "🔴" : "🟡"}</span>
                {incident.issue}
                <RuleTag code={incident.ruleCode} />
              </h2>
              <p className="mt-1 text-[11px] text-slate-500">
                {FURNACE.name} · {FURNACE.workOrderId} · ตรวจพบ{" "}
                {fmtDateTime(incident.detectedAt)}
              </p>
            </div>

            <div
              className={`shrink-0 rounded-xl px-3 py-2 text-right ring-1 ${
                incident.status === "CLOSED"
                  ? "bg-emerald-50 ring-emerald-200"
                  : overdue
                    ? "bg-red-50 ring-red-200"
                    : "bg-slate-50 ring-slate-200"
              }`}
            >
              <p className="text-[10px] font-semibold tracking-wide text-slate-500 uppercase">
                SLA {incident.slaMinutes} นาที
              </p>
              <p
                className={`text-sm font-bold tabular-nums ${
                  incident.status === "CLOSED"
                    ? "text-emerald-700"
                    : overdue
                      ? "text-red-700"
                      : "text-slate-800"
                }`}
              >
                {incident.status === "CLOSED"
                  ? `ปิดเมื่อ ${fmtTime(incident.closedAt ?? now)}`
                  : fmtCountdown(incident.deadline, now)}
              </p>
            </div>
          </div>

          {/* Workflow timeline */}
          <ol className="no-scrollbar -mx-1 mt-4 flex gap-2 overflow-x-auto px-1 pb-1">
            {STEPS.map((step, index) => {
              const skipped =
                step.key === "APPROVAL" && !incident.requiresApproval;
              const done =
                step.key === "APPROVAL"
                  ? approvalDone
                  : index < current || incident.status === "CLOSED";
              const isCurrent =
                !skipped &&
                (step.key === "APPROVAL"
                  ? incident.status === "ACKNOWLEDGED" && !approvalDone
                  : index === current);
              return (
                <li
                  key={step.key}
                  className={`shrink-0 rounded-full border px-3 py-1.5 text-[11px] font-bold whitespace-nowrap ${
                    skipped
                      ? "border-slate-200 bg-slate-50 text-slate-300 line-through"
                      : isCurrent
                        ? "border-blue-600 bg-blue-600 text-white shadow-sm shadow-blue-600/30"
                        : done
                          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                          : "border-slate-200 bg-white text-slate-400"
                  }`}
                >
                  {done && !isCurrent ? "✓ " : `${index + 1}. `}
                  {step.label}
                </li>
              );
            })}
          </ol>

          <div className="mt-4 grid gap-2.5 text-xs sm:grid-cols-2 xl:grid-cols-4">
            <Field label="Source">
              {sourceLabel(incident.source)}
            </Field>
            <Field label="ผู้รับผิดชอบ">
              {incident.owner}
              {incident.escalated && (
                <span className="ml-1.5 rounded-full bg-amber-100 px-1.5 py-0.5 text-[9px] font-bold text-amber-700">
                  ESCALATED
                </span>
              )}
            </Field>
            <Field label="ค่าที่ตรวจพบ" mono>
              {incident.snapshot}
            </Field>
            <Field label="ผู้อนุมัติ">
              {incident.requiresApproval
                ? approvalDone
                  ? `${incident.approvedBy} · ${fmtTime(incident.approvedAt ?? 0)}`
                  : "รออนุมัติ"
                : "ไม่ต้องอนุมัติ"}
            </Field>
          </div>

          <div className="mt-3.5 flex flex-wrap gap-2">
            <Impact on={incident.impactQuality} label="กระทบคุณภาพ" />
            <Impact on={incident.impactSmell} label="กระทบกลิ่น" />
            <Impact on={incident.impactFail} label="เสี่ยงของเสีย" />
          </div>

          <div className="mt-4 border-t border-slate-100 pt-4">
            <IncidentActions incident={incident} />
          </div>
        </div>
      </Panel>

      <div className="grid gap-3 sm:gap-4 lg:grid-cols-2">
        <Panel title="AI Recommendation" icon="🤖">
          <p className="mb-3 rounded-xl border border-slate-100 bg-slate-50/70 px-3 py-2 text-xs">
            <span className="font-semibold text-slate-400">
              งานที่มอบหมาย:{" "}
            </span>
            <span className="text-slate-700">{incident.task}</span>
          </p>
          <ol className="space-y-2">
            {incident.aiSuggestion.map((suggestion, index) => (
              <li
                key={suggestion}
                className="flex gap-2.5 rounded-xl border border-violet-100 bg-gradient-to-br from-violet-50/80 to-blue-50/60 px-3 py-2.5 text-xs leading-relaxed"
              >
                <span className="grid size-5 shrink-0 place-items-center rounded-full bg-violet-600 text-[10px] font-bold text-white">
                  {index + 1}
                </span>
                <span className="text-slate-700">{suggestion}</span>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-[10px] text-slate-400">
            AI เสนอทางเลือก ผู้รับผิดชอบเป็นผู้อนุมัติและตัดสินใจ
          </p>
        </Panel>

        <Panel title="Audit Log" icon="🧾">
          <ol className="space-y-3.5">
            {incident.auditLog.map((entry, index) => (
              <li key={`${entry.at}-${index}`} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <span className="mt-1 size-2.5 shrink-0 rounded-full bg-blue-500 ring-4 ring-blue-100" />
                  {index < incident.auditLog.length - 1 && (
                    <span className="mt-1 w-px flex-1 bg-slate-200" />
                  )}
                </div>
                <div className="min-w-0 pb-0.5">
                  <p className="text-xs font-bold text-slate-800">
                    {entry.action}
                  </p>
                  <p className="text-[11px] tabular-nums text-slate-400">
                    {fmtTime(entry.at)} · {entry.actor}
                  </p>
                  {entry.detail && (
                    <p className="mt-0.5 text-[11px] leading-relaxed text-slate-600">
                      {entry.detail}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </Panel>
      </div>

      <Link
        href="/incidents"
        className="inline-block text-xs font-semibold text-blue-600 hover:underline"
      >
        ← กลับไปหน้ารายการ Incident
      </Link>
    </div>
  );
}

function Field({
  label,
  children,
  mono = false,
}: {
  label: string;
  children: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="rounded-xl border border-slate-200/70 bg-slate-50/80 px-3 py-2">
      <p className="text-[10px] font-semibold tracking-wide text-slate-400 uppercase">
        {label}
      </p>
      <p
        className={`mt-0.5 break-words text-slate-800 ${mono ? "font-mono text-[11px]" : "font-medium"}`}
      >
        {children}
      </p>
    </div>
  );
}

function Impact({ on, label }: { on: boolean; label: string }) {
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-[11px] font-bold ${
        on
          ? "border-red-200 bg-red-50 text-red-700"
          : "border-slate-200 bg-slate-50 text-slate-400"
      }`}
    >
      {on ? "●" : "○"} {label}
    </span>
  );
}
