import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export function GET() {
  return NextResponse.json(
    {
      service: "pcc",
      alive: true,
      timestamp: new Date().toISOString(),
      deployment: process.env.DEPLOYMENT_VERSION ?? "local",
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
