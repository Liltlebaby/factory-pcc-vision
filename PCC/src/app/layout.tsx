import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AppShell } from "@/components/AppShell";

export const metadata: Metadata = {
  title: "PCC — Production Control Center",
  description:
    "ศูนย์รวมสถานะเซ็นเซอร์ กระบวนการผลิต และผลวิเคราะห์จากระบบ AI ภายในโรงงาน",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#2563eb",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="th" className="h-full antialiased">
      <body className="app-bg flex min-h-full flex-col text-slate-900">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
