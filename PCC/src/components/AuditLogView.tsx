"use client";

import { useMemo, useState } from "react";
import { FactoryIcon } from "./FactoryIcon";
import { auditActionLabel, auditEntityLabel, type PccAuditFeed, type PccAuditRecord } from "@/lib/audit-log";

const ROLE_LABEL = { admin: "Admin", operator: "Operator", viewer: "Viewer", system: "System" } as const;

function formatAuditTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "ไม่ทราบเวลา";
  return new Intl.DateTimeFormat("th-TH", {
    dateStyle: "medium",
    timeStyle: "medium",
    timeZone: "Asia/Bangkok",
  }).format(date);
}

function RecordBody({ record }: { record: PccAuditRecord }) {
  return <>
    <div className="flex min-w-0 items-start gap-3">
      <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-700 ring-1 ring-blue-100"><FactoryIcon name="audit" className="size-[18px]" /></span>
      <div className="min-w-0"><p className="truncate text-sm font-black text-slate-900">{auditActionLabel(record.action)}</p><p className="mt-1 truncate text-[11px] text-slate-500">{auditEntityLabel(record.entityType)} · <span className="font-mono">{record.entityId}</span></p></div>
    </div>
    {record.changedFields.length > 0 ? <div className="mt-3 flex flex-wrap gap-1.5">{record.changedFields.map((field) => <span key={field} className="rounded-md bg-slate-100 px-2 py-1 font-mono text-[9px] font-semibold text-slate-600">{field}</span>)}</div> : null}
  </>;
}

export function AuditLogView({ feed }: { feed: PccAuditFeed }) {
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("all");
  const [action, setAction] = useState("all");
  const actions = useMemo(() => [...new Set(feed.records.map((record) => record.action))].sort(), [feed.records]);
  const filtered = useMemo(() => {
    const term = query.trim().toLocaleLowerCase("th-TH");
    return feed.records.filter((record) => {
      const matchesRole = role === "all" || record.actorRole === role;
      const matchesAction = action === "all" || record.action === action;
      const haystack = `${record.actorName} ${record.entityType} ${record.entityId} ${record.requestId ?? ""} ${auditActionLabel(record.action)}`.toLocaleLowerCase("th-TH");
      return matchesRole && matchesAction && (!term || haystack.includes(term));
    });
  }, [action, feed.records, query, role]);
  const uniqueActors = new Set(feed.records.map((record) => record.actorId ?? record.actorName)).size;
  const latest = feed.records[0];

  return <div className="space-y-4 sm:space-y-5">
    <section className="overflow-hidden rounded-3xl bg-slate-950 text-white shadow-xl shadow-slate-900/10">
      <div className="grid gap-6 px-5 py-6 sm:px-7 sm:py-7 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <div className="max-w-2xl"><div className="flex items-center gap-3"><span className="grid size-11 place-items-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-950"><FactoryIcon name="audit" className="size-6" /></span><div><h1 className="text-xl font-black tracking-tight sm:text-2xl">บันทึกการใช้งานระบบ</h1><p className="mt-1 text-xs leading-5 text-slate-400">ตรวจสอบผู้ดำเนินการ เวลา และรายการที่เปลี่ยนแปลงจากแหล่งข้อมูลฝั่งเซิร์ฟเวอร์</p></div></div></div>
        <div className="grid grid-cols-3 divide-x divide-white/10 rounded-2xl border border-white/10 bg-white/[0.04] px-1 py-3">
          <div className="px-4"><p className="text-[9px] font-bold uppercase tracking-wider text-slate-500">รายการ</p><p className="mt-1 text-lg font-black tabular-nums">{feed.records.length}</p></div>
          <div className="px-4"><p className="text-[9px] font-bold uppercase tracking-wider text-slate-500">ผู้ใช้งาน</p><p className="mt-1 text-lg font-black tabular-nums">{uniqueActors}</p></div>
          <div className="px-4"><p className="text-[9px] font-bold uppercase tracking-wider text-slate-500">สถานะ</p><p className="mt-1 text-xs font-black text-emerald-400">IMMUTABLE</p></div>
        </div>
      </div>
    </section>

    <section className="card-shadow rounded-2xl border border-slate-200/80 bg-white">
      <div className="grid gap-3 border-b border-slate-100 p-4 md:grid-cols-[minmax(240px,1fr)_190px_190px_auto]">
        <label className="relative"><span className="sr-only">ค้นหา Audit Log</span><FactoryIcon name="search" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ค้นหาผู้ใช้ เหตุการณ์ หรือ Request ID" className="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pl-9 pr-3 text-xs font-semibold outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100" /></label>
        <label><span className="sr-only">กรองตามสิทธิ์</span><select value={role} onChange={(event) => setRole(event.target.value)} className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-xs font-bold text-slate-700 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"><option value="all">ทุกสิทธิ์</option><option value="admin">Admin</option><option value="operator">Operator</option><option value="viewer">Viewer</option><option value="system">System</option></select></label>
        <label><span className="sr-only">กรองตามการกระทำ</span><select value={action} onChange={(event) => setAction(event.target.value)} className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-xs font-bold text-slate-700 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"><option value="all">ทุกการกระทำ</option>{actions.map((item) => <option key={item} value={item}>{auditActionLabel(item)}</option>)}</select></label>
        <button type="button" onClick={() => { setQuery(""); setRole("all"); setAction("all"); }} className="h-10 rounded-xl border border-slate-200 px-4 text-xs font-bold text-slate-600 transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700">ล้างตัวกรอง</button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-[10px] text-slate-500 sm:px-5"><span>พบ <strong className="text-slate-900">{filtered.length}</strong> จาก {feed.records.length} รายการ</span><span>ล่าสุด {latest ? formatAuditTime(latest.occurredAt) : "—"}</span></div>

      {filtered.length === 0 ? <div className="grid min-h-64 place-items-center border-t border-slate-100 px-6 text-center"><div><span className="mx-auto grid size-12 place-items-center rounded-2xl bg-slate-100 text-slate-500"><FactoryIcon name="search" className="size-5" /></span><p className="mt-3 text-sm font-black text-slate-800">ไม่พบรายการที่ตรงกับตัวกรอง</p><p className="mt-1 text-xs text-slate-500">ลองเปลี่ยนคำค้นหา สิทธิ์ หรือประเภทการทำงาน</p></div></div> : <>
        <div className="hidden overflow-x-auto border-t border-slate-100 md:block"><table className="w-full min-w-[920px] text-left"><thead className="bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-500"><tr><th className="px-5 py-3">การทำงาน</th><th className="px-4 py-3">ผู้ดำเนินการ</th><th className="px-4 py-3">เวลา</th><th className="px-4 py-3">Request ID</th></tr></thead><tbody className="divide-y divide-slate-100">{filtered.map((record) => <tr key={record.id} className="align-top transition hover:bg-blue-50/40"><td className="px-5 py-4"><RecordBody record={record} /></td><td className="px-4 py-4"><p className="max-w-44 truncate text-xs font-bold text-slate-800">{record.actorName}</p><span className="mt-1 inline-flex rounded-md bg-slate-100 px-2 py-1 text-[9px] font-black text-slate-600">{record.actorRole ? ROLE_LABEL[record.actorRole] : "Unknown"}</span></td><td className="whitespace-nowrap px-4 py-4 text-[11px] tabular-nums text-slate-600">{formatAuditTime(record.occurredAt)}</td><td className="px-4 py-4 font-mono text-[10px] text-slate-500">{record.requestId ?? "—"}</td></tr>)}</tbody></table></div>
        <ol className="divide-y divide-slate-100 border-t border-slate-100 md:hidden">{filtered.map((record) => <li key={record.id} className="p-4"><RecordBody record={record} /><div className="mt-3 grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-3 text-[10px]"><div><p className="text-slate-400">ผู้ดำเนินการ</p><p className="mt-1 truncate font-bold text-slate-700">{record.actorName}</p></div><div><p className="text-slate-400">เวลา</p><p className="mt-1 font-semibold tabular-nums text-slate-700">{formatAuditTime(record.occurredAt)}</p></div></div></li>)}</ol>
      </>}
    </section>
  </div>;
}

