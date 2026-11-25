import { IncidentList } from "@/components/IncidentList";
import { Panel } from "@/components/ui";
import { readStationAlertFeed } from "@/lib/telemetry-database";
import { getCurrentPccUser } from "@/lib/auth-server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function IncidentsPage() {
  const [initialStationAlerts, currentUser] = await Promise.all([
    readStationAlertFeed({ state: "OPEN", limit: 100 }),
    getCurrentPccUser(),
  ]);
  return (
    <div className="space-y-3 sm:space-y-4">
      <IncidentList initialStationAlerts={initialStationAlerts} currentRole={currentUser?.role ?? null} />

      <Panel title="Workflow กลางเดียวกันทั้ง 3 ฟังก์ชัน" icon="🔀">
        <div className="overflow-x-auto">
          <pre className="font-mono text-[11px] leading-relaxed whitespace-pre text-slate-500">
            {`INCIDENT
   ├── Weight Issue  (ตาชั่งหน้าเตา)
   ├── Temp Issue    (Burner / Recorder vs Actual)
   └── Pond Issue    (อุณหภูมิบ่อสุดท้าย ≤ 35°C)
          ↓
     AI Analysis → Impact Assessment → Approval
          ↓
     Action / Task → Verify → Closed`}
          </pre>
        </div>
      </Panel>
    </div>
  );
}
