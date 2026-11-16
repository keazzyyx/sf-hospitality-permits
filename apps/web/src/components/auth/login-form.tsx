"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, ArrowLeft, KeyRound, Loader2, MailCheck, Settings2 } from "lucide-react";
import { toast } from "sonner";
import { APP_NAME } from "@/lib/brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { useSession } from "@/hooks/use-session";
import { getSupabaseBrowserClient, getSupabaseOtpClient } from "@/lib/supabase/client";
import { readPendingMemo } from "@/lib/pending-memo";
import { readPendingPreview } from "@/lib/pending-preview";

function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/app";
  return raw;
}

function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
      <path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.3-1.6 3.9-5.5 3.9-3.3 0-6-2.7-6-6.1s2.7-6.1 6-6.1c1.9 0 3.1.8 3.9 1.5l2.6-2.6C16.9 3.2 14.7 2.2 12 2.2 6.6 2.2 2.2 6.6 2.2 12S6.6 21.8 12 21.8c5.6 0 9.4-4 9.4-9.6 0-.6-.1-1.1-.2-1.6H12z" />
    </svg>
  );
}

export function LoginForm() {
  const params = useSearchParams();
  const router = useRouter();
  const { user, loading, configured } = useSession();
  const next = safeNext(params.get("next"));
  const urlError = params.get("error");

  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState<"email" | "google" | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(urlError);
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);

  const pending = useMemo(() => (typeof window === "undefined" ? null : readPendingPreview()), []);
  const pendingMemo = useMemo(() => (typeof window === "undefined" ? null : readPendingMemo()), []);

  useEffect(() => {
    if (!loading && user) router.replace(next);
  }, [loading, user, next, router]);

  const redirectTo = () => `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`;

  async function sendMagicLink(e: React.FormEvent) {
    e.preventDefault();
    // Implicit-flow sender: no PKCE verifier, so the link works in whichever browser opens it.
    const supabase = getSupabaseOtpClient();
    if (!supabase) return;
    setBusy("email");
    setError(null);
    const { error: err } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: redirectTo(), shouldCreateUser: true },
    });
    setBusy(null);
    if (err) {
      setError(err.message);
      return;
    }
    setSentTo(email.trim());
    setCode("");
    setCodeError(null);
  }

  /**
   * Fallback for people who cannot open the link: the one-time code from the same email. Verified
   * with the email + code pair, so it works in any browser and needs no PKCE verifier.
   */
  async function verifyCode(e: React.FormEvent) {
    e.preventDefault();
    const supabase = getSupabaseBrowserClient();
    if (!supabase || !sentTo) return;
    const token = code.replace(/\D/g, "");
    if (token.length < 6) {
      setCodeError("Enter the 6-digit code from the email.");
      return;
    }
    setVerifying(true);
    setCodeError(null);
    const { error: err } = await supabase.auth.verifyOtp({ email: sentTo, token, type: "email" });
    setVerifying(false);
    if (err) {
      setCodeError(
        /expired|invalid/i.test(err.message)
          ? "That code is wrong or has expired. Check the latest email or request a new link."
          : err.message,
      );
      return;
    }
    // Document load so the middleware and Server Components see the cookies verifyOtp just wrote.
    window.location.replace(new URL(next, window.location.origin).toString());
  }

  async function signInWithGoogle() {
    const supabase = getSupabaseBrowserClient();
    if (!supabase) return;
    setBusy("google");
    setError(null);
    const { error: err } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: redirectTo(), queryParams: { prompt: "select_account" } },
    });
    if (err) {
      setBusy(null);
      setError(err.message);
      toast.error("Google sign-in failed", { description: err.message });
    }
  }

  if (!configured) {
    return (
      <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
        <div className="flex items-start gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-estimated-soft text-estimated" aria-hidden>
            <Settings2 className="size-4" />
          </span>
          <div>
            <h1 className="text-xl font-semibold">Sign-in is not configured</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              This deployment is missing <code className="font-mono text-xs">NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
              <code className="font-mono text-xs">NEXT_PUBLIC_SUPABASE_ANON_KEY</code>. Add them and redeploy to enable
              magic-link and Google sign-in. The anonymous preview on the home page still works.
            </p>
          </div>
        </div>
        <Button asChild variant="outline" className="mt-6">
          <Link href="/">
            <ArrowLeft /> Back to home
          </Link>
        </Button>
      </div>
    );
  }

  if (sentTo) {
    return (
      <div className="rounded-2xl border border-border bg-card p-6 shadow-sm" role="status">
        <span className="grid size-10 place-items-center rounded-full bg-verified-soft text-verified" aria-hidden>
          <MailCheck className="size-5" />
        </span>
        <h1 className="mt-4 text-2xl font-semibold">Check your inbox</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          We sent a sign-in link to <span className="font-medium text-foreground">{sentTo}</span>. Open it on any
          device to continue{pendingMemo ? " to your memo" : pending ? " to your plan" : ""}. It expires in an hour.
        </p>

        <form onSubmit={verifyCode} className="mt-6 space-y-3" aria-label="Sign in with the emailed code">
          <div className="grid gap-1.5">
            <Label htmlFor="otp-code" className="flex items-center gap-1.5">
              <KeyRound className="size-3.5" aria-hidden /> Or enter the 6-digit code from the email
            </Label>
            <Input
              id="otp-code"
              data-testid="otp-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]*"
              maxLength={8}
              placeholder="123456"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              disabled={verifying}
              className="font-mono tracking-[0.3em]"
            />
          </div>
          {codeError && (
            <p role="alert" className="flex items-start gap-2 rounded-lg border border-dead/30 bg-dead-soft p-3 text-sm text-dead">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {codeError}
            </p>
          )}
          <Button type="submit" variant="outline" className="w-full" disabled={verifying || code.length < 6}>
            {verifying && <Loader2 className="animate-spin" />}
            Sign in with code
          </Button>
        </form>

        <Button variant="ghost" size="sm" className="mt-4" onClick={() => setSentTo(null)}>
          Use a different email
        </Button>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
      <h1 className="text-2xl font-semibold">
        {pendingMemo ? "Sign in to check this address" : pending ? "One step from your full plan" : `Sign in to ${APP_NAME}`}
      </h1>
      <p className="mt-1.5 text-sm text-muted-foreground">
        {pendingMemo
          ? `We will pick up “${pendingMemo.address}” the moment you are in. Your first memo teasers are free.`
          : pending
            ? "Create a free account and we will build the complete plan from the preview you just ran."
            : "New here? The same link creates your account. Free memo teasers and 3 free checklists included."}
      </p>

      {error && (
        <p role="alert" className="mt-4 flex items-start gap-2 rounded-lg border border-dead/30 bg-dead-soft p-3 text-sm text-dead">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {error}
        </p>
      )}

      <form onSubmit={sendMagicLink} className="mt-6 space-y-3">
        <div className="grid gap-1.5">
          <Label htmlFor="email">Work email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            placeholder="you@restaurant.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={busy !== null}
          />
        </div>
        <Button type="submit" className="w-full" disabled={busy !== null}>
          {busy === "email" && <Loader2 className="animate-spin" />}
          Email me a sign-in link
        </Button>
      </form>

      <div className="my-5 flex items-center gap-3 text-xs text-muted-foreground">
        <Separator className="flex-1" /> or <Separator className="flex-1" />
      </div>

      <Button type="button" variant="outline" className="w-full" onClick={signInWithGoogle} disabled={busy !== null}>
        {busy === "google" ? <Loader2 className="animate-spin" /> : <GoogleMark />}
        Continue with Google
      </Button>

      <p className="mt-6 text-xs leading-relaxed text-muted-foreground">
        No password to remember: we email you a one-time link and code each time. By continuing you agree to our{" "}
        <Link href="/terms" className="underline">Terms</Link> and{" "}
        <Link href="/privacy" className="underline">Privacy policy</Link>.
      </p>
    </div>
  );
}
