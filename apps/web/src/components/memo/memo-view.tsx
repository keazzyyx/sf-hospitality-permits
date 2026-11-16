"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CalendarDays, FileDown, FlaskConical, History, ListOrdered, Loader2, Lock, MapPin, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { cn } from "cn";
import { AnswerRoundForm, EarlierVersions } from "@/components/memo/answer-round";
import { Cite, CitationList, CitationProvider } from "@/components/memo/citations";
import { ComparablesMapLazy } from "@/components/memo/comparables-map-lazy";
import { ComparablesTable } from "@/components/memo/comparables-table";
import { MemoOffers, type MemoOfferMode } from "@/components/memo/memo-offers";
import {
  ApprovalRows,
  CouldNotEstablish,
  Disclaimers,
  FactsSection,
  HeadlineFindings,
  HowToRead,
  OutcomeCounts,
  SectionHeading,
  SiteHistorySection,
  SourceNotes,
  ZoningPanel,
} from "@/components/memo/memo-sections";
import { StatusPill } from "@/components/memo/status-pill";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate, pluralize, statusLabel } from "@/lib/format";
import {
  ANSWERS_BUTTON,
  ANSWERS_FORM_TITLE,
  ANSWERS_LIMIT_NOTE,
  ANSWERS_NEW_MEMO_NOTE,
  ANSWER_ROUND_LIMIT,
  FACTS_HEADING,
  FACTS_HINT,
  LEGACY_PAID_NOTE,
  LEGACY_RERUN_USED_NOTE,
  answerableQuestions,
  answersRoundLabel,
  answersRunningLine,
  conceptFromRecord,
  isLegacyRecord,
  overallOf,
  rulesDateLine,
} from "@/lib/memo";
import { memoQuery } from "@/lib/pending-memo";
import { TESTING_NOTICE } from "@/lib/site-copy";
import type { GeoJsonFeatureCollection, IntakeAnswers, IntakeQuestionId, Me, MemoRecord, MemoRevision } from "@/lib/api-types";

export interface MemoViewActions {
  /** Instant unlock (user has a memo credit or Pro). */
  onUnlock?: () => void;
  /** Start Stripe Checkout for an offer. */
  onCheckout?: (mode: MemoOfferMode) => void;
  onExportPdf?: () => void;
  onDelete?: () => Promise<void> | void;
  /** An answer round: the same memo run again with these answers (`POST /v1/memos/{id}/answers`), free. */
  onAnswer?: (answers: IntakeAnswers) => void;
}

export interface MemoViewProps {
  record: MemoRecord;
  me: Me | null;
  geojson?: GeoJsonFeatureCollection | null;
  actions?: MemoViewActions;
  busy?: { unlock?: boolean; checkout?: MemoOfferMode | null; export?: boolean; answer?: boolean };
  /** Shown above the memo (e.g. "Payment received, unlocking…"). */
  notice?: React.ReactNode;
  /** The versions answer rounds replaced (`GET /v1/memos/{id}/revisions`), oldest first. */
  revisions?: MemoRevision[] | null;
  /** Why the last answer round was refused before it started (the API's message). */
  answerError?: string | null;
}

/** Unlimited memos: Pro, or an owner account listed in the API's ADMIN_EMAILS (no paywall, no credit used). */
export function isPro(me: Me | null | undefined): boolean {
  return me?.pro_status === "active" || me?.pro_status === "trialing" || me?.is_admin === true;
}

/**
 * Pure memo page: takes `MemoRecord` + `Me` and renders either the teaser (overall status + counts above an
 * unlock card and a blurred preview), the full report (format 3: the headline findings first, then the rules
 * and the evidence, one row per
 * approval with its rule lines and the facts its rules read; no text a model wrote), or the "earlier format"
 * card for memos stored before format 3. No data fetching, no app context, so the same component powers
 * `/app/memos/[id]` and the development preview route.
 */
