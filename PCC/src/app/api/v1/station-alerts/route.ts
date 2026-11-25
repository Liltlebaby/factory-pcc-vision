import { NextResponse } from "next/server";
import { readStationAlertFeed } from "@/lib/telemetry-database";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const ID = /^[A-Za-z0-9_-]{1,100}$/;

export async function GET(request: Request) {
  const url = new URL(request.url);
  const stationIds = [...new Set((url.searchParams.get("station_ids") ?? "").split(",").filter(Boolean))];
  const requestedState = url.searchParams.get("state")?.toUpperCase();
  if (
    stationIds.length > 20 ||
    stationIds.some((id) => !ID.test(id)) ||
    (requestedState && requestedState !== "OPEN" && requestedState !== "CLOSED")
  ) {
    return NextResponse.json({ error: "invalid_query" }, { status: 400 });
  }
  try {
    const feed = await readStationAlertFeed({
      stationIds,
      state: requestedState as "OPEN" | "CLOSED" | undefined,
      limit: Number(url.searchParams.get("limit") ?? 30),
    });
    return NextResponse.json(feed, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    console.error("Unable to read station alerts", error);
    return NextResponse.json({ error: "station_alert_query_failed" }, { status: 503 });
  }
}
