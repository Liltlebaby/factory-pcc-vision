"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { Factory3D, type SpotTone } from "./Factory3D";
import { FactoryIcon, type FactoryIconName } from "./FactoryIcon";
import { FurnaceGraphic, PondGraphic, RackInfeedGraphic, ScaleGraphic, toneOf } from "./StationGraphic";
import { DataStatus, H2sStatus, ProcessStatus, type DataState } from "./StatusMark";
import { fmtTime } from "@/lib/format";
import { getH2sLevel } from "@/lib/h2s-levels";
import type { Status } from "@/lib/types";

export interface CommandCenterIncident {
  id: string;
  issue: string;
  severity: string;
  owner: string;
  detectedAt: number;
  href: string;
}

export interface CommandCenterEvent {
  id: string;
  message: string;
  level: string;
  at: number;
}

export interface CommandCenterLayoutProps {
  updatedAt: number;
  pond: { temp?: number; ph?: number; status: Status; dataState: DataState; aiState: DataState; trend: number[] };
  rack: { count?: number; tracks?: number; status: Status; dataState: DataState; model?: string; trend?: number[] };
  odor: { value?: number; dataState: DataState; updatedAt?: number };
  weight: { value?: number; status: Status; dataState: DataState; target: number; trend: number[] };
  furnace: { actual?: number; burner?: number; recorder?: number; status: Status; dataState: DataState; trend: number[] };
  limits: { pondTempMax: number; pondPhMin: number; pondPhMax: number; pondTempUnit: string; furnaceUnit: string };
  incidents: CommandCenterIncident[];
  events: CommandCenterEvent[];
  alertsLive: boolean;
  visionMonitorUrl: string;
}

function StationCard({ step, icon, title, source, href, status, badge, dataState, visual, value, unit, detail, accent }: {
  step: number;
  icon: FactoryIconName;
  title: string;
  source: string;
  href: string;
  status?: Status;
  badge?: ReactNode;
  dataState: DataState;
  visual: ReactNode;
  value: string;
  unit?: string;
  detail: string;
  accent: "blue" | "cyan" | "violet" | "amber" | "emerald";
}) {
  const accents = {
    blue: "from-blue-50 text-blue-700 ring-blue-100",
    cyan: "from-cyan-50 text-cyan-700 ring-cyan-100",
    violet: "from-violet-50 text-violet-700 ring-violet-100",
    amber: "from-amber-50 text-amber-700 ring-amber-100",
    emerald: "from-emerald-50 text-emerald-700 ring-emerald-100",
  } as const;

  return <Link href={href} className="group relative flex min-h-[302px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_12px_30px_rgba(15,23,42,0.06)] transition duration-200 hover:-translate-y-1 hover:border-blue-200 hover:shadow-[0_18px_38px_rgba(37,99,235,0.13)]">
    <span className="absolute right-4 top-3 text-5xl font-black leading-none text-slate-100">{String(step).padStart(2, "0")}</span>
    <div className="relative flex items-start gap-3 px-4 pb-2 pt-4">
      <span className={`grid size-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br to-white ring-1 ${accents[accent]}`}><FactoryIcon name={icon} className="size-5" /></span>
      <div className="min-w-0 pr-5"><p className="text-[9px] font-bold uppercase tracking-[0.14em] text-slate-400">{source}</p><h3 className="mt-1 min-h-10 text-sm font-extrabold leading-5 text-slate-900">{title}</h3></div>
    </div>
    <div className="mx-4 flex h-[106px] items-center justify-center rounded-2xl bg-gradient-to-b from-slate-50 to-white px-2 ring-1 ring-slate-100">{visual}</div>
    <div className="flex flex-1 flex-col px-4 pb-4 pt-3">
      <div className="flex items-end justify-between gap-2"><p className="text-3xl font-black tabular-nums tracking-tight text-slate-950">{value}{unit ? <span className="ml-1 text-xs text-slate-400">{unit}</span> : null}</p>{badge ?? (status ? <ProcessStatus status={status} /> : <DataStatus state={dataState} />)}</div>
      <p className="mt-2 line-clamp-2 min-h-8 text-[11px] leading-4 text-slate-500">{detail}</p>
      <div className="mt-auto flex items-center justify-between border-t border-slate-100 pt-3"><DataStatus state={dataState} /><span className="inline-flex items-center gap-1 text-[11px] font-bold text-blue-700">ดูรายละเอียด <FactoryIcon name="chevron" className="size-3.5" /></span></div>
    </div>
  </Link>;
}

function points(values: number[], width = 760, height = 170) {
  const data = values.length > 1 ? values : [0, 0];
  const min = Math.min(...data);
  const span = Math.max(...data) - min || 1;
  return data.map((value, index) => `${(8 + index / (data.length - 1) * (width - 16)).toFixed(1)},${(8 + (1 - (value - min) / span) * (height - 16)).toFixed(1)}`).join(" ");
}

