import { notFound } from "next/navigation";
import { StationDetail } from "@/components/StationDetail";
import { isStationId } from "@/lib/stations";
import { getStationAIStatus } from "@/lib/rack-server";
import { readStationTelemetry } from "@/lib/telemetry-database";

export default async function StationPage({ params }: { params: Promise<{ stationId: string }> }) {
  const { stationId } = await params;
  if (!isStationId(stationId)) notFound();
  const [initialAI, initialTelemetry] = await Promise.all([
    stationId === "final-pond" || stationId === "rack-infeed"
      ? getStationAIStatus(stationId)
      : null,
    stationId === "final-pond" || stationId === "rubber-scale" || stationId === "furnace-temperature"
      ? readStationTelemetry(stationId)
      : null,
  ]);
  return <StationDetail stationId={stationId} initialAI={initialAI} initialTelemetry={initialTelemetry} />;
}
