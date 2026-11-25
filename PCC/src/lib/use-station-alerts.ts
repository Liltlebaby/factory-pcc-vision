"use client";

import { useEffect, useState } from "react";
import type { StationAlertFeed } from "@/lib/telemetry";

const EMPTY_FEED: StationAlertFeed = {
  data_status: "offline",
  generated_at: new Date(0).toISOString(),
  alerts: [],
};

export function useStationAlerts(initial: StationAlertFeed = EMPTY_FEED, intervalMs = 5000) {
  const [feed, setFeed] = useState(initial);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch("/api/v1/station-alerts?state=open&limit=30", { cache: "no-store" });
        if (!response.ok) throw new Error("station_alert_fetch_failed");
        const next = await response.json() as StationAlertFeed;
        if (active) setFeed(next);
      } catch {
        if (active) setFeed((current) => ({ ...current, data_status: "offline" }));
      }
    };
    const timer = window.setInterval(load, intervalMs);
    window.addEventListener("pcc:station-alerts-refresh", load);
    void load();
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener("pcc:station-alerts-refresh", load);
    };
  }, [intervalMs]);

  return feed;
}
