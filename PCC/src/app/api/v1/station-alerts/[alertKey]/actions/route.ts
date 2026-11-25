import { NextResponse } from "next/server";
import { hasCapability } from "@/lib/access-control";
import { getCurrentPccUser } from "@/lib/auth-server";
import {
  ALERT_KEY_PATTERN,
  IDEMPOTENCY_KEY_PATTERN,
  parseIncidentActionInput,
} from "@/lib/incident-action-contract";
import {
  applyStationIncidentAction,
  IncidentActionDatabaseError,
} from "@/lib/telemetry-database";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ alertKey: string }> },
) {
  // Incident mutations use a fresh Auth user record so role changes do not
  // depend on an older JWT claim. The database verifies the active profile too.
  const user = await getCurrentPccUser({ fresh: true });
  if (!user) return NextResponse.json({ error: "authentication_required" }, { status: 401 });

  const { alertKey } = await params;
  if (!ALERT_KEY_PATTERN.test(alertKey)) {
    return NextResponse.json({ error: "invalid_alert_key" }, { status: 400 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const parsed = parseIncidentActionInput(body);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const capability = parsed.value.action === "ACKNOWLEDGE"
    ? "incidents:acknowledge"
    : "incidents:resolve";
  if (!hasCapability(user.role, capability)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  if (user.role !== "admin" && user.role !== "operator") {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const idempotencyKey = request.headers.get("idempotency-key") ?? "";
  if (!IDEMPOTENCY_KEY_PATTERN.test(idempotencyKey)) {
    return NextResponse.json({ error: "invalid_idempotency_key" }, { status: 400 });
  }
  const requestId = request.headers.get("x-request-id") ?? crypto.randomUUID();

  try {
    const alert = await applyStationIncidentAction({
      alertKey,
      action: parsed.value.action,
      note: parsed.value.note,
      actorUserId: user.id,
      actorRole: user.role,
      idempotencyKey,
      requestId,
    });
    return NextResponse.json({ alert }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (error instanceof IncidentActionDatabaseError) {
      const status = error.code === "P0002" ? 404
        : error.code === "P0001" || error.code === "23505" ? 409
          : error.code === "22023" ? 400
            : error.code === "42501" ? 403
            : 503;
      return NextResponse.json(
        {
          error: status === 503
            ? "incident_action_unavailable"
            : status === 403
              ? "forbidden"
              : error.message,
        },
        { status },
      );
    }
    console.error("Unable to apply station incident action", error);
    return NextResponse.json({ error: "incident_action_failed" }, { status: 503 });
  }
}
