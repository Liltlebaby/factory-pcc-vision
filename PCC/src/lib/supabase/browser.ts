"use client";

import { createBrowserClient } from "@supabase/ssr";

export function browserAuthConfigured() {
  return Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL &&
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  );
}

export function createSupabaseBrowserClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) throw new Error("supabase_auth_not_configured");
  return createBrowserClient(url, key, { cookieOptions: { sameSite: "lax" } });
}
