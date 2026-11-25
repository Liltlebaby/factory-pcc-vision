import "server-only";

import { roleFromClaims, type PccRole } from "@/lib/access-control";
import { createSupabaseServerClient, serverAuthConfigured } from "@/lib/supabase/server";

export type PccUser = {
  id: string;
  email: string | null;
  role: PccRole;
};

export function authRequired() {
  return process.env.PCC_AUTH_REQUIRED === "true";
}

export async function getCurrentPccUser(options: { fresh?: boolean } = {}): Promise<PccUser | null> {
  if (!serverAuthConfigured()) return null;
  const supabase = await createSupabaseServerClient();
  if (options.fresh) {
    const { data, error } = await supabase.auth.getUser();
    if (error || !data.user) return null;
    const role = roleFromClaims({
      sub: data.user.id,
      email: data.user.email,
      app_metadata: data.user.app_metadata,
    });
    if (!role) return null;
    return { id: data.user.id, email: data.user.email ?? null, role };
  }
  const { data, error } = await supabase.auth.getClaims();
  if (error || !data?.claims) return null;
  const role = roleFromClaims(data.claims);
  const id = typeof data.claims.sub === "string" ? data.claims.sub : null;
  if (!role || !id) return null;
  return {
    id,
    email: typeof data.claims.email === "string" ? data.claims.email : null,
    role,
  };
}
