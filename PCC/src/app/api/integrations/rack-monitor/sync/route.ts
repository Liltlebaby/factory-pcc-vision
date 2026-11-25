import { timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";
import { rackDatabaseConfigured, readRackSyncCursor } from "@/lib/rack-database";
import { syncRackAIEvents } from "@/lib/rack-event-sync";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function authorized(request: Request) {
  const expected = process.env.PCC_SYNC_TOKEN;
  if (!expected) return process.env.NODE_ENV !== "production";
  const actual = request.headers.get("authorization") ?? "";
  const wanted = `Bearer ${expected}`;
  const actualBuffer = Buffer.from(actual);
  const wantedBuffer = Buffer.from(wanted);
  return (
    actualBuffer.length === wantedBuffer.length &&
    timingSafeEqual(actualBuffer, wantedBuffer)
  );
}

export async function GET() {
  const configured = rackDatabaseConfigured();
  const cursor = configured ? await readRackSyncCursor() : 0;
  return NextResponse.json(
    { configured, cursor },
    { headers: { "Cache-Control": "no-store" } },
  );
}

export async function POST(request: Request) {
  if (!authorized(request)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  try {
    const result = await syncRackAIEvents();
    return NextResponse.json(result, {
      status: result.configured ? 200 : 503,
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    console.error("Unable to sync Vision Monitor events", error);
    return NextResponse.json(
      { error: "rack_event_sync_failed" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
