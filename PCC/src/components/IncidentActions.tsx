"use client";

import { useStore } from "@/lib/store";
import type { Incident } from "@/lib/types";

const BUTTON =
  "rounded-lg px-3.5 py-2 text-xs font-bold transition active:scale-[0.97] disabled:opacity-40";

export function IncidentActions({ incident }: { incident: Incident }) {
  const { acknowledge, approve, resolve, escalate } = useStore();

  if (incident.status === "CLOSED") {
    return (
      <p className="rounded-lg bg-emerald-50 px-3 py-2 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200">
        ✓ ปิดงานแล้ว — ค่ากลับเข้าเกณฑ์และบันทึกใน Audit Log
      </p>
    );
  }

  if (incident.status === "VERIFYING") {
    return (
      <p className="rounded-lg bg-sky-50 px-3 py-2 text-[11px] font-semibold text-sky-700 ring-1 ring-sky-200">
        ⏳ รอระบบตรวจค่ารอบถัดไปอีก {incident.verifyRemaining} ครั้ง
        ก่อนปิด Incident อัตโนมัติ
      </p>
    );
  }

  return (
    <div className="flex flex-wrap gap-2">
      {incident.status === "OPEN" && (
        <button
          type="button"
          onClick={() => acknowledge(incident.id)}
          className={`${BUTTON} bg-blue-600 text-white shadow-sm shadow-blue-600/30 hover:bg-blue-700`}
        >
          รับทราบ
        </button>
      )}

      {incident.status === "ACKNOWLEDGED" && incident.requiresApproval && (
        <button
          type="button"
          onClick={() => approve(incident.id)}
          className={`${BUTTON} bg-violet-600 text-white shadow-sm shadow-violet-600/30 hover:bg-violet-700`}
        >
          อนุมัติแนวทาง
        </button>
      )}

      {incident.status === "IN_PROGRESS" && (
        <button
          type="button"
          onClick={() => resolve(incident.id)}
          className={`${BUTTON} bg-emerald-600 text-white shadow-sm shadow-emerald-600/30 hover:bg-emerald-700`}
        >
          แก้ไขแล้ว
        </button>
      )}

      {!incident.escalated && (
        <button
          type="button"
          onClick={() => escalate(incident.id)}
          className={`${BUTTON} border border-amber-300 bg-white text-amber-700 hover:bg-amber-50`}
        >
          Escalate
        </button>
      )}
    </div>
  );
}
