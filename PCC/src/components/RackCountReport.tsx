"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  EMPTY_RACK_REPORT,
  bangkokDateKey,
  dateShiftRackReport,
  hourlyRackReport,
  hourlyShiftRackReport,
  parseRackReport,
  recordRackCount,
  type RackReportState,
} from "@/lib/rack-report";
import type { RackStatus } from "@/lib/rack";

const STORAGE_KEY = "pcc.rack-count-report.v1";
const REFRESH_MS = 30_000;

type ReportSource = "browser" | "supabase";

type RackReportResponse = {
  configured: boolean;
  events: RackReportState["events"];
};

function timestampMs(value?: string) {
  if (!value) return Date.now();
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : Date.now();
}

function eventTimestampMs(value?: number) {
  if (!value || !Number.isFinite(value)) return undefined;
  return value < 1_000_000_000_000 ? value * 1000 : value;
}

export function RackCountReport({ status }: { status: RackStatus | null }) {
  const [report, setReport] = useState<RackReportState>(EMPTY_RACK_REPORT);
  const [now, setNow] = useState<number | null>(null);
  const [source, setSource] = useState<ReportSource>("browser");
  const [selectedDate, setSelectedDate] = useState("");
  const [openShift, setOpenShift] = useState<number | null>(null);
  const loaded = useRef(false);
  const reportRef = useRef<RackReportState>(EMPTY_RACK_REPORT);
  const sourceRef = useRef<ReportSource>("browser");

  useEffect(() => {
    const updateClock = () => setNow(Date.now());
    updateClock();
    const timer = window.setInterval(updateClock, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const stored = parseRackReport(window.localStorage.getItem(STORAGE_KEY));
    reportRef.current = stored;
    loaded.current = true;
    const frame = window.requestAnimationFrame(() => setReport(stored));
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadCentralReport = async () => {
      try {
        const response = await fetch("/api/rack/report", { cache: "no-store" });
        if (!response.ok) return;
        const data = (await response.json()) as RackReportResponse;
        if (cancelled || !data.configured) return;

        const central: RackReportState = {
          version: 1,
          lastCount: null,
          events: data.events,
        };
        reportRef.current = central;
        sourceRef.current = "supabase";
        setReport(central);
        setSource("supabase");
      } catch {
        // ใช้ข้อมูลสำรองในเบราว์เซอร์ต่อเมื่อฐานข้อมูลยังเข้าไม่ถึง
      }
    };

    void loadCentralReport();
    const timer = window.setInterval(loadCentralReport, REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [status?.lastEvent?.timestamp]);

  useEffect(() => {
    if (!status || !loaded.current || sourceRef.current === "supabase") return;

    const previous = reportRef.current;
    const observedAt = timestampMs(status.timestamp);
    const next = recordRackCount(
      previous,
      status.count,
      observedAt,
      eventTimestampMs(status.lastEvent?.timestamp),
    );

    reportRef.current = next;
    if (next !== previous) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    }
    const frame = window.requestAnimationFrame(() => setReport(next));
    return () => window.cancelAnimationFrame(frame);
  }, [status]);

  const hourly = useMemo(
    () => (now ? hourlyRackReport(report.events, now) : []),
    [now, report.events],
  );
  const today = now ? bangkokDateKey(now) : "";
  const reportDate = selectedDate || today;
  const shifts = useMemo(
    () => (now ? dateShiftRackReport(report.events, reportDate, now) : []),
    [now, report.events, reportDate],
  );
  const maxHourly = Math.max(1, ...hourly.map((bucket) => bucket.count));
  const currentHour = hourly.at(-1)?.count ?? 0;
  const dayTotal = shifts.reduce((sum, shift) => sum + shift.count, 0);
  const modalShift = shifts.find((shift) => shift.start === openShift);
  const modalHours = modalShift && now
    ? hourlyShiftRackReport(report.events, modalShift, now)
    : [];

  useEffect(() => {
    if (openShift === null) return;
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenShift(null);
    };
    document.addEventListener("keydown", onEscape);
    return () => document.removeEventListener("keydown", onEscape);
  }, [openShift]);

  return (
    <section className="mt-5 border-t border-slate-100 pt-4">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h3 className="text-xs font-bold tracking-wide text-slate-700 uppercase">
            รายงานการนับเก๊ะ
          </h3>
          <p className="mt-0.5 text-[10px] text-slate-400">
            สรุปจากยอดสะสม · เวลาโรงงาน UTC+7
          </p>
        </div>
        <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[10px] font-semibold text-slate-500">
          {source === "supabase"
            ? "ฐานข้อมูลกลาง · Supabase"
            : "สำรองในเบราว์เซอร์ · 7 วัน"}
        </span>
      </div>

      {now ? (
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.65fr)]">
          <div className="rounded-xl border border-slate-200/70 bg-slate-50/70 p-3 sm:p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[10px] font-semibold tracking-wide text-slate-500 uppercase">
                  รายชั่วโมง · 8 ชั่วโมงล่าสุด
                </p>
                <p className="mt-1 text-[10px] text-slate-400">
                  แท่งขวาสุดคือชั่วโมงปัจจุบัน
                </p>
              </div>
              <div className="text-right">
                <p className="text-2xl font-extrabold tabular-nums text-blue-700">
                  {currentHour}
                </p>
                <p className="text-[10px] text-slate-400">เก๊ะ / ชั่วโมงนี้</p>
              </div>
            </div>

            <div className="mt-4 grid h-28 grid-cols-8 items-end gap-1.5 sm:gap-2">
              {hourly.map((bucket, index) => {
                const height = Math.max(5, (bucket.count / maxHourly) * 72);
                const isCurrent = index === hourly.length - 1;
                return (
                  <div
                    key={bucket.start}
                    className="flex min-w-0 flex-col items-center justify-end gap-1"
                    title={`${bucket.label} นับได้ ${bucket.count} เก๊ะ`}
                  >
                    <span className="text-[9px] font-bold tabular-nums text-slate-600">
                      {bucket.count}
                    </span>
                    <div
                      className={`w-full max-w-9 rounded-t-md transition-[height] ${
                        isCurrent ? "bg-blue-600" : "bg-sky-300"
                      }`}
                      style={{ height }}
                    />
                    <span
                      className={`truncate text-[8px] tabular-nums sm:text-[9px] ${
                        isCurrent ? "font-bold text-blue-700" : "text-slate-400"
                      }`}
                    >
                      {bucket.label}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200/70 bg-slate-50/70 p-3 sm:p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[10px] font-semibold tracking-wide text-slate-500 uppercase">
                  รายกะ · เลือกวันที่
                </p>
                <p className="mt-1 text-[10px] text-slate-400">
                  กะดึกนับถึง 08:00 ของวันถัดไป
                </p>
              </div>
              <label className="text-[10px] font-semibold text-slate-500">
                วันที่
                <input
                  type="date"
                  aria-label="เลือกวันที่รายงานการนับเก๊ะรายกะ"
                  value={reportDate}
                  max={today}
                  min={now ? bangkokDateKey(now - 6 * 24 * 60 * 60 * 1000) : undefined}
                  onChange={(event) => {
                    setSelectedDate(event.target.value);
                    setOpenShift(null);
                  }}
                  className="mt-1 block max-w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs font-semibold text-slate-700 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                />
              </label>
            </div>

            <div className="mt-3 flex items-end justify-between rounded-lg bg-indigo-50 px-3 py-2">
              <span className="text-xs font-bold text-indigo-700">
                {shifts[0]?.dateLabel ?? reportDate}
              </span>
              <span className="text-right">
                <strong className="text-2xl font-extrabold tabular-nums text-indigo-700">{dayTotal}</strong>
                <span className="ml-1 text-[10px] text-indigo-500">เก๊ะ / 2 กะ</span>
              </span>
            </div>

            <div className="mt-3 space-y-2">
              {shifts.map((shift) => (
                <div
                  key={shift.start}
                  className={`flex items-center justify-between gap-3 rounded-lg border px-3 py-2 ${
                    shift.current
                      ? "border-indigo-200 bg-indigo-50/80"
                      : "border-slate-200 bg-white/80"
                  }`}
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <p className="text-xs font-bold text-slate-700">{shift.name}</p>
                      {shift.current && (
                        <span className="rounded-full bg-indigo-100 px-1.5 py-0.5 text-[8px] font-bold text-indigo-700">
                          ปัจจุบัน
                        </span>
                      )}
                    </div>
                    <p className="text-[9px] tabular-nums text-slate-400">
                      {shift.label}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <p className="text-lg font-extrabold tabular-nums text-slate-900">
                      {shift.count}
                      <span className="ml-1 text-[9px] font-medium text-slate-400">เก๊ะ</span>
                    </p>
                    <button
                      type="button"
                      aria-label={`ดูรายชั่วโมง${shift.name} วันที่ ${shift.dateLabel}`}
                      title={`ดูรายชั่วโมง${shift.name}`}
                      onClick={() => setOpenShift(shift.start)}
                      className="rounded-lg border border-indigo-200 bg-white p-1.5 text-indigo-600 transition hover:bg-indigo-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4" aria-hidden="true">
                        <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
                        <circle cx="12" cy="12" r="2.5" />
                      </svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
      )}

      <p className="mt-2 text-[10px] leading-relaxed text-slate-400">
        {source === "supabase"
          ? "ข้อมูลกลางจาก Camera 09 · ทุกเครื่องเห็นรายงานชุดเดียวกัน"
          : "ยังไม่ได้เชื่อมฐานข้อมูลกลาง รายงานจึงเริ่มเก็บเมื่อเปิดบนเบราว์เซอร์นี้ครั้งแรก"}
      </p>

      {modalShift && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/60 p-3 sm:p-6"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setOpenShift(null);
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="rack-shift-hourly-title"
            className="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
          >
            <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
              <div>
                <h3 id="rack-shift-hourly-title" className="text-base font-bold text-slate-900">
                  รายชั่วโมง · {modalShift.name}
                </h3>
                <p className="mt-1 text-xs text-slate-500">
                  {modalShift.dateLabel} · {modalShift.label} · เวลาไทย
                </p>
              </div>
              <button
                type="button"
                aria-label="ปิดรายงานรายชั่วโมง"
                onClick={() => setOpenShift(null)}
                className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="size-5" aria-hidden="true">
                  <path d="M5 5 19 19M19 5 5 19" />
                </svg>
              </button>
            </div>
            <div className="overflow-y-auto px-5 py-4">
              <div className="mb-3 rounded-xl bg-indigo-50 px-4 py-3 text-indigo-800">
                <span className="text-xs font-semibold">รวม {modalShift.name}</span>
                <strong className="float-right text-xl tabular-nums">{modalShift.count} เก๊ะ</strong>
              </div>
              <div className="space-y-1.5">
                {modalHours.map((hour) => {
                  const notStarted = now !== null && hour.start > now;
                  return (
                    <div key={hour.start} className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-sm">
                      <span className="tabular-nums text-slate-600">
                        {hour.label}
                        {bangkokDateKey(hour.start) !== reportDate && <span className="ml-1 text-[10px] text-slate-400">วันถัดไป</span>}
                      </span>
                      <span className={`font-bold tabular-nums ${notStarted ? "text-slate-400" : "text-indigo-700"}`}>
                        {notStarted ? "ยังไม่ถึงเวลา" : `${hour.count} เก๊ะ`}
                      </span>
                    </div>
                  );
                })}
              </div>
              <p className="mt-3 text-[10px] text-slate-400">
                นับจากเหตุการณ์ที่บันทึกได้เท่านั้น · ค่า 0 อาจหมายถึงกล้องออฟไลน์ ไม่ใช่ยืนยันว่าไม่มีเก๊ะ
              </p>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
