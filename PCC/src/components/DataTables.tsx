"use client";

import { FURNACE, POND_SPEC, STATUS_META, TEMP_SPEC } from "@/lib/config";
import { fmtTime } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { Status } from "@/lib/types";
import { Panel, RuleTag } from "./ui";

function StatusCell({ status }: { status: Status }) {
  const meta = STATUS_META[status];
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${meta.bg} ${meta.text}`}
    >
      {status}
    </span>
  );
}

const TH =
  "py-2.5 pr-3 text-[10px] font-bold tracking-wider text-slate-400 uppercase whitespace-nowrap";
const TD = "py-2 pr-3 whitespace-nowrap";

export function DataTables() {
  const { weightSeries, tempSeries, pondSeries } = useStore();
  const weightRows = [...weightSeries].reverse().slice(0, 12);
  const tempRows = [...tempSeries].reverse().slice(0, 12);
  const pondRows = [...pondSeries].reverse().slice(0, 12);

  return (
    <div className="space-y-3 sm:space-y-4">
      <Panel title="โครงสร้างข้อมูลกลาง" icon="🗄️">
        <div className="grid gap-3 lg:grid-cols-2">
          <div className="overflow-x-auto rounded-xl border border-slate-100 bg-slate-50/70 p-3">
            <pre className="font-mono text-[11px] leading-relaxed text-slate-600">
              {`production_lines
  └── furnaces
        ├── weighing_scales
        ├── burners
        ├── recorders
        └── final_pond_sensors
  └── work_orders
        └── lots`}
            </pre>
          </div>
          <ul className="space-y-2 text-xs">
            <li className="rounded-xl border border-blue-100 bg-blue-50/60 px-3 py-2">
              <span className="font-mono font-bold text-blue-700">
                measurements
              </span>
              <span className="text-slate-600">
                {" "}
                — ค่าดิบจากเครื่อง (WEIGHT / TEMPERATURE / POND_TEMPERATURE)
              </span>
            </li>
            <li className="rounded-xl border border-blue-100 bg-blue-50/60 px-3 py-2">
              <span className="font-mono font-bold text-blue-700">
                comparisons
              </span>
              <span className="text-slate-600">
                {" "}
                — ค่าที่ระบบคำนวณแล้ว (delta, status, rule_code)
              </span>
            </li>
            <li className="rounded-xl border border-blue-100 bg-blue-50/60 px-3 py-2">
              <span className="font-mono font-bold text-blue-700">
                incidents
              </span>
              <span className="text-slate-600">
                {" "}
                — Workflow กลาง + SLA + Audit Log
              </span>
            </li>
          </ul>
        </div>
      </Panel>

      <Panel
        title="measurements + comparisons · FINAL POND"
        icon="🌊"
        bodyClassName="p-3 sm:p-5"
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200">
                <th className={TH}>measured_at</th>
                <th className={TH}>location</th>
                <th className={TH}>source</th>
                <th className={TH}>value</th>
                <th className={TH}>upper_limit</th>
                <th className={TH}>margin</th>
                <th className={TH}>status</th>
                <th className={TH}>rule_code</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono">
              {pondRows.map((row) => (
                <tr key={row.tick} className="transition hover:bg-cyan-50/50">
                  <td className={`${TD} text-slate-400`}>
                    {fmtTime(row.measuredAt)}
                  </td>
                  <td className={`${TD} text-slate-600`}>{POND_SPEC.name}</td>
                  <td className={`${TD} text-slate-400`}>POND_SENSOR</td>
                  <td className={`${TD} font-bold tabular-nums text-slate-900`}>
                    {row.value.toFixed(1)}°C
                  </td>
                  <td className={`${TD} tabular-nums text-slate-600`}>
                    ≤ {POND_SPEC.max.toFixed(0)}°C
                  </td>
                  <td className={`${TD} tabular-nums text-slate-700`}>
                    {(POND_SPEC.max - row.value).toFixed(1)}°C
                  </td>
                  <td className={TD}>
                    <StatusCell status={row.status} />
                  </td>
                  <td className={TD}>
                    <RuleTag code={row.ruleCode} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2.5 text-[10px] text-slate-400">
          เกณฑ์ควบคุมอุณหภูมิบ่อสุดท้ายต้องไม่เกิน {POND_SPEC.max}°C ·
          สถานะ WARNING เริ่มเมื่อเหลือระยะห่างไม่เกิน {POND_SPEC.warningMargin}°C
        </p>
      </Panel>

      <Panel
        title="measurements + comparisons · WEIGHT"
        icon="⚖️"
        action={
          <span className="text-[10px] text-slate-400 lg:hidden">
            ← เลื่อนตารางแนวนอนได้
          </span>
        }
        bodyClassName="p-3 sm:p-5"
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200">
                <th className={TH}>measured_at</th>
                <th className={TH}>lot_id</th>
                <th className={TH}>source</th>
                <th className={TH}>value</th>
                <th className={TH}>reference</th>
                <th className={TH}>delta</th>
                <th className={TH}>limits</th>
                <th className={TH}>status</th>
                <th className={TH}>rule_code</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono">
              {weightRows.map((row) => (
                <tr
                  key={row.measurement.id}
                  className="transition hover:bg-blue-50/40"
                >
                  <td className={`${TD} text-slate-400`}>
                    {fmtTime(row.measurement.measuredAt)}
                  </td>
                  <td className={`${TD} text-slate-600`}>
                    {row.measurement.lotId}
                  </td>
                  <td className={`${TD} text-slate-400`}>SCALE</td>
                  <td className={`${TD} font-bold tabular-nums text-slate-900`}>
                    {row.measurement.value.toFixed(2)} kg
                  </td>
                  <td className={`${TD} tabular-nums text-slate-400`}>
                    {row.comparison.referenceValue.toFixed(2)}
                  </td>
                  <td className={`${TD} tabular-nums text-slate-700`}>
                    {row.comparison.delta > 0 ? "+" : ""}
                    {row.comparison.delta.toFixed(2)}
                  </td>
                  <td className={`${TD} tabular-nums text-slate-400`}>
                    {row.comparison.lowerLimit.toFixed(2)}–
                    {row.comparison.upperLimit.toFixed(2)}
                  </td>
                  <td className={TD}>
                    <StatusCell status={row.comparison.status} />
                  </td>
                  <td className={TD}>
                    <RuleTag code={row.comparison.ruleCode} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2.5 text-[10px] text-slate-400">
          furnace_id = {FURNACE.id} · work_order_id = {FURNACE.workOrderId}
        </p>
      </Panel>

      <Panel
        title="measurements + comparisons · TEMPERATURE"
        icon="🌡️"
        action={
          <span className="text-[10px] text-slate-400 lg:hidden">
            ← เลื่อนตารางแนวนอนได้
          </span>
        }
        bodyClassName="p-3 sm:p-5"
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200">
                <th className={TH}>measured_at</th>
                <th className={TH}>actual (ref)</th>
                <th className={TH}>burner</th>
                <th className={TH}>Δ burner</th>
                <th className={TH}>recorder</th>
                <th className={TH}>Δ recorder</th>
                <th className={TH}>worst error</th>
                <th className={TH}>swing 15m</th>
                <th className={TH}>status</th>
                <th className={TH}>rule_code</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono">
              {tempRows.map((row) => (
                <tr key={row.tick} className="transition hover:bg-blue-50/40">
                  <td className={`${TD} text-slate-400`}>
                    {fmtTime(row.measuredAt)}
                  </td>
                  <td className={`${TD} font-bold tabular-nums text-slate-900`}>
                    {row.actual.toFixed(1)}
                  </td>
                  <td className={`${TD} tabular-nums text-slate-600`}>
                    {row.burner.toFixed(1)}
                  </td>
                  <td className={`${TD} tabular-nums text-slate-700`}>
                    {row.deltaBurner > 0 ? "+" : ""}
                    {row.deltaBurner.toFixed(1)}
                  </td>
                  <td className={`${TD} tabular-nums text-slate-600`}>
                    {row.recorder.toFixed(1)}
                  </td>
                  <td className={`${TD} tabular-nums text-slate-700`}>
                    {row.deltaRecorder > 0 ? "+" : ""}
                    {row.deltaRecorder.toFixed(1)}
                  </td>
                  <td className={`${TD} font-bold tabular-nums text-slate-900`}>
                    {row.worstError > 0 ? "+" : ""}
                    {row.worstError.toFixed(1)}
                  </td>
                  <td
                    className={`${TD} tabular-nums ${
                      row.swing15 > TEMP_SPEC.swingLimit
                        ? "font-bold text-amber-600"
                        : "text-slate-400"
                    }`}
                  >
                    {row.swing15.toFixed(1)}
                  </td>
                  <td className={TD}>
                    <StatusCell status={row.status} />
                  </td>
                  <td className={TD}>
                    <RuleTag code={row.ruleCode} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2.5 text-[10px] leading-relaxed text-slate-400">
          Recorder ใช้เครื่องเดิมของบริษัท ดึงเป็น Time Series
          เข้าฐานข้อมูลกลาง ไม่ต้องซื้อใหม่ · Swing = MAX − MIN ใน{" "}
          {TEMP_SPEC.swingWindowMinutes} นาที
        </p>
      </Panel>
    </div>
  );
}