export function MemoView({ record, me, geojson, actions = {}, busy = {}, notice, revisions = null, answerError = null }: MemoViewProps) {
  const [answerOpen, setAnswerOpen] = useState(false);
  const legacy = isLegacyRecord(record);
  // Every read of the memo goes through this: a record without full access renders no memo content,
  // even if one arrives attached.
  const memo = legacy || record.access !== "full" ? null : record.memo;
  const teaser = legacy ? null : record.teaser;
  const overall = legacy ? null : overallOf({ memo, teaser });
  const full = memo !== null;
  const concept = conceptFromRecord({ description: record.description, memo });
  // Printed only when the rules applied are not those of the day the report was generated.
  const rulesLine = memo ? rulesDateLine(memo.pathway?.rules_date) : null;
  // A memo in an earlier format is re-run with `rerun_of`, so the API can make the first re-run of one the user
  // unlocked free (it then uses that memo's own address and description). A free re-run that did not finish
  // (failed, or still not ready) names that earlier memo too, so retrying it stays free.
  const rerunOf = legacy ? record.id : record.status !== "ready" ? (record.rerun_of ?? null) : null;
  const rerunHref = `/app/memo?${memoQuery({ address: record.address, description: record.description, lat: record.lat, lng: record.lng, intake: record.intake, rerunOf })}`;
  // What the report could not settle for want of an answer the applicant can give: the form opens with the same
  // address, concept and answers, the questions the report asked for marked, and waits for them.
  const ask = memo ? answerableQuestions(memo.could_not_establish) : [];
  const answerHref = ask.length > 0 ? `/app/memo?${memoQuery({ address: record.address, description: record.description, lat: record.lat, lng: record.lng, intake: record.intake, ask })}` : null;
  // An answer round (owner decision of 2026-11-16): the same memo run again with the answers, free, and the page
  // stays. A memo the API cannot answer that way (made before its intake result was kept, or with no round left)
  // keeps the link above, which makes a new memo, and says so.
  const rounds = record.answers_round ?? 0;
  // a round that finished closes the form; the page shows the updated report
  useEffect(() => {
    setAnswerOpen(false);
  }, [rounds]);
  const canAnswer = record.answers_available === true && record.status === "ready" && Boolean(actions.onAnswer);
  const answerNote = canAnswer || !actions.onAnswer ? null : rounds >= ANSWER_ROUND_LIMIT ? ANSWERS_LIMIT_NOTE : ANSWERS_NEW_MEMO_NOTE;
  const submitAnswers = (answers: IntakeAnswers) => {
    actions.onAnswer?.(answers);
  };
  const answerForm = (asked: readonly IntakeQuestionId[]) =>
    canAnswer && answerOpen ? (
      <AnswerRoundForm record={record} asked={asked} onAnswer={submitAnswers} onCancel={() => setAnswerOpen(false)} busy={busy.answer} error={answerError} />
    ) : null;
  const answerButton = canAnswer ? (
    <Button type="button" variant="outline" className="shrink-0" onClick={() => setAnswerOpen(true)} disabled={answerOpen || busy.answer} data-testid="answer-questions-button">
      {ANSWERS_BUTTON}
    </Button>
  ) : null;

  return (
    <CitationProvider citations={memo?.citations ?? []}>
    <article className="space-y-8" data-testid="memo-view" data-access={record.access} data-format={legacy ? "legacy" : "3"}>
      <header className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 max-w-3xl">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="border-ink/20 bg-paper-deep text-ink">
                Location Risk Memo
              </Badge>
              {legacy ? (
                <Badge variant="outline" className="border-border bg-muted text-muted-foreground" data-testid="access-badge">
                  Earlier format
                </Badge>
              ) : (
                <Badge
                  variant="outline"
                  className={cn(
                    full ? "border-verified/30 bg-verified-soft text-verified" : "border-estimated/40 bg-estimated-soft text-estimated",
                  )}
                  data-testid="access-badge"
                >
                  {full ? "Full memo" : "Teaser"}
                </Badge>
              )}
              {record.status !== "ready" && <Badge variant="outline">{statusLabel(record.status)}</Badge>}
              {!legacy && rounds > 0 && (
                <Badge variant="outline" className="border-verified/30 bg-verified-soft text-verified" data-testid="answers-round-label" data-round={rounds}>
                  {answersRoundLabel(rounds)}
                </Badge>
              )}
              {record.batch_id && (
                <Link href={`/app/memos/bulk/${encodeURIComponent(record.batch_id)}`} className="font-mono text-xs text-muted-foreground hover:text-foreground">
                  batch {record.batch_id.slice(0, 8)}
                </Link>
              )}
            </div>
            <h1 className="mt-2 flex items-start gap-2 text-2xl font-semibold leading-tight sm:text-3xl">
              <MapPin className="mt-1.5 size-5 shrink-0 text-signal" aria-hidden />
              <span data-testid="memo-address">{record.address}</span>
            </h1>
            <p className="mt-1.5 text-base text-muted-foreground" data-testid="memo-concept">
              <span className="sr-only">Your description: </span>“{concept}”
            </p>
            <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <CalendarDays className="size-3.5" aria-hidden /> Generated {formatDate(record.created_at)}
              {record.unlocked_at ? ` · unlocked ${formatDate(record.unlocked_at)}` : ""}
              {rounds > 0 && record.answered_at ? ` · updated ${formatDate(record.answered_at)}` : ""}
              {rulesLine && (
                <>
                  {" · "}
                  <span data-testid="rules-date">{rulesLine}</span>
                </>
              )}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {full && actions.onExportPdf && (
              <Button type="button" variant="outline" onClick={actions.onExportPdf} disabled={busy.export} data-testid="export-pdf">
                {busy.export ? <Loader2 className="animate-spin" /> : <FileDown />} Export PDF
              </Button>
            )}
            <Button asChild variant="outline">
              <Link href={rerunHref} data-testid="rerun-link">
                <RefreshCw /> Re-run
              </Link>
            </Button>
          </div>
        </div>

        <p
          className="flex items-start gap-2 rounded-xl border border-estimated/40 bg-estimated-soft px-4 py-3 text-sm font-medium leading-relaxed text-foreground"
          role="note"
          data-testid="testing-notice"
        >
          <FlaskConical className="mt-0.5 size-4 shrink-0 text-estimated" aria-hidden />
          <span>{TESTING_NOTICE}</span>
        </p>

        {/* first: what changes the business's plans here, set by rule (app.memo.pathway rule 9) */}
        {memo && <HeadlineFindings findings={memo.headline_findings} />}

        {overall && (
          <div className="rounded-2xl border border-border bg-card p-5" data-testid="overall-card">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:gap-5">
              <StatusPill status={overall.status} size="lg" />
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Overall</p>
                <p className="mt-0.5 text-base leading-relaxed text-foreground" data-testid="overall-line">
                  {overall.line}
                  {memo && <Cite ids={memo.overall.citations} />}
                </p>
                {teaser && (
                  <p className="mt-2 text-sm text-muted-foreground" data-testid="teaser-counts">
                    {pluralize(teaser.comparable_count, "comparable case")} found · {pluralize(teaser.approvals_count, "approval")} needed · {teaser.blockers_count} marked Potential blocker or Not permitted
                  </p>
                )}
              </div>
            </div>
            {memo && memo.entitlement_path && (
              <div className="mt-4 border-t border-border pt-4" data-testid="entitlement-path">
                <p className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  <ListOrdered className="size-3.5" aria-hidden /> Approvals to file, in order
                </p>
                <p className="mt-1 text-sm font-medium leading-relaxed">{memo.entitlement_path}</p>
              </div>
            )}
          </div>
        )}
      </header>

      {notice}

      {record.status === "failed" && (
        <div role="alert" className="rounded-xl border border-dead/30 bg-dead-soft p-5 text-sm text-dead">
          <p className="font-semibold">Generation failed</p>
          <p className="mt-1">{record.error ?? "Something went wrong while writing this memo. Re-run it; failed memos are not charged."}</p>
        </div>
      )}

      {record.status === "generating" &&
        (record.answers_running ? (
          <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-5 text-sm" role="status" data-testid="answers-running">
            <Loader2 className="size-4 animate-spin text-signal" aria-hidden />
            {answersRunningLine(rounds + 1)}
          </div>
        ) : (
          <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-5 text-sm">
            <Loader2 className="size-4 animate-spin text-signal" aria-hidden />
            This memo is still being written. The page refreshes itself.
          </div>
        ))}

      {/* a ready memo with an error line: an answer round that did not finish left the report as it was */}
      {record.status === "ready" && record.error && !legacy && (
        <p role="status" className="rounded-xl border border-estimated/40 bg-estimated-soft p-4 text-sm" data-testid="answers-error">
          {record.error}
        </p>
      )}

      {legacy && record.status === "ready" && (
        <section className="rounded-2xl border border-border bg-card p-6" data-testid="legacy-card" aria-labelledby="legacy-title">
          <p className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            <History className="size-3.5" aria-hidden /> Earlier format
          </p>
          <p id="legacy-title" className="mt-2 text-base font-medium leading-relaxed">
            This memo was generated in an earlier report format. Re-run it to get the current report.
          </p>
          {record.access === "full" && (
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground" data-testid="legacy-paid-note" data-rerun-free={record.rerun_free === true ? "true" : "false"}>
              {record.rerun_free === true ? LEGACY_PAID_NOTE : LEGACY_RERUN_USED_NOTE}
            </p>
          )}
          <Button asChild className="mt-4">
            <Link href={rerunHref} data-testid="legacy-rerun-link">
              <RefreshCw /> Re-run
            </Link>
          </Button>
        </section>
      )}

      {legacy ? null : full && memo ? (
          <div className="space-y-10">
            <section aria-labelledby="sec-approvals">
              <SectionHeading id="sec-approvals" eyebrow="Approvals" title={`${pluralize(memo.approvals.length, "approval")} this concept needs`} hint="One row per approval. Rules set each status from what you told us and the records found. Each row shows the rules applied, the facts they read and where each came from, and what is not known." />
              <ApprovalRows memo={memo} />
            </section>

            <section aria-labelledby="sec-facts">
              <SectionHeading id="sec-facts" eyebrow="Your concept" title={FACTS_HEADING} hint={FACTS_HINT} />
              <FactsSection memo={memo} />
            </section>

            <section aria-labelledby="sec-unknowns">
              <SectionHeading id="sec-unknowns" eyebrow="Could not establish" title="What the rules could not settle" hint="Each line names a fact that is not known and the approvals that need it, grouped by what would settle it." />
              <CouldNotEstablish memo={memo} answerHref={answerHref} answerAction={answerButton} answerNote={answerNote} answerSlot={answerForm(ask)} />
            </section>

            {/* Guarded: a report written by an API build from before the site history has no such field. */}
            {memo.site_history && (
              <section aria-labelledby="sec-site-history">
                <SectionHeading id="sec-site-history" eyebrow="Records at this address or parcel" title="Site history" />
                <SiteHistorySection memo={memo} />
              </section>
            )}

            <section aria-labelledby="sec-comparables" className="space-y-5">
              <SectionHeading id="sec-comparables" eyebrow="Comparable cases" title={`${pluralize(memo.comparable_cases.length, "comparable case")} within 1,000 ft`} hint={memo.comparables_note || undefined} />
              <ComparablesMapLazy subject={{ lat: memo.lat, lng: memo.lng, address: memo.address }} cases={memo.comparable_cases} geojson={geojson ?? null} />
              <ComparablesTable cases={memo.comparable_cases} asOf={memo.data_as_of} />
              <SourceNotes notes={memo.source_notes} />
            </section>

            <section aria-labelledby="sec-zoning">
              <SectionHeading id="sec-zoning" eyebrow="Zoning & overlays" title="The rules at this parcel" />
              <ZoningPanel memo={memo} />
            </section>

            <section aria-labelledby="sec-outcomes">
              <SectionHeading id="sec-outcomes" eyebrow="Outcome counts" title="How comparable decisions nearby ended" hint="Dated Planning decisions near the address with a known outcome. Open the list to see each decision counted." />
              <OutcomeCounts memo={memo} />
            </section>

            <section aria-labelledby="sec-how-to-read">
              <SectionHeading id="sec-how-to-read" eyebrow="How to read this report" title="What the statuses mean" />
              <HowToRead memo={memo} />
            </section>

            <section aria-labelledby="sec-citations">
              <SectionHeading id="sec-citations" eyebrow="Citations" title={`${pluralize(memo.citations.length, "public record")} behind this memo`} hint="Every rule line and every fact from a record points at one of these. Open the record to read it yourself." />
              <CitationList />
            </section>

            <Disclaimers memo={memo} />
          </div>
      ) : (
        record.status === "ready" && (
          <>
            {canAnswer && (
              <section className="space-y-4 rounded-2xl border border-border bg-card p-5" data-testid="teaser-answers" aria-label={ANSWERS_FORM_TITLE}>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-sm leading-relaxed">
                    <span className="font-semibold">{ANSWERS_FORM_TITLE}.</span> The rules never guess a missing input, so each row that needs one stays undecided until you give it.
                  </p>
                  {answerButton}
                </div>
                {answerForm([])}
              </section>
            )}
            <TeaserBody record={record} me={me} actions={actions} busy={busy} />
          </>
        )
      )}

      {!legacy && revisions && revisions.length > 0 && <EarlierVersions revisions={revisions} />}

      {actions.onDelete && (
        <div className="flex justify-end border-t border-border pt-6">
          <DeleteMemo address={record.address} onDelete={actions.onDelete} />
        </div>
      )}
    </article>
    </CitationProvider>
  );
}

