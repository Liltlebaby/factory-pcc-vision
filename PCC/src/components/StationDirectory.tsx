"use client";

import Link from "next/link";
import { DEMO_SENSORS, POND_PH_SPEC, POND_SPEC, TEMP_SPEC, WEIGHT_SPEC } from "@/lib/config";
import { STATIONS } from "@/lib/stations";
import { useStore } from "@/lib/store";
import { useStationAIStatus } from "@/lib/use-station-ai-status";
import type { Status } from "@/lib/types";
import { FactoryIcon } from "./FactoryIcon";
import { DataStatus, H2sStatus, ProcessStatus, type DataState } from "./StatusMark";
import { getH2sLevel } from "@/lib/h2s-levels";
import { h2sDataState } from "@/lib/h2s-state";
import { useH2sSensor } from "@/lib/use-h2s-sensor";

export function StationDirectory() {
  const { latestPond, latestTemp, latestWeight } = useStore();
  // ยอดเก๊ะต้องมาจากกล้องนับจริง ของเดิมหยิบ lotNo ของตาชั่งมาแสดงเป็นจำนวนก้อน
  // ซึ่งเป็นคนละค่ากันคนละจุดงาน
  const rackAI = useStationAIStatus("rack-infeed", 10000, null);
  const rackTask = rackAI.status?.cameras[0]?.tasks.find(
    (task) => task.task_id === "rack-counting" || task.task_id === "rubber-counting",
  );
  const rackCount = rackTask?.latest?.rack_count ?? rackTask?.latest?.rubber_count;
  const rackLive = rackAI.reachable && rackAI.status?.data_status === "live";

  const h2s = useH2sSensor(5_000);
  const h2sLevel = h2s.online ? getH2sLevel(h2s.latest?.h2s_ppm) : undefined;

  const stationData: Record<string, { value: string; hint: string; status: Status; installed: boolean; badge?: React.ReactNode; state?: DataState }> = {
    "final-pond": {
      value: latestPond ? `${latestPond.value.toFixed(1)}°C · pH ${latestPond.ph?.toFixed(2) ?? "—"}` : "—",
      hint: `เกณฑ์ ≤${POND_SPEC.max}°C · pH ${POND_PH_SPEC.min}–${POND_PH_SPEC.max}`,
      status: latestPond?.status ?? "SENSOR_ERROR",
      installed: true,
    },
    "rack-infeed": {
      value: rackCount === undefined ? "—" : `${rackCount} เก๊ะ`,
      hint: "ยอดสะสมจากกล้องนับเก๊ะก่อนเข้าเตา",
      status: rackLive ? "GREEN" : "SENSOR_ERROR",
      installed: true,
    },
    "rubber-odor": {
      value: h2s.latest ? `${h2s.latest.h2s_ppm.toFixed(1)} ppm` : "—",
      hint: h2sLevel?.action ?? h2sLevel?.meaning ?? "H₂S · เกณฑ์ 0.5 / 1 / 5 / 10 ppm",
      status: h2sLevel?.status ?? "SENSOR_ERROR",
      installed: true,
      badge: h2sLevel ? <H2sStatus level={h2sLevel} /> : undefined,
      state: h2sDataState(h2s),
    },
    "rubber-scale": {
      value: latestWeight ? `${latestWeight.measurement.value.toFixed(2)} kg` : "—",
      hint: `เป้าหมาย ${WEIGHT_SPEC.target.toFixed(2)} kg`,
      status: latestWeight?.comparison.status ?? "SENSOR_ERROR",
      installed: DEMO_SENSORS.weight,
    },
    "furnace-temperature": {
      value: latestTemp ? `${latestTemp.actual.toFixed(1)}°C` : "—",
      hint: `ค่าอ้างอิง ${TEMP_SPEC.target.toFixed(1)}°C`,
      status: latestTemp?.status ?? "SENSOR_ERROR",
      installed: DEMO_SENSORS.furnace,
    },
  };

  return (
    <div className="space-y-5">
      <header className="px-1 sm:px-0">
        <p className="text-xs font-black uppercase tracking-[0.16em] text-blue-700">Factory stations</p>
        <h1 className="mt-1 text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">จุดตรวจในโรงงาน</h1>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-slate-500">แต่ละหน้าแสดงเฉพาะข้อมูลที่เกี่ยวข้องกับจุดงานนั้น เพื่อให้ตรวจสถานะและตัดสินใจได้เร็ว</p>
      </header>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {STATIONS.map((station) => {
          const data = stationData[station.id];
          return (
            <Link key={station.id} href={`/stations/${station.id}`} className="group flex min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">
              {/* ส่วนหัวยืดได้ตามความยาวคำอธิบาย แถบค่าและแถบท้ายจึงตรงกันทุกใบในแถวเดียวกัน */}
              <div className="flex flex-1 items-start gap-3 p-4 sm:p-5">
                <span className={`grid size-11 shrink-0 place-items-center rounded-xl ${data.installed ? "bg-blue-50 text-blue-700" : "bg-slate-100 text-slate-400"}`}><FactoryIcon name={station.icon} className="size-6" /></span>
                <div className="min-w-0 flex-1"><h2 className="font-black leading-snug text-slate-950 group-hover:text-blue-700">{station.name}</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">{station.description}</p></div>
                <FactoryIcon name="chevron" className="mt-1 size-4 shrink-0 text-slate-300 group-hover:text-blue-600" />
              </div>
              <div className="border-y border-slate-100 bg-slate-50/70 px-4 py-4 sm:px-5">
                <div className="flex min-h-9 flex-col items-start gap-2 sm:flex-row sm:items-end sm:justify-between sm:gap-3">
                  {/* ช่องนี้สงวนไว้ให้ค่าที่วัดได้ ข้อความบอกสถานะจึงไม่ควรใช้ขนาดเดียวกับตัวเลข
                      ไม่งั้น "รอติดตั้ง" จะเด่นกว่าค่าจริงของจุดงานข้าง ๆ */}
                  {data.installed && data.value !== "—"
                    ? <strong className="max-w-full break-words text-[clamp(1.25rem,5vw,1.5rem)] font-black leading-tight tabular-nums text-slate-950">{data.value}</strong>
                    : <span className="text-sm font-bold text-slate-400">{data.installed ? "ยังไม่มีข้อมูล" : data.value}</span>}
                  {data.badge ?? <ProcessStatus status={data.status} />}
                </div>
                <p className="mt-2 text-[11px] leading-relaxed text-slate-500">{data.hint}</p>
              </div>
              <div className="flex min-h-12 items-center justify-between gap-2 px-4 py-3 sm:px-5"><DataStatus state={data.state ?? (data.installed ? "DEMO" : "NOT_INSTALLED")} /><span className="shrink-0 text-[11px] font-bold text-blue-700">เปิดรายละเอียด</span></div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
