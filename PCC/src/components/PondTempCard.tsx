"use client";

import { useState } from "react";
import { POND_PH_SPEC, POND_SPEC, STATUS_META } from "@/lib/config";
import { useStore } from "@/lib/store";
import { Sparkline } from "./Sparkline";
import { Panel, StatusBadge } from "./ui";

export function PondTempCard() {
  const { latestPond, pondSeries } = useStore();
  const [showPhGuide, setShowPhGuide] = useState(false);

  if (!latestPond) {
    return (
      <Panel title="Function 03 · บ่อสุดท้าย" icon="🌊">
        <p className="py-6 text-center text-sm text-slate-400">
          รอข้อมูลจากเซ็นเซอร์บ่อสุดท้าย…
        </p>
      </Panel>
    );
  }

  const meta = STATUS_META[latestPond.status];
  const margin = POND_SPEC.max - latestPond.value;
  const values = pondSeries.map((sample) => sample.value);
  const phValues = pondSeries
    .map((sample) => sample.ph)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const isOver = latestPond.value > POND_SPEC.max;
  const nearLimit = !isOver && margin <= POND_SPEC.warningMargin;
  const ph = latestPond.ph;
  const phState = ph === undefined || !Number.isFinite(ph)
    ? "UNKNOWN"
    : ph < POND_PH_SPEC.min
      ? "LOW"
      : ph > POND_PH_SPEC.max
        ? "HIGH"
        : "OK";
  const phOutOfRange = phState === "LOW" || phState === "HIGH";
  // ช่วงแสดงผลของหลอดเน้นบริเวณใช้งานจริง เพื่อให้การเปลี่ยนแปลงมองเห็นได้ชัด
  const thermometerMin = 28;
  const thermometerMax = 40;
  const thermometerLevel = Math.min(
    Math.max(
      ((latestPond.value - thermometerMin) /
        (thermometerMax - thermometerMin)) *
        100,
      6,
    ),
    94,
  );
  const limitLevel =
    ((POND_SPEC.max - thermometerMin) /
      (thermometerMax - thermometerMin)) *
    100;

  return (
    <Panel
      title="Function 03 · บ่อสุดท้าย"
      icon="🌊"
      action={<StatusBadge status={phOutOfRange ? "RED" : latestPond.status} />}
    >
      <div className="grid h-36 grid-cols-[minmax(0,1fr)_112px] items-stretch gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold tracking-wide text-slate-400 uppercase">
            อุณหภูมิน้ำ
          </p>
          <p
            className={`mt-0.5 text-[2.35rem] leading-none font-extrabold tracking-tight tabular-nums ${meta.text}`}
          >
            {latestPond.value.toFixed(1)}
            <span className="ml-1 text-base font-semibold text-slate-400">
              {POND_SPEC.unit}
            </span>
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] font-semibold">
            <span className="text-slate-500">เกณฑ์ ≤ {POND_SPEC.max}°C</span>
            <span className={isOver ? "text-red-600" : nearLimit ? "text-amber-600" : "text-emerald-600"}>
              {isOver
                ? `เกิน ${Math.abs(margin).toFixed(1)}°C`
                : `ต่ำกว่า ${margin.toFixed(1)}°C`}
            </span>
          </div>
        </div>

        <div
          className={`relative h-36 w-28 overflow-hidden rounded-[1.75rem] border-4 bg-slate-50 shadow-inner ${
            isOver ? "border-red-200" : nearLimit ? "border-amber-200" : "border-cyan-200"
          }`}
          role="img"
          aria-label={`ภาพบ่อน้ำสุดท้าย อุณหภูมิ ${latestPond.value.toFixed(1)} องศาเซลเซียส`}
        >
          <div className="absolute inset-x-0 bottom-0 h-[64%] bg-gradient-to-b from-cyan-300 via-sky-400 to-blue-600">
            <div className="pond-wave absolute -top-2 -left-5 h-5 w-48 rounded-[50%] bg-cyan-200/90" />
            <span className="absolute top-6 left-4 size-2 rounded-full bg-white/45" />
            <span className="absolute top-11 right-7 size-3 rounded-full border-2 border-white/45" />
            <span className="absolute right-12 bottom-5 size-1.5 rounded-full bg-white/40" />
          </div>
          <div className="absolute top-3 right-3 h-[72%] w-8 rounded-full bg-white/85 shadow-md ring-1 ring-slate-200/80">
            <span className="absolute top-2 left-1/2 h-[calc(100%-1rem)] w-2 -translate-x-1/2 overflow-hidden rounded-full bg-slate-200 shadow-inner">
              <span
                className="absolute inset-x-0 bottom-0 rounded-full transition-[height,background-color] duration-700 ease-out"
                style={{
                  height: `${thermometerLevel}%`,
                  backgroundColor: meta.hex,
                }}
              />
            </span>
            <span
              className="absolute right-full mr-1 h-px w-2 bg-red-400"
              style={{ bottom: `${limitLevel}%` }}
              title={`ขีดจำกัด ${POND_SPEC.max}°C`}
            />
            <span
              className="absolute right-full mr-3 -translate-y-1/2 text-[8px] font-bold text-red-600"
              style={{ bottom: `${limitLevel}%` }}
            >
              35°
            </span>
            <span
              className="absolute -bottom-1.5 left-1/2 size-5 -translate-x-1/2 rounded-full border-2 border-white shadow-sm transition-colors duration-500"
              style={{ backgroundColor: meta.hex }}
            />
            <span className="sr-only">
              ระดับปรอท {thermometerLevel.toFixed(0)} เปอร์เซ็นต์ของช่วง 28 ถึง
              40 องศาเซลเซียส
            </span>
          </div>
          <div className="absolute inset-x-0 bottom-2 text-center text-[10px] font-bold tracking-wide text-white/90">
            {POND_SPEC.name}
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-cyan-100 bg-cyan-50/50 p-2">
        <Sparkline
          values={values}
          min={Math.min(29, ...values) - 0.3}
          max={Math.max(37, ...values) + 0.3}
          color={isOver ? "#dc2626" : nearLimit ? "#d97706" : "#0284c7"}
          bands={[
            { value: POND_SPEC.max, color: "#ef4444" },
            {
              value: POND_SPEC.max - POND_SPEC.warningMargin,
              color: "#f59e0b",
              dashed: true,
            },
          ]}
        />
      </div>
      <div className="mt-2 flex items-center justify-between text-[10px] text-slate-400">
        <span>แนวโน้มอุณหภูมิบ่อแบบ real-time</span>
        <span className="font-semibold text-red-500">เส้นแดง = 35°C</span>
      </div>
      <button
        type="button"
        onClick={() => setShowPhGuide(true)}
        aria-label="ดูเกณฑ์ pH และแนวทางปฏิบัติ"
        className={`mt-5 block w-full rounded-2xl border px-4 py-3 text-left shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 ${
          phOutOfRange
            ? "border-red-200 bg-red-50 hover:bg-red-100"
            : "border-violet-100 bg-gradient-to-r from-violet-50 via-white to-cyan-50 hover:from-violet-100"
        }`}
      >
        <span className="flex items-center gap-3">
          <span className={`flex size-11 shrink-0 items-center justify-center rounded-xl ${phOutOfRange ? "bg-red-100 text-red-600" : "bg-violet-100 text-violet-600"}`}>
            <svg viewBox="0 0 32 32" fill="none" className="size-7" aria-hidden="true">
              <path d="M16 3C12.5 8.5 6 15.3 6 21a10 10 0 0 0 20 0c0-5.7-6.5-12.5-10-18Z" fill="currentColor" fillOpacity=".16" stroke="currentColor" strokeWidth="1.8" />
              <path d="M10.5 23.5c1.1 1.8 3 2.9 5.5 2.9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              <circle cx="20" cy="15" r="1.3" fill="currentColor" />
              <circle cx="23" cy="19" r=".9" fill="currentColor" />
            </svg>
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[11px] font-bold tracking-wide text-slate-700 uppercase">ค่า pH ในน้ำบ่อสุดท้าย</span>
            <span className="mt-0.5 block text-[10px] text-slate-500">เกณฑ์ {POND_PH_SPEC.min}–{POND_PH_SPEC.max} · ข้อมูลจำลอง · กดดูแนวทาง</span>
          </span>
          <span className="shrink-0 text-right">
            <span className={`block text-3xl leading-none font-extrabold tabular-nums ${phOutOfRange ? "text-red-700" : "text-violet-700"}`}>
              {phState === "UNKNOWN" ? "—" : ph?.toFixed(2)}
            </span>
            <span className={`mt-1 block text-[10px] font-bold ${phOutOfRange ? "text-red-600" : phState === "OK" ? "text-emerald-600" : "text-slate-400"}`}>
              {phState === "LOW" ? "ต่ำกว่าเกณฑ์" : phState === "HIGH" ? "สูงกว่าเกณฑ์" : phState === "OK" ? "ปกติ" : "ไม่มีค่า"}
            </span>
          </span>
        </span>
        <span className="mt-3 block rounded-xl border border-violet-100/80 bg-white/75 px-2 py-1.5">
          {phValues.length > 0 ? (
            <Sparkline
              values={phValues}
              min={Math.min(9.7, ...phValues) - 0.1}
              max={Math.max(11.3, ...phValues) + 0.1}
              height={42}
              color={phOutOfRange ? "#dc2626" : "#7c3aed"}
              bands={[
                { value: POND_PH_SPEC.min, color: "#f59e0b", dashed: true },
                { value: POND_PH_SPEC.max, color: "#f59e0b", dashed: true },
              ]}
            />
          ) : (
            <span className="block py-3 text-center text-[10px] text-slate-400">ยังไม่มีข้อมูลแนวโน้ม pH</span>
          )}
        </span>
        <span className="mt-1.5 flex justify-between text-[9px] text-slate-500">
          <span>แนวโน้ม pH · อัปเดตตามรอบจำลอง</span>
          <span>เส้นประ = เกณฑ์ 10 / 11</span>
        </span>
      </button>
      {showPhGuide && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/60 p-3 sm:p-6"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShowPhGuide(false);
          }}
        >
          <div role="dialog" aria-modal="true" aria-labelledby="pond-ph-guide-title" className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl sm:p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 id="pond-ph-guide-title" className="text-lg font-bold text-slate-900">แนวทางควบคุม pH น้ำบ่อสุดท้าย</h3>
                <p className="mt-1 text-sm text-slate-500">เกณฑ์ {POND_PH_SPEC.min}–{POND_PH_SPEC.max} · ค่าปัจจุบัน {phState === "UNKNOWN" ? "ไม่มีข้อมูล" : ph?.toFixed(2)}</p>
              </div>
              <button type="button" onClick={() => setShowPhGuide(false)} aria-label="ปิดแนวทางควบคุม pH" className="rounded-lg px-2 py-1 text-xl text-slate-500 hover:bg-slate-100">×</button>
            </div>
            <div className="mt-5 space-y-3 text-sm">
              <div className={`rounded-xl border p-3 ${phState === "LOW" ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-slate-50"}`}>
                <p className="font-bold text-slate-800">pH &lt; {POND_PH_SPEC.min} · ต่ำกว่าเกณฑ์</p>
                <p className="mt-1 text-slate-600">แจ้งผู้รับผิดชอบเติมปูนขาวเพื่อปรับ pH ตามขั้นตอนหน้างาน แล้ววัดซ้ำ</p>
              </div>
              <div className={`rounded-xl border p-3 ${phState === "HIGH" ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-slate-50"}`}>
                <p className="font-bold text-slate-800">pH &gt; {POND_PH_SPEC.max} · สูงกว่าเกณฑ์</p>
                <p className="mt-1 text-slate-600">แจ้งผู้รับผิดชอบเติมน้ำเพื่อเจือจางด้วยการ Overflow ตามขั้นตอนหน้างาน และวัด pH ซ้ำสม่ำเสมอ</p>
              </div>
              <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-3">
                <p className="font-bold text-cyan-900">รายการตรวจสอบหน้างาน</p>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-cyan-900">
                  <li>ตรวจปั๊มน้ำไหลกลับที่บ่อเหล็ก (AJ1) ให้ไหลตลอดเวลา</li>
                  <li>ตรวจ pH ของปูนขาวขณะรับเข้าให้ผ่านมาตรฐานที่หน้างานกำหนด</li>
                </ul>
              </div>
            </div>
            <p className="mt-4 text-xs text-slate-500">ค่า pH บนหน้าจอนี้ยังเป็นข้อมูลจำลอง รายการตรวจสอบข้างต้นต้องยืนยันโดยผู้ปฏิบัติงาน ไม่ใช่ผลจากเซ็นเซอร์</p>
          </div>
        </div>
      )}
    </Panel>
  );
}
