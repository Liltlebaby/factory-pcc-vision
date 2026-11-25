import { SystemOperations } from "@/components/SystemOperations";
import { readSystemStatus } from "@/lib/system-status-server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function SystemPage() {
  return <SystemOperations initialStatus={await readSystemStatus()} />;
}
