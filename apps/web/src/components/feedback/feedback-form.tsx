"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, CheckCircle2, CircleCheck, CircleDashed, CircleX, Clock3, Loader2, MapPin, Undo2 } from "lucide-react";
import { cn } from "cn";
import { APP_NAME } from "@/lib/brand";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, describeApiError, isApiError } from "@/lib/api";
import { capture } from "@/lib/analytics";
import type { FeedbackInfo, FeedbackOutcome } from "@/lib/api-types";

const OUTCOMES: { value: FeedbackOutcome; label: string; hint: string; icon: typeof CircleCheck; cls: string }[] = [
  { value: "approved", label: "Approved", hint: "As filed, no conditions beyond the standard ones", icon: CircleCheck, cls: "border-verified/40 bg-verified-soft text-verified hover:border-verified" },
  { value: "approved_with_conditions", label: "Approved with conditions", hint: "Hours, sound, security or other conditions attached", icon: CircleDashed, cls: "border-estimated/50 bg-estimated-soft text-estimated hover:border-estimated" },
  { value: "denied", label: "Denied", hint: "The Commission or agency refused it", icon: CircleX, cls: "border-dead/40 bg-dead-soft text-dead hover:border-dead" },
  { value: "withdrew", label: "We withdrew", hint: "Pulled the application or walked away from the site", icon: Undo2, cls: "border-border bg-muted text-foreground hover:border-ink/50" },
  { value: "still_pending", label: "Still pending", hint: "Filed and waiting, or not filed yet", icon: Clock3, cls: "border-ink/20 bg-paper-deep text-ink hover:border-ink/60" },
];

/** `/feedback/[token]`: public outcome report from the 90-day email. No auth. */
export function FeedbackForm({ token }: { token: string }) {
  const [info, setInfo] = useState<FeedbackInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [outcome, setOutcome] = useState<FeedbackOutcome | null>(null);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .feedback(token)
      .then((res) => {
        if (!cancelled) setInfo(res);
      })
      .catch((err) => {
        if (cancelled) return;
        if (isApiError(err) && (err.status === 404 || err.status === 410 || err.status === 400)) setInvalid(true);
        else setLoadError(describeApiError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!outcome || busy) return;
    setBusy(true);
    setSubmitError(null);
    try {
      await api.submitFeedback(token, { outcome, notes: notes.trim() || undefined });
      capture("feedback_submitted", { memo_id: info?.memo_id ?? null, outcome, has_notes: notes.trim().length > 0, concept_type: info?.concept_type ?? null });
      setDone(true);
    } catch (err) {
      if (isApiError(err) && err.status === 409) {
        setInfo((i) => (i ? { ...i, already_answered: true } : i));
      } else {
        setSubmitError(describeApiError(err));
      }
    } finally {
      setBusy(false);
    }
  }

  if (invalid) {
    return (
      <div className="rounded-2xl border border-border bg-card p-8 text-center" data-testid="feedback-invalid">
        <h1 className="text-2xl font-semibold">This link is no longer valid</h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">Feedback links expire, and each one belongs to a single memo. If you still want to tell us how it went, reply to the email you received.</p>
        <Button asChild variant="outline" className="mt-6">
          <Link href="/">Back to {APP_NAME}</Link>
        </Button>
      </div>
    );
  }

  if (loadError) {
    return (
      <div role="alert" className="rounded-2xl border border-dead/30 bg-dead-soft p-6 text-sm text-dead">
        <p className="font-semibold">Could not load this feedback request</p>
        <p className="mt-1">{loadError}</p>
      </div>
    );
  }

  if (!info) {
    return (
      <div className="space-y-4" aria-busy>
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-10 w-96 max-w-full" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const subject = (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Your memo</p>
      <p className="mt-1 inline-flex items-start gap-2 font-semibold leading-snug">
        <MapPin className="mt-0.5 size-4 shrink-0 text-signal" aria-hidden /> <span data-testid="feedback-address">{info.address}</span>
      </p>
      <p className="mt-0.5 text-sm text-muted-foreground" data-testid="feedback-concept">
        {info.concept_type.replace(/_/g, " ")}
      </p>
    </div>
  );

  if (done) {
    return (
      <div className="space-y-6" data-testid="feedback-thanks" role="status">
        <div className="rounded-2xl border border-verified/30 bg-verified-soft p-8 text-center">
          <CheckCircle2 className="mx-auto size-10 text-verified" aria-hidden />
          <h1 className="mt-4 text-2xl font-semibold">Thank you</h1>
          <p className="mx-auto mt-2 max-w-md text-sm text-foreground/80">
            Your outcome is now part of the record behind every future memo on this block. Real decisions are the best signal we have, and most operators never report back.
          </p>
        </div>
        {subject}
        <Button asChild>
          <Link href="/">
            Check another address <ArrowRight />
          </Link>
        </Button>
      </div>
    );
  }

  if (info.already_answered) {
    return (
      <div className="space-y-6" data-testid="feedback-already">
        <div className="rounded-2xl border border-border bg-card p-8 text-center">
          <CheckCircle2 className="mx-auto size-10 text-verified" aria-hidden />
          <h1 className="mt-4 text-2xl font-semibold">Already answered</h1>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">We have your outcome for this memo on file. If something changed since, reply to the email and we will update it.</p>
        </div>
        {subject}
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-6" data-testid="feedback-form">
      <header>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-signal">90-day check-in</p>
        <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">How did it go?</h1>
        <p className="mt-2 max-w-xl text-sm text-muted-foreground">One tap. Your answer calibrates the reports other operators see for this neighborhood, and we never show who reported it.</p>
      </header>

      {subject}

      <fieldset>
        <legend className="mb-3 text-sm font-medium">What happened with the application?</legend>
        <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Outcome">
          {OUTCOMES.map((o) => {
            const active = outcome === o.value;
            return (
              <button
                key={o.value}
                type="button"
                role="radio"
                aria-checked={active}
                data-testid={`outcome-${o.value}`}
                onClick={() => setOutcome(o.value)}
                className={cn(
                  "flex items-start gap-3 rounded-2xl border-2 p-4 text-left transition-all",
                  o.cls,
                  active ? "ring-[3px] ring-ring/40 shadow-md" : "opacity-90",
                )}
              >
                <o.icon className="mt-0.5 size-6 shrink-0" aria-hidden />
                <span>
                  <span className="block text-base font-semibold">{o.label}</span>
                  <span className="mt-0.5 block text-xs text-foreground/70">{o.hint}</span>
                </span>
              </button>
            );
          })}
        </div>
      </fieldset>

      <div className="grid gap-1.5">
        <Label htmlFor="feedback-notes">Anything worth passing on? (optional)</Label>
        <Textarea
          id="feedback-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={4}
          maxLength={2000}
          placeholder="Conditions you were given, how long the hearing took, who showed up to oppose, what the Commission asked about…"
          className="resize-y bg-background"
        />
      </div>

      {submitError && (
        <p role="alert" className="flex items-start gap-2 rounded-lg border border-dead/30 bg-dead-soft p-3 text-sm text-dead">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {submitError}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">{outcome ? "Ready to send." : "Pick an outcome to continue."}</p>
        <Button type="submit" size="lg" disabled={!outcome || busy} data-testid="feedback-submit">
          {busy && <Loader2 className="animate-spin" />} Send my answer
        </Button>
      </div>
    </form>
  );
}
