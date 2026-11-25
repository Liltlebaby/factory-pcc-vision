"use client";

import Link from "next/link";
import { FactoryIcon } from "./FactoryIcon";
import { PondGraphic, RackInfeedGraphic, ScaleGraphic, toneOf } from "./StationGraphic";
import { Sparkline } from "./Sparkline";
import { DataStatus, H2sStatus, ProcessStatus, type DataState } from "./StatusMark";
import { CommandCenterLayout } from "./CommandCenterLayout";
import { useStore } from "@/lib/store";
import { useStationAIStatus } from "@/lib/use-station-ai-status";
import { useStationsTelemetry } from "@/lib/use-stations-telemetry";
import { useStationAlerts } from "@/lib/use-station-alerts";
import { getH2sLevel } from "@/lib/h2s-levels";
import { h2sDataState as h2sDataStateOf } from "@/lib/h2s-state";
import { useH2sSensor } from "@/lib/use-h2s-sensor";
import { POND_PH_SPEC, POND_SPEC, TEMP_SPEC, WEIGHT_SPEC, DEMO_SENSORS } from "@/lib/config";
import { classifyPondTemp, classifyTemp, classifyWeight, compareTemp } from "@/lib/engine";
import { fmtTime } from "@/lib/format";
import type { Status } from "@/lib/types";
import { signalVerdict, type StationAIStatus } from "@/lib/rack";
import type { StationAlertFeed, StationTelemetry } from "@/lib/telemetry";

const RACK_MONITOR_URL = process.env.NEXT_PUBLIC_RACK_MONITOR_URL ?? "http://127.0.0.1:8011";
const SENSOR_STATIONS = ["final-pond", "rubber-scale", "furnace-temperature"] as const;
const EMPTY_TELEMETRY: Record<string, StationTelemetry> = {};
const EMPTY_ALERT_FEED: StationAlertFeed = { data_status: "offline", generated_at: new Date(0).toISOString(), alerts: [] };

function telemetryState(status?: StationTelemetry["data_status"]): DataState {
  if (status === "live") return "LIVE";
  if (status === "stale") return "STALE";
  if (status === "demo") return "DEMO";
  return "OFFLINE";
}

function newestTimestamp(...timestamps: Array<string | undefined>) {
  const values = timestamps.map((value) => value ? Date.parse(value) : 0).filter(Number.isFinite);
  return values.length ? Math.max(...values) : undefined;
}

function StationHeader({ icon, title, href, status }: { icon: "pond" | "conveyor" | "odor" | "scale" | "thermometer"; title: string; href: string; status: Status }) {
  return <div className="flex items-center gap-3 border-b border-slate-100 px-4 py-3.5 sm:px-5">
    <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-700"><FactoryIcon name={icon} className="size-5" /></span>
    <div className="min-w-0 flex-1"><h2 className="text-sm font-extrabold leading-snug text-slate-900">{title}</h2><div className="mt-1"><ProcessStatus status={status} /></div></div>
    <Link href={href} aria-label={`ดูรายละเอียด ${title}`} className="grid size-8 place-items-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-blue-700"><FactoryIcon name="chevron" className="size-4" /></Link>
  </div>;
}

function Freshness({ at, state = "DEMO" }: { at?: number; state?: DataState }) {
  return <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-4 py-3 text-[11px] sm:px-5">
    <DataStatus state={state} />
    <span className="flex items-center gap-1.5 text-slate-400"><FactoryIcon name="clock" className="size-3.5" />{at ? `อัปเดต ${fmtTime(at)}` : "ยังไม่มีข้อมูล"}</span>
  </div>;
}

