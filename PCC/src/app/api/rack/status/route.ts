import { NextResponse } from "next/server";
import { persistRackEvent } from "@/lib/rack-database";
import { RACK_API, rackHeaders } from "@/lib/rack";
import type { RackStatus } from "@/lib/rack";

// ห้าม cache: ตัวเลขนับต้องเป็นค่าล่าสุดเสมอ
export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  try {
    // ตั้ง timeout ไว้ ไม่งั้นถ้า service ค้าง หน้าเว็บจะค้างตาม
    const response = await fetch(`${RACK_API}/api/status`, {
      headers: rackHeaders(),
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
    });
    if (!response.ok) {
      return NextResponse.json(
        { error: "rack_service_error", status: response.status },
        { status: 502 },
      );
    }
    const status = (await response.json()) as RackStatus;
    try {
      await persistRackEvent(status.lastEvent);
    } catch (error) {
      // ฐานข้อมูลล่มต้องไม่ทำให้ภาพและสถานะกล้องล่มตาม
      console.error("Unable to persist Camera 09 event", error);
    }
    return NextResponse.json(status, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    // service ปิดอยู่ หรือเครื่องเข้าไม่ถึง — ไม่ใช่ข้อผิดพลาดของหน้าเว็บ
    return NextResponse.json({ error: "rack_service_unreachable" }, { status: 503 });
  }
}
