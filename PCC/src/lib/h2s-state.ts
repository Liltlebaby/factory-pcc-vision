import type { DataState } from "@/components/StatusMark";
import type { H2sSensorStatus } from "./use-h2s-sensor";

/** สถานะข้อมูลของการ์ด H2S — ใช้ที่เดียวทุกหน้า เพื่อให้ "ยังไม่ติดตั้ง" แสดงเหมือนกันหมด */
export function h2sDataState(status: H2sSensorStatus | null | undefined): DataState {
  if (status?.installed === false) return "NOT_INSTALLED";
  if (status?.online) return "LIVE";
  return status?.serial?.connected ? "STALE" : "OFFLINE";
}
