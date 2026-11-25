"use client";

import { useEffect, useState } from "react";
import type { StationAIStatus } from "@/lib/rack";

type StationAIResult = {
  status: StationAIStatus | null;
  reachable: boolean;
  loading: boolean;
};

export function useStationAIStatus(
  stationId: string,
  intervalMs = 5000,
  initialStatus: StationAIStatus | null = null,
): StationAIResult {
  const [result, setResult] = useState<StationAIResult>({
    status: initialStatus,
    reachable: initialStatus !== null,
    loading: initialStatus === null,
  });

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    async function refresh() {
      try {
        const response = await fetch(
          `/api/integrations/rack-monitor/stations/${encodeURIComponent(stationId)}`,
          { cache: "no-store", signal: controller.signal },
        );
        if (!response.ok) throw new Error("rack_monitor_unreachable");
        const status = (await response.json()) as StationAIStatus;
        if (active) setResult({ status, reachable: true, loading: false });
      } catch (error) {
        if (active && !(error instanceof DOMException && error.name === "AbortError")) {
          setResult((current) => ({ ...current, reachable: false, loading: false }));
        }
      }
    }

    void refresh();
    const timer = window.setInterval(refresh, intervalMs);
    return () => {
      active = false;
      controller.abort();
      window.clearInterval(timer);
    };
  }, [intervalMs, stationId]);

  return result;
}
