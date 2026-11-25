import { timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";
import { parseSensorTelemetryBatch } from "@/lib/telemetry-contract";
import {
  persistSensorTelemetry,
  persistStationRuleEvaluations,
  readStationTelemetry,
  readStationsTelemetry,
} from "@/lib/telemetry-database";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function authorized(request: Request) {
  const expected = process.env.PCC_TELEMETRY_TOKEN;
  if (!expected) return process.env.NODE_ENV !== "production";
  const actual = Buffer.from(request.headers.get("authorization") ?? "");
  const wanted = Buffer.from(`Bearer ${expected}`);
  return actual.length === wanted.length && timingSafeEqual(actual, wanted);
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const stationId = url.searchParams.get("station_id");
  const stationIds = url.searchParams.get("station_ids")?.split(",").filter(Boolean) ?? [];
  const requested = stationId ? [stationId] : [...new Set(stationIds)];
  if (requested.length === 0 || requested.length > 20 || requested.some((id) => !/^[A-Za-z0-9_-]{1,100}$/.test(id))) {
    return NextResponse.json({ error: "invalid_station_id" }, { status: 400 });
  }
  try {
    const options = {
      hours: Number(url.searchParams.get("hours") ?? 2),
      limit: Number(url.searchParams.get("limit") ?? 500),
    };
    const result = stationId
      ? await readStationTelemetry(stationId, options)
      : { stations: await readStationsTelemetry(requested, options) };
    return NextResponse.json(result, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    console.error("Unable to read station telemetry", error);
    return NextResponse.json({ error: "telemetry_query_failed" }, { status: 503 });
  }
}

export async function POST(request: Request) {
  if (!authorized(request)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  try {
    const items = parseSensorTelemetryBatch(await request.json());
    const accepted = await persistSensorTelemetry(items);
    const stationIds = [...new Set(items.map((item) => item.station_id))];
    const stations = await readStationsTelemetry(stationIds);
    const rulePersistence = await persistStationRuleEvaluations(Object.values(stations));
    return NextResponse.json(
      {
        accepted,
        evaluated: rulePersistence.observations,
        alert_changes: rulePersistence.alerts,
        stations: Object.values(stations).map((station) => ({
          station_id: station.station_id,
          data_status: station.data_status,
          process_status: station.process_status,
          violations: station.rules.filter((rule) => rule.is_violation).map((rule) => rule.rule_code),
        })),
      },
      { status: 202, headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    const invalid = error instanceof Error && error.message.startsWith("invalid_sensor_telemetry");
    if (!invalid) console.error("Unable to ingest sensor telemetry", error);
    return NextResponse.json(
      { error: invalid ? "invalid_sensor_telemetry" : "telemetry_ingest_failed" },
      { status: invalid ? 400 : 503 },
    );
  }
}
