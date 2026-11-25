"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FactoryIcon } from "./FactoryIcon";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";
import type { PccRole } from "@/lib/access-control";

type Account = { id: string; email: string | null; role: PccRole };

const ROLE_LABEL: Record<PccRole, string> = {
  admin: "ผู้ดูแลระบบ",
  operator: "ผู้ปฏิบัติงาน",
  viewer: "ผู้ดูข้อมูล",
};

export function AccountMenu() {
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/auth/me", { cache: "no-store", signal: controller.signal })
      .then((response) => response.ok ? response.json() : null)
      .then((payload) => {
        if (payload?.authenticated && payload.user) setAccount(payload.user as Account);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setProblem("อ่านบัญชีไม่สำเร็จ");
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);

  if (!account) return null;
  const initial = (account.email?.trim()[0] ?? account.role[0]).toUpperCase();

  async function signOut() {
    setSigningOut(true);
    setProblem(null);
    try {
      const { error } = await createSupabaseBrowserClient().auth.signOut();
      if (error) throw error;
      router.replace("/login");
      router.refresh();
    } catch {
      setProblem("ออกจากระบบไม่สำเร็จ กรุณาลองอีกครั้ง");
      setSigningOut(false);
    }
  }

  return <div ref={menuRef} className="relative">
    <button type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-haspopup="menu" aria-label="เปิดเมนูบัญชีผู้ใช้" className="inline-flex h-8 items-center gap-2 rounded-full border border-slate-200 bg-white py-1 pl-1 pr-2 text-left shadow-sm transition hover:border-blue-300 hover:bg-blue-50">
      <span className="grid size-6 place-items-center rounded-full bg-slate-900 text-[10px] font-black text-white">{initial}</span>
      <span className="hidden max-w-28 truncate text-[10px] font-bold text-slate-700 xl:block">{account.email ?? ROLE_LABEL[account.role]}</span>
    </button>
    {open ? <div role="menu" className="absolute right-0 top-10 z-50 w-64 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-900/15">
      <div className="border-b border-slate-100 p-4">
        <div className="flex items-center gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-900 text-sm font-black text-white">{initial}</span>
          <div className="min-w-0"><p className="truncate text-xs font-black text-slate-900">{account.email ?? "บัญชี PCC"}</p><p className="mt-1 text-[10px] font-bold text-blue-600">{ROLE_LABEL[account.role]}</p></div>
        </div>
      </div>
      <div className="p-2">
        <button role="menuitem" type="button" disabled={signingOut} onClick={signOut} className="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-xs font-bold text-slate-700 transition hover:bg-red-50 hover:text-red-700 disabled:opacity-50"><FactoryIcon name="logout" className="size-4" />{signingOut ? "กำลังออกจากระบบ..." : "ออกจากระบบ"}</button>
        {problem ? <p role="alert" className="px-3 pb-2 text-[10px] leading-4 text-red-600">{problem}</p> : null}
      </div>
    </div> : null}
  </div>;
}
