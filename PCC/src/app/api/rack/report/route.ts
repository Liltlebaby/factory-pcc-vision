import { NextResponse } from "next/server";
import {
  rackDatabaseConfigured,
  readRackEvents,
} from "@/lib/rack-database";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const RETENTION_MS = 7 * 24 * 60 * 60 * 1000;

export async function GET() {
  if (!rackDatabaseConfigured()) {
    return NextResponse.json(
      { configured: false, events: [] },
      { headers: { "Cache-Control": "no-store" } },
    );
  }

  try {
    const events = await readRackEvents(new Date(Date.now() - RETENTION_MS));
    return NextResponse.json(
      { configured: true, events },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    console.error("Unable to read rack report from Supabase", error);
    return NextResponse.json(
      { configured: true, error: "database_unavailable", events: [] },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}

