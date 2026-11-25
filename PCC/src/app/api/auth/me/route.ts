import { NextResponse } from "next/server";
import { getCurrentPccUser } from "@/lib/auth-server";
import { serverAuthConfigured } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const configured = serverAuthConfigured();
  const user = configured ? await getCurrentPccUser({ fresh: true }) : null;
  return NextResponse.json(
    { configured, authenticated: Boolean(user), user },
    { headers: { "Cache-Control": "private, no-store, max-age=0" } },
  );
}
