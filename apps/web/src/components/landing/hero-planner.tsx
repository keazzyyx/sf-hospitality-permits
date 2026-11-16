"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowRight, CalendarDays, Loader2, RotateCcw, Sparkles } from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ClarifyForm, type ClarifyAnswers } from "@/components/stream/clarify-form";
import { StageProgressList } from "@/components/stream/stage-progress";
import { PreviewResults } from "@/components/landing/preview-results";
import { SAMPLE_PROMPTS } from "@/components/landing/sample-prompts";
import { useGenerationStream } from "@/hooks/use-generation-stream";
import { capture } from "@/lib/analytics";
import { describeApiError, describeErrorCode, isApiError } from "@/lib/api";
import { savePendingPreview } from "@/lib/pending-preview";
import { toIsoDate } from "@/lib/format";

const MIN_DESCRIPTION = 12;

export function HeroPlanner() {
  const [description, setDescription] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [inlineError, setInlineError] = useState<string | null>(null);
  const { state, start, reset } = useGenerationStream();
  const panelRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const minDate = toIsoDate(new Date());

  const active = state.status !== "idle";
  const streaming = state.status === "streaming";

  useEffect(() => {
    if (state.status === "clarify" && state.clarification?.preview_id) {
      setPreviewId(state.clarification.preview_id);
      capture("clarification_shown", { context: "preview", questions: state.clarification.questions.length });
    }
  }, [state.status, state.clarification]);

  useEffect(() => {
    if (state.status === "done" && state.preview) {
      setPreviewId(state.preview.preview_id);
      savePendingPreview({
        preview_id: state.preview.preview_id,
        description,
        target_open_date: targetDate || null,
      });
      capture("preview_completed", {
        preview_id: state.preview.preview_id,
        permit_count: state.preview.permit_count,
        city_supported: state.preview.city_supported,
        city_slug: state.preview.profile.city_slug,
      });
    }
    // description/targetDate are captured at completion time on purpose.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status, state.preview]);

  useEffect(() => {
    if (active) panelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [active]);

  const run = useCallback(
    async (path: string, body: unknown) => {
      setInlineError(null);
      try {
        await start(path, body);
      } catch (err) {
        if (isApiError(err)) setInlineError(describeApiError(err));
      }
    },
    [start],
  );

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = description.trim();
    if (text.length < MIN_DESCRIPTION) {
      setInlineError("Tell us a little more: what you are opening, where, and anything unusual (alcohol, music, patio, late hours).");
      textareaRef.current?.focus();
      return;
    }
    capture("preview_started", { length: text.length, has_target_date: Boolean(targetDate) });
    void run("/v1/preview", { description: text });
  }

  function clarify(answers: ClarifyAnswers) {
    if (!previewId) return;
    void run(`/v1/preview/${encodeURIComponent(previewId)}/clarify`, { answers });
  }

  function startOver() {
    reset();
    setPreviewId(null);
    setInlineError(null);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  return (
    <div ref={panelRef} className="scroll-mt-24">
      {!active ? (
        <form
          onSubmit={submit}
          className="rounded-2xl border border-border bg-card p-4 shadow-[0_1px_0_rgba(20,27,45,0.04),0_12px_40px_-24px_rgba(20,27,45,0.35)] sm:p-6"
          aria-label="Plan builder"
        >
          <Label id="describe-label" htmlFor="describe" className="text-base font-semibold">
            Describe your business
          </Label>
          <p className="mt-1 text-sm text-muted-foreground">
            Concept, city or neighborhood, seats, kitchen, alcohol, hours, music, patio, build-out. Plain English is perfect.
          </p>
          <Textarea
            ref={textareaRef}
            id="describe"
            name="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Opening a 40-seat wine bar in SF Mission, small kitchen, serve until 1am, maybe live music…"
            rows={5}
            maxLength={4000}
            className="mt-3 min-h-32 resize-y bg-background text-base leading-relaxed"
            aria-describedby="describe-help"
          />
          <div id="describe-help" className="mt-3 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Sparkles className="size-3.5" aria-hidden /> Try one:
            </span>
            {SAMPLE_PROMPTS.map((s) => (
              <button
                key={s.label}
                type="button"
                onClick={() => {
                  setDescription(s.text);
                  setInlineError(null);
                  textareaRef.current?.focus();
                }}
                className="rounded-full border border-border bg-background px-3 py-1 text-xs font-medium text-foreground transition-colors hover:border-ink/40 hover:bg-accent"
              >
                {s.label} · {s.city}
              </button>
            ))}
          </div>

          <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div className="grid gap-1.5">
              <Label htmlFor="target-date" className="text-xs text-muted-foreground">
                <CalendarDays className="size-3.5" aria-hidden /> Target open date (optional)
              </Label>
              <Input
                id="target-date"
                type="date"
                min={minDate}
                value={targetDate}
                onChange={(e) => setTargetDate(e.target.value)}
                className="w-full bg-background sm:w-48"
              />
            </div>
            <Button type="submit" size="lg" className="h-11 px-6 text-base">
              Build my plan <ArrowRight />
            </Button>
          </div>

          {inlineError && (
            <p role="alert" className="mt-4 flex items-start gap-2 rounded-lg border border-dead/30 bg-dead-soft p-3 text-sm text-dead">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {inlineError}
            </p>
          )}
        </form>
      ) : (
        <div className="rounded-2xl border border-border bg-card p-4 shadow-sm sm:p-6" data-testid="preview-panel">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-3 border-b border-border pb-4">
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Your description</p>
              <p className="mt-1 line-clamp-2 text-sm text-foreground/90">{description}</p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={startOver} disabled={streaming && state.stages.length === 0}>
              <RotateCcw /> Start over
            </Button>
          </div>

          {(streaming || state.status === "clarify") && (
            <div className={cn("grid gap-6", state.status === "clarify" && "lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]")}>
              <div>
                <p className="mb-3 inline-flex items-center gap-2 text-sm font-medium">
                  {streaming && <Loader2 className="size-4 animate-spin text-signal" aria-hidden />}
                  {streaming ? "Building your preview" : "Paused for your answers"}
                </p>
                <StageProgressList stages={state.stages} streaming={streaming} />
              </div>
              {state.status === "clarify" && state.clarification && (
                <ClarifyForm
                  key={state.clarification.questions.map((q) => q.id).join("|")}
                  questions={state.clarification.questions}
                  profile={state.clarification.profile}
                  busy={false}
                  onSubmit={clarify}
                />
              )}
            </div>
          )}

          {state.status === "error" && state.error && (
            <div role="alert" className="rounded-lg border border-dead/30 bg-dead-soft p-4 text-sm text-dead">
              <p className="font-semibold">{state.error.code === "rate_limited" ? "Slow down a moment" : state.error.code === "not_hospitality" ? "We only plan hospitality businesses" : "We could not build that preview"}</p>
              <p className="mt-1 text-dead/90">
                {inlineError ?? describeErrorCode(state.error.code, state.error.message)}
              </p>
              <Button type="button" variant="outline" size="sm" className="mt-3 border-dead/40 text-dead hover:bg-dead/10" onClick={startOver}>
                Edit description
              </Button>
            </div>
          )}

          {state.status === "done" && state.preview && (
            <div className="space-y-6">
              {state.stages.length > 0 && (
                <div className="rounded-lg border border-border bg-paper-deep/40 px-4 py-3">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">How we built this preview</p>
                  <StageProgressList stages={state.stages} streaming={false} className="space-y-1.5" />
                </div>
              )}
              <PreviewResults preview={state.preview} description={description} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
