"use client";

import { useCallback, useEffect, useState } from "react";
import type { RackDailyReport } from "@/lib/rack";
import { FactoryIcon } from "./FactoryIcon";

/**
 * ยอดนับเก๊ะรายชั่วโมงและรายกะ
 *
 * อ่านจาก /api/rack/daily ซึ่งส่งต่อไปยัง Vision Monitor ที่สรุปมาจากเหตุการณ์
 * ที่บันทึกไว้จริง จงใจไม่สะสมยอดฝั่งเบราว์เซอร์เหมือนของเดิม เพราะวิธีนั้นนับได้
 * เฉพาะตอนมีคนเปิดหน้าจอค้างไว้ ปิดแท็บข้ามคืนแล้วยอดกะดึกจะหายไปทั้งกะ
 * และแต่ละเครื่องจะได้ตัวเลขไม่ตรงกัน
 *
 * วันรายงานคือ 07:00 ถึง 08:00 ของวันถัดไป แบ่งเป็น
 * กะเช้า 07:00–18:00 · นอกกะ 18:00–20:00 · กะดึก 20:00–08:00
 * ช่วง 18:00–20:00 ไม่ได้อยู่ในกะไหนตามที่โรงงานกำหนด จึงแสดงแยกแทนการซ่อน
 */

const TONE: Record<string, { bar: string; edge: string; chip: string }> = {
  day: { bar: "bg-blue-500", edge: "bg-blue-500", chip: "text-blue-700" },
  outside: { bar: "bg-amber-400", edge: "bg-amber-400", chip: "text-amber-700" },
  night: { bar: "bg-violet-500", edge: "bg-violet-500", chip: "text-violet-700" },
};

function addDays(key: string, days: number) {
  const [year, month, day] = key.split("-").map(Number);
  const moment = new Date(Date.UTC(year, month - 1, day));
  moment.setUTCDate(moment.getUTCDate() + days);
  return moment.toISOString().slice(0, 10);
}

function thaiDate(key: string) {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("th-TH", {
    weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  });
}

