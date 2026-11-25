"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { FURNACE } from "@/lib/config";
import { fmtDateTime, fmtTime } from "@/lib/format";
import { useStore } from "@/lib/store";
import { FactoryIcon, type FactoryIconName } from "./FactoryIcon";
import { AccountMenu } from "./AccountMenu";

const NAV: Array<{ href: string; label: string; icon: FactoryIconName }> = [
  { href: "/", label: "ภาพรวม", icon: "overview" },
  { href: "/stations", label: "จุดตรวจในโรงงาน", icon: "stations" },
  { href: "/incidents", label: "เหตุการณ์", icon: "incident" },
  { href: "/reports", label: "รายงาน", icon: "report" },
  { href: "/devices", label: "อุปกรณ์และการเชื่อมต่อ", icon: "device" },
  { href: "/system", label: "สถานะระบบ", icon: "system" },
  { href: "/audit", label: "Audit Log", icon: "audit" },
];

function NavItems({ mobile = false }: { mobile?: boolean }) {
  const pathname = usePathname();
  return NAV.map((item) => {
    const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
    return (
      <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined}
        className={mobile
          ? `inline-flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold transition ${active ? "bg-blue-600 text-white" : "text-slate-600 hover:bg-slate-100"}`
          : `group flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-bold transition ${active ? "bg-blue-600 text-white shadow-lg shadow-blue-950/25" : "text-slate-300 hover:bg-slate-800 hover:text-white"}`}>
        <FactoryIcon name={item.icon} className="size-[18px]" />
        {item.label}
      </Link>
    );
  });
}

export function TopBar() {
  const { running, activeIncidents } = useStore();
  const [wallClock, setWallClock] = useState<number | null>(null);

  useEffect(() => {
    const updateClock = () => setWallClock(Date.now());
    updateClock();
    const timer = window.setInterval(updateClock, 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-slate-800 bg-[#101b2d] p-4 lg:flex">
        <Link href="/" className="flex items-center gap-3 rounded-2xl border border-slate-700/70 bg-slate-900/50 p-3">
          <span className="grid size-11 place-items-center rounded-xl bg-blue-600 text-white shadow-lg shadow-blue-950/30"><FactoryIcon name="factory" className="size-6" /></span>
          <span><strong className="block text-sm font-black tracking-tight text-white">PCC</strong><span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">Production Control</span></span>
        </Link>

        <div className="mt-6 px-2 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">Monitoring</div>
        <nav className="mt-2 space-y-1.5"><NavItems /></nav>

        <div className="mt-auto rounded-2xl border border-slate-700 bg-slate-900/60 p-3">
          <div className="flex items-center justify-between"><span className="text-[11px] font-bold text-slate-300">สถานะระบบ</span><span className={`size-2 rounded-full ${running ? "bg-emerald-400" : "bg-slate-500"}`} /></div>
          <p className="mt-2 text-xs font-extrabold text-white">{running ? "กำลังจำลองข้อมูล" : "หยุดชั่วคราว"}</p>
          <p className="mt-1 text-[10px] leading-relaxed text-slate-400">LINE-1 · {FURNACE.workOrderId}</p>
        </div>
      </aside>

      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white lg:ml-60">
        <div className="flex min-h-16 items-center justify-between gap-3 px-4 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-blue-600 text-white lg:hidden"><FactoryIcon name="factory" className="size-5" /></span>
            <div className="min-w-0"><p className="truncate text-sm font-black text-slate-950">Production Control Center</p><p className="truncate text-[11px] text-slate-500">{FURNACE.line} · {FURNACE.name} · {FURNACE.workOrderId}</p></div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="hidden text-xs tabular-nums text-slate-500 sm:inline">{wallClock === null ? "-- --- --:--:--" : fmtDateTime(wallClock)}</span>
            <span className="text-[11px] tabular-nums text-slate-500 sm:hidden">{wallClock === null ? "--:--" : fmtTime(wallClock)}</span>
            {activeIncidents.length > 0 && <Link href="/incidents" className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-1 text-[10px] font-black text-red-700 ring-1 ring-red-200"><span className="size-1.5 rounded-full bg-red-500" />{activeIncidents.length} แจ้งเตือน</Link>}
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-black ring-1 ${running ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-slate-100 text-slate-500 ring-slate-200"}`}><span className={`size-1.5 rounded-full ${running ? "bg-emerald-500" : "bg-slate-400"}`} />DEMO</span>
            <AccountMenu />
          </div>
        </div>
        <nav className="no-scrollbar flex gap-1.5 overflow-x-auto border-t border-slate-100 px-3 py-2 lg:hidden"><NavItems mobile /></nav>
      </header>
    </>
  );
}
