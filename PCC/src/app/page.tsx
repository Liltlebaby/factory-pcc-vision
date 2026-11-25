import { PccOverview } from "@/components/PccOverview";
import { getStationAIStatus } from "@/lib/rack-server";
import { readStationAlertFeed, readStationsTelemetry } from "@/lib/telemetry-database";

const OVERVIEW_SENSOR_STATIONS = ["final-pond", "rubber-scale", "furnace-temperature"];

export default async function ControlCenterPage() {
  const [initialRackAI, initialPondAI, initialTelemetry, initialStationAlerts] = await Promise.all([
    getStationAIStatus("rack-infeed"),
    getStationAIStatus("final-pond"),
    readStationsTelemetry(OVERVIEW_SENSOR_STATIONS),
    readStationAlertFeed({ state: "OPEN", limit: 30 }),
  ]);
  return <PccOverview initialRackAI={initialRackAI} initialPondAI={initialPondAI} initialTelemetry={initialTelemetry} initialStationAlerts={initialStationAlerts} />;
}
