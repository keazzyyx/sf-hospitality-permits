"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, ArrowRight, Loader2, Lock, MapPinOff, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/components/app/app-context";
import { AddressAutocomplete } from "@/components/memo/address-autocomplete";
import { IntakeQuestions } from "@/components/memo/intake-questions";
import { MemoOffers, type MemoOfferMode } from "@/components/memo/memo-offers";
import { isPro } from "@/components/memo/memo-view";
import { ClarifyForm, type ClarifyAnswers } from "@/components/stream/clarify-form";
import { StageProgressList } from "@/components/stream/stage-progress";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { MEMO_STAGE_LABELS, useGenerationStream } from "@/hooks/use-generation-stream";
import { capture } from "@/lib/analytics";
import { api, describeApiError, describeErrorCode, isApiError } from "@/lib/api";
import { overallStatusOf } from "@/lib/memo";
import { ANSWER_PARAM, ASK_PARAM, EMPTY_INTAKE_FORM, askedQuestions, intakeAnswersFromForm, intakeFormErrors, intakeFormFromAnswers, intakeFromQuery, type IntakeForm } from "@/lib/intake";
import { clearPendingMemo, readPendingMemo, savePendingMemo } from "@/lib/pending-memo";
import type { CreateMemoBody, GeocodeSuggestion, IntakeAnswers, IntakeQuestionId } from "@/lib/api-types";

const MIN_DESCRIPTION = 12;
const CONCEPT_EXAMPLES = [
  "40-seat wine bar, small kitchen, open until 1am, occasional live music",
  "Daytime cafe with pastries from a commissary, beer and wine, closes 6pm",
  "Cocktail bar with DJ on weekends, 60 seats, open until 2am",
  "Full-service restaurant, full liquor, 90 seats, sidewalk tables",
];

interface MemoInput {
  address: string;
  description: string;
  lat?: number;
  lng?: number;
  /** The optional intake answers; null or absent when none was given (the request then carries none). */
  intake?: IntakeAnswers | null;
  /** The earlier-format memo this re-runs (`rerun_of`): the API then uses that memo's address and description. */
  rerunOf?: string | null;
}

/** A re-run link's memo id with the address and description it came with: `rerun_of` is sent only while the form
 * still holds exactly those, since the API runs the earlier memo's own address and description. */
interface RerunSource {
  id: string;
  address: string;
  description: string;
}

