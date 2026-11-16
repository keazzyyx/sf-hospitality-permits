/** Pure helpers for /auth/callback (kept out of the route file so they can be unit-tested). */

export function safeNext(raw: string | null | undefined): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/app";
  return raw;
}

/**
 * Where to go after sign-in. Email links carry it as `redirect_to=<origin>/auth/callback?next=…`
 * (Supabase's `{{ .RedirectTo }}` template variable); PKCE and Google flows carry `next` directly.
 * Only the path survives, so a link minted on a preview deployment cannot redirect off-site.
 */
export function nextFromCallbackParams(searchParams: URLSearchParams): string {
  const direct = searchParams.get("next");
  if (direct) return safeNext(direct);
  const redirectTo = searchParams.get("redirect_to");
  if (redirectTo) {
    try {
      return safeNext(new URL(redirectTo).searchParams.get("next"));
    } catch {
      /* not a URL: fall through */
    }
  }
  return "/app";
}

/** Turn Supabase's error strings into something a person can act on. */
export function friendlyAuthError(message: string): string {
  const m = message.toLowerCase();
  if (m.includes("code verifier")) {
    return "That link was opened in a different browser than the one that asked for it. Request a new link here, or enter the code from the email.";
  }
  if (m.includes("expired") || m.includes("invalid") || m.includes("not found")) {
    return "That sign-in link has expired or was already used. Request a new one.";
  }
  return message;
}