export function AuditAccessState({ state }: { state: "not_configured" | "unauthenticated" | "forbidden" | "offline" }) {
  const content = {
    not_configured: ["ยังไม่ได้เชื่อมระบบบัญชี", "ตั้งค่า Supabase Auth และเปิด PCC_AUTH_REQUIRED เพื่อใช้งาน Audit Log ด้วยบัญชี Admin"],
    unauthenticated: ["ต้องเข้าสู่ระบบก่อน", "Audit Log เป็นข้อมูลสำหรับผู้ดูแลระบบ กรุณาเข้าสู่ระบบด้วยบัญชีที่ได้รับอนุญาต"],
    forbidden: ["บัญชีนี้ไม่มีสิทธิ์ดู Audit Log", "เฉพาะ Admin ที่มีสิทธิ์ audit:view เท่านั้นที่สามารถอ่านประวัติการเปลี่ยนแปลงได้"],
    offline: ["ยังอ่าน Audit Log ไม่ได้", "ฐานข้อมูลหรือ Migration สำหรับ Audit ยังไม่พร้อม ตรวจการเชื่อมต่อ Supabase แล้วลองอีกครั้ง"],
  }[state];
  return <section className="grid min-h-[65vh] place-items-center"><div className="card-shadow w-full max-w-xl rounded-3xl border border-slate-200 bg-white p-7 text-center sm:p-10"><span className="mx-auto grid size-16 place-items-center rounded-2xl bg-slate-950 text-white shadow-lg"><FactoryIcon name="audit" className="size-8" /></span><h1 className="mt-5 text-xl font-black text-slate-950">{content[0]}</h1><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">{content[1]}</p><div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs font-semibold text-amber-800">ระบบจะไม่แสดงข้อมูลตัวอย่างแทน Audit จริง เพื่อป้องกันความเข้าใจผิดในการตรวจสอบย้อนหลัง</div></div></section>;
}
