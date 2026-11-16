"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowRight, CalendarDays, Loader2, Sparkles } from "lucide-react";
import { useApp } from "@/components/app/app-context";
import { PaywallCard } from "@/components/billing/paywall-card";
import { SAMPLE_PROMPTS } from "@/components/landing/sample-prompts";
import { ClarifyForm, type ClarifyAnswers } from "@/components/stream/clarify-form";
import { NarrativeBox, StageProgressList } from "@/components/stream/stage-progress";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useGenerationStream } from "@/hooks/use-generation-stream";
import { capture } from "@/lib/analytics";
import { describeErrorCode, isApiError } from "@/lib/api";
import { toIsoDate } from "@/lib/format";
import { clearPendingPreview, readPendingPreview } from "@/lib/pending-preview";

const MIN_DESCRIPTION = 12;

export function NewPlan() {
  const router = useRouter();
  const { accessToken, me, refreshMe } = useApp();
  const { state, start, reset } = useGenerationStream();
  const [description, setDescription] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [paywall, setPaywall] = useState<{ plans_created?: number; free_limit?: number } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [resumed, setResumed] = useState(false);
  const autoStarted = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const minDate = toIsoDate(new Date());
  const streaming = state.status === "streaming";

  const createPlan = useCallback(
    async (body: { description: string; target_open_date?: string; preview_id?: string }) => {
      setFormError(null);
      setPaywall(null);
      capture("plan_started", {
        from_preview: Boolean(body.preview_id),
        has_target_date: Boolean(body.target_open_date),
        length: body.description.length,
      });
      try {
        await start("/v1/plans", body, { token: accessToken });
      } catch (err) {
        if (isApiError(err) && err.isPaywall) {
          capture("paywall_hit", { source: "new_plan", action: "blocked", ...err.extra });
          setPaywall({
            plans_created: typeof err.extra.plans_created === "number" ? err.extra.plans_created : undefined,
            free_limit: typeof err.extra.free_limit === "number" ? err.extra.free_limit : undefined,
          });
          return;
        }
        if (isApiError(err)) setFormError(describeErrorCode(err.code, err.message));
      }
    },
    [accessToken, start],
  );

  // Resume the anonymous preview from the landing page.
  useEffect(() => {
    if (autoStarted.current) return;
    const pending = readPendingPreview();
    if (!pending) return;
    autoStarted.current = true;
    setResumed(true);
    setDescription(pending.description);
    setTargetDate(pending.target_open_date ?? "");
    setPreviewId(pending.preview_id);
    void createPlan({
      description: pending.description,
      target_open_date: pending.target_open_date ?? undefined,
      preview_id: pending.preview_id,
    });
  }, [createPlan]);

  // The plan row exists once plan_created arrives; the pending preview is no longer needed.
  useEffect(() => {
    if (state.planId) clearPendingPreview();
  }, [state.planId]);

  useEffect(() => {
    if (state.status === "clarify" && state.clarification) {
      capture("clarification_shown", { context: "plan", questions: state.clarification.questions.length });
    }
  }, [state.status, state.clarification]);

  useEffect(() => {
    if (state.status === "done" && state.plan) {
      capture("plan_completed", {
        plan_id: state.plan.id,
        steps: state.plan.plan?.steps.length ?? 0,
        city_supported: state.plan.plan?.city_supported ?? null,
        version: state.plan.version,
      });
      void refreshMe();
      router.push(`/app/plans/${state.plan.id}`);
    }
  }, [state.status, state.plan, router, refreshMe]);

  useEffect(() => {
    if (state.status === "error") clearPendingPreview();
  }, [state.status]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = description.trim();
    if (text.length < MIN_DESCRIPTION) {
      setFormError("Tell us a little more: what you are opening, where, and anything unusual (alcohol, music, patio, late hours).");
      textareaRef.current?.focus();
      return;
    }
    void createPlan({
      description: text,
      target_open_date: targetDate || undefined,
      preview_id: previewId ?? undefined,
    });
  }

  function clarify(answers: ClarifyAnswers) {
    if (!state.planId) return;
    void (async () => {
      try {
        await start(`/v1/plans/${encodeURIComponent(state.planId as string)}/clarify`, { answers }, { token: accessToken });
      } catch (err) {
        if (isApiError(err)) setFormError(describeErrorCode(err.code, err.message));
      }
    })();
  }

  if (paywall) {
    return (
      <div className="space-y-6">
        <header>
          <h1 className="text-2xl font-semibold sm:text-3xl">Unlock your next plan</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {description ? `“${description.slice(0, 120)}${description.length > 120 ? "…" : ""}”` : "Your description is saved."}
          </p>
        </header>
        <PaywallCard plansCreated={paywall.plans_created} freeLimit={paywall.free_limit} />
      </div>
    );
  }

  const busyPanel = streaming || state.status === "clarify" || state.status === "done";

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold sm:text-3xl">New plan</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {me && me.entitlement.kind === "free" && !me.is_admin
              ? `${me.free_plans_remaining} of ${me.free_limit} free plans remaining.`
              : "Describe the business and we will sequence every permit."}
          </p>
        </div>
      </header>

      {!busyPanel ? (
        <form onSubmit={submit} className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
          <Label htmlFor="new-description" className="text-base font-semibold">
            Describe your business
          </Label>
          <p className="mt-1 text-sm text-muted-foreground">
            Concept, city, seats, kitchen, alcohol, hours, music, patio, build-out. The more specific, the fewer questions we ask.
          </p>
          <Textarea
            ref={textareaRef}
            id="new-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={6}
            maxLength={4000}
            placeholder="Opening a 40-seat wine bar in SF Mission, small kitchen, serve until 1am, maybe live music…"
            className="mt-3 min-h-36 resize-y bg-background text-base leading-relaxed"
          />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Sparkles className="size-3.5" aria-hidden /> Try one:
            </span>
            {SAMPLE_PROMPTS.map((s) => (
              <button
                key={s.label}
                type="button"
                onClick={() => setDescription(s.text)}
                className="rounded-full border border-border bg-background px-3 py-1 text-xs font-medium transition-colors hover:border-ink/40 hover:bg-accent"
              >
                {s.label} · {s.city}
              </button>
            ))}
          </div>
          <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div className="grid gap-1.5">
              <Label htmlFor="new-target" className="text-xs text-muted-foreground">
                <CalendarDays className="size-3.5" aria-hidden /> Target open date (optional)
              </Label>
              <Input id="new-target" type="date" min={minDate} value={targetDate} onChange={(e) => setTargetDate(e.target.value)} className="w-full bg-background sm:w-48" />
            </div>
            <Button type="submit" size="lg">
              Build my plan <ArrowRight />
            </Button>
          </div>
          {(formError || state.status === "error") && (
            <p role="alert" className="mt-4 flex items-start gap-2 rounded-lg border border-dead/30 bg-dead-soft p-3 text-sm text-dead">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
              {formError ?? (state.error ? describeErrorCode(state.error.code, state.error.message) : "Something went wrong.")}
            </p>
          )}
        </form>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <section className="rounded-2xl border border-border bg-card p-5 sm:p-6">
            <p className="mb-1 inline-flex items-center gap-2 text-sm font-medium">
              {streaming && <Loader2 className="size-4 animate-spin text-signal" aria-hidden />}
              {streaming ? "Building your plan" : state.status === "done" ? "Plan ready — opening it" : "Paused for your answers"}
            </p>
            <p className="mb-4 line-clamp-3 text-xs text-muted-foreground">
              {resumed ? "Resumed from your preview · " : ""}
              {description}
            </p>
            <StageProgressList stages={state.stages} streaming={streaming} />
            {state.status === "clarify" && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="mt-4"
                onClick={() => {
                  reset();
                  setPreviewId(null);
                }}
              >
                Start over with a new description
              </Button>
            )}
          </section>
          <div className="space-y-4">
            {state.status === "clarify" && state.clarification && (
              <ClarifyForm
                key={state.clarification.questions.map((q) => q.id).join("|")}
                questions={state.clarification.questions}
                profile={state.clarification.profile}
                busy={false}
                onSubmit={clarify}
              />
            )}
            <NarrativeBox text={state.narrative} streaming={streaming} />
            {formError && (
              <p role="alert" className="flex items-start gap-2 rounded-lg border border-dead/30 bg-dead-soft p-3 text-sm text-dead">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {formError}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
