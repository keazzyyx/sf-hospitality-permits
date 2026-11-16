"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import { friendlyAuthError, safeNext } from "@/lib/auth-callback";

const GIVE_UP_MS = 8000;

/**
 * Lands here from /auth/callback when a sign-in link carried the session in the URL fragment
 * (implicit flow). We hand `#access_token`/`#refresh_token` to the cookie-backed client with
 * setSession, which validates them and writes the auth cookies, then move on. `#error=…` fragments and silence both end on /login.
 */
export function CompleteSignIn() {
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const [status, setStatus] = useState<"working" | "failed">("working");
  const done = useRef(false);

  useEffect(() => {
    const toLogin = (message: string) => {
      if (done.current) return;
      done.current = true;
      const url = new URL("/login", window.location.origin);
      url.searchParams.set("error", friendlyAuthError(message));
      url.searchParams.set("next", next);
      window.location.replace(url.toString());
    };

    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const hashError = hash.get("error_description") ?? hash.get("error");
    if (hashError) {
      toLogin(hashError);
      return;
    }

    const supabase = getSupabaseBrowserClient();
    if (!supabase) {
      toLogin("Authentication is not configured on this deployment.");
      return;
    }

    // Full navigation (not router.replace): the auth cookies were just written, and a document load
    // is the one path that guarantees the middleware and every Server Component see them.
    const finish = () => {
      if (done.current) return;
      done.current = true;
      window.location.replace(new URL(next, window.location.origin).toString());
    };

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) finish();
    });

    // Implicit-flow links put the tokens in the fragment. @supabase/ssr runs PKCE and will not read
    // them itself, so hand them over explicitly; setSession validates them and writes the cookies.
    const accessToken = hash.get("access_token");
    const refreshToken = hash.get("refresh_token");
    if (accessToken && refreshToken) {
      supabase.auth
        .setSession({ access_token: accessToken, refresh_token: refreshToken })
        .then(({ data, error }) => {
          if (error) toLogin(error.message);
          else if (data.session) {
            window.history.replaceState(null, "", window.location.pathname + window.location.search);
            finish();
          }
        });
    } else {
      supabase.auth.getSession().then(({ data }) => {
        if (data.session) finish();
      });
    }
    const timer = window.setTimeout(() => {
      if (done.current) return;
      setStatus("failed");
      toLogin("Email link is invalid or has expired");
    }, GIVE_UP_MS);

    return () => {
      subscription.unsubscribe();
      window.clearTimeout(timer);
    };
  }, [next]);

  return (
    <div className="w-full rounded-2xl border border-border bg-card p-6 text-center shadow-sm" role="status" aria-live="polite">
      <Loader2 className="mx-auto size-6 animate-spin text-muted-foreground" aria-hidden />
      <p className="mt-3 text-sm text-muted-foreground">
        {status === "working" ? "Signing you in…" : "That link did not work. Sending you back to sign in…"}
      </p>
    </div>
  );
}
