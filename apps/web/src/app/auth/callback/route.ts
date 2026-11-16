import { NextResponse, type NextRequest } from "next/server";
import type { EmailOtpType } from "@supabase/supabase-js";
import { friendlyAuthError, nextFromCallbackParams } from "@/lib/auth-callback";
import { createSupabaseServerClient } from "@/lib/supabase/server";

/**
 * Supabase sends people here after a magic link / signup email or Google OAuth consent.
 *
 * Email links use the token-hash flow: the email template links to
 * `/auth/callback?token_hash=…&type=email&redirect_to=…` and we verify the hash server-side with
 * `verifyOtp`, which needs no browser-side PKCE code verifier. That is what lets a link requested on
 * a phone be opened on a laptop, or in a mail app's in-app browser. The `?code=` branch remains for
 * Google OAuth, which starts and finishes in the same browser.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const next = nextFromCallbackParams(searchParams);
  const code = searchParams.get("code");
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  const providerError = searchParams.get("error_description") ?? searchParams.get("error");

  const fail = (message: string) => {
    const url = new URL("/login", origin);
    url.searchParams.set("error", friendlyAuthError(message));
    url.searchParams.set("next", next);
    return NextResponse.redirect(url);
  };

  if (providerError) return fail(providerError);

  // Implicit-flow links (the default Supabase email template) arrive with the session in the URL
  // fragment, which never reaches the server. Browsers keep the fragment across this redirect, and
  // the /auth/complete client page stores the session in the auth cookies.
  if (!tokenHash && !code) {
    const url = new URL("/auth/complete", origin);
    url.searchParams.set("next", next);
    return NextResponse.redirect(url);
  }

  const supabase = await createSupabaseServerClient();
  if (!supabase) return fail("Authentication is not configured on this deployment.");

  if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type });
    if (error) return fail(error.message);
    return NextResponse.redirect(new URL(next, origin));
  }

  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) return fail(error.message);
    return NextResponse.redirect(new URL(next, origin));
  }

  return fail("The sign-in link is missing its code. Request a new one.");
}
