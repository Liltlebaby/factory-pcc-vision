"use client";

import { useStore } from "@/lib/store";
import { fmtDateTime } from "@/lib/format";
import { FactoryIcon } from "./FactoryIcon";
import { DataStatus } from "./StatusMark";

export function PccReports() {
  const { now, weightSeries, tempSeries, pondSeries, closedIncidents, activeIncidents } = useStore();
  const cards = [
    { label: "ก้อนยางที่บันทึกได้", value: weightSeries.length, unit: "ก้อน", color: "text-blue-700" },
    { label: "เหตุการณ์ที่ปิดแล้ว", value: closedIncidents.length, unit: "รายการ", color: "text-emerald-700" },
    { label: "เหตุการณ์ที่ยังค้าง", value: activeIncidents.length, unit: "รายการ", color: "text-red-700" },
  ];
  const rows = [
    { name: "ตาชั่งน้ำหนักยาง", count: weightSeries.length, latest: weightSeries.at(-1)?.measurement.measuredAt },
    { name: "อุณหภูมิเตา", count: tempSeries.length, latest: tempSeries.at(-1)?.measuredAt },
    { name: "บ่อสุดท้าย", count: pondSeries.length, latest: pondSeries.at(-1)?.measuredAt },
  ];
  return <div className="space-y-5">
    <header><p className="text-xs font-black uppercase tracking-[0.16em] text-blue-700">Reports</p><h1 className="mt-1 text-2xl font-black tracking-tight text-slate-950 sm:text-3xl">รายงานการผลิต</h1><p className="mt-1 text-sm text-slate-500">ภาพรวมข้อมูลที่ระบบรวบรวมได้ในเซสชันปัจจุบัน</p></header>
    <div className="grid gap-4 sm:grid-cols-3">{cards.map(card => <section key={card.label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><p className="text-xs font-bold text-slate-500">{card.label}</p><p className={`mt-2 text-4xl font-black tabular-nums ${card.color}`}>{card.value}<span className="ml-1 text-xs font-bold text-slate-400">{card.unit}</span></p></section>)}</div>
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="flex items-center justify-between border-b border-slate-100 px-5 py-4"><h2 className="flex items-center gap-2 text-sm font-black"><FactoryIcon name="database" className="size-4 text-blue-600"/>ความพร้อมของข้อมูล</h2><DataStatus state="DEMO"/></div><div className="divide-y divide-slate-100">{rows.map(row => <div key={row.name} className="grid gap-2 px-5 py-4 sm:grid-cols-[1fr_120px_220px] sm:items-center"><strong className="text-sm text-slate-800">{row.name}</strong><span className="text-xs tabular-nums text-slate-500">{row.count} จุดข้อมูล</span><span className="text-xs text-slate-400">{row.latest ? fmtDateTime(row.latest) : "ยังไม่มีข้อมูล"}</span></div>)}</div></section>
    <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-xs leading-relaxed text-blue-900">ขณะนี้เป็นรายงานข้อมูลจำลอง ณ {fmtDateTime(now)} เมื่อเชื่อมฐานข้อมูลจริง จะเพิ่มตัวกรองวันที่ กะ จุดงาน และดาวน์โหลด CSV/PDF ในหน้านี้</div>
  </div>;
}