export function RackHourlyReport() {
  const [report, setReport] = useState<RackDailyReport | null>(null);
  const [today, setToday] = useState<string | null>(null);
  const [date, setDate] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (key: string | null) => {
    setLoading(true);
    try {
      const response = await fetch(`/api/rack/daily${key ? `?date=${key}` : ""}`, { cache: "no-store" });
      if (!response.ok) throw new Error(response.status === 503 ? "ติดต่อ Vision Monitor ไม่ได้" : `HTTP ${response.status}`);
      const value = (await response.json()) as RackDailyReport;
      setReport(value);
      setDate(value.date);
      setToday((current) => current ?? value.date);
      setError(null);
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "โหลดยอดนับไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // เริ่มโหลดใน task ถัดไปเพื่อไม่ให้ effect สร้าง cascading render แบบ synchronous
    const timer = window.setTimeout(() => void load(null), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  // วันปัจจุบันเดินไปเรื่อย ๆ จึงรีเฟรชเองทุกนาที ส่วนวันย้อนหลังไม่เปลี่ยนแล้ว
  useEffect(() => {
    if (!date || !today || date !== today) return;
    const timer = window.setInterval(() => load(date), 60_000);
    return () => window.clearInterval(timer);
  }, [date, today, load]);

  const peak = Math.max(1, ...(report?.hours ?? []).map((hour) => hour.count));
  const atToday = Boolean(date && today && date >= today);

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-col gap-3 border-b border-slate-100 px-4 py-4 sm:flex-row sm:items-start sm:justify-between sm:px-5">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-sm font-black text-slate-900">
            <FactoryIcon name="activity" className="size-4 text-blue-600" />ยอดนับเก๊ะรายชั่วโมง
          </h2>
          <p className="mt-1 text-[11px] text-slate-400">
            {date ? thaiDate(date) : "กำลังโหลด"} · วันรายงาน 07:00 ถึง 08:00 วันถัดไป
          </p>
        </div>
        <div className="grid w-full grid-cols-[2.5rem_minmax(0,1fr)_2.5rem_auto] items-center gap-1.5 sm:flex sm:w-auto">
          <button type="button" onClick={() => date && load(addDays(date, -1))} aria-label="วันก่อนหน้า"
            className="grid size-10 place-items-center rounded-lg border border-slate-200 text-lg text-slate-500 transition hover:border-blue-300 hover:text-blue-700">‹</button>
          <input type="date" value={date ?? ""} max={today ?? undefined} aria-label="เลือกวันที่"
            onChange={(event) => event.target.value && load(event.target.value)}
            className="h-10 min-w-0 w-full rounded-lg border border-slate-200 px-2 text-xs text-slate-700 outline-none focus:border-blue-500 sm:w-auto" />
          <button type="button" disabled={atToday} onClick={() => date && load(addDays(date, 1))} aria-label="วันถัดไป"
            className="grid size-10 place-items-center rounded-lg border border-slate-200 text-lg text-slate-500 transition hover:border-blue-300 hover:text-blue-700 disabled:opacity-40 disabled:hover:border-slate-200 disabled:hover:text-slate-500">›</button>
          <button type="button" disabled={atToday} onClick={() => load(today)}
            className="h-10 rounded-lg border border-slate-200 px-2 text-xs font-bold text-slate-600 transition hover:border-blue-300 hover:text-blue-700 disabled:opacity-40 sm:px-3">วันนี้</button>
        </div>
      </div>

      <div className={`p-4 transition-opacity sm:p-5 ${loading ? "opacity-60" : ""}`}>
        {error && (
          <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-700">{error}</p>
        )}
        {report?.storage === "unavailable" && (
          <p className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800">
            Vision Monitor ยังไม่มีที่เก็บเหตุการณ์ ตัวเลขด้านล่างจึงเป็นศูนย์ทั้งหมด
          </p>
        )}

        <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
          {(report?.shifts ?? []).map((shift) => (
            <div key={shift.key}
              className={`relative min-w-0 overflow-hidden rounded-xl border p-3 sm:p-4 ${shift.current ? "border-blue-300 bg-blue-50/60" : "border-slate-200 bg-slate-50"}`}>
              <span className={`absolute inset-y-0 left-0 w-1 ${TONE[shift.key]?.edge ?? "bg-slate-300"}`} />
              <div className="flex flex-wrap items-center justify-between gap-1">
                <span className="text-xs font-bold text-slate-500">{shift.name}</span>
                {shift.current && <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[9px] font-black text-blue-700">กำลังดำเนินอยู่</span>}
              </div>
              <p className="mt-1.5 text-2xl font-black tabular-nums text-slate-950 sm:text-3xl">{shift.count.toLocaleString("th-TH")}</p>
              <p className="mt-1.5 flex flex-wrap justify-between gap-1 text-[10px] text-slate-500"><span>{shift.label}</span><span>{shift.hours} ชม.</span></p>
            </div>
          ))}
          <div className="relative min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-50 p-3 sm:p-4">
            <span className="absolute inset-y-0 left-0 w-1 bg-slate-800" />
            <span className="text-xs font-bold text-slate-500">รวมทั้งวันรายงาน</span>
            <p className="mt-1.5 text-2xl font-black tabular-nums text-slate-950 sm:text-3xl">{(report?.total ?? 0).toLocaleString("th-TH")}</p>
            <p className="mt-1.5 flex flex-wrap justify-between gap-1 text-[10px] text-slate-500"><span>07:00 – 08:00</span><span>25 ชม.</span></p>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-xs font-black text-slate-700">รายชั่วโมง</h3>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-slate-500">
            <span className="flex items-center gap-1"><i className="size-2 rounded-sm bg-blue-500" />กะเช้า</span>
            <span className="flex items-center gap-1"><i className="size-2 rounded-sm bg-amber-400" />นอกกะ</span>
            <span className="flex items-center gap-1"><i className="size-2 rounded-sm bg-violet-500" />กะดึก</span>
            <span className="flex items-center gap-1"><i className="size-2 rounded-sm bg-slate-200" />ยังไม่ถึงเวลา</span>
          </div>
        </div>

        <ol aria-label="ยอดนับเก๊ะรายชั่วโมง" className="mt-3 max-h-72 space-y-1.5 overflow-y-auto pr-1 sm:hidden">
          {(report?.hours ?? []).map((hour) => {
            const group = hour.next_day || hour.hour >= 20 ? "night" : hour.hour >= 18 ? "outside" : "day";
            return <li key={`${hour.label}-${hour.start}`} className="flex min-h-11 items-center justify-between gap-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
              <span className="flex min-w-0 items-center gap-2 text-xs font-semibold text-slate-700"><i aria-hidden="true" className={`size-2.5 shrink-0 rounded-sm ${hour.pending ? "bg-slate-200" : TONE[group].bar}`} />{hour.label}{hour.next_day ? " · วันถัดไป" : ""}</span>
              <strong className={`shrink-0 text-sm tabular-nums ${hour.pending ? "font-medium text-slate-400" : "font-black text-slate-950"}`}>{hour.pending ? "รอเวลา" : `${hour.count.toLocaleString("th-TH")} เก๊ะ`}</strong>
            </li>;
          })}
          {!report && !error && <li className="py-6 text-center text-xs text-slate-500">กำลังโหลดยอดนับ…</li>}
        </ol>
        <div className="mt-3 hidden h-40 items-end gap-1 overflow-x-auto pb-1 sm:flex">
          {(report?.hours ?? []).map((hour) => {
            const group = hour.next_day || hour.hour >= 20 ? "night" : hour.hour >= 18 ? "outside" : "day";
            return (
              <div key={`${hour.label}-${hour.start}`} className="flex h-full min-w-[26px] flex-1 flex-col items-center justify-end gap-1"
                title={hour.pending ? `${hour.label} ยังไม่ถึงเวลา` : `${hour.label}${hour.next_day ? " (วันถัดไป)" : ""} นับได้ ${hour.count} เก๊ะ`}>
                <span className="min-h-3 text-[10px] font-bold tabular-nums text-slate-500">{hour.pending ? "" : hour.count}</span>
                <span
                  className={`w-full rounded-t ${hour.pending ? "bg-slate-200" : TONE[group].bar}`}
                  style={{ height: hour.pending ? 4 : `${Math.max(4, (hour.count / peak) * 100)}%` }}
                />
                <span className={`text-[9px] whitespace-nowrap ${hour.pending ? "text-slate-300" : "text-slate-400"}`}>{hour.label}</span>
              </div>
            );
          })}
          {!report && !error && <p className="w-full self-center text-center text-xs text-slate-400">กำลังโหลดยอดนับ…</p>}
        </div>
      </div>
    </section>
  );
}