function parseCoord(v: string | null): number | undefined {
  if (v === null) return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

/** `/app/memo`: step 1 address + concept, step 2 the streamed generation, then `/app/memos/[id]`. */
export function NewMemo() {
  const router = useRouter();
  const params = useSearchParams();
  const { accessToken, me, refreshMe } = useApp();
  const { state, start, reset } = useGenerationStream();
  const [address, setAddress] = useState("");
  const [selected, setSelected] = useState<GeocodeSuggestion | null>(null);
  const [description, setDescription] = useState("");
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [intake, setIntake] = useState<IntakeForm>(EMPTY_INTAKE_FORM);
  // The intake questions an earlier report named as not given (an "answer these" link from that report).
  const [asked, setAsked] = useState<IntakeQuestionId[]>([]);
  const [formError, setFormError] = useState<string | null>(null);
  const [paywall, setPaywall] = useState(false);
  const [checkoutBusy, setCheckoutBusy] = useState<MemoOfferMode | null>(null);
  const [resumed, setResumed] = useState<"query" | "pending" | "checkout" | null>(null);
  const autoStarted = useRef(false);
  const rerunSource = useRef<RerunSource | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const streaming = state.status === "streaming";

  const createMemo = useCallback(
    async (input: MemoInput) => {
      setFormError(null);
      setPaywall(false);
      const answers = input.intake ?? null;
      const rerunOf = input.rerunOf ?? null;
      savePendingMemo({ address: input.address, description: input.description, lat: input.lat ?? null, lng: input.lng ?? null, intake: answers, rerun_of: rerunOf });
      capture("memo_started", { has_coords: typeof input.lat === "number", length: input.description.length, intake_answered: answers ? Object.keys(answers).length : 0, rerun: rerunOf !== null });
      const body: CreateMemoBody = { address: input.address, description: input.description };
      if (rerunOf) body.rerun_of = rerunOf;
      if (typeof input.lat === "number" && typeof input.lng === "number") {
        body.lat = input.lat;
        body.lng = input.lng;
      }
      if (answers) body.intake = answers;
      try {
        await start("/v1/memos", body, { token: accessToken });
      } catch (err) {
        if (isApiError(err) && err.isPaywall) {
          capture("memo_paywall_hit", { source: "new_memo", action: "blocked", ...err.extra });
          setPaywall(true);
          return;
        }
        if (isApiError(err)) setFormError(describeErrorCode(err.code, err.message));
      }
    },
    [accessToken, start],
  );

  // Prefill (and auto-start) from the landing page query or a memo saved before sign-in / checkout.
  useEffect(() => {
    if (autoStarted.current) return;
    autoStarted.current = true;
    const qAddress = params.get("address")?.trim() ?? "";
    const qDescription = params.get("description")?.trim() ?? "";
    const checkout = params.get("checkout");
    if (checkout) {
      router.replace("/app/memo");
      if (checkout === "success") {
        capture("upgrade", { mode: params.get("mode") ?? "memo", source: "new_memo" });
        void refreshMe();
        toast.success("Payment received", { description: "Resuming your memo." });
      } else {
        toast.info("Checkout cancelled", { description: "No charge was made." });
      }
    }
    if (qAddress || qDescription) {
      const lat = parseCoord(params.get("lat"));
      const lng = parseCoord(params.get("lng"));
      const qIntake = intakeFromQuery(params);
      const qRerunOf = params.get("rerun_of")?.trim() || null;
      rerunSource.current = qRerunOf ? { id: qRerunOf, address: qAddress, description: qDescription } : null;
      setAddress(qAddress);
      setDescription(qDescription);
      setIntake(intakeFormFromAnswers(qIntake));
      if (typeof lat === "number" && typeof lng === "number") setCoords({ lat, lng });
      // An "answer these" link from a report: the form opens filled in, with the questions the report asked for
      // marked, and waits for the answers. Any other link with an address and a concept starts the report at once.
      const answering = params.get(ANSWER_PARAM) === "1";
      setAsked(answering ? askedQuestions(params.get(ASK_PARAM)) : []);
      if (!answering && qAddress && qDescription.length >= MIN_DESCRIPTION) {
        setResumed("query");
        void createMemo({ address: qAddress, description: qDescription, lat, lng, intake: qIntake, rerunOf: qRerunOf });
      }
      return;
    }
    const pending = readPendingMemo();
    if (!pending) return;
    rerunSource.current = pending.rerun_of ? { id: pending.rerun_of, address: pending.address, description: pending.description } : null;
    setAddress(pending.address);
    setDescription(pending.description);
    setIntake(intakeFormFromAnswers(pending.intake));
    if (pending.lat !== null && pending.lng !== null) setCoords({ lat: pending.lat, lng: pending.lng });
    if (pending.address && pending.description.length >= MIN_DESCRIPTION) {
      setResumed(checkout === "success" ? "checkout" : "pending");
      void createMemo({ address: pending.address, description: pending.description, lat: pending.lat ?? undefined, lng: pending.lng ?? undefined, intake: pending.intake, rerunOf: pending.rerun_of });
    }
  }, [params, createMemo, router, refreshMe]);

  // The memo row exists once memo_created arrives; the saved input is no longer needed.
  useEffect(() => {
    if (state.memoId) clearPendingMemo();
  }, [state.memoId]);

  useEffect(() => {
    if (state.status === "clarify" && state.clarification) {
      capture("clarification_shown", { context: "memo", questions: state.clarification.questions.length });
    }
  }, [state.status, state.clarification]);

  useEffect(() => {
    if (state.status === "done" && state.memo) {
      capture("memo_completed", {
        memo_id: state.memo.id,
        access: state.memo.access,
        overall_status: overallStatusOf(state.memo),
        comparable_count: state.memo.teaser?.comparable_count ?? null,
      });
      void refreshMe();
      router.push(`/app/memos/${state.memo.id}`);
    }
  }, [state.status, state.memo, router, refreshMe]);

  useEffect(() => {
    if (state.status === "error" && state.error && state.error.code !== "stream_ended" && state.error.code !== "network") clearPendingMemo();
  }, [state.status, state.error]);

  // The stream dropped after the memo was created: the run goes on on the server (it is not stopped by a closed
  // connection), so open the memo's own page, which follows it until it is ready, rather than offering a retry that
  // would start, and charge, a second memo.
  useEffect(() => {
    if (state.status === "error" && state.memoId && (state.error?.code === "stream_ended" || state.error?.code === "network")) {
      router.replace(`/app/memos/${encodeURIComponent(state.memoId)}`);
    }
  }, [state.status, state.error, state.memoId, router]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = description.trim();
    const addr = address.trim();
    if (addr.length < 5) {
      setFormError("Enter the street address you are considering (number, street and city).");
      return;
    }
    if (text.length < MIN_DESCRIPTION) {
      setFormError("Describe the concept in a sentence: seats, kitchen, alcohol, closing time, music.");
      textareaRef.current?.focus();
      return;
    }
    const intakeErrors = intakeFormErrors(intake);
    if (intakeErrors.length > 0) {
      setFormError(intakeErrors.join(" "));
      return;
    }
    const lat = selected?.lat ?? coords?.lat;
    const lng = selected?.lng ?? coords?.lng;
    const source = rerunSource.current;
    const rerunOf = source && source.address.trim() === addr && source.description.trim() === text ? source.id : null;
    void createMemo({ address: addr, description: text, lat, lng, intake: intakeAnswersFromForm(intake), rerunOf });
  }

  function clarify(answers: ClarifyAnswers) {
    if (!state.memoId) return;
    void (async () => {
      try {
        await start(`/v1/memos/${encodeURIComponent(state.memoId as string)}/clarify`, { answers }, { token: accessToken });
      } catch (err) {
        if (isApiError(err)) setFormError(describeErrorCode(err.code, err.message));
      }
    })();
  }

  async function checkout(mode: MemoOfferMode) {
    capture("memo_paywall_hit", { source: "new_memo", action: "checkout_click", mode });
    setCheckoutBusy(mode);
    try {
      const origin = window.location.origin;
      const { url } = await api.checkout(accessToken, {
        mode,
        success_url: `${origin}/app/memo?checkout=success&mode=${mode}`,
        cancel_url: `${origin}/app/memo?checkout=cancelled`,
      });
      window.location.assign(url);
    } catch (err) {
      setCheckoutBusy(null);
      toast.error("Could not start checkout", { description: describeApiError(err) });
    }
  }

  function startOver() {
    reset();
    setFormError(null);
    setResumed(null);
  }

  const errorCode = state.status === "error" ? state.error?.code : null;
  const coverageProblem = errorCode === "outside_coverage" || errorCode === "address_not_found";

  if (paywall) {
    return (
      <div className="space-y-6" data-testid="memo-paywall">
        <header>
          <h1 className="text-2xl font-semibold sm:text-3xl">Unlock your next memo</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {address ? `${address} · ` : ""}
            {description ? `“${description.slice(0, 100)}${description.length > 100 ? "…" : ""}”` : "Your address and concept are saved."}
          </p>
        </header>
        <div className="rounded-2xl border border-signal/30 bg-signal-soft p-5">
          <p className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-signal">
            <Lock className="size-3.5" aria-hidden /> Free teasers used
          </p>
          <h2 className="mt-1 text-xl font-semibold">You have used your free memo previews</h2>
          <p className="mt-1 text-sm text-foreground/80">
            Buy one memo for this address or go Pro for unlimited checks. Your input is kept and the memo starts the moment payment completes.
          </p>
        </div>
        <MemoOffers onSelect={(mode) => void checkout(mode)} busy={checkoutBusy} />
        <p className="text-xs text-muted-foreground">
          Payments are processed by Stripe. Already have a plan? <Link href="/app/billing" className="underline">Check your billing page</Link>.
        </p>
      </div>
    );
  }

  const busyPanel = streaming || state.status === "clarify" || state.status === "done";

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold sm:text-3xl">New memo</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {me
              ? me.is_admin
                ? "Owner account: unlimited memos, every memo unlocked in full."
                : isPro(me)
                ? "Pro: every memo is unlocked in full."
                : me.memo_credits > 0
                  ? `${me.memo_credits} memo ${me.memo_credits === 1 ? "credit" : "credits"} on your account · ${me.free_teasers_remaining} free ${me.free_teasers_remaining === 1 ? "teaser" : "teasers"} left.`
                  : `${me.free_teasers_remaining} free memo ${me.free_teasers_remaining === 1 ? "teaser" : "teasers"} left. Full memos are $499 or included in Pro.`
              : "Every approval your concept needs at a San Francisco address, with the rules and records behind each, and what's still unknown."}
          </p>
        </div>
      </header>

      {!busyPanel ? (
        <form onSubmit={submit} className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6" aria-label="New memo">
          <div className="grid gap-1.5">
            <Label htmlFor="memo-address" className="text-base font-semibold">
              Step 1 · The address
            </Label>
            <p className="text-sm text-muted-foreground">San Francisco only for now. Pick a suggestion so we pin the exact parcel.</p>
            <AddressAutocomplete
              id="memo-address"
              value={address}
              onChange={(v) => {
                setAddress(v);
                setCoords(null);
              }}
              onSelect={(s) => setSelected(s)}
              selected={selected}
              className="mt-2"
            />
          </div>

          <div className="mt-6 grid gap-1.5">
            <Label htmlFor="memo-description" className="text-base font-semibold">
              Step 2 · The concept
            </Label>
            <p className="text-sm text-muted-foreground">Seats, kitchen, alcohol, closing time, music, patio. What you do not say is listed as not known, never guessed.</p>
            <Textarea
              ref={textareaRef}
              id="memo-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              maxLength={2000}
              placeholder="40-seat wine bar, small kitchen, open until 1am, occasional live music"
              className="mt-2 min-h-28 resize-y bg-background text-base leading-relaxed"
            />
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Sparkles className="size-3.5" aria-hidden /> Try one:
              </span>
              {CONCEPT_EXAMPLES.map((c) => (
                <button key={c} type="button" onClick={() => setDescription(c)} className="rounded-full border border-border bg-background px-3 py-1 text-xs font-medium transition-colors hover:border-ink/40 hover:bg-accent">
                  {c.split(",")[0]}
                </button>
              ))}
            </div>
          </div>

          {asked.length > 0 && (
            <p className="mt-6 rounded-xl border border-estimated/40 bg-estimated-soft px-4 py-3 text-sm leading-relaxed" role="note" data-testid="intake-asked-note">
              The last report could not decide {asked.length === 1 ? "one thing" : `${asked.length} things`} it had no answer for. Answer the marked {asked.length === 1 ? "question" : "questions"} below and check the address again.
            </p>
          )}
          <IntakeQuestions value={intake} onChange={setIntake} asked={asked} />

          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-muted-foreground">Pulls Planning, Entertainment Commission, ABC and Planning Commission records within 500 ft and 1,000 ft and applies the rules. Usually under two minutes.</p>
            <Button type="submit" size="lg" data-testid="memo-submit">
              Check this address <ArrowRight />
            </Button>
          </div>

          {(formError || state.status === "error") && (
            <div role="alert" className={coverageProblem ? "mt-4 flex items-start gap-3 rounded-lg border border-estimated/40 bg-estimated-soft p-4 text-sm" : "mt-4 flex items-start gap-2 rounded-lg border border-dead/30 bg-dead-soft p-3 text-sm text-dead"} data-testid="memo-error">
              {coverageProblem ? <MapPinOff className="mt-0.5 size-4 shrink-0 text-estimated" aria-hidden /> : <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />}
              <div>
                {coverageProblem && <p className="font-semibold">{errorCode === "outside_coverage" ? "Outside our coverage area" : "We could not place that address"}</p>}
                <p className={coverageProblem ? "mt-0.5 text-foreground/85" : undefined}>{formError ?? (state.error ? describeErrorCode(state.error.code, state.error.message) : "Something went wrong.")}</p>
                {errorCode === "outside_coverage" && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Want the free permit checklist for this city instead? <Link href="/checklist" className="underline">It works anywhere in the US.</Link>
                  </p>
                )}
              </div>
            </div>
          )}
        </form>
      ) : (
        <div className={state.status === "clarify" ? "grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]" : "grid max-w-2xl gap-6"}>
          <section className="rounded-2xl border border-border bg-card p-5 sm:p-6" data-testid="memo-progress">
            <p className="mb-1 inline-flex items-center gap-2 text-sm font-medium">
              {streaming && <Loader2 className="size-4 animate-spin text-signal" aria-hidden />}
              {streaming ? "Checking this address" : state.status === "done" ? "Memo ready — opening it" : "Paused for your answers"}
            </p>
            <p className="mb-1 text-sm font-medium">{address}</p>
            <p className="mb-4 line-clamp-3 text-xs text-muted-foreground">
              {resumed === "pending" ? "Resumed after sign-in · " : resumed === "checkout" ? "Resumed after payment · " : ""}
              {description}
            </p>
            <StageProgressList stages={state.stages} streaming={streaming} labels={MEMO_STAGE_LABELS} connectingLabel="Connecting to the records…" />
            {state.status === "clarify" && (
              <Button type="button" variant="ghost" size="sm" className="mt-4" onClick={startOver}>
                Start over with a different address
              </Button>
            )}
          </section>
          <div className="space-y-4">
            {state.status === "clarify" && state.clarification && (
              <ClarifyForm key={state.clarification.questions.map((q) => q.id).join("|")} questions={state.clarification.questions} profile={state.clarification.profile} busy={false} onSubmit={clarify} />
            )}
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
