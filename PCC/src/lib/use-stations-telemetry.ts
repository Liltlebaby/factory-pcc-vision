"use client";

import { useEffect, useState } from "react";
import type { StationTelemetry } from "@/lib/telemetry";

export function useStationsTelemetry(
  stationIds: readonly string[],
  initial: Record<string, StationTelemetry>,
) {
  const [stations, setStations] = useState(initial);
  const stationKey = stationIds.join(",");

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch(`/api/v1/telemetry?station_ids=${encodeURIComponent(stationKey)}`, { cache: "no-store" });
        if (!response.ok) return;
        const body = await response.json() as { stations: Record<string, StationTelemetry> };
        if (active) setStations(body.stations);
      } catch {
        // Keep last-known values; their freshness state remains visible.
      }
    };
    const timer = window.setInterval(load, 5_000);
    void load();
    return () => { active = false; window.clearInterval(timer); };
  }, [stationKey]);

  return stations;
}
