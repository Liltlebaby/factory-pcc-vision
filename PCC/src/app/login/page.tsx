import { Suspense } from "react";
import { LoginForm } from "@/components/LoginForm";
import { FactoryIcon } from "@/components/FactoryIcon";
import { serverAuthConfigured } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default function LoginPage() {
  const configured = serverAuthConfigured();
  return <div className="mx-auto grid min-h-[calc(100vh-12rem)] max-w-5xl items-center gap-8 lg:grid-cols-[1.1fr_0.9fr]">
    <section className="hidden rounded-3xl bg-slate-950 p-10 text-white shadow-2xl lg:block"><span className="grid size-14 place-items-center rounded-2xl bg-blue-600 shadow-lg shadow-blue-950"><FactoryIcon name="factory" className="size-8" /></span><p className="mt-8 text-xs font-black uppercase tracking-[0.2em] text-cyan-300">Production Control Center</p><h1 className="mt-3 text-4xl font-black leading-tight">ควบคุมข้อมูลโรงงาน<br />ด้วยสิทธิ์ที่ตรวจสอบได้</h1><p className="mt-4 max-w-md text-sm leading-7 text-slate-300">Admin จัดการระบบ · Operator รับทราบและปิดเหตุ · Viewer ดูสถานะและรายงาน โดยทุก action สำคัญถูกบันทึกใน Audit Log</p><div className="mt-10 grid grid-cols-3 gap-3">{[["Admin", "ตั้งค่า"], ["Operator", "ดำเนินการ"], ["Viewer", "ดูข้อมูล"]].map(([role, detail]) => <div key={role} className="rounded-2xl border border-white/10 bg-white/5 p-3"><strong className="text-xs">{role}</strong><p className="mt-1 text-[10px] text-slate-400">{detail}</p></div>)}</div></section>
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-[0_24px_60px_rgba(15,23,42,0.12)] sm:p-8"><div className="flex items-center gap-3"><span className="grid size-11 place-items-center rounded-xl bg-blue-50 text-blue-700"><FactoryIcon name="system" className="size-5" /></span><div><p className="text-[10px] font-black uppercase tracking-[0.16em] text-blue-700">Secure access</p><h2 className="text-2xl font-black text-slate-950">เข้าสู่ระบบ</h2></div></div><p className="mt-4 text-sm leading-6 text-slate-500">ใช้บัญชีที่ผู้ดูแลระบบโรงงานออกให้ สิทธิ์จะถูกตรวจซ้ำที่เซิร์ฟเวอร์ก่อนทำรายการสำคัญ</p><Suspense fallback={<div className="mt-7 h-72 animate-pulse rounded-2xl bg-slate-100" />}><LoginForm configured={configured} /></Suspense></section>
  </div>;
}