function UnlockCard({ record, me, actions, busy }: Pick<MemoViewProps, "record" | "me" | "actions" | "busy">) {
  const pro = isPro(me);
  const credits = me?.memo_credits ?? 0;
  const instant = pro || credits > 0;
  return (
    <section className="relative overflow-hidden rounded-2xl border border-ink bg-ink p-6 text-paper sm:p-8" data-testid="unlock-card" aria-labelledby="unlock-title">
      <div className="absolute -right-12 -top-12 size-48 rounded-full bg-signal/25 blur-3xl" aria-hidden />
      <div className="relative">
        <p className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-signal">
          <Lock className="size-3.5" aria-hidden /> Teaser
        </p>
        <h2 id="unlock-title" className="mt-1 text-xl font-semibold sm:text-2xl">
          Unlock the full memo — $499 one-time or Pro $299/mo
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-paper/75">
          The overall status above is final; the full memo adds the rules applied to {record.teaser ? `each of the ${pluralize(record.teaser.approvals_count, "approval")}` : "each approval"} the concept needs, the facts the rules read and where each came from, what is not known, the records at this address, the comparable cases on a map with their decisions and conditions, the decisions behind the outcome counts, zoning and every source link.
        </p>
        {instant ? (
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button type="button" size="lg" className="bg-signal text-white hover:bg-signal/90" onClick={actions?.onUnlock} disabled={busy?.unlock || !actions?.onUnlock} data-testid="unlock-now">
              {busy?.unlock ? <Loader2 className="animate-spin" /> : <Sparkles />}
              {pro ? "Unlock now · included in Pro" : `Unlock now · uses 1 of ${credits} memo ${credits === 1 ? "credit" : "credits"}`}
            </Button>
            {!pro && (
              <Button type="button" variant="ghost" className="text-paper/80 hover:bg-paper/10 hover:text-paper" onClick={() => actions?.onCheckout?.("pro")} disabled={Boolean(busy?.checkout)}>
                Or start Pro for unlimited memos
              </Button>
            )}
          </div>
        ) : (
          <div className="mt-6">
            <MemoOffers compact onSelect={(mode) => actions?.onCheckout?.(mode)} busy={busy?.checkout ?? null} disabled={!actions?.onCheckout} className="[&>div]:border-paper/15 [&>div]:bg-paper/5 [&>div]:text-paper [&>div_p]:text-paper/70 [&>div:last-child]:border-signal/40 [&>div:last-child]:bg-ink-2" />
          </div>
        )}
        {me && !pro && (
          <p className="mt-4 text-xs text-paper/60">
            {me.free_teasers_remaining} free {me.free_teasers_remaining === 1 ? "teaser" : "teasers"} remaining on your account. Payments are processed by Stripe.
          </p>
        )}
      </div>
    </section>
  );
}

