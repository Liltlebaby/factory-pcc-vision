"use client";

import { useState } from "react";
import Link from "next/link";
import { FactoryIcon, type FactoryIconName } from "./FactoryIcon";
import type { DependencyProbe, SystemStatusSnapshot } from "@/lib/system-health";

type Tone = "good" | "warning" | "danger" | "muted";

const TONE: Record<Tone, { dot: string; text: string; soft: string }> = {
  good: { dot: "bg-emerald-500", text: "text-emerald-700", soft: "bg-emerald-50" },
  warning: { dot: "bg-amber-500", text: "text-amber-700", soft: "bg-amber-50" },
  danger: { dot: "bg-red-500", text: "text-red-700", soft: "bg-red-50" },
  muted: { dot: "bg-slate-400", text: "text-slate-500", soft: "bg-slate-100" },
};

function statusTime(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return new Intl.DateTimeFormat("th-TH", {
    timeZone: "Asia/Bangkok",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function relativeStatusTime(value: string) {
  const age = Math.max(0, Date.now() - Date.parse(value));
  if (age < 15_000) return "เมื่อสักครู่";
  if (age < 60_000) return `${Math.floor(age / 1000)} วินาทีที่แล้ว`;
  return statusTime(value);
}

function dependencyState(probe: DependencyProbe, camera = false) {
  if (!probe.ok) {
    if (probe.reason === "not_configured" || probe.reason === "schema_unavailable") {
      return { label: "ยังไม่ได้ตั้งค่า", tone: "danger" as Tone };
    }
    return { label: "ติดต่อไม่ได้", tone: "danger" as Tone };
  }
  if (probe.ready === false) {
    return { label: camera ? "ไม่มีสัญญาณ" : "ยังไม่พร้อม", tone: "warning" as Tone };
  }
  return { label: "พร้อมใช้งาน", tone: "good" as Tone };
}

function syncState(status: SystemStatusSnapshot) {
  if (status.event_sync.data_status === "live") return { label: "ทำงานปกติ", tone: "good" as Tone };
  if (status.event_sync.data_status === "stale") return { label: "ข้อมูลล่าช้า", tone: "warning" as Tone };
  return {
    label: status.event_sync.last_error ? "ซิงก์ไม่สำเร็จ" : "รอระบบต้นทาง",
    tone: status.event_sync.last_error ? "danger" as Tone : "warning" as Tone,
  };
}

function StateText({ label, tone }: { label: string; tone: Tone }) {
  const style = TONE[tone];
  return <span className={`inline-flex items-center gap-2 text-xs font-extrabold ${style.text}`}><span className={`size-2 rounded-full ${style.dot}`} />{label}</span>;
}

function TopologyNode({
  icon,
  title,
  subtitle,
  label,
  tone,
}: {
  icon: FactoryIconName;
  title: string;
  subtitle: string;
  label: string;
  tone: Tone;
}) {
  return (
    <div className="relative z-10 min-w-0 rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-[0_10px_25px_-22px_rgba(15,23,42,0.7)]">
      <div className="flex items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-700"><FactoryIcon name={icon} className="size-5" /></span>
        <div className="min-w-0 flex-1"><strong className="block text-sm leading-tight text-slate-950">{title}</strong><span className="mt-0.5 block text-[10px] text-slate-400">{subtitle}</span></div>
        <span className="shrink-0 xl:hidden"><StateText label={label} tone={tone} /></span>
      </div>
      <span className="mt-3 hidden xl:block"><StateText label={label} tone={tone} /></span>
    </div>
  );
}

function ServiceRow({ icon, name, process, state, latency, checked }: {
  icon: FactoryIconName;
  name: string;
  process: string;
  state: { label: string; tone: Tone };
  latency: number | null;
  checked: string;
}) {
  return (
    <div className="border-t border-slate-100 px-5 py-3.5 text-xs">
      <div className="flex items-center gap-3 md:hidden"><span className="grid size-9 shrink-0 place-items-center rounded-lg bg-blue-50 text-blue-700"><FactoryIcon name={icon} className="size-4" /></span><div className="min-w-0 flex-1"><strong className="block text-slate-900">{name}</strong><code className="text-[10px] text-slate-500">process: {process}</code></div><div className="shrink-0 text-right"><StateText {...state} /><p className="mt-1 tabular-nums text-[10px] text-slate-400">{latency === null ? "—" : `${latency} ms`} · {checked}</p></div></div>
      <div className="hidden gap-3 md:grid md:grid-cols-[1.35fr_0.8fr_0.85fr_0.55fr_0.85fr] md:items-center"><div className="flex items-center gap-3"><span className="grid size-8 place-items-center rounded-lg bg-blue-50 text-blue-700"><FactoryIcon name={icon} className="size-4" /></span><strong className="text-slate-900">{name}</strong></div><code className="w-fit text-[10px] text-slate-500">{process}</code><StateText {...state} /><span className="tabular-nums text-slate-500">{latency === null ? "—" : `${latency} ms`}</span><span className="text-slate-500">{checked}</span></div>
    </div>
  );
}

export function SystemOperations({ initialStatus }: { initialStatus: SystemStatusSnapshot }) {
  const [status, setStatus] = useState(initialStatus);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState(false);

  const databaseState = dependencyState(status.dependencies.database);
  const visionState = dependencyState(status.dependencies.vision_monitor);
  const cameraState = dependencyState(status.dependencies.vision_monitor, true);
  const eventSyncState = syncState(status);
  const overall = status.status === "ready"
    ? { label: "พร้อมใช้งานจริง", tone: "good" as Tone }
    : status.status === "degraded"
      ? { label: "ทำงานแบบจำกัด", tone: "warning" as Tone }
      : { label: "ยังไม่พร้อมใช้งานจริง", tone: "danger" as Tone };

  async function refreshStatus() {
    setRefreshing(true);
    setRefreshError(false);
    try {
      const response = await fetch("/api/ready", { cache: "no-store" });
      const next = (await response.json()) as SystemStatusSnapshot;
      if (!next?.timestamp) throw new Error("invalid_status");
      setStatus(next);
    } catch {
      setRefreshError(true);
    } finally {
      setRefreshing(false);
    }
  }

  const checked = relativeStatusTime(status.timestamp);
  const operations = [
    { icon: "system" as const, name: "PCC Web", process: "pcc-web", state: { label: "พร้อมใช้งาน", tone: "good" as Tone }, latency: null },
    { icon: "database" as const, name: "Supabase Database", process: "supabase", state: databaseState, latency: status.dependencies.database.latency_ms },
    { icon: "system" as const, name: "Vision Monitor API", process: "vision-api", state: visionState, latency: status.dependencies.vision_monitor.latency_ms },
    { icon: "camera" as const, name: "Camera 09 / AI Model", process: "camera-09", state: cameraState, latency: null },
  ];

  return (
    <div className="space-y-4 sm:space-y-5">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div><h1 className="text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">สถานะระบบและการเชื่อมต่อ</h1><p className="mt-1 text-sm text-slate-500">ตรวจสอบความพร้อมของ PCC, ฐานข้อมูล และ Vision Monitor จากจุดเดียว</p></div>
        {refreshError ? <p role="alert" className="text-xs font-bold text-red-600">ตรวจสอบสถานะไม่สำเร็จ กรุณาลองอีกครั้ง</p> : null}
      </header>

      <section className="grid grid-cols-2 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:grid-cols-[1fr_1.15fr_0.7fr_auto] lg:divide-x lg:divide-slate-100">
        <div className="flex items-center gap-3 px-5 py-4"><span className="size-3 rounded-full bg-emerald-500 shadow-[0_0_0_6px_rgba(16,185,129,0.10)]"/><div><strong className="text-sm text-slate-950">PCC <span className="text-emerald-600">พร้อมใช้งาน</span></strong><p className="text-[11px] text-slate-400">เว็บควบคุมการผลิตตอบสนองปกติ</p></div></div>
        <div className="flex items-center gap-3 border-l border-slate-100 px-5 py-4 lg:border-l-0"><span className={`size-3 rounded-full ${TONE[overall.tone].dot}`} /><div><strong className="text-sm text-slate-950">ระบบโดยรวม <span className={TONE[overall.tone].text}>{overall.label}</span></strong><p className="text-[11px] text-slate-400">{status.ready ? "บริการสำคัญผ่านเกณฑ์ readiness" : "ยังมีบริการที่ต้องดำเนินการ"}</p></div></div>
        <div className="flex items-center gap-3 border-t border-slate-100 px-5 py-4 lg:border-t-0"><FactoryIcon name="clock" className="size-6 text-slate-500"/><div><strong className="text-xs text-slate-800">ตรวจล่าสุด</strong><p className="text-[11px] text-slate-400">{checked}</p></div></div>
        <div className="flex flex-col items-stretch gap-1 border-l border-t border-slate-100 px-4 py-3 sm:flex-row sm:items-center lg:border-l-0 lg:border-t-0"><button type="button" onClick={refreshStatus} disabled={refreshing} className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-xs font-black text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-wait disabled:opacity-60"><span className={refreshing ? "animate-spin" : ""}><FactoryIcon name="refresh" className="size-4"/></span>{refreshing ? "กำลังตรวจ..." : "ตรวจสอบอีกครั้ง"}</button><a href="#next-steps" className="inline-flex h-8 items-center justify-center px-3 text-xs font-bold text-blue-700 hover:text-blue-900">คู่มือติดตั้ง</a></div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div><h2 className="text-lg font-black text-slate-950">โครงสร้างการเชื่อมต่อของระบบ</h2><p className="text-xs text-slate-500">ความสัมพันธ์ระหว่าง PCC และระบบที่เกี่ยวข้อง</p></div>
        <div className="relative mt-4 grid gap-3 before:absolute before:bottom-5 before:left-5 before:top-5 before:w-px before:bg-slate-300 md:grid-cols-2 md:before:hidden xl:grid-cols-5 xl:before:left-[8%] xl:before:right-[8%] xl:before:top-1/2 xl:before:block xl:before:h-px xl:before:w-auto">
          <TopologyNode icon="factory" title="PCC" subtitle="Production Control Center" label="พร้อมใช้งาน" tone="good" />
          <TopologyNode icon="database" title="ฐานข้อมูล Supabase" subtitle="Database connection" {...databaseState} />
          <TopologyNode icon="system" title="Vision Monitor" subtitle="API (HTTP)" {...visionState} />
          <TopologyNode icon="camera" title="Camera 09" subtitle="RTSP + AI Model" {...cameraState} />
          <TopologyNode icon="sync" title="Event Sync" subtitle="Cursor Event API" {...eventSyncState} />
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[1.35fr_1fr]">
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="px-5 py-4"><h2 className="text-lg font-black text-slate-950">ความพร้อมของบริการหลัก</h2><p className="text-xs text-slate-500">สถานะของแต่ละบริการในระบบ</p></div>
          <div className="hidden grid-cols-[1.35fr_0.8fr_0.85fr_0.55fr_0.85fr] gap-3 border-t border-slate-100 bg-slate-50/80 px-5 py-2.5 text-[10px] font-black uppercase tracking-wider text-slate-400 md:grid"><span>บริการ</span><span>Process</span><span>Ready</span><span>Latency</span><span>ตรวจล่าสุด</span></div>
          {operations.map((item) => <ServiceRow key={item.process} {...item} checked={checked} />)}
        </section>

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="px-5 py-4"><h2 className="text-lg font-black text-slate-950">สถานะ Event Sync</h2><p className="text-xs text-slate-500">การรับส่งเหตุการณ์จาก Vision Monitor</p></div>
          <dl className="divide-y divide-slate-100 border-t border-slate-100 px-5">
            <div className="flex items-center gap-3 py-3.5"><FactoryIcon name="sync" className="size-4 text-blue-700"/><dt className="flex-1 text-xs font-bold text-slate-700">Event Cursor ล่าสุด</dt><dd className="text-xs tabular-nums text-slate-500">{status.event_sync.last_cursor ?? "—"}</dd></div>
            <div className="flex items-center gap-3 py-3.5"><FactoryIcon name="database" className="size-4 text-blue-700"/><dt className="flex-1 text-xs font-bold text-slate-700">ซิงก์สำเร็จล่าสุด</dt><dd className="text-xs tabular-nums text-slate-500">{statusTime(status.event_sync.last_success_at)}</dd></div>
            <div className="flex items-center gap-3 py-3.5"><FactoryIcon name="clock" className="size-4 text-blue-700"/><dt className="flex-1 text-xs font-bold text-slate-700">อัปเดตสถานะล่าสุด</dt><dd className="text-xs tabular-nums text-slate-500">{statusTime(status.event_sync.updated_at)}</dd></div>
            <div className="flex items-start gap-3 py-3.5"><FactoryIcon name="activity" className="mt-0.5 size-4 text-blue-700"/><dt className="flex-1 text-xs font-bold text-slate-700">Rule Engine</dt><dd className="max-w-[52%] text-right"><StateText label={status.dependencies.database.ok ? "พร้อมประเมิน" : "รอฐานข้อมูล"} tone={status.dependencies.database.ok ? "good" : "danger"}/>{status.event_sync.last_error ? <p className="mt-1 break-all text-[10px] text-red-500">{status.event_sync.last_error}</p> : null}</dd></div>
          </dl>
        </section>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.25fr_1fr]">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-center justify-between gap-3"><div><h2 className="text-lg font-black text-slate-950">บันทึกเหตุการณ์ของระบบ</h2><p className="text-xs text-slate-500">ผลจากการตรวจความพร้อมล่าสุด</p></div><span className="text-[10px] font-bold text-slate-400">deployment {status.deployment}</span></div><ol className="mt-4 space-y-0"><li className="relative flex gap-4 pb-4 before:absolute before:left-[5px] before:top-3 before:h-full before:w-px before:bg-slate-200"><span className="relative z-10 mt-1.5 size-2.5 rounded-full bg-emerald-500"/><div><p className="text-xs font-bold text-slate-700">PCC Web ทำงานปกติ (alive check)</p><time className="text-[10px] text-slate-400">{statusTime(status.timestamp)}</time></div></li><li className="relative flex gap-4 pb-4 before:absolute before:left-[5px] before:top-3 before:h-full before:w-px before:bg-slate-200"><span className={`relative z-10 mt-1.5 size-2.5 rounded-full ${TONE[databaseState.tone].dot}`}/><div><p className="text-xs font-bold text-slate-700">ฐานข้อมูล Supabase: {databaseState.label}</p><time className="text-[10px] text-slate-400">{statusTime(status.timestamp)}</time></div></li><li className="flex gap-4"><span className={`mt-1.5 size-2.5 rounded-full ${TONE[visionState.tone].dot}`}/><div><p className="text-xs font-bold text-slate-700">Vision Monitor: {visionState.label}</p><time className="text-[10px] text-slate-400">{statusTime(status.timestamp)}</time></div></li></ol></section>

        <section id="next-steps" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><h2 className="text-lg font-black text-slate-950">ขั้นตอนถัดไป</h2><p className="text-xs text-slate-500">แนวทางการแก้ไขเพื่อให้ระบบพร้อมใช้งาน</p><div className="mt-4 divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200"><Link href="/devices" className="flex items-center gap-3 px-4 py-3 transition hover:bg-blue-50"><span className="grid size-8 place-items-center rounded-lg bg-blue-50 text-blue-700"><FactoryIcon name="database" className="size-4"/></span><span className="flex-1"><strong className="block text-xs text-blue-700">ตั้งค่า Supabase</strong><span className="text-[10px] text-slate-400">กำหนดค่าเชื่อมต่อฐานข้อมูลและตรวจสอบ migration</span></span><FactoryIcon name="chevron" className="size-4 text-slate-400"/></Link><Link href="/devices" className="flex items-center gap-3 px-4 py-3 transition hover:bg-blue-50"><span className="grid size-8 place-items-center rounded-lg bg-blue-50 text-blue-700"><FactoryIcon name="camera" className="size-4"/></span><span className="flex-1"><strong className="block text-xs text-blue-700">ตรวจ RTSP Camera 09</strong><span className="text-[10px] text-slate-400">ตรวจสอบเครือข่ายและสตรีมจากกล้อง</span></span><FactoryIcon name="chevron" className="size-4 text-slate-400"/></Link><a href={process.env.NEXT_PUBLIC_RACK_MONITOR_URL ?? "http://127.0.0.1:8011"} target="_blank" rel="noreferrer" className="flex items-center gap-3 px-4 py-3 transition hover:bg-blue-50"><span className="grid size-8 place-items-center rounded-lg bg-blue-50 text-blue-700"><FactoryIcon name="system" className="size-4"/></span><span className="flex-1"><strong className="block text-xs text-blue-700">เปิด Vision Monitor</strong><span className="text-[10px] text-slate-400">ตรวจสถานะกล้องและ AI โดยตรง</span></span><FactoryIcon name="chevron" className="size-4 text-slate-400"/></a></div></section>
      </div>
    </div>
  );
}