function TrendChart({ pond, weight, furnace }: { pond: number[]; weight: number[]; furnace: number[] }) {
  return <div>
    <div className="mb-4 flex flex-wrap gap-x-5 gap-y-2 text-[11px] font-semibold text-slate-500">
      {[["#06b6d4", "อุณหภูมิบ่อ"], ["#2563eb", "น้ำหนักยาง"], ["#f59e0b", "อุณหภูมิเตา"]].map(([color, label]) => <span key={label} className="inline-flex items-center gap-2"><i className="h-0.5 w-5 rounded-full" style={{ backgroundColor: color }} />{label}</span>)}
    </div>
    <svg viewBox="0 0 760 170" className="h-[170px] w-full" role="img" aria-label="กราฟแนวโน้มค่าหลักของสายการผลิต">
      {[28, 68, 108, 148].map((y) => <line key={y} x1="8" x2="752" y1={y} y2={y} stroke="#e2e8f0" strokeDasharray="5 7" />)}
      <polyline points={points(pond)} fill="none" stroke="#06b6d4" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points={points(weight)} fill="none" stroke="#2563eb" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points={points(furnace)} fill="none" stroke="#f59e0b" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  </div>;
}

/** ข้อมูลที่ไม่สดไม่ควรเรืองเขียวบนผัง ให้เป็นสีเทาแทน */
function spotTone(status: Status, dataState: DataState): SpotTone {
  if (dataState === "NOT_INSTALLED" || dataState === "OFFLINE") return "idle";
  return toneOf(status);
}

