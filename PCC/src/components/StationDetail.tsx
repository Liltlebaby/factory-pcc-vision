"use client";

import Link from "next/link";
import { POND_PH_SPEC, POND_SPEC, TEMP_SPEC, WEIGHT_SPEC, DEMO_SENSORS } from "@/lib/config";
import { classifyTemp, classifyWeight, compareTemp } from "@/lib/engine";
import { STATION_BY_ID, type StationId } from "@/lib/stations";
import { useStore } from "@/lib/store";
import { useStationAIStatus } from "@/lib/use-station-ai-status";
import { useStationTelemetry } from "@/lib/use-station-telemetry";
import { fmtTime } from "@/lib/format";
import { FactoryIcon } from "./FactoryIcon";
import { RackHourlyReport } from "./RackHourlyReport";
import { Sparkline } from "./Sparkline";
import { FurnaceGraphic, PondGraphic, RackInfeedGraphic, ScaleGraphic, toneOf } from "./StationGraphic";
import { DataStatus, H2sStatus, ProcessStatus, type DataState } from "./StatusMark";
import { getH2sLevel, H2S_LEVELS } from "@/lib/h2s-levels";
import { h2sDataState } from "@/lib/h2s-state";
import { useH2sSensor } from "@/lib/use-h2s-sensor";
import { signalVerdict, type StationAIStatus } from "@/lib/rack";
import type { StationTelemetry } from "@/lib/telemetry";

const RACK_MONITOR_URL = process.env.NEXT_PUBLIC_RACK_MONITOR_URL ?? "http://127.0.0.1:8011";

function Panel({ title, children, className = "" }: { title?: string; children: React.ReactNode; className?: string }) {
  return <section className={`min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm ${className}`}>{title && <h2 className="border-b border-slate-100 px-4 py-3 text-sm font-black text-slate-900 sm:px-5 sm:py-4">{title}</h2>}{children}</section>;
}

function Metric({ label, value, unit, hint, className = "" }: { label: string; value: string; unit?: string; hint?: string; className?: string }) {
  return <div className={`min-w-0 rounded-xl border border-slate-200 bg-slate-50 p-3.5 sm:p-4 ${className}`}><p className="text-[11px] font-bold leading-snug text-slate-500 sm:text-xs">{label}</p><p className="mt-1 break-words text-2xl font-black leading-tight tabular-nums text-slate-950 sm:text-3xl">{value}{unit && <span className="ml-1 text-xs text-slate-500 sm:text-sm">{unit}</span>}</p>{hint && <p className="mt-1 text-[10px] leading-snug text-slate-500">{hint}</p>}</div>;
}

function CameraLink({ stationId }: { stationId: StationId }) {
  const destination = new URL(RACK_MONITOR_URL);
  destination.searchParams.set("station", stationId);
  destination.hash = "ai-modules";
  return <a href={destination.toString()} target="_blank" rel="noreferrer" className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-xs font-black text-white shadow-sm transition hover:bg-blue-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 sm:w-auto"><FactoryIcon name="camera" className="size-4" />เปิด Vision Monitor</a>;
}

function EmptyState({ icon, title, detail }: { icon: "camera" | "activity" | "incident"; title: string; detail: string }) {
  return <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/60 px-5 py-8 text-center">
    <FactoryIcon name={icon} className="mx-auto size-8 text-slate-300" />
    <p className="mt-3 text-sm font-bold text-slate-600">{title}</p>
    <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-slate-400">{detail}</p>
  </div>;
}

function aiDataState(reachable: boolean, loading: boolean, status?: string): DataState {
  if (loading) return "STALE";
  if (!reachable) return "OFFLINE";
  if (status === "live" || status === "pilot") return "LIVE";
  if (status === "not_installed") return "NOT_INSTALLED";
  return "OFFLINE";
}

function telemetryDataState(status?: StationTelemetry["data_status"]): DataState {
  if (status === "live") return "LIVE";
  if (status === "stale") return "STALE";
  if (status === "demo") return "DEMO";
  return "OFFLINE";
}

