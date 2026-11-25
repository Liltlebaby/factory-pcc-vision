"use client";

import { useStore } from "@/lib/store";
import { Panel } from "./ui";

function Bar({
  label,
  percent,
  from,
  to,
}: {
  label: string;
  percent: number;
  from: string;
  to: string;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="font-semibold text-slate-600">{label}</span>
        <span className="font-bold tabular-nums text-slate-900">
          {percent.toFixed(1)}%
        </span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${from} ${to} transition-all duration-500`}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
    </div>
  );
}

function Stat({
  value,
  label,
  tone,
}: {
  value: number;
  label: string;
  tone: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200/70 bg-slate-50/80 px-2 py-2.5 text-center">
      <p className={`text-xl font-extrabold tabular-nums ${tone}`}>{value}</p>
      <p className="text-[10px] font-medium text-slate-500">{label}</p>
    </div>
  );
}

export function ProcessHealth() {
  const {
    weightHealth,
    tempHealth,
    pondHealth,
    activeIncidents,
    closedIncidents,
    weightSeries,
  } = useStore();

  return (
    <Panel title="Process Health" icon="📊">
      <div className="space-y-3.5">
        <Bar
          label="Weight"
          percent={weightHealth}
          from="from-blue-500"
          to="to-sky-400"
        />
        <Bar
          label="Temperature"
          percent={tempHealth}
          from="from-sky-500"
          to="to-cyan-400"
        />
        <Bar
          label="Final Pond ≤ 35°C"
          percent={pondHealth}
          from="from-cyan-500"
          to="to-blue-500"
        />
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2">
        <Stat
          value={activeIncidents.length}
          label="Incident ค้าง"
          tone="text-red-600"
        />
        <Stat
          value={closedIncidents.length}
          label="ปิดแล้ว"
          tone="text-emerald-600"
        />
        <Stat
          value={weightSeries.length}
          label="ก้อนที่ชั่ง"
          tone="text-slate-900"
        />
      </div>
    </Panel>
  );
}
