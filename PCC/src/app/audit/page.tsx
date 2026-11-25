import { AuditAccessState, AuditLogView } from "@/components/AuditLogView";
import { hasCapability } from "@/lib/access-control";
import { getCurrentPccUser } from "@/lib/auth-server";
import { readPccAuditFeed } from "@/lib/telemetry-database";
import { serverAuthConfigured } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function AuditPage() {
  if (!serverAuthConfigured()) return <AuditAccessState state="not_configured" />;
  const user = await getCurrentPccUser({ fresh: true });
  if (!user) return <AuditAccessState state="unauthenticated" />;
  if (!hasCapability(user.role, "audit:view")) return <AuditAccessState state="forbidden" />;
  const feed = await readPccAuditFeed({ limit: 200 });
  if (feed.dataStatus !== "live") return <AuditAccessState state="offline" />;
  return <AuditLogView feed={feed} />;
}