function FinalPondDetail({ initialAI, initialTelemetry }: { initialAI: StationAIStatus | null; initialTelemetry: StationTelemetry | null }) {
  const { latestPond, pondSeries, activeIncidents, now } = useStore();
  const workerAI = useStationAIStatus("final-pond", 5000, initialAI);
  // งานเฝ้าพื้นที่แยกออกจากงานหมวกแล้ว (Vision Monitor ส่ง presence ใน work-area-presence)
  // เก็บ ppe-helmet ไว้เป็นทางสำรองให้ Vision Monitor เวอร์ชันเก่า
  const workerCamera = workerAI.status?.cameras.find((camera) =>
    camera.tasks.some((task) => task.task_id === "work-area-presence" || task.task_id === "ppe-helmet"),
  ) ?? workerAI.status?.cameras.find((camera) =>
    camera.tasks.some((task) => task.task_id === "worker-activity"),
  );
  const workerTask = workerCamera?.tasks.find((task) => task.task_id === "work-area-presence")
    ?? workerCamera?.tasks.find((task) => task.task_id === "ppe-helmet")
    ?? workerCamera?.tasks.find((task) => task.task_id === "worker-activity");
  const telemetry = useStationTelemetry("final-pond", initialTelemetry);
  const liveTemp = telemetry?.latest.water_temperature;
  const livePh = telemetry?.latest.water_ph;
  const hasTelemetry = Boolean(liveTemp || livePh);
  const temp = liveTemp?.value ?? latestPond?.value ?? 0;
  const ph = livePh?.value ?? latestPond?.ph ?? 0;
  const tempHistory = telemetry?.history.filter((item) => item.metric === "water_temperature").map((item) => item.value) ?? [];
  const phHistory = telemetry?.history.filter((item) => item.metric === "water_ph").map((item) => item.value) ?? [];
  const dataState = hasTelemetry ? telemetryDataState(telemetry?.data_status) : "DEMO";
  const latestMeasuredAt = Math.max(
    liveTemp ? Date.parse(liveTemp.measured_at) : 0,
    livePh ? Date.parse(livePh.measured_at) : 0,
    latestPond?.measuredAt ?? 0,
  );
  const tempValues = tempHistory.length ? tempHistory : pondSeries.slice(-60).map((s) => s.value);
  const phValues = phHistory.length ? phHistory : pondSeries.slice(-60).map((s) => s.ph ?? 0);
  const pondOutOfSpec = temp > POND_SPEC.max || (ph > 0 && (ph < POND_PH_SPEC.min || ph > POND_PH_SPEC.max));
  const pondStatus = hasTelemetry
    ? telemetry?.process_status ?? (pondOutOfSpec ? "RED" : "GREEN")
    : latestPond?.status ?? "SENSOR_ERROR";
  const incidents = activeIncidents.filter((item) => item.source === "POND");
  return <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
    <div className="min-w-0 space-y-4">
      <Panel><div className="grid gap-3 p-4 sm:gap-4 sm:p-5 md:grid-cols-[0.8fr_1.2fr]"><div className="mx-auto h-36 w-full max-w-[300px] sm:h-44"><PondGraphic temp={temp || undefined} ph={ph || undefined} tone={toneOf(pondStatus)} /></div><div className="grid min-w-0 grid-cols-2 content-center gap-2 sm:gap-3"><Metric label="อุณหภูมิน้ำ" value={temp ? temp.toFixed(1) : "—"} unit="°C" hint={`เกณฑ์ไม่เกิน ${POND_SPEC.max}°C`} /><Metric label="ค่า pH" value={ph ? ph.toFixed(2) : "—"} hint={`ช่วงมาตรฐาน ${POND_PH_SPEC.min}–${POND_PH_SPEC.max}`} /><div className="col-span-2 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-blue-100 bg-blue-50 p-3"><DataStatus state={dataState} /><span className="text-[11px] text-blue-800">อัปเดตล่าสุด {fmtTime(latestMeasuredAt || now)}</span></div></div></div></Panel>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="แนวโน้มอุณหภูมิน้ำ"><div className="p-4 sm:p-5"><Sparkline values={tempValues} min={25} max={40} color="#0284c7" bands={[{ value: 35, color: "#ef4444" }]} height={110}/>{tempValues.length > 0 && <div className="mt-3 flex flex-wrap justify-between gap-1 text-[10px] text-slate-500"><span>{hasTelemetry ? "ข้อมูลจาก Sensor Gateway" : "ข้อมูลสาธิตย้อนหลัง 60 จุด"}</span><span className="font-bold text-red-600">เส้นแดง = 35°C</span></div>}</div></Panel>
        <Panel title="แนวโน้มค่า pH"><div className="p-4 sm:p-5"><Sparkline values={phValues} min={8.5} max={12.5} color="#7c3aed" bands={[{ value: 10, color: "#f59e0b", dashed: true },{ value: 11, color: "#f59e0b", dashed: true }]} height={110}/>{phValues.length > 0 && <div className="mt-3 flex flex-wrap justify-between gap-1 text-[10px] text-slate-500"><span>{hasTelemetry ? "ข้อมูลจาก Sensor Gateway" : "ข้อมูลสาธิตย้อนหลัง 60 จุด"}</span><span className="font-bold text-violet-700">มาตรฐาน pH 10–11</span></div>}</div></Panel>
      </div>
    </div>
    <aside className="space-y-4">
      <Panel title="สถานะจากระบบ AI"><div className="space-y-4 p-5"><div className="rounded-xl border border-slate-200 bg-slate-50 p-4"><div className="flex items-start gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-100 text-blue-700"><FactoryIcon name="camera" className="size-5"/></span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-start justify-between gap-2"><div><p className="text-sm font-black text-slate-900">{workerTask?.name ?? "ตรวจสถานะการทำงานของคนงาน"}</p><p className="mt-0.5 text-[11px] text-slate-500">{workerCamera?.name ?? "กล้องตรวจสถานะงาน"}</p></div><DataStatus state={aiDataState(workerAI.reachable, workerAI.loading, workerCamera?.data_status)}/></div>{workerCamera?.location && <p className="mt-3 flex items-center gap-2 text-[11px] text-slate-500"><FactoryIcon name="activity" className="size-3.5 text-slate-400" />{workerCamera.location}</p>}{workerTask?.latest && <div className="mt-3 grid grid-cols-2 gap-2 border-t border-slate-200 pt-3 text-[11px]"><div className="rounded-lg bg-white p-2 text-slate-500">คนในพื้นที่ <strong className="block text-lg text-slate-900">{workerTask.latest.workers_in_pond ?? workerTask.latest.people_count ?? "—"}</strong></div><div className="rounded-lg bg-white p-2 text-slate-500">กรองวัตถุออก <strong className="block text-lg text-blue-700">{workerTask.latest.filtered_out ?? "—"}</strong></div><div className="rounded-lg bg-white p-2 text-slate-500">สวมหมวก <strong className="block text-lg text-emerald-700">{workerTask.latest.helmet_pass ?? "—"}</strong></div><div className="rounded-lg bg-white p-2 text-slate-500">ไม่ทราบสถานะ <strong className="block text-lg text-amber-700">{workerTask.latest.undecided ?? "—"}</strong></div></div>}<p className="mt-3 border-t border-slate-200 pt-3 text-[11px] leading-relaxed text-slate-500">PCC รับเฉพาะผลวิเคราะห์และสถานะเหตุการณ์ ไม่รับภาพหรือวิดีโอจากกล้อง</p></div></div></div><CameraLink stationId="final-pond" /></div></Panel>
      <Panel title="แนวทางเมื่อ pH ผิดเกณฑ์"><ol className="space-y-3 p-5 text-xs leading-relaxed text-slate-600"><li><strong className="text-amber-700">pH &lt; 10:</strong> เติมปูนขาวและวัดซ้ำ</li><li><strong className="text-blue-700">pH &gt; 11:</strong> เติมน้ำเจือจางแบบ Overflow และวัดซ้ำ</li><li>ตรวจปั๊มน้ำไหลกลับที่บ่อเหล็ก AJ1 ให้ไหลตลอดเวลา</li><li>ตรวจปูนขาวขณะรับเข้าให้ผ่านมาตรฐาน</li></ol></Panel>
      <Panel title="เหตุการณ์ของจุดนี้"><div className="p-5">{incidents.length ? incidents.map((item) => <Link key={item.id} href={`/incidents/${item.id}`} className="mb-2 block rounded-xl border border-red-100 bg-red-50 p-3 text-xs font-bold text-red-800">{item.issue}</Link>) : <p className="py-2 text-center text-xs text-slate-400">ไม่มีเหตุการณ์ค้าง</p>}</div></Panel>
    </aside>
  </div>;
}

