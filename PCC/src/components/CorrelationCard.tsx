"use client";

import { useStore } from "@/lib/store";
import { Chip, Panel } from "./ui";

/**
 * ส่วนเชื่อม Weight + Temperature
 * Prototype แสดงเป็น "ข้อเสนอ" เท่านั้น การตัดสินใจยังเป็นของผู้รับผิดชอบ
 */
export function CorrelationCard() {
  const { correlation } = useStore();

  if (!correlation) {
    return (
      <Panel title="Weight × Temperature Correlation" icon="🔗">
        <div className="flex h-full flex-col justify-center py-2">
          <p className="text-sm text-slate-500">
            ยังไม่พบความสัมพันธ์ระหว่างน้ำหนักและอุณหภูมิในช่วงเวลานี้
          </p>
          <p className="mt-1.5 text-[11px] leading-relaxed text-slate-400">
            ระบบจะเชื่อมให้อัตโนมัติเมื่อน้ำหนักเริ่มตก/ดริฟท์
            พร้อมกับอุณหภูมิที่ไม่นิ่งในช่วงเวลาเดียวกัน
          </p>
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      title="Weight × Temperature Correlation"
      icon="🔗"
      action={<Chip tone="violet">AI เสนอ · คนตัดสินใจ</Chip>}
    >
      <ul className="grid gap-2 sm:grid-cols-2">
        <li className="rounded-xl border border-slate-100 bg-slate-50/70 px-3 py-2 text-xs">
          <p className="text-[10px] font-semibold tracking-wide text-slate-400 uppercase">
            น้ำหนัก
          </p>
          <p className="mt-0.5 text-slate-700">{correlation.weightNote}</p>
        </li>
        <li className="rounded-xl border border-slate-100 bg-slate-50/70 px-3 py-2 text-xs">
          <p className="text-[10px] font-semibold tracking-wide text-slate-400 uppercase">
            อุณหภูมิ
          </p>
          <p className="mt-0.5 text-slate-700">{correlation.tempNote}</p>
        </li>
      </ul>

      <div className="mt-3 flex gap-2.5 rounded-xl border border-violet-200 bg-gradient-to-br from-violet-50 to-blue-50 px-3 py-2.5">
        <span className="text-base leading-none" aria-hidden>
          💡
        </span>
        <p className="text-xs leading-relaxed font-medium text-violet-900">
          {correlation.suggestion}
        </p>
      </div>

      <p className="mt-2 text-[10px] text-slate-400">
        Possible Process Correlation — เป็นข้อสังเกตจากข้อมูล
        ไม่ใช่คำสั่งให้ปรับกระบวนการ
      </p>
    </Panel>
  );
}
