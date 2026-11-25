import { DeviceDirectory } from "@/components/DeviceDirectory";
import { getH2sGatewayStatus } from "@/lib/h2s-server";
import { getStationAIStatus } from "@/lib/rack-server";
import { readStationsTelemetry } from "@/lib/telemetry-database";

export default async function DevicesPage() {
  const [visionStatus, telemetry, h2sStatus] = await Promise.all([
    getStationAIStatus("rack-infeed"),
    readStationsTelemetry(["final-pond", "rubber-scale", "furnace-temperature"]),
    getH2sGatewayStatus(),
  ]);
  return <DeviceDirectory visionStatus={visionStatus} telemetry={telemetry} h2sStatus={h2sStatus} />;
}