function GhostRows({ n }: { n: number }) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="grid grid-cols-6 gap-3 border-b border-border bg-paper-deep/50 px-4 py-2.5">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-3" />
        ))}
      </div>
      {Array.from({ length: n }).map((_, r) => (
        <div key={r} className="grid grid-cols-6 gap-3 border-b border-border px-4 py-3 last:border-b-0">
          <Skeleton className="h-4 col-span-2" />
          <Skeleton className="h-4" />
          <Skeleton className="h-4 w-16 rounded-full" />
          <Skeleton className="h-4" />
          <Skeleton className="h-1.5 self-center" />
        </div>
      ))}
    </div>
  );
}

/** Teaser: the unlock card followed by a blurred, inert skeleton of the sections the full memo contains. */
function TeaserBody({ record, me, actions, busy }: Pick<MemoViewProps, "record" | "me" | "actions" | "busy">) {
  const approvals = Math.max(1, Math.min(6, record.teaser?.approvals_count ?? 3));
  const comps = Math.max(2, Math.min(8, record.teaser?.comparable_count ?? 4));
  return (
    <div className="space-y-6">
      <UnlockCard record={record} me={me} actions={actions} busy={busy} />
      <div className="relative" data-testid="teaser-preview">
        <div className="pointer-events-none select-none space-y-10 blur-[3px] saturate-50" aria-hidden>
          <section>
            <SectionHeading id="ghost-approvals" eyebrow="Approvals" title={`${pluralize(approvals, "approval")} this concept needs`} />
            <div className="space-y-4">
              {Array.from({ length: Math.min(approvals, 4) }).map((_, i) => (
                <div key={i} className="rounded-xl border border-border border-l-4 border-l-estimated bg-card p-5">
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="mt-3 h-3 w-full" />
                  <Skeleton className="mt-1.5 h-3 w-11/12" />
                  <Skeleton className="mt-1.5 h-3 w-2/3" />
                </div>
              ))}
            </div>
          </section>
          <section>
            <SectionHeading id="ghost-facts" eyebrow="Your concept" title={FACTS_HEADING} />
            <GhostRows n={4} />
          </section>
          <section>
            <SectionHeading id="ghost-comparables" eyebrow="Comparable cases" title={`${pluralize(comps, "comparable case")} within 1,000 ft`} />
            <div className="paper-grid h-72 rounded-xl border border-border bg-card" />
            <div className="mt-4">
              <GhostRows n={comps} />
            </div>
          </section>
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-background to-transparent" aria-hidden />
      </div>
    </div>
  );
}

function DeleteMemo({ address, onDelete }: { address: string; onDelete: () => Promise<void> | void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-dead" data-testid="delete-memo">
          <Trash2 /> Delete memo
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete this memo?</DialogTitle>
          <DialogDescription>The memo for “{address}” will be removed permanently. Deleting does not refund a memo credit or a free teaser.</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
            Keep it
          </Button>
          <Button
            variant="destructive"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onDelete();
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy && <Loader2 className="animate-spin" />} Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
