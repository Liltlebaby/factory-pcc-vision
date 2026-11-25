"use client";

import { STATUS_META, WEIGHT_SPEC } from "@/lib/config";
import { useStore } from "@/lib/store";
import { Sparkline } from "./Sparkline";
import { Metric, Panel, RuleTag, StatusBadge } from "./ui";

export function WeightCard() {
  const { latestWeight, weightSeries } = useStore();
  const spec = WEIGHT_SPEC;

  if (!latestWeight) {
    return (
      <Panel title="Function 01 · Biscuit Weight" icon="⚖️">
        <p className="py-6 text-center text-sm text-slate-400">
          รอข้อมูลจากตาชั่งหน้าเตา…
        </p>
      </Panel>
    );
  }

  const value = latestWeight.measurement.value;
  const status = latestWeight.comparison.status;
  const meta = STATUS_META[status];
  const deviation = latestWeight.deviation;
  const last10 = weightSeries.slice(-10);
  const mean10 =
    last10.reduce((sum, s) => sum + s.measurement.value, 0) / last10.length;

  // ค่าที่เอาไปวาดกราฟ — ค่าเซ็นเซอร์ผิดปกติแทนด้วย Target เพื่อไม่ให้กราฟกระโดด
  const chartValues = weightSeries.map((s) =>
    s.comparison.status === "SENSOR_ERROR" ? spec.target : s.measurement.value,
  );

  // ตำแหน่งของค่าปัจจุบันบนแถบเกณฑ์ LSL–USL
  const positionPercent = Math.min(
    Math.max(((value - spec.lsl) / (spec.usl - spec.lsl)) * 100, 0),
    100,
  );
  const platformOffset = Math.min(
    Math.max(Math.abs(deviation) * 5, 0),
    3,
  );

  return (
    <Panel
      title="Function 01 · Biscuit Weight"
      icon="⚖️"
      action={<StatusBadge status={status} />}
    >
      <div className="grid items-center gap-4 sm:grid-cols-[minmax(0,1fr)_150px] lg:grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_150px]">
        {/* @container: ให้ตัวเลขบนจอย่อตามความกว้างของตาชั่งเอง ไม่ใช่ตามความ
            กว้างของหน้าจอ เพราะการ์ดนี้ถูกวางในคอลัมน์ที่กว้างไม่เท่ากันในแต่ละ
            breakpoint ตัวเลขจึงล้นจอตาชั่งเมื่อคอลัมน์แคบ */}
        <div
          className="@container relative mx-auto h-44 w-full max-w-[280px]"
          role="img"
          aria-label={`ตาชั่งบิสกิตแสดงน้ำหนัก ${value.toFixed(2)} กิโลกรัม`}
        >
          <div
            className="absolute inset-x-7 top-1 transition-transform duration-500 ease-out"
            style={{ transform: `translateY(${platformOffset}px)` }}
          >
            <div className="mx-auto flex h-9 w-[72%] items-end justify-center gap-1 rounded-t-lg border border-amber-300 bg-gradient-to-b from-amber-100 to-amber-300 px-3 pb-1 shadow-sm">
              {[0, 1, 2, 3, 4].map((item) => (
                <span
                  key={item}
                  className="h-5 flex-1 rounded-sm border border-amber-400/70 bg-amber-200 shadow-inner"
                />
              ))}
            </div>
            <div className="h-3 rounded-[50%] border border-slate-400 bg-gradient-to-b from-slate-100 to-slate-400 shadow-md" />
          </div>

          <div className="absolute top-[3.25rem] left-1/2 h-6 w-8 -translate-x-1/2 bg-gradient-to-r from-slate-400 via-slate-100 to-slate-400" />
          {/* ตัวเรือนตาชั่ง — inset แคบลงจากเดิมเพื่อให้จอมีที่พอสำหรับตัวเลข */}
          <div className="absolute inset-x-7 top-[4.4rem] bottom-0 rounded-[1.5rem] border border-slate-300 bg-gradient-to-br from-slate-100 via-white to-slate-300 p-3 shadow-[0_12px_24px_-14px_rgba(15,23,42,.65)]">
            <div className="overflow-hidden rounded-xl border-4 border-slate-700 bg-slate-950 px-2.5 py-2 text-center shadow-inner">
              <p className="text-[9px] font-semibold tracking-[0.18em] text-emerald-400 uppercase">
                Net weight
              </p>
              {/* ตัวเลขกับหน่วยวางเป็นแถวเดียว ไม่ตัดบรรทัด และไม่ใส่ tracking
                  เพิ่ม เพราะฟอนต์ mono กว้างคงที่อยู่แล้ว การเพิ่มระยะห่าง
                  ทำให้ตัวเลขล้นจอตาชั่งเมื่อการ์ดถูกบีบให้แคบ */}
              <p className="flex items-baseline justify-center gap-1 whitespace-nowrap font-mono text-[1.75rem] leading-none font-black tabular-nums text-emerald-300 @max-[250px]:text-[1.45rem] @max-[210px]:text-[1.2rem] [text-shadow:0_0_8px_rgba(110,231,183,.55)]">
                {status === "SENSOR_ERROR" ? "--.--" : value.toFixed(2)}
                <span className="text-xs font-bold text-emerald-500">kg</span>
              </p>
            </div>
            <div className="mt-2 flex items-center justify-between px-1">
              <span className="text-[9px] font-bold tracking-wide text-slate-500">INDUSTRIAL SCALE</span>
              <span
                className="size-2.5 rounded-full shadow-[0_0_7px_currentColor]"
                style={{ backgroundColor: meta.hex, color: meta.hex }}
              />
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-100 bg-slate-50/70 p-3 text-center sm:text-right lg:text-center 2xl:text-right">
          <p className="text-[11px] text-slate-500">ห่าง Target</p>
          <p className={`text-2xl font-bold tabular-nums ${meta.text}`}>
            {deviation > 0 ? "+" : ""}{deviation.toFixed(2)}
            <span className="ml-0.5 text-xs font-semibold text-slate-400">kg</span>
          </p>
          <p className="mt-1 text-[10px] leading-relaxed text-slate-400">
            เฉลี่ย 10 ก้อน<br />{mean10.toFixed(2)} kg
          </p>
          <div className="mt-2 flex flex-wrap justify-center gap-1 sm:justify-end lg:justify-center 2xl:justify-end">
            <RuleTag code={latestWeight.comparison.ruleCode} />
          </div>
        </div>
      </div>

      <p className="mt-1 flex flex-wrap items-center justify-center gap-x-2 text-[11px] text-slate-500">
        <span>{latestWeight.measurement.lotId}</span>
        <span className="text-slate-300">·</span>
        <span>ก้อนที่ {latestWeight.lotNo}</span>
      </p>

      {/* แถบเกณฑ์ LSL — Target — USL */}
      <div className="mt-5">
        <div className="relative h-2.5 rounded-full bg-amber-200/80 ring-1 ring-red-300/70 ring-offset-1 ring-offset-white">
          <div className="absolute inset-y-0 left-1/4 right-1/4 bg-emerald-300" />
          <div
            className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-white shadow-md transition-all duration-500"
            style={{
              left: `${positionPercent}%`,
              backgroundColor: meta.hex,
            }}
          />
        </div>
        <div className="mt-2 flex justify-between text-[10px] font-semibold tabular-nums text-slate-400">
          <span>LSL {spec.lsl.toFixed(2)}</span>
          <span className="text-emerald-600">
            Target {spec.target.toFixed(2)}
          </span>
          <span>USL {spec.usl.toFixed(2)}</span>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        <Metric
          label="แถบเตือน"
          value={`±${spec.warningBand.toFixed(2)}`}
          hint={`${(spec.target - spec.warningBand).toFixed(2)}–${(spec.target + spec.warningBand).toFixed(2)} kg`}
        />
        <Metric label="เกรด" value="AJ2" hint="17.00–18.00 kg" />
        <Metric
          label="ชั่งแล้ว"
          value={String(latestWeight.lotNo)}
          hint="ก้อน / กะนี้"
        />
      </div>

      <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50/60 p-2">
        <Sparkline
          values={chartValues}
          min={Math.min(spec.lsl - 0.4, ...chartValues) - 0.1}
          max={Math.max(spec.usl + 0.4, ...chartValues) + 0.1}
          color="#2563eb"
          bands={[
            { value: spec.usl, color: "#ef4444" },
            {
              value: spec.target + spec.warningBand,
              color: "#f59e0b",
              dashed: true,
            },
            { value: spec.target, color: "#10b981", dashed: true },
            {
              value: spec.target - spec.warningBand,
              color: "#f59e0b",
              dashed: true,
            },
            { value: spec.lsl, color: "#ef4444" },
          ]}
        />
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-slate-400">
        น้ำหนักย้อนหลัง {weightSeries.length} ก้อน · เส้นแดง = LSL/USL ·
        เส้นเหลือง = Warning Band · เส้นเขียว = Target
      </p>
    </Panel>
  );
}
