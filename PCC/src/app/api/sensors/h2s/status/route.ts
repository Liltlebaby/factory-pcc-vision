import { NextResponse } from "next/server";
import { getH2sGatewayStatus } from "@/lib/h2s-server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  return NextResponse.json(await getH2sGatewayStatus(), {
    headers: { "Cache-Control": "no-store" },
  });
}
