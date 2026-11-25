"use client";

import {
  SECONDS_PER_TICK,
  TICK_MS,
  WEIGHT_TICKS_PER_SAMPLE,
} from "@/lib/config";
import { SCENARIOS } from "@/lib/simulator";
import { useStore } from "@/lib/store";

export function SimControls() {
  const { scenario, setScenario, running, setRunning, reset } = useStore();
  const active = SCENARIOS.find((s) => s.id === scenario);

  return (
    <section className="rounded-2xl border border-dashed border-blue-200 bg-blue-50/40 p-3.5 sm:p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-bold text-slate-800">
            🎛️ โหมดจำลองสัญญาณหน้างาน (Prototype)
          </h2>
          <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
            ในระบบจริงส่วนนี้จะถูกแทนด้วย Gateway ของตาชั่ง และตัวดึงข้อมูลจาก
            Recorder เดิม · เดโมเดินเร็วกว่าเวลาจริง{" "}
            {((SECONDS_PER_TICK * 1000) / TICK_MS).toFixed(1)} เท่า ·
            อ่านอุณหภูมิทุก {SECONDS_PER_TICK} วินาที · ชั่งน้ำหนักทุก{" "}
            {SECONDS_PER_TICK * WEIGHT_TICKS_PER_SAMPLE} วินาที
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={() => setRunning(!running)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 active:scale-[0.97]"
          >
            {running ? "หยุดชั่วคราว" : "เดินต่อ"}
          </button>
          <button
            type="button"
            onClick={reset}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-500 shadow-sm transition hover:bg-slate-50 active:scale-[0.97]"
          >
            ล้างข้อมูล
          </button>
        </div>
      </div>

      <div className="no-scrollbar -mx-1 mt-3 flex gap-2 overflow-x-auto px-1 pb-1">
        {SCENARIOS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setScenario(item.id)}
            className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold transition active:scale-[0.97] ${
              scenario === item.id
                ? "border-blue-600 bg-blue-600 text-white shadow-sm shadow-blue-600/30"
                : "border-slate-200 bg-white text-slate-600 hover:border-blue-300 hover:text-blue-700"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {active && (
        <p className="mt-2 text-[11px] text-slate-500">→ {active.hint}</p>
      )}
    </section>
  );
}
