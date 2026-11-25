"use client";

import { usePathname } from "next/navigation";
import { TopBar } from "./TopBar";
import { StoreProvider } from "@/lib/store";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const authScreen = pathname === "/login";

  return <StoreProvider>
    {authScreen ? null : <TopBar />}
    <main className={authScreen
      ? "w-full flex-1 px-4 py-6 sm:px-8 lg:py-8"
      : "w-full flex-1 px-3 py-5 sm:px-6 lg:ml-60 lg:w-[calc(100%-15rem)] lg:px-8 lg:py-7"}>
      <div className={`mx-auto w-full ${authScreen ? "max-w-[1200px]" : "max-w-[1500px]"}`}>{children}</div>
    </main>
    <footer className={`px-4 py-4 text-center text-[11px] text-slate-400 ${authScreen ? "" : "lg:ml-60"}`}>
      {authScreen ? "PCC Secure Access · บัญชีและสิทธิ์ออกโดยผู้ดูแลระบบ" : "PCC รุ่นพัฒนา · ค่าที่ระบุ “ข้อมูลจำลอง” ยังไม่ใช่ค่าจากอุปกรณ์จริง"}
    </footer>
  </StoreProvider>;
}
