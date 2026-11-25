import "server-only";

import { RACK_API, rackHeaders } from "@/lib/rack";
import type { StationAIStatus } from "@/lib/rack";

export async function getStationAIStatus(stationId: string): Promise<StationAIStatus | null> {
  try {
    const response = await fetch(
      `${RACK_API}/api/v1/stations/${encodeURIComponent(stationId)}/ai-status`,
      {
        headers: rackHeaders(),
        cache: "no-store",
        signal: AbortSignal.timeout(4000),
      },
    );
    if (!response.ok) return null;
    return (await response.json()) as StationAIStatus;
  } catch {
    return null;
  }
}