function RackInfeedDetail({ initialAI }: { initialAI: StationAIStatus | null }) {
  const ai = useStationAIStatus("rack-infeed", 5000, initialAI);
  const camera = ai.status?.cameras[0];
  // รองรับ task id ทั้งชื่อใหม่และชื่อเดิม เผื่อ rack_ai ยังไม่ได้รีสตาร์ท
  const task = camera?.tasks.find((item) => item.task_id === "rack-counting" || item.task_id === "rubber-counting");
  const count = task?.latest?.rack_count ?? task?.latest?.rubber_count;
  const tracks = task?.latest?.active_tracks;
  const event = task?.latest?.last_event;
  const state = aiDataState(ai.reachable, ai.loading, ai.status?.data_status);
  const live = state === "LIVE";
  // สัญญาณจาก DVR อ่านแยกจาก camera_status เพราะกล้องที่สายหลุดยังส่งเฟรมอยู่
  const signal = camera?.source_signal;
  const verdict = signalVerdict(signal);
  const updatedAt = camera?.updated_at ? Date.parse(camera.updated_at) : Number.NaN;
  return <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_340px]"><div className="min-w-0 space-y-4"><Panel><div className="mx-auto w-full max-w-[420px] px-4 pt-4 sm:px-5 sm:pt-5"><div className="h-36 sm:h-40"><RackInfeedGraphic live={live} blind={verdict === "blind"} tracking={tracks} /></div></div>{verdict === "blind" && <div className="mx-5 mt-4 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4"><FactoryIcon name="incident" className="mt-0.5 size-5 shrink-0 text-red-600"/><div className="min-w-0"><p className="text-sm font-black text-red-800">กล้องไม่มีสัญญาณเข้าเครื่องบันทึก</p><p className="mt-1 text-xs leading-relaxed text-red-700">เครื่องบันทึกรายงานช่อง {signal?.channel ?? "—"} ว่า NO VIDEO ระบบจึงยังได้รับเฟรมอยู่แต่เป็นภาพเปล่า ยอดนับที่ไม่ขยับมาจากสาเหตุนี้ ไม่ใช่เพราะไม่มีเก๊ะผ่าน — ให้ตรวจสายกล้อง Camera 09{signal?.checked_at ? ` · ตรวจเมื่อ ${fmtTime(Date.parse(signal.checked_at))}` : ""}</p></div></div>}
              {verdict === "unknown" && signal && <p className="mx-5 mt-4 text-[11px] text-slate-400">ตรวจสัญญาณกล้องจากเครื่องบันทึกไม่ได้{signal.error ? ` (${signal.error})` : ""} — ยอดนับยังทำงานตามปกติ</p>}
              <div className="grid grid-cols-2 gap-2 p-4 sm:grid-cols-3 sm:gap-3 sm:p-5"><Metric className="col-span-2 sm:col-span-1" label="ยอดนับสะสม" value={count === undefined ? "—" : String(count)} unit="เก๊ะ" hint="ค่าจริงจาก Camera 09"/><Metric label="กำลังติดตาม" value={tracks === undefined ? "—" : String(tracks)} unit="วัตถุ" hint="วัตถุที่โมเดลกำลังติดตาม"/><Metric label="Inference" value={task ? task.inference_fps.toFixed(1) : "—"} unit="FPS" hint={task?.model_version ? `โมเดล ${task.model_version}` : "ยังไม่มีข้อมูลโมเดล"}/></div></Panel><RackHourlyReport /><Panel title="เหตุการณ์ล่าสุดจาก AI"><div className="p-5">{event ? <div className="flex flex-col gap-3 rounded-xl border border-blue-100 bg-blue-50 p-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-sm font-black text-blue-950">นับเก๊ะที่ {event.rackNumber}</p><p className="mt-1 text-xs text-blue-700">Track #{event.trackId} · ความมั่นใจ {(event.confidence * 100).toFixed(0)}%</p></div><span className="text-xs font-bold text-blue-800">{fmtTime(event.timestamp * 1000)}</span></div> : <EmptyState icon="camera" title="ยังไม่มีเหตุการณ์จากกล้อง" detail="เมื่อมีเก๊ะผ่านเส้นนับ รายการล่าสุดจะขึ้นที่นี่ทันที" />}</div></Panel></div><aside className="min-w-0 space-y-4"><Panel title="กล้องนับเก๊ะ"><div className="space-y-4 p-5"><div className="flex flex-wrap items-center justify-between gap-2"><ProcessStatus status={live ? "GREEN" : "SENSOR_ERROR"}/><DataStatus state={state}/></div><p className="text-xs leading-relaxed text-slate-500">PCC รับเฉพาะยอดนับ สถานะ และเวลาเหตุการณ์ ภาพวิดีโอคงอยู่ใน Vision Monitor</p><CameraLink stationId="rack-infeed" /></div></Panel><Panel title="รายละเอียดการเชื่อมต่อ"><dl className="divide-y divide-slate-100 px-5 py-2 text-xs"><div className="flex flex-wrap justify-between gap-2 py-3"><dt className="text-slate-400">Camera</dt><dd className="break-words text-right font-bold text-slate-800">{camera?.camera_id ?? "—"}</dd></div><div className="flex flex-wrap justify-between gap-2 py-3"><dt className="text-slate-400">สถานะกล้อง</dt><dd className="break-words text-right font-bold text-slate-800">{camera?.camera_status ?? "offline"}</dd></div><div className="flex flex-wrap justify-between gap-2 py-3"><dt className="text-slate-400">สัญญาณภาพเข้า</dt><dd className={`font-bold ${verdict === "blind" ? "text-red-700" : verdict === "ok" ? "text-emerald-700" : "text-slate-400"}`}>{verdict === "blind" ? "ไม่มีสัญญาณ" : verdict === "ok" ? signal?.resolution ?? "ปกติ" : "—"}</dd></div><div className="flex flex-wrap justify-between gap-2 py-3"><dt className="text-slate-400">อัปเดตล่าสุด</dt><dd className="break-words text-right font-bold text-slate-800">{Number.isNaN(updatedAt) ? "—" : fmtTime(updatedAt)}</dd></div></dl></Panel></aside></div>;
}