function TrendMini({ label, value, unit, values, color }: { label: string; value: string; unit: string; values: number[]; color: string }) {
  return <div className="min-w-0 border-t border-slate-100 px-4 py-4 first:border-t-0 md:border-t-0 md:border-l md:first:border-l-0 sm:px-5"><div className="flex items-end justify-between gap-3"><div><p className="text-xs font-bold text-slate-500">{label}</p><p className="mt-1 text-xl font-black tabular-nums text-slate-950">{value}<span className="ml-1 text-[10px] text-slate-400">{unit}</span></p></div><span className="text-[10px] text-slate-400">ล่าสุด</span></div><div className="mt-3"><Sparkline values={values} min={Math.min(...values, 0)} max={Math.max(...values, 1)} color={color} height={56}/></div></div>;
}

export function PccOverview({
  initialRackAI = null,
  initialPondAI = null,
  initialTelemetry = EMPTY_TELEMETRY,
  initialStationAlerts = EMPTY_ALERT_FEED,
}: {
  initialRackAI?: StationAIStatus | null;
  initialPondAI?: StationAIStatus | null;
  initialTelemetry?: Record<string, StationTelemetry>;
  initialStationAlerts?: StationAlertFeed;
}) {
  const { now, latestPond, latestWeight, latestTemp, pondSeries, weightSeries, tempSeries, activeIncidents: simulatorIncidents, events } = useStore();
  const rackAI = useStationAIStatus("rack-infeed", 5000, initialRackAI);
  const pondAI = useStationAIStatus("final-pond", 5000, initialPondAI);
  const h2sSensor = useH2sSensor();
  const telemetry = useStationsTelemetry(SENSOR_STATIONS, initialTelemetry);
  const stationAlerts = useStationAlerts(initialStationAlerts);
  const pondTelemetry = telemetry["final-pond"];
  const scaleTelemetry = telemetry["rubber-scale"];
  const furnaceTelemetry = telemetry["furnace-temperature"];
  const pondTempReading = pondTelemetry?.latest.water_temperature;
  const pondPhReading = pondTelemetry?.latest.water_ph;
  const pondHasTelemetry = Boolean(pondTempReading || pondPhReading);
  const pondTemp = pondTempReading?.value ?? latestPond?.value ?? 0;
  const pondPh = pondPhReading?.value ?? latestPond?.ph;
  const pondOutOfSpec = (pondTempReading ? classifyPondTemp(pondTemp).status === "RED" : false)
    || (pondPhReading ? pondPh < POND_PH_SPEC.min || pondPh > POND_PH_SPEC.max : false);
  const pondStatus: Status = pondHasTelemetry
    ? pondTelemetry?.process_status ?? (pondOutOfSpec ? "RED" : "GREEN")
    : latestPond?.status ?? "SENSOR_ERROR";
  const pondSensorState = pondHasTelemetry ? telemetryState(pondTelemetry?.data_status) : "DEMO";
  const pondUpdatedAt = newestTimestamp(pondTempReading?.measured_at, pondPhReading?.measured_at) ?? latestPond?.measuredAt ?? now;
  const weightReading = scaleTelemetry?.latest.rubber_weight;
  const weightValue = weightReading?.value ?? latestWeight?.measurement.value;
  const weightStatus = weightReading
    ? scaleTelemetry?.process_status ?? classifyWeight(weightReading.value).status
    : latestWeight?.comparison.status ?? "SENSOR_ERROR";
  const weightDataState: DataState = weightReading ? telemetryState(scaleTelemetry?.data_status) : DEMO_SENSORS.weight ? "DEMO" : "NOT_INSTALLED";
  const weightUpdatedAt = weightReading ? Date.parse(weightReading.measured_at) : latestWeight?.measurement.measuredAt ?? now;
  const furnaceActual = furnaceTelemetry?.latest.furnace_temperature;
  const furnaceBurner = furnaceTelemetry?.latest.furnace_burner_temperature;
  const furnaceRecorder = furnaceTelemetry?.latest.furnace_recorder_temperature;
  const furnaceComplete = Boolean(furnaceActual && furnaceBurner && furnaceRecorder);
  const furnaceHasTelemetry = Boolean(furnaceActual || furnaceBurner || furnaceRecorder);
  const actualValue = furnaceActual?.value ?? latestTemp?.actual;
  const burnerValue = furnaceBurner?.value ?? latestTemp?.burner;
  const recorderValue = furnaceRecorder?.value ?? latestTemp?.recorder;
  const tempStatus: Status = furnaceComplete
    ? furnaceTelemetry?.process_status ?? classifyTemp(compareTemp(furnaceActual!.value, furnaceBurner!.value, furnaceRecorder!.value).worstError).status
    : furnaceHasTelemetry
      ? "SENSOR_ERROR"
      : latestTemp?.status ?? "SENSOR_ERROR";
  const furnaceDataState: DataState = furnaceComplete
    ? telemetryState(furnaceTelemetry?.data_status)
    : furnaceHasTelemetry
      ? "STALE"
      : DEMO_SENSORS.furnace ? "DEMO" : "NOT_INSTALLED";
  const furnaceUpdatedAt = newestTimestamp(furnaceActual?.measured_at, furnaceBurner?.measured_at, furnaceRecorder?.measured_at) ?? latestTemp?.measuredAt ?? now;
  const pondTrend = pondTelemetry?.history.filter((item) => item.metric === "water_temperature").map((item) => item.value) ?? [];
  const weightTrend = scaleTelemetry?.history.filter((item) => item.metric === "rubber_weight").map((item) => item.value) ?? [];
  const furnaceTrend = furnaceTelemetry?.history.filter((item) => item.metric === "furnace_temperature").map((item) => item.value) ?? [];
  const rackCamera = rackAI.status?.cameras[0];
  // รองรับทั้ง task id ใหม่และชื่อเดิม เผื่อ rack_ai ยังไม่ได้รีสตาร์ทด้วยเวอร์ชันใหม่
  const rackTask = rackCamera?.tasks.find((task) => task.task_id === "rack-counting" || task.task_id === "rubber-counting");
  const rackCount = rackTask?.latest?.rack_count ?? rackTask?.latest?.rubber_count;
  const rackTracks = rackTask?.latest?.active_tracks;
  const rackIsLive = rackAI.reachable && rackAI.status?.data_status === "live";
  // DVR บอกว่าช่องนี้ยังมีภาพเข้าไหม — ถ้าไม่มี ยอดที่หยุดนิ่งแปลว่ากล้องตาบอด
  // ไม่ใช่ว่าไม่มีเก๊ะผ่าน ซึ่งเป็นคนละเรื่องกันโดยสิ้นเชิง
  const rackSignal = rackCamera?.source_signal;
  const rackBlind = signalVerdict(rackSignal) === "blind";
  const rackDataState: DataState = rackAI.loading
    ? "STALE"
    : rackIsLive
      ? "LIVE"
      : rackAI.status?.data_status === "not_installed"
        ? "NOT_INSTALLED"
        : "OFFLINE";
  const rackUpdatedAt = rackCamera?.updated_at
    ? Date.parse(rackCamera.updated_at)
    : undefined;
  const pondCamera = pondAI.status?.cameras.find((camera) =>
    camera.tasks.some((task) => task.task_id === "work-area-presence" || task.task_id === "ppe-helmet"),
  );
  const pondAIDataState: DataState = pondAI.loading
    ? "STALE"
    : pondAI.reachable && (pondCamera?.data_status === "live" || pondCamera?.data_status === "pilot")
      ? "LIVE"
      : pondCamera?.data_status === "not_installed"
        ? "NOT_INSTALLED"
        : "OFFLINE";
  const h2sUpdatedAt = h2sSensor.latest ? Date.parse(h2sSensor.latest.captured_at) : undefined;
  const h2sDataState: DataState = h2sDataStateOf(h2sSensor);
  const h2sLevel = h2sSensor.online ? getH2sLevel(h2sSensor.latest?.h2s_ppm) : undefined;
  const recentEvents = events.slice(-5).reverse();
  const activeIncidents = stationAlerts.data_status === "live"
    ? stationAlerts.alerts.map((alert) => ({
        id: alert.alert_key,
        issue: alert.title,
        severity: alert.severity,
        owner: alert.owner,
        detectedAt: Date.parse(alert.opened_at),
        href: "/incidents",
      }))
    : simulatorIncidents.map((incident) => ({
        id: incident.id,
        issue: incident.issue,
        severity: incident.severity,
        owner: incident.owner,
        detectedAt: incident.detectedAt,
        href: `/incidents/${incident.id}`,
      }));

  if (process.env.NEXT_PUBLIC_PCC_LAYOUT !== "legacy") {
    const visionMonitorUrl = (() => {
      try {
        const url = new URL(RACK_MONITOR_URL);
        url.searchParams.set("station", "rack-infeed");
        url.hash = "ai-modules";
        return url.toString();
      } catch {
        return RACK_MONITOR_URL;
      }
    })();

    return <CommandCenterLayout
      updatedAt={Math.max(pondUpdatedAt, weightUpdatedAt, furnaceUpdatedAt, h2sUpdatedAt ?? 0)}
      pond={{
        temp: pondTemp || undefined,
        ph: pondPh,
        status: pondStatus,
        dataState: pondSensorState,
        aiState: pondAIDataState,
        trend: pondTrend.length ? pondTrend : pondSeries.slice(-40).map((item) => item.value),
      }}
      rack={{
        count: rackCount,
        tracks: rackTracks,
        status: rackBlind || !rackIsLive ? "SENSOR_ERROR" : "GREEN",
        dataState: rackDataState,
        model: rackTask?.model_version ?? undefined,
      }}
      odor={{
        value: h2sSensor.latest?.h2s_ppm,
        dataState: h2sDataState,
        updatedAt: h2sUpdatedAt,
      }}
      weight={{
        value: weightValue,
        status: weightStatus,
        dataState: weightDataState,
        target: WEIGHT_SPEC.target,
        trend: weightTrend.length ? weightTrend : weightSeries.slice(-40).map((item) => item.measurement.value),
      }}
      furnace={{
        actual: actualValue,
        burner: burnerValue,
        recorder: recorderValue,
        status: tempStatus,
        dataState: furnaceDataState,
        trend: furnaceTrend.length ? furnaceTrend : tempSeries.slice(-40).map((item) => item.actual),
      }}
      limits={{
        pondTempMax: POND_SPEC.max,
        pondPhMin: POND_PH_SPEC.min,
        pondPhMax: POND_PH_SPEC.max,
        pondTempUnit: POND_SPEC.unit,
        furnaceUnit: TEMP_SPEC.unit,
      }}
      incidents={activeIncidents}
      events={recentEvents}
      alertsLive={stationAlerts.data_status === "live"}
      visionMonitorUrl={visionMonitorUrl}
    />;
  }

  return <div className="space-y-5">
    <section className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div><h1 className="text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">ภาพรวมสายการผลิต LINE-1</h1><p className="mt-1 text-sm text-slate-500">สถานะจุดงานสำคัญจากเซ็นเซอร์และผลวิเคราะห์ของระบบ</p></div>
      <div className="flex items-center gap-2"><label htmlFor="shift" className="text-xs font-semibold text-slate-500">ช่วงเวลา</label><select id="shift" className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 outline-none focus:border-blue-500"><option>กะปัจจุบัน</option><option>วันนี้</option></select></div>
    </section>

    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_310px]">
      <div className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <StationHeader icon="pond" title="บ่อสุดท้าย" href="/stations/final-pond" status={pondStatus} />
            <div className="grid gap-2 p-4 sm:grid-cols-[0.9fr_1.1fr] sm:p-5"><div className="mx-auto h-32 w-full max-w-[240px]"><PondGraphic temp={pondTemp || undefined} ph={pondPh} tone={toneOf(pondStatus)} /></div><div className="grid grid-cols-2 gap-2 self-center">
              <div className="rounded-xl bg-slate-50 p-3"><span className="text-xs font-semibold text-slate-500">อุณหภูมิ</span><p className="mt-1 text-3xl font-black tabular-nums text-slate-950">{pondTemp ? pondTemp.toFixed(1) : "—"}<span className="ml-1 text-sm text-slate-500">{POND_SPEC.unit}</span></p><p className="mt-1 text-[10px] text-slate-400">เกณฑ์ ≤{POND_SPEC.max}°C</p></div>
              <div className="rounded-xl bg-slate-50 p-3"><span className="text-xs font-semibold text-slate-500">ค่า pH</span><p className="mt-1 text-3xl font-black tabular-nums text-slate-950">{pondPh?.toFixed(2) ?? "—"}</p><p className="mt-1 text-[10px] text-slate-400">เกณฑ์ {POND_PH_SPEC.min}–{POND_PH_SPEC.max}</p></div>
            </div></div>
            <div className="mx-4 mb-4 flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 sm:mx-5"><div className="flex min-w-0 items-center gap-2"><FactoryIcon name="camera" className="size-4 shrink-0 text-slate-500"/><div className="min-w-0"><p className="truncate text-xs font-bold text-slate-800">AI ตรวจสถานะการทำงานของคนงาน</p><p className="text-[10px] text-slate-400">รับเฉพาะผลวิเคราะห์ ไม่โหลดภาพกล้อง</p></div></div><DataStatus state={pondAIDataState}/></div>
            <Freshness at={pondUpdatedAt} state={pondSensorState} />
          </section>

          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <StationHeader icon="conveyor" title="หอโรยยาง · นับเก๊ะเข้าเตา" href="/stations/rack-infeed" status={rackBlind || !rackIsLive ? "SENSOR_ERROR" : "GREEN"} />
            <div className="p-4 sm:p-5"><div className="flex items-center gap-5"><div className="hidden h-32 min-w-0 flex-1 sm:block"><RackInfeedGraphic live={rackIsLive} blind={rackBlind} tracking={rackTracks} /></div><div className="min-w-[165px]"><p className="text-xs font-semibold text-slate-500">จำนวนเก๊ะสะสม</p><p className="mt-1 text-5xl font-black tabular-nums tracking-tight text-slate-950">{rackCount ?? "—"}<span className="ml-1.5 text-base text-slate-500">เก๊ะ</span></p><p className="mt-3 text-xs text-slate-500">วัตถุที่กำลังติดตาม <strong className="text-slate-900">{rackTracks ?? "—"}</strong></p></div></div>
              {rackBlind && <div className="mt-4 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-3"><FactoryIcon name="incident" className="mt-0.5 size-4 shrink-0 text-red-600"/><div className="min-w-0"><p className="text-xs font-black text-red-800">กล้องไม่มีสัญญาณเข้าเครื่องบันทึก</p><p className="mt-1 text-[11px] leading-relaxed text-red-700">ยอดนับที่หยุดนิ่งมาจากการที่กล้องมองไม่เห็น ไม่ใช่เพราะไม่มีเก๊ะผ่าน ตรวจสายกล้อง Camera 09 ที่เครื่องบันทึก{rackSignal?.checked_at ? ` · ตรวจเมื่อ ${fmtTime(Date.parse(rackSignal.checked_at))}` : ""}</p></div></div>}
              <div className="mt-4 flex flex-col gap-3 rounded-xl border border-blue-100 bg-blue-50/60 p-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-xs font-bold text-blue-950">ผลจาก Vision Monitor</p><div className="mt-1 flex flex-wrap items-center gap-2"><DataStatus state={rackDataState}/><span className="text-[10px] text-blue-700">{rackTask?.model_version ? `โมเดล ${rackTask.model_version}` : "ยังไม่ได้รับข้อมูลจากโมเดล"}</span></div></div><a href={RACK_MONITOR_URL} target="_blank" rel="noreferrer" className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-lg border border-blue-300 bg-white px-3 text-xs font-bold text-blue-700 transition hover:bg-blue-50"><FactoryIcon name="camera" className="size-4" />เปิด Vision Monitor</a></div>
            </div><Freshness at={Number.isNaN(rackUpdatedAt) ? undefined : rackUpdatedAt} state={rackDataState} />
          </section>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><StationHeader icon="odor" title="ตรวจจับกลิ่นเหม็นของยาง" href="/stations/rubber-odor" status={h2sLevel?.status ?? "SENSOR_ERROR"}/><div className="px-5 py-5"><FactoryIcon name="odor" className="mx-auto size-9 text-violet-500"/><p className="mt-3 text-xs font-semibold text-slate-500">ก๊าซไฮโดรเจนซัลไฟด์</p><p className="mt-1 text-4xl font-black tabular-nums text-slate-950">{h2sSensor.latest?.h2s_ppm.toFixed(1) ?? "—"}<span className="ml-1 text-sm text-slate-500">ppm</span></p>{h2sLevel ? <div className="mt-2 flex justify-center"><H2sStatus level={h2sLevel} /></div> : null}</div><Freshness at={h2sUpdatedAt} state={h2sDataState} /></section>
          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><StationHeader icon="scale" title="ตาชั่งน้ำหนักยาง" href="/stations/rubber-scale" status={weightStatus}/><div className="px-5 py-5"><div className="mx-auto mb-3 h-24 w-full max-w-[200px]"><ScaleGraphic value={weightValue} tone={toneOf(weightStatus)} /></div><p className="text-xs font-semibold text-slate-500">น้ำหนักยางล่าสุด</p><p className="mt-1 text-4xl font-black tabular-nums text-slate-950">{weightValue?.toFixed(2) ?? "—"}<span className="ml-1 text-sm text-slate-500">kg</span></p><div className="mt-4 flex justify-between border-t border-slate-100 pt-3 text-xs"><span className="text-slate-400">เป้าหมาย</span><strong>{WEIGHT_SPEC.target.toFixed(2)} kg</strong></div></div><Freshness at={weightUpdatedAt} state={weightDataState}/></section>
          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><StationHeader icon="thermometer" title="อุณหภูมิเตา" href="/stations/furnace-temperature" status={tempStatus}/><div className="divide-y divide-slate-100 px-5 py-3">{[["Digital Thermometer",actualValue],["Burner",burnerValue],["Recorder",recorderValue]].map(([label,value]) => <div key={String(label)} className="flex items-center justify-between py-2.5"><span className="text-xs font-semibold text-slate-500">{label}</span><strong className="text-lg tabular-nums text-slate-950">{typeof value === "number" ? value.toFixed(1) : "—"}<span className="ml-1 text-[10px] text-slate-400">{TEMP_SPEC.unit}</span></strong></div>)}</div><Freshness at={furnaceUpdatedAt} state={furnaceDataState}/></section>
        </div>

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-4"><div><h2 className="flex items-center gap-2 text-sm font-extrabold text-slate-900"><FactoryIcon name="activity" className="size-4 text-blue-600"/>แนวโน้มการผลิต</h2><p className="mt-1 text-[10px] text-slate-400">เปรียบเทียบค่าล่าสุดจากจุดสำคัญในมุมมองเดียว</p></div><Link href="/reports" className="text-xs font-bold text-blue-700 hover:underline">ดูรายงาน →</Link></div><div className="grid md:grid-cols-3"><TrendMini label="อุณหภูมิบ่อ" value={pondTemp ? pondTemp.toFixed(1) : "—"} unit="°C" values={pondTrend.length ? pondTrend : pondSeries.slice(-40).map((item) => item.value)} color="#0891b2"/><TrendMini label="น้ำหนักยาง" value={weightValue?.toFixed(2) ?? "—"} unit="kg" values={weightTrend.length ? weightTrend : weightSeries.slice(-40).map((item) => item.measurement.value)} color="#2563eb"/><TrendMini label="อุณหภูมิเตา" value={actualValue?.toFixed(1) ?? "—"} unit="°C" values={furnaceTrend.length ? furnaceTrend : tempSeries.slice(-40).map((item) => item.actual)} color="#059669"/></div></section>
      </div>

      <aside className="space-y-4">
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="flex items-center justify-between border-b border-slate-100 px-4 py-3.5"><div><h2 className="flex items-center gap-2 text-sm font-extrabold"><FactoryIcon name="incident" className="size-4 text-red-500"/>เหตุการณ์ที่ต้องดำเนินการ</h2><p className="mt-1 text-[10px] text-slate-400">{stationAlerts.data_status === "live" ? "Rule Engine ฝั่งเซิร์ฟเวอร์" : "ข้อมูลจำลองระหว่างรอฐานข้อมูล"}</p></div><span className="text-xs font-bold text-red-600">{activeIncidents.length}</span></div><div className="divide-y divide-slate-100">{activeIncidents.length ? activeIncidents.slice(0,3).map(item => <Link key={item.id} href={item.href} className="block p-4 transition hover:bg-slate-50"><div className="flex gap-3"><span className={`mt-1 size-2 shrink-0 rounded-full ${item.severity === "CRITICAL" ? "bg-red-500" : "bg-amber-500"}`}/><div className="min-w-0"><p className="text-xs font-bold text-slate-800">{item.issue}</p><p className="mt-1 text-[10px] text-slate-400">{item.owner} · {fmtTime(item.detectedAt)}</p></div></div></Link>) : <div className="px-4 py-8 text-center text-xs text-slate-400">ไม่มีเหตุการณ์ค้าง</div>}</div><Link href="/incidents" className="block border-t border-slate-100 px-4 py-3 text-center text-xs font-bold text-blue-700 hover:bg-blue-50">ดูเหตุการณ์ทั้งหมด</Link></section>
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="border-b border-slate-100 px-4 py-3.5"><h2 className="flex items-center gap-2 text-sm font-extrabold"><FactoryIcon name="activity" className="size-4 text-blue-600"/>กิจกรรมล่าสุด</h2></div><ol className="relative mx-4 my-4 border-l border-slate-200 pl-4">{recentEvents.map(event => <li key={event.id} className="relative pb-4 last:pb-0"><span className={`absolute -left-[21px] top-1 size-2.5 rounded-full border-2 border-white ${event.level === "RED" ? "bg-red-500" : event.level === "YELLOW" ? "bg-amber-500" : "bg-blue-500"}`}/><p className="text-[11px] font-semibold leading-relaxed text-slate-700">{event.message}</p><p className="mt-0.5 text-[10px] text-slate-400">{fmtTime(event.at)}</p></li>)}</ol></section>
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-4 py-3.5"><h2 className="text-sm font-extrabold text-slate-900">รายงานที่เกี่ยวข้อง</h2></div>
          <div className="divide-y divide-slate-100">
            <Link href="/reports" className="flex items-center gap-3 px-4 py-3 text-xs font-bold text-slate-700 transition hover:bg-blue-50 hover:text-blue-700"><span className="grid size-8 place-items-center rounded-lg bg-blue-50 text-blue-700"><FactoryIcon name="activity" className="size-4"/></span><span className="flex-1">รายงานการนับเก๊ะรายกะ</span><FactoryIcon name="chevron" className="size-4"/></Link>
            <Link href="/devices" className="flex items-center gap-3 px-4 py-3 text-xs font-bold text-slate-700 transition hover:bg-blue-50 hover:text-blue-700"><span className="grid size-8 place-items-center rounded-lg bg-slate-100 text-slate-600"><FactoryIcon name="device" className="size-4"/></span><span className="flex-1">สถานะอุปกรณ์และการเชื่อมต่อ</span><FactoryIcon name="chevron" className="size-4"/></Link>
          </div>
        </section>
      </aside>
    </div>
  </div>;
}
