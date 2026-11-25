"use client";

import { useEffect, useState } from "react";
import type { StationTelemetry } from "@/lib/telemetry";

export function useStationTelemetry(stationId: string, initial: StationTelemetry | null) {
  const [status, setStatus] = useState<StationTelemetry | null>(initial);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch(`/api/v1/telemetry?station_id=${encodeURIComponent(stationId)}`, { cache: "no-store" });
        if (!response.ok) return;
        const next = await response.json() as StationTelemetry;
        if (active) setStatus(next);
      } catch {
        // Preserve the latest known reading; freshness status remains visible.
      }
    };
    const timer = window.setInterval(load, 5_000);
    void load();
    return () => { active = false; window.clearInterval(timer); };
  }, [stationId]);

  return status;
}
