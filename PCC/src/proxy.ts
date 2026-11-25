import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_PATHS = new Set(["/login"]);

export async function proxy(request: NextRequest) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? process.env.SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  const required = process.env.PCC_AUTH_REQUIRED === "true";
  if (!url || !key) return NextResponse.next();

  let response = NextResponse.next({ request });
  const supabase = createServerClient(url, key, {
    cookieOptions: { sameSite: "lax" },
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll(cookiesToSet, headers) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        Object.entries(headers).forEach(([name, value]) => response.headers.set(name, value));
      },
    },
  });

  const { data } = await supabase.auth.getClaims();
  const authenticated = Boolean(data?.claims?.sub);
  const pathname = request.nextUrl.pathname;

  if (required && !authenticated && !PUBLIC_PATHS.has(pathname)) {
    const login = request.nextUrl.clone();
    login.pathname = "/login";
    login.searchParams.set("next", pathname);
    return NextResponse.redirect(login);
  }

  if (authenticated && pathname === "/login") {
    const home = request.nextUrl.clone();
    home.pathname = "/";
    home.search = "";
    return NextResponse.redirect(home);
  }

  return response;
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