function OdorDetail() {
  const h2s = useH2sSensor();
  const ppm = h2s.latest?.h2s_ppm;
  const dataState: DataState = h2sDataState(h2s);
  const level = h2s.online ? getH2sLevel(ppm) : undefined;
  const values = h2s.history.map((item) => item.h2s_ppm);
  // สเกลขั้นต่ำ 0–2 ppm ให้เห็นเส้นเกณฑ์ 0.5/1 เสมอ แล้วขยายตามค่าสูงสุดที่วัดได้
  const chartMax = Math.max(2, Math.ceil(Math.max(0, ...values) * 1.2));
  const bands = [
    { value: 0.5, color: "#f59e0b", dashed: true },
    { value: 1, color: "#f97316", dashed: true },
    { value: 5, color: "#ef4444" },
    { value: 10, color: "#b91c1c" },
  ].filter((band) => band.value <= chartMax);
  const updatedAt = h2s.latest ? Date.parse(h2s.latest.captured_at) : undefined;
  return <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
    <div className="min-w-0 space-y-4">
      <Panel><div className="p-4 sm:p-5"><div className="mx-auto mb-4 grid size-24 place-items-center rounded-full bg-violet-50 text-violet-500 ring-1 ring-violet-100"><FactoryIcon name="odor" className="size-11" /></div><Metric label="ก๊าซไฮโดรเจนซัลไฟด์ (H₂S)" value={ppm?.toFixed(1) ?? "—"} unit="ppm" hint={level?.meaning ?? "ช่วงวัด 0–100 ppm · ละเอียด 0.1 ppm"} />{level?.action && <div className={`mt-3 rounded-xl p-3 text-xs font-bold leading-relaxed ring-1 ${level.classes}`}><p className="text-[10px] uppercase tracking-wide opacity-80">สิ่งที่ต้องทำ</p><p className="mt-1">{level.action}</p></div>}<div className="mt-4 flex flex-wrap items-center justify-between gap-2">{level ? <H2sStatus level={level} /> : <ProcessStatus status="SENSOR_ERROR" />}<DataStatus state={dataState} /></div><p className="mt-2 text-right text-[10px] text-slate-400">อัปเดต {updatedAt ? fmtTime(updatedAt) : "—"}</p></div></Panel>
      <Panel title="การเชื่อมต่อเซ็นเซอร์"><dl className="divide-y divide-slate-100 px-5 py-2 text-xs">{[
        ["เซ็นเซอร์", "SN-3002-H2S-N01 (RS485)"],
        ["อุปกรณ์", h2s.latest?.device_id ?? "—"],
        ["Gateway", h2s.installed === false ? "ยังไม่ติดตั้ง" : h2s.serial.connected ? "เชื่อมต่อ" : "ไม่เชื่อมต่อ"],
        ["คุณภาพข้อมูล", h2s.latest?.quality ?? "—"],
        ["จำนวนค่าที่รับ", String(h2s.serial.samples)],
      ].map(([label, value]) => <div key={label} className="flex flex-wrap justify-between gap-2 py-3"><dt className="text-slate-400">{label}</dt><dd className="break-words text-right font-bold text-slate-800">{value}</dd></div>)}</dl>{h2s.serial.error && <p className="mx-5 mb-4 rounded-lg bg-red-50 p-3 text-[11px] leading-relaxed text-red-700">{h2s.serial.error}</p>}</Panel>
    </div>
    <div className="min-w-0 space-y-4">
      <Panel title="แนวโน้มย้อนหลัง (ประมาณ 2 นาที)"><div className="p-4 sm:p-5"><Sparkline values={values} min={0} max={chartMax} color="#7c3aed" bands={bands} height={180} />{values.length > 0 && <div className="mt-3 flex flex-wrap justify-between gap-1 text-[10px] text-slate-500"><span>ข้อมูลจาก Sensor Gateway ทุก 1 วินาที</span><span><span className="font-bold text-amber-600">0.5</span> · <span className="font-bold text-orange-600">1</span> · <span className="font-bold text-red-600">5</span> · <span className="font-bold text-red-800">10</span> ppm</span></div>}</div></Panel>
      <Panel title="เกณฑ์ H₂S"><div className="overflow-x-auto"><table className="w-full min-w-[640px] text-left text-xs"><thead className="bg-slate-50 text-[11px] text-slate-500"><tr><th className="px-4 py-2.5 font-bold sm:px-5">H₂S (ppm)</th><th className="px-4 py-2.5 font-bold">สถานะ</th><th className="px-4 py-2.5 font-bold">ความหมาย</th><th className="px-4 py-2.5 font-bold sm:px-5">สิ่งที่ต้องทำ</th></tr></thead><tbody className="divide-y divide-slate-100">{[...H2S_LEVELS].reverse().map((item) => {
        const current = item.key === level?.key;
        return <tr key={item.key} className={current ? "bg-violet-50" : undefined} aria-current={current ? "true" : undefined}><td className="whitespace-nowrap px-4 py-3 font-bold tabular-nums text-slate-800 sm:px-5">{item.range}</td><td className="px-4 py-3"><H2sStatus level={item} /></td><td className="px-4 py-3 leading-relaxed text-slate-600">{item.meaning}</td><td className="px-4 py-3 font-semibold leading-relaxed text-slate-800 sm:px-5">{item.action ?? "—"}{current && <strong className="ml-2 text-violet-700">← ตอนนี้</strong>}</td></tr>;
      })}</tbody></table></div></Panel>
    </div>
  </div>;
}

