import type { H2sLevel } from "@/lib/h2s-levels";
import type { Status } from "@/lib/types";

export type DataState = "LIVE" | "STALE" | "OFFLINE" | "NOT_INSTALLED" | "DEMO";

const PROCESS = {
  GREEN: { label: "ปกติ", classes: "bg-emerald-50 text-emerald-700 ring-emerald-200", dot: "bg-emerald-500" },
  YELLOW: { label: "เฝ้าระวัง", classes: "bg-amber-50 text-amber-700 ring-amber-200", dot: "bg-amber-500" },
  RED: { label: "ผิดปกติ", classes: "bg-red-50 text-red-700 ring-red-200", dot: "bg-red-500" },
  SENSOR_ERROR: { label: "ข้อมูลขัดข้อง", classes: "bg-slate-100 text-slate-600 ring-slate-200", dot: "bg-slate-400" },
} as const;

const DATA = {
  LIVE: { label: "ข้อมูลสด", classes: "text-emerald-700", dot: "bg-emerald-500" },
  STALE: { label: "ข้อมูลเก่า", classes: "text-amber-700", dot: "bg-amber-500" },
  OFFLINE: { label: "ไม่เชื่อมต่อ", classes: "text-red-700", dot: "bg-red-500" },
  NOT_INSTALLED: { label: "ยังไม่ติดตั้ง", classes: "text-slate-500", dot: "bg-slate-400" },
  DEMO: { label: "ข้อมูลจำลอง", classes: "text-blue-700", dot: "bg-blue-500" },
} as const;

export function ProcessStatus({ status }: { status: Status }) {
  const meta = PROCESS[status];
  return <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold ring-1 ${meta.classes}`}><span className={`size-1.5 rounded-full ${meta.dot}`} />{meta.label}</span>;
}

export function H2sStatus({ level }: { level: H2sLevel }) {
  return <span title={level.meaning} className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold ring-1 ${level.classes}`}><span className={`size-1.5 rounded-full ${level.dot}`} />{level.label}</span>;
}

export function DataStatus({ state }: { state: DataState }) {
  const meta = DATA[state];
  return <span className={`inline-flex items-center gap-1.5 text-[11px] font-semibold ${meta.classes}`}><span className={`size-1.5 rounded-full ${meta.dot}`} />{meta.label}</span>;
}
