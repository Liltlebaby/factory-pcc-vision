import { NextResponse } from "next/server";
import { RACK_API, rackHeaders } from "@/lib/rack";
import type { StationAIStatus } from "@/lib/rack";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const STATION_ID = /^[a-z0-9-]{1,64}$/;

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ stationId: string }> },
) {
  const { stationId } = await params;
  if (!STATION_ID.test(stationId)) {
    return NextResponse.json({ error: "invalid_station_id" }, { status: 400 });
  }

  try {
    const response = await fetch(
      `${RACK_API}/api/v1/stations/${encodeURIComponent(stationId)}/ai-status`,
      {
        headers: rackHeaders(),
        cache: "no-store",
        signal: AbortSignal.timeout(4000),
      },
    );
    if (!response.ok) {
      return NextResponse.json(
        { error: "rack_service_error", status: response.status },
        { status: 502 },
      );
    }

    const status = (await response.json()) as StationAIStatus;
    return NextResponse.json(status, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { error: "rack_service_unreachable" },
      { status: 503 },
    );
  }
}