function StandardDetail({ id, initialTelemetry }: { id: "rubber-scale" | "furnace-temperature"; initialTelemetry: StationTelemetry | null }) {
  const { latestWeight, latestTemp, tempSeries, weightSeries } = useStore();
  const telemetry = useStationTelemetry(id, initialTelemetry);
  const isScale = id === "rubber-scale";
  const weightReading = telemetry?.latest.rubber_weight;
  const actualReading = telemetry?.latest.furnace_temperature;
  const burnerReading = telemetry?.latest.furnace_burner_temperature;
  const recorderReading = telemetry?.latest.furnace_recorder_temperature;
  const hasTelemetry = isScale ? Boolean(weightReading) : Boolean(actualReading || burnerReading || recorderReading);
  const furnaceComplete = Boolean(actualReading && burnerReading && recorderReading);
  const actual = actualReading?.value ?? latestTemp?.actual;
  const burner = burnerReading?.value ?? latestTemp?.burner;
  const recorder = recorderReading?.value ?? latestTemp?.recorder;
  const liveValues = telemetry?.history
    .filter((item) => item.metric === (isScale ? "rubber_weight" : "furnace_temperature"))
    .map((item) => item.value) ?? [];
  const values = liveValues.length
    ? liveValues
    : isScale
      ? weightSeries.slice(-60).map((sample) => sample.measurement.value)
      : tempSeries.slice(-60).map((sample) => sample.actual);
  const value = isScale
    ? (weightReading?.value ?? latestWeight?.measurement.value)?.toFixed(2)
    : actual?.toFixed(1);
  const unit = isScale ? "kg" : "°C";
  const target = isScale ? WEIGHT_SPEC.target.toFixed(2) : TEMP_SPEC.target.toFixed(1);
  const status = isScale
    ? weightReading ? classifyWeight(weightReading.value).status : latestWeight?.comparison.status
    : furnaceComplete ? classifyTemp(compareTemp(actualReading!.value, burnerReading!.value, recorderReading!.value).worstError).status : hasTelemetry ? "SENSOR_ERROR" : latestTemp?.status;
  const dataState: DataState = hasTelemetry
    ? !isScale && !furnaceComplete ? "STALE" : telemetryDataState(telemetry?.data_status)
    : DEMO_SENSORS[isScale ? "weight" : "furnace"] ? "DEMO" : "NOT_INSTALLED";
  const measuredAt = isScale
    ? weightReading ? Date.parse(weightReading.measured_at) : latestWeight?.measurement.measuredAt
    : Math.max(
      actualReading ? Date.parse(actualReading.measured_at) : 0,
      burnerReading ? Date.parse(burnerReading.measured_at) : 0,
      recorderReading ? Date.parse(recorderReading.measured_at) : 0,
      latestTemp?.measuredAt ?? 0,
    );
  return <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[340px_minmax(0,1fr)]"><Panel><div className="p-4 sm:p-5"><div className="mx-auto mb-4 h-28 w-full max-w-[240px]">{isScale ? <ScaleGraphic value={weightReading?.value ?? latestWeight?.measurement.value} tone={toneOf(status ?? "SENSOR_ERROR")} /> : <FurnaceGraphic value={actual} tone={toneOf(status ?? "SENSOR_ERROR")} />}</div><Metric label={isScale ? "น้ำหนักยางล่าสุด" : "Digital Thermometer"} value={value ?? "—"} unit={unit} hint={`เป้าหมาย ${target} ${unit}`}/><div className="mt-4 flex flex-wrap items-center justify-between gap-2"><ProcessStatus status={status ?? "SENSOR_ERROR"}/><DataStatus state={dataState}/></div><p className="mt-2 text-right text-[10px] text-slate-400">อัปเดต {measuredAt ? fmtTime(measuredAt) : "—"}</p>{!isScale && <div className="mt-4 divide-y divide-slate-100 rounded-xl border border-slate-200 px-3">{[["Burner Display",burner],["Recorder",recorder]].map(([label,v]) => <div key={String(label)} className="flex flex-wrap justify-between gap-2 py-3 text-xs"><span className="text-slate-500">{label}</span><strong>{typeof v === "number" ? v.toFixed(1) : "—"} °C</strong></div>)}</div>}</div></Panel><Panel title="แนวโน้มย้อนหลัง"><div className="p-4 sm:p-5"><Sparkline values={values} min={isScale ? 16.5 : 176} max={isScale ? 18.5 : 185} color={isScale ? "#2563eb" : "#059669"} height={180}/>{values.length > 0 && <p className="mt-3 text-[10px] text-slate-400">{hasTelemetry ? "ข้อมูลจาก Sensor Gateway" : "ข้อมูลสาธิต"}</p>}</div></Panel></div>;
}

