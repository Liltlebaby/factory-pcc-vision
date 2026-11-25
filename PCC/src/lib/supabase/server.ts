import "server-only";

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export function serverAuthConfigured() {
  return Boolean(
    (process.env.NEXT_PUBLIC_SUPABASE_URL ?? process.env.SUPABASE_URL) &&
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  );
}

export async function createSupabaseServerClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? process.env.SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) throw new Error("supabase_auth_not_configured");
  const cookieStore = await cookies();

  return createServerClient(url, key, {
    cookieOptions: { sameSite: "lax" },
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
        } catch {
          // Server Components cannot write cookies. proxy.ts refreshes the
          // session before rendering and owns response cookie updates.
        }
      },
    },
  });
}
