import { RACK_API, rackHeaders } from "@/lib/rack";

// ต้องเป็น nodejs runtime เพื่อส่งต่อสตรีมแบบไม่รอให้จบก่อน
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const revalidate = 0;

/**
 * ส่งต่อภาพสด MJPEG จาก rack_ai มาที่ origin เดียวกับหน้าเว็บ
 *
 * ภาพที่ได้เป็นภาพที่ rack_ai วาดกรอบ เส้นนับ และยอด RACK OUT ลงไปแล้ว
 * จึงไม่ต้องวาดซ้ำฝั่งเบราว์เซอร์ และไม่ต้องส่งพิกัดกล่องข้ามเครือข่าย
 */
export async function GET(request: Request) {
  try {
    const upstream = await fetch(`${RACK_API}/api/live/stream`, {
      headers: rackHeaders(),
      cache: "no-store",
      // ผูกกับ request ของเบราว์เซอร์ พอผู้ใช้ปิดแท็บ สตรีมฝั่งบนก็ถูกปิดตาม
      signal: request.signal,
    });
    if (!upstream.ok || !upstream.body) {
      return new Response("rack_service_error", { status: 502 });
    }
    return new Response(upstream.body, {
      headers: {
        "Content-Type":
          upstream.headers.get("content-type") ??
          "multipart/x-mixed-replace; boundary=frame",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return new Response("rack_service_unreachable", { status: 503 });
  }
}
