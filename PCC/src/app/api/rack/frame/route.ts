import { RACK_API, rackHeaders } from "@/lib/rack";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const revalidate = 0;

/**
 * ภาพนิ่งเฟรมเดียว — ใช้เป็นทางสำรองเมื่อสตรีม MJPEG ใช้ไม่ได้
 * (พร็อกซีบางตัวหรือเบราว์เซอร์บางรุ่นจัดการ multipart ได้ไม่ดี)
 */
export async function GET() {
  try {
    const upstream = await fetch(`${RACK_API}/api/live/frame`, {
      headers: rackHeaders(),
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
    });
    if (!upstream.ok) {
      // 503 จาก rack_ai แปลว่ากล้องยังไม่พร้อม ไม่ใช่ระบบพัง
      return new Response("camera_not_ready", { status: upstream.status });
    }
    return new Response(await upstream.arrayBuffer(), {
      headers: { "Content-Type": "image/jpeg", "Cache-Control": "no-store" },
    });
  } catch {
    return new Response("rack_service_unreachable", { status: 503 });
  }
}