export function StationDetail({ stationId, initialAI = null, initialTelemetry = null }: { stationId: StationId; initialAI?: StationAIStatus | null; initialTelemetry?: StationTelemetry | null }) {
  const station = STATION_BY_ID[stationId];
  return <div className="min-w-0 space-y-4 sm:space-y-5"><header className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div className="min-w-0"><Link href="/stations" className="inline-flex min-h-10 items-center text-xs font-bold text-blue-700 hover:underline">← จุดตรวจทั้งหมด</Link><div className="mt-1 flex min-w-0 items-start gap-3 sm:mt-2 sm:items-center"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-600 text-white sm:size-11"><FactoryIcon name={station.icon} className="size-6"/></span><div className="min-w-0"><h1 className="text-xl font-black leading-tight tracking-tight text-slate-950 sm:text-2xl">{station.name}</h1><p className="mt-1 text-xs leading-relaxed text-slate-500 sm:text-sm">{station.description}</p></div></div></div>{stationId === "final-pond" || stationId === "rack-infeed" ? <CameraLink stationId={stationId} /> : null}</header>{stationId === "final-pond" ? <FinalPondDetail initialAI={initialAI} initialTelemetry={initialTelemetry} /> : stationId === "rack-infeed" ? <RackInfeedDetail initialAI={initialAI} /> : stationId === "rubber-odor" ? <OdorDetail /> : <StandardDetail id={stationId} initialTelemetry={initialTelemetry} />}</div>;
}
