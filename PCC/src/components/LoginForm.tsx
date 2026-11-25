"use client";

import { useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { FactoryIcon } from "./FactoryIcon";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

export function LoginForm({ configured }: { configured: boolean }) {
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!configured) return;
    setLoading(true);
    setError(null);
    try {
      const supabase = createSupabaseBrowserClient();
      const result = await supabase.auth.signInWithPassword({ email: email.trim(), password });
      if (result.error) throw result.error;
      const next = searchParams.get("next");
      window.location.assign(next?.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "เข้าสู่ระบบไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }

  return <form onSubmit={submit} className="mt-7 space-y-4">
    {!configured ? <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-800">ยังไม่ได้ตั้งค่า Supabase Auth ระบบ Demo ยังเปิดใช้งานได้ตามเดิม กำหนด Public URL, Publishable Key และ `PCC_AUTH_REQUIRED=true` เมื่อต้องการเปิด Login</div> : null}
    <div><label htmlFor="email" className="text-xs font-bold text-slate-700">อีเมลบริษัท</label><input id="email" type="email" autoComplete="username" required disabled={!configured || loading} value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1.5 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100 disabled:bg-slate-100" placeholder="name@factory.local" /></div>
    <div><label htmlFor="password" className="text-xs font-bold text-slate-700">รหัสผ่าน</label><input id="password" type="password" autoComplete="current-password" required disabled={!configured || loading} value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1.5 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100 disabled:bg-slate-100" placeholder="••••••••" /></div>
    {error ? <p role="alert" className="text-xs font-bold text-red-600">{error}</p> : null}
    <button type="submit" disabled={!configured || loading} className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 text-sm font-black text-white shadow-lg shadow-blue-200 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"><FactoryIcon name="system" className="size-4" />{loading ? "กำลังตรวจสอบ..." : "เข้าสู่ระบบ PCC"}</button>
    <p className="text-center text-[10px] leading-4 text-slate-400">ผู้ใช้ไม่ได้สมัครบัญชีเอง · ผู้ดูแลระบบเป็นผู้กำหนด role ผ่าน app_metadata</p>
  </form>;
}