export function CommandCenterLayout(props: CommandCenterLayoutProps) {
  const { pond, rack, odor, weight, furnace, limits } = props;
  // ประเมินเกณฑ์เฉพาะตอนข้อมูลสด ค่าเก่า/ขาดการเชื่อมต่อจะแสดงสถานะข้อมูลแทน
  const odorLevel = odor.dataState === "LIVE" ? getH2sLevel(odor.value) : undefined;
  return <div className="space-y-6">
    <section className="relative overflow-hidden rounded-3xl bg-slate-950 px-5 py-6 text-white shadow-[0_20px_50px_rgba(15,23,42,0.18)] sm:px-7 lg:px-8">
      <div className="absolute inset-y-0 right-0 w-1/2 bg-[radial-gradient(circle_at_center,rgba(37,99,235,0.34),transparent_68%)]" />
      <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div><div className="mb-3 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-300"><span className="size-2 rounded-full bg-emerald-400 shadow-[0_0_12px_#34d399]" />Production Control Center</div><h1 className="text-2xl font-black tracking-tight sm:text-3xl">ภาพรวมสายการผลิต LINE-1</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">ศูนย์รวมสถานะ Sensor / IoT และผลวิเคราะห์จาก Vision Monitor โดยไม่โหลดภาพกล้องเข้าสู่ PCC</p></div>
        <div className="flex flex-wrap items-center gap-2"><div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-300">อัปเดตล่าสุด <strong className="ml-1 tabular-nums text-white">{fmtTime(props.updatedAt)}</strong></div><label htmlFor="shift" className="sr-only">ช่วงเวลา</label><select id="shift" className="h-9 rounded-xl border border-white/15 bg-white/10 px-3 text-xs font-bold text-white outline-none focus:border-cyan-400"><option className="text-slate-900">กะปัจจุบัน</option><option className="text-slate-900">วันนี้</option></select></div>
      </div>
    </section>

    <Factory3D spots={[
      {
        key: "final-pond",
        value: pond.ph === undefined ? "—" : pond.ph.toFixed(2),
        unit: "pH",
        detail: `น้ำ ${pond.temp?.toFixed(1) ?? "—"}${limits.pondTempUnit} · เกณฑ์ pH ${limits.pondPhMin}–${limits.pondPhMax}`,
        tone: spotTone(pond.status, pond.dataState),
        dataState: pond.dataState,
      },
      {
        key: "rack-infeed",
        value: rack.count === undefined ? "—" : String(rack.count),
        unit: "เก๊ะ",
        detail: `กล้องนับก่อนเข้าเตา · ติดตาม ${rack.tracks ?? "—"} วัตถุ`,
        tone: spotTone(rack.status, rack.dataState),
        dataState: rack.dataState,
      },
      {
        key: "furnace-temperature",
        value: furnace.dataState === "NOT_INSTALLED" ? "—" : furnace.actual?.toFixed(1) ?? "—",
        unit: limits.furnaceUnit,
        detail: `Burner ${furnace.burner?.toFixed(1) ?? "—"} · Recorder ${furnace.recorder?.toFixed(1) ?? "—"}`,
        tone: spotTone(furnace.status, furnace.dataState),
        dataState: furnace.dataState,
      },
      {
        key: "rubber-scale",
        value: weight.dataState === "NOT_INSTALLED" ? "—" : weight.value?.toFixed(2) ?? "—",
        unit: "kg",
        detail: `เป้าหมาย ${weight.target.toFixed(2)} kg`,
        tone: spotTone(weight.status, weight.dataState),
        dataState: weight.dataState,
      },
      {
        key: "rubber-odor",
        value: odor.dataState === "NOT_INSTALLED" ? "—" : odor.value?.toFixed(1) ?? "—",
        unit: odor.dataState === "NOT_INSTALLED" ? undefined : "ppm",
        detail: odor.dataState === "NOT_INSTALLED" ? "บอร์ดเดิมย้ายไปวัด pH บ่อสุดท้าย" : odorLevel?.meaning ?? "H₂S",
        tone: odorLevel ? spotTone(odorLevel.status, odor.dataState) : "idle",
        dataState: odor.dataState,
      },
    ]} />

    <section aria-labelledby="production-flow-title">
      <div className="mb-3 flex items-end justify-between gap-4"><div><h2 id="production-flow-title" className="text-base font-black text-slate-950">สถานะ 5 จุดหลัก</h2><p className="mt-1 text-xs text-slate-500">เลื่อนแนวนอนบนหน้าจอขนาดเล็ก · กดการ์ดเพื่อดูรายละเอียดแต่ละจุด</p></div><Link href="/stations" className="hidden text-xs font-bold text-blue-700 hover:underline sm:block">ดูทุกสถานี →</Link></div>
      <div className="grid auto-cols-[minmax(240px,1fr)] grid-flow-col gap-4 overflow-x-auto pb-4 xl:grid-flow-row xl:grid-cols-5 xl:overflow-visible xl:pb-0">
        <StationCard step={1} icon="pond" title="บ่อสุดท้าย" source="Sensor / IoT + Vision AI" href="/stations/final-pond" status={pond.status} dataState={pond.dataState} visual={<PondGraphic temp={pond.temp} ph={pond.ph} tone={toneOf(pond.status)} />} value={pond.temp?.toFixed(1) ?? "—"} unit={limits.pondTempUnit} detail={`pH ${pond.ph?.toFixed(2) ?? "—"} · เกณฑ์ ${limits.pondPhMin}–${limits.pondPhMax} · AI คนงาน ${pond.aiState === "LIVE" ? "เชื่อมต่อ" : "ยังไม่พร้อม"}`} accent="cyan" />
        <StationCard step={2} icon="conveyor" title="หอโรยยาง · นับเก๊ะเข้าเตา" source="Vision Monitor" href="/stations/rack-infeed" status={rack.status} dataState={rack.dataState} visual={<RackInfeedGraphic live={rack.dataState === "LIVE"} tracking={rack.tracks} />} value={rack.count === undefined ? "—" : String(rack.count)} unit="เก๊ะ" detail={`กำลังติดตาม ${rack.tracks ?? "—"} วัตถุ · ${rack.model ? `โมเดล ${rack.model}` : "รอข้อมูลโมเดล"}`} accent="blue" />
        <StationCard step={3} icon="odor" title="ตรวจจับกลิ่นเหม็นของยาง" source="Sensor / IoT" href="/stations/rubber-odor" badge={odorLevel ? <H2sStatus level={odorLevel} /> : undefined} dataState={odor.dataState} visual={<div className="grid size-24 place-items-center rounded-full bg-violet-50 text-violet-500 ring-1 ring-violet-100"><FactoryIcon name="odor" className="size-11" /></div>} value={odor.value?.toFixed(1) ?? "—"} unit="ppm" detail={odorLevel ? `${odorLevel.action ?? odorLevel.meaning} · อัปเดต ${odor.updatedAt ? fmtTime(odor.updatedAt) : "—"}` : `H₂S · ช่วงวัด 0–100 ppm${odor.updatedAt ? ` · อัปเดต ${fmtTime(odor.updatedAt)}` : " · รอข้อมูลจากเซ็นเซอร์"}`} accent="violet" />
        <StationCard step={4} icon="scale" title="ตาชั่งน้ำหนักยาง" source="Sensor / IoT" href="/stations/rubber-scale" status={weight.dataState === "NOT_INSTALLED" ? undefined : weight.status} dataState={weight.dataState} visual={<ScaleGraphic value={weight.value} tone={toneOf(weight.status)} />} value={weight.value?.toFixed(2) ?? "—"} unit="kg" detail={`เป้าหมาย ${weight.target.toFixed(2)} kg`} accent="emerald" />
        <StationCard step={5} icon="thermometer" title="อุณหภูมิเตา" source="Sensor / IoT" href="/stations/furnace-temperature" status={furnace.dataState === "NOT_INSTALLED" ? undefined : furnace.status} dataState={furnace.dataState} visual={<FurnaceGraphic value={furnace.actual} tone={toneOf(furnace.status)} />} value={furnace.actual?.toFixed(1) ?? "—"} unit={limits.furnaceUnit} detail={`Burner ${furnace.burner?.toFixed(1) ?? "—"} · Recorder ${furnace.recorder?.toFixed(1) ?? "—"} ${limits.furnaceUnit}`} accent="amber" />
      </div>
    </section>

    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.75fr)]">
      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4"><div><h2 className="flex items-center gap-2 text-sm font-extrabold text-slate-900"><FactoryIcon name="activity" className="size-4 text-blue-600" />แนวโน้มค่าหลัก</h2><p className="mt-1 text-[11px] text-slate-400">กราฟปรับสเกลแยกแต่ละชุดเพื่อให้เห็นแนวโน้มร่วมกันได้ง่าย</p></div><Link href="/reports" className="text-xs font-bold text-blue-700 hover:underline">เปิดรายงาน →</Link></div><div className="px-5 py-4"><TrendChart pond={pond.trend} weight={weight.trend} furnace={furnace.trend} /></div></section>
      <aside className="grid gap-4 md:grid-cols-2 xl:grid-cols-1">
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="flex items-center justify-between border-b border-slate-100 px-4 py-3.5"><h2 className="flex items-center gap-2 text-sm font-extrabold"><FactoryIcon name="incident" className="size-4 text-red-500" />รายการที่ต้องดำเนินการ</h2><span className={`rounded-full px-2 py-0.5 text-xs font-black ${props.incidents.length ? "bg-red-50 text-red-600" : "bg-emerald-50 text-emerald-700"}`}>{props.incidents.length}</span></div><div className="divide-y divide-slate-100">{props.incidents.length ? props.incidents.slice(0, 3).map((item) => <Link key={item.id} href={item.href} className="block p-4 transition hover:bg-slate-50"><div className="flex gap-3"><span className={`mt-1 size-2 shrink-0 rounded-full ${item.severity === "CRITICAL" ? "bg-red-500" : "bg-amber-500"}`} /><div className="min-w-0"><p className="text-xs font-bold text-slate-800">{item.issue}</p><p className="mt-1 text-[10px] text-slate-400">{item.owner} · {fmtTime(item.detectedAt)}</p></div></div></Link>) : <div className="px-4 py-8 text-center text-xs text-slate-400">ไม่มีเหตุการณ์ค้าง</div>}</div><Link href="/incidents" className="block border-t border-slate-100 px-4 py-3 text-center text-xs font-bold text-blue-700 hover:bg-blue-50">ดูเหตุการณ์ทั้งหมด</Link></section>
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="flex items-center justify-between border-b border-slate-100 px-4 py-3.5"><h2 className="flex items-center gap-2 text-sm font-extrabold"><FactoryIcon name="activity" className="size-4 text-blue-600" />กิจกรรมล่าสุด</h2><DataStatus state={props.alertsLive ? "LIVE" : "DEMO"} /></div><ol className="relative mx-4 my-4 border-l border-slate-200 pl-4">{props.events.map((event) => <li key={event.id} className="relative pb-3 last:pb-0"><span className={`absolute -left-[21px] top-1 size-2.5 rounded-full border-2 border-white ${event.level === "RED" ? "bg-red-500" : event.level === "YELLOW" ? "bg-amber-500" : "bg-blue-500"}`} /><p className="text-[11px] font-semibold leading-relaxed text-slate-700">{event.message}</p><p className="mt-0.5 text-[10px] text-slate-400">{fmtTime(event.at)}</p></li>)}</ol></section>
      </aside>
    </div>

    <section className="flex flex-col gap-4 rounded-2xl border border-blue-100 bg-gradient-to-r from-blue-50 to-cyan-50 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"><div className="flex items-start gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white text-blue-700 shadow-sm ring-1 ring-blue-100"><FactoryIcon name="camera" className="size-5" /></span><div><h2 className="text-sm font-extrabold text-blue-950">PCC รับเฉพาะผลวิเคราะห์จาก Vision Monitor</h2><p className="mt-1 text-xs leading-5 text-blue-700">ภาพกล้องและงาน AI ทำงานแยกบริการ ช่วยลดโหลดของ PCC และทำให้เพิ่มกล้องหรือโมเดลใหม่ได้โดยไม่กระทบหน้าควบคุม</p></div></div><a href={props.visionMonitorUrl} target="_blank" rel="noreferrer" className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-xl bg-blue-700 px-4 text-xs font-bold text-white shadow-sm transition hover:bg-blue-800"><FactoryIcon name="camera" className="size-4" />เปิด Vision Monitor</a></section>
  </div>;
}
