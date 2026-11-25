"use client";

import { STATUS_META, TEMP_SPEC } from "@/lib/config";
import { fmtDelta } from "@/lib/engine";
import { useStore } from "@/lib/store";
import { Sparkline } from "./Sparkline";
import { Panel, RuleTag, StatusBadge } from "./ui";

/** ช่วงที่แถบ Worst Error ครอบคลุม ±3°C (เกินเกณฑ์แดง 2°C อยู่หนึ่งองศา) */
const ERROR_SPAN = 3;

export function TempCard() {
  const { latestTemp, tempSeries } = useStore();

  if (!latestTemp) {
    return (
      <Panel title="Function 02 · Temperature" icon="🌡️">
        <p className="py-6 text-center text-sm text-slate-400">
          รอข้อมูลจาก Recorder / Burner…
        </p>
      </Panel>
    );
  }

  const meta = STATUS_META[latestTemp.status];
  const swingWarning = latestTemp.swing15 > TEMP_SPEC.swingLimit;
  const errorValues = tempSeries.map((s) => s.worstError);

  // ตำแหน่งจุดบนแถบ Worst Error
  const errorPercent = Math.min(
    Math.max(((latestTemp.worstError + ERROR_SPAN) / (ERROR_SPAN * 2)) * 100, 0),
    100,
  );

  const sources = [
    {
      key: "BURNER",
      label: "Burner Display",
      value: latestTemp.burner,
      delta: latestTemp.deltaBurner,
    },
    {
      key: "RECORDER",
      label: "Recorder (เครื่องเดิม)",
      value: latestTemp.recorder,
      delta: latestTemp.deltaRecorder,
    },
  ];

  const deltaTone = (delta: number) =>
    Math.abs(delta) > TEMP_SPEC.yellowLimit
      ? "bg-red-50 text-red-600 ring-red-200"
      : Math.abs(delta) > TEMP_SPEC.greenLimit
        ? "bg-amber-50 text-amber-600 ring-amber-200"
        : "bg-emerald-50 text-emerald-600 ring-emerald-200";

  return (
    <Panel
      title="Function 02 · Temperature"
      icon="🌡️"
      action={<StatusBadge status={latestTemp.status} />}
    >
      {/* Digital Thermometer เป็นค่าหลักที่ใช้เทียบกับเครื่องทั้งสอง */}
      <div
        className="rounded-2xl border-4 border-slate-700 bg-slate-950 px-4 py-3 text-center shadow-inner"
        role="img"
        aria-label={`Digital Thermometer ${latestTemp.actual.toFixed(1)} องศาเซลเซียส`}
      >
        <p className="text-[10px] font-bold tracking-[0.2em] text-sky-400 uppercase">
          Digital Thermometer · Reference
        </p>
        <p className="mt-1 flex items-baseline justify-center gap-1.5 font-mono text-4xl leading-none font-black tabular-nums whitespace-nowrap text-sky-300 sm:text-5xl [text-shadow:0_0_10px_rgba(125,211,252,.6)]">
          {latestTemp.actual.toFixed(1)}
          <span className="text-sm font-bold text-sky-500">{TEMP_SPEC.unit}</span>
        </p>
      </div>

      {/* จอที่ติดตั้งหน้างาน วางคู่กันเพื่อลดความสูงและเทียบค่าได้ทันที */}
      <ul className="mt-3 grid grid-cols-2 gap-2">
        {sources.map((source) => (
          <li
            key={source.key}
            className="min-w-0 rounded-xl border border-slate-200 bg-slate-50 p-2"
          >
            <span className="block truncate text-center text-[10px] font-bold text-slate-500">
              {source.label}
            </span>
            <div className="mt-1 rounded-lg border-2 border-slate-700 bg-slate-950 px-2 py-2 text-center shadow-inner">
              <span className="font-mono text-xl font-black tabular-nums whitespace-nowrap text-emerald-300 [text-shadow:0_0_7px_rgba(110,231,183,.5)]">
                {source.value.toFixed(1)}
                <span className="ml-1 text-[10px] text-emerald-500">
                  {TEMP_SPEC.unit}
                </span>
              </span>
            </div>
            <span
              className={`mx-auto mt-1.5 block w-14 rounded-full py-0.5 text-center text-[10px] font-bold tabular-nums ring-1 ${deltaTone(source.delta)}`}
            >
              Δ {fmtDelta(source.delta)}
            </span>
          </li>
        ))}
      </ul>

      <div className="mt-3 grid grid-cols-[1fr_1fr_auto] items-center gap-2 rounded-xl border border-slate-100 bg-slate-50/70 px-3 py-2">
        <div>
          <p className="text-[9px] font-semibold text-slate-400 uppercase">Worst Error</p>
          <p className={`text-base font-bold tabular-nums ${meta.text}`}>
            {fmtDelta(latestTemp.worstError)}
            <span className="ml-0.5 text-[10px] text-slate-400">{TEMP_SPEC.unit}</span>
          </p>
        </div>
        <div>
          <p className="text-[9px] font-semibold text-slate-400 uppercase">
            Swing {TEMP_SPEC.swingWindowMinutes} นาที
          </p>
          <p className={`text-base font-bold tabular-nums ${swingWarning ? "text-amber-600" : "text-slate-800"}`}>
            {latestTemp.swing15.toFixed(1)}
            <span className="ml-0.5 text-[10px] text-slate-400">{TEMP_SPEC.unit}</span>
          </p>
        </div>
        <RuleTag code={latestTemp.ruleCode} />
      </div>

      {/* ---- แถบเกณฑ์ Worst Error: แดง | เหลือง | เขียว | เหลือง | แดง ---- */}
      <div className="mt-4">
        <div className="relative h-2.5 rounded-full bg-red-200/80 ring-1 ring-red-300/70 ring-offset-1 ring-offset-white">
          <div className="absolute inset-y-0 left-[16.667%] right-[16.667%] bg-amber-200" />
          <div className="absolute inset-y-0 left-1/3 right-1/3 bg-emerald-300" />
          <div
            className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-white shadow-md transition-all duration-500"
            style={{ left: `${errorPercent}%`, backgroundColor: meta.hex }}
          />
        </div>
        <div className="mt-2 flex justify-between text-[10px] font-semibold tabular-nums text-slate-400">
          <span>−{TEMP_SPEC.yellowLimit.toFixed(1)}</span>
          <span className="text-emerald-600">
            Target ±{TEMP_SPEC.greenLimit.toFixed(1)}
          </span>
          <span>+{TEMP_SPEC.yellowLimit.toFixed(1)}</span>
        </div>
      </div>

      {swingWarning && (
        <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-800">
          <span className="font-bold">🟡 Temperature Stability Warning</span> —
          ค่าปัจจุบันยังไม่เกิน ±{TEMP_SPEC.yellowLimit}°C แต่ Recorder แกว่ง{" "}
          {latestTemp.swing15.toFixed(1)}°C ใน {TEMP_SPEC.swingWindowMinutes}{" "}
          นาที กระบวนการเริ่มไม่นิ่ง
        </p>
      )}

      <div className="mt-3 rounded-xl border border-slate-100 bg-slate-50/60 p-2">
        <Sparkline
          values={errorValues}
          min={Math.min(-3.5, ...errorValues) - 0.3}
          max={Math.max(3.5, ...errorValues) + 0.3}
          color="#0284c7"
          bands={[
            { value: TEMP_SPEC.yellowLimit, color: "#ef4444" },
            { value: TEMP_SPEC.greenLimit, color: "#f59e0b", dashed: true },
            { value: 0, color: "#10b981", dashed: true },
            { value: -TEMP_SPEC.greenLimit, color: "#f59e0b", dashed: true },
            { value: -TEMP_SPEC.yellowLimit, color: "#ef4444" },
          ]}
        />
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-slate-400">
        Worst Error = MAX(|Δ Burner|, |Δ Recorder|) เทียบค่าจริง · เส้นแดง = ±
        {TEMP_SPEC.yellowLimit}
        {TEMP_SPEC.unit} · เส้นเหลือง = ±{TEMP_SPEC.greenLimit}
        {TEMP_SPEC.unit} · เส้นเขียว = ตรงค่าจริง
      </p>
    </Panel>
  );
}
