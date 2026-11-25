import { NextResponse } from "next/server";
import { RACK_API, rackHeaders } from "@/lib/rack";
import type { RackDailyReport } from "@/lib/rack";

// ห้าม cache: ยอดรายชั่วโมงของวันปัจจุบันเปลี่ยนตลอดเวลา
export const dynamic = "force-dynamic";
export const revalidate = 0;

/**
 * ส่งต่อคำขอยอดนับรายชั่วโมง/รายกะไปยัง Vision Monitor
 *
 * ให้เซิร์ฟเวอร์เป็นคนเรียกแทนเบราว์เซอร์ เพราะ token ของ Vision Monitor
 * ต้องไม่หลุดไปฝั่งลูกค้า และเบราว์เซอร์ของผู้ใช้ที่สำนักงานใหญ่อาจเข้าถึง
 * เครื่องในโรงงานไม่ได้อยู่แล้ว
 */
export async function GET(request: Request) {
  const requested = new URL(request.url).searchParams.get("date");
  // ตรวจรูปแบบวันที่ก่อนส่งต่อ กันไม่ให้ค่าจากผู้ใช้ไหลเข้า query ปลายทางดิบ ๆ
  const date = requested && /^\d{4}-\d{2}-\d{2}$/.test(requested) ? requested : null;

  try {
    const target = new URL(`${RACK_API}/api/v1/rack-count/daily`);
    if (date) target.searchParams.set("date", date);
    const response = await fetch(target, {
      headers: rackHeaders(),
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) {
      return NextResponse.json(
        { error: "rack_service_error", status: response.status },
        { status: 502 },
      );
    }
    const report = (await response.json()) as RackDailyReport;
    return NextResponse.json(report, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "rack_service_unreachable" }, { status: 503 });
  }
}
