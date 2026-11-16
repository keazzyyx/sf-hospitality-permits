import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { env, isSupabaseConfigured } from "@/lib/env";

const PROTECTED_PREFIX = "/app";

function loginRedirect(request: NextRequest): NextResponse {
  const url = request.nextUrl.clone();
  const next = `${request.nextUrl.pathname}${request.nextUrl.search}`;
  url.pathname = "/login";
  url.search = "";
  url.searchParams.set("next", next);
  return NextResponse.redirect(url);
}

function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/app";
  return raw;
}

/**
 * Refreshes the Supabase session cookie on every matched request and enforces
 * auth on /app/*. Without Supabase configuration we still protect /app so that
 * the redirect behaviour is identical in CI.
 */
export async function updateSession(request: NextRequest): Promise<NextResponse> {
  const { pathname } = request.nextUrl;
  const isProtected = pathname === PROTECTED_PREFIX || pathname.startsWith(`${PROTECTED_PREFIX}/`);

  if (!isSupabaseConfigured) {
    return isProtected ? loginRedirect(request) : NextResponse.next({ request });
  }

  let response = NextResponse.next({ request });

  const supabase = createServerClient(env.supabaseUrl, env.supabaseAnonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
      },
    },
  });

  // IMPORTANT: no code between client creation and getUser(); it refreshes the token.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user && isProtected) return loginRedirect(request);

  if (user && pathname === "/login") {
    const url = request.nextUrl.clone();
    url.pathname = safeNext(request.nextUrl.searchParams.get("next"));
    url.search = "";
    return NextResponse.redirect(url);
  }

  return response;
}
