"use client";

import { useRef, useState } from "react";
import { hasCapability, type PccRole } from "@/lib/access-control";
import type { IncidentAction } from "@/lib/incident-action-contract";
import type { StationAlert } from "@/lib/telemetry";

const WORKFLOW_LABEL: Record<StationAlert["workflow_state"], string> = {
  OPEN: "รอรับทราบ",
  ACKNOWLEDGED: "รับทราบแล้ว",
  VERIFYING: "รอตรวจค่ารอบถัดไป",
  CLOSED: "ปิดแล้ว",
};

const ERROR_TEXT: Record<string, string> = {
  authentication_required: "กรุณาเข้าสู่ระบบอีกครั้ง",
  forbidden: "บัญชีนี้ไม่มีสิทธิ์ดำเนินการ",
  incident_not_open: "เหตุการณ์นี้ถูกรับทราบไปแล้ว",
  incident_not_acknowledged: "ต้องรับทราบเหตุการณ์ก่อนบันทึกการแก้ไข",
  incident_already_closed: "เหตุการณ์นี้ถูกปิดแล้ว",
  incident_action_unavailable: "ฐานข้อมูล Incident ยังไม่พร้อมใช้งาน",
};

export function StationAlertActions({ alert, role }: { alert: StationAlert; role: PccRole | null }) {
  const [note, setNote] = useState(alert.resolution_note ?? "");
  const [pending, setPending] = useState<IncidentAction | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const requestKey = useRef<string | null>(null);
  const canAcknowledge = hasCapability(role, "incidents:acknowledge");
  const canResolve = hasCapability(role, "incidents:resolve");

  async function submit(action: IncidentAction) {
    const resolution = note.trim();
    if (action === "RESOLVE" && resolution.length < 3) {
      setMessage({ tone: "error", text: "กรุณาระบุสิ่งที่ดำเนินการอย่างน้อย 3 ตัวอักษร" });
      return;
    }
    setPending(action);
    setMessage(null);
    requestKey.current ??= crypto.randomUUID();
    try {
      const response = await fetch(
        `/api/v1/station-alerts/${encodeURIComponent(alert.alert_key)}/actions`,
        {
          method: "POST",
          cache: "no-store",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": requestKey.current,
          },
          body: JSON.stringify({ action, note: action === "RESOLVE" ? resolution : null }),
        },
      );
      const result = await response.json() as { error?: string };
      if (!response.ok) throw new Error(result.error ?? "incident_action_failed");
      requestKey.current = null;
      setMessage({
        tone: "success",
        text: action === "ACKNOWLEDGE" ? "บันทึกการรับทราบแล้ว" : "บันทึกการแก้ไขแล้ว ระบบกำลังตรวจค่ารอบถัดไป",
      });
      window.dispatchEvent(new Event("pcc:station-alerts-refresh"));
    } catch (error) {
      const code = error instanceof Error ? error.message : "incident_action_failed";
      setMessage({ tone: "error", text: ERROR_TEXT[code] ?? "ดำเนินการไม่สำเร็จ กรุณาลองใหม่" });
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="mt-3 border-t border-slate-100 pt-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-black tracking-wide text-slate-600">
          WORKFLOW · {WORKFLOW_LABEL[alert.workflow_state]}
        </span>
        {!role ? <span className="text-[10px] font-semibold text-slate-400">เข้าสู่ระบบเพื่อดำเนินการ</span> : null}
      </div>

      {alert.workflow_state === "OPEN" ? (
        <button
          type="button"
          disabled={!canAcknowledge || pending !== null}
          onClick={() => void submit("ACKNOWLEDGE")}
          className="mt-3 inline-flex h-9 items-center justify-center rounded-lg bg-blue-600 px-4 text-xs font-black text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {pending === "ACKNOWLEDGE" ? "กำลังบันทึก…" : "รับทราบเหตุการณ์"}
        </button>
      ) : null}

      {alert.workflow_state === "ACKNOWLEDGED" ? (
        <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
          <label className="text-[11px] font-bold text-slate-600">
            สิ่งที่ดำเนินการแก้ไข
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              disabled={!canResolve || pending !== null}
              maxLength={1000}
              rows={2}
              placeholder="เช่น เติมน้ำและตรวจวัด pH ซ้ำแล้ว"
              className="mt-1 min-h-16 w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-normal outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100 disabled:bg-slate-100"
            />
          </label>
          <button
            type="button"
            disabled={!canResolve || pending !== null}
            onClick={() => void submit("RESOLVE")}
            className="h-9 rounded-lg bg-emerald-600 px-4 text-xs font-black text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {pending === "RESOLVE" ? "กำลังบันทึก…" : "บันทึกว่าแก้ไขแล้ว"}
          </button>
        </div>
      ) : null}

      {alert.workflow_state === "VERIFYING" ? (
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] font-semibold text-amber-800">
          บันทึกการแก้ไขแล้ว · รอ Rule Engine ยืนยันว่าค่ากลับเข้าเกณฑ์ก่อนปิดเหตุอัตโนมัติ
        </p>
      ) : null}

      {message ? (
        <p
          role="status"
          className={`mt-2 text-[11px] font-bold ${message.tone === "success" ? "text-emerald-700" : "text-red-600"}`}
        >
          {message.text}
        </p>
      ) : null}
    </div>
  );
}
