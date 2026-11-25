import { NextResponse } from "next/server";
import { readSystemStatus } from "@/lib/system-status-server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const result = await readSystemStatus();
  return NextResponse.json(result, {
    status: result.ready ? 200 : 503,
    headers: { "Cache-Control": "no-store" },
  });
}
