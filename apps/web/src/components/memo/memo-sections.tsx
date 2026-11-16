"use client";

import Link from "next/link";
import { ExternalLink, History, Info, Landmark, Quote } from "lucide-react";
import { cn } from "cn";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Cite } from "@/components/memo/citations";
import { OutcomeBadge, RecordedFacts } from "@/components/memo/comparables-table";
import { RecordKindBadge, StatusPill } from "@/components/memo/status-pill";
import { formatDate } from "@/lib/format";
import { INTAKE_QUESTIONS, isIntakeQuestionId } from "@/lib/intake";
import {
  COUNTED_HEADING,
  FACTS_READ_HEADING,
  HEADLINE_CONTINGENT,
  HEADLINE_DEFINITE,
  HEADLINE_HEADING,
  HEADLINE_HINT,
  MISSING_INPUTS_HEADING,
  NO_DISTRICT,
  PATHWAY_HINT,
  REFERRAL_STEPS_HEADING,
  REFERRAL_STEPS_NOTE,
  STATUS_DISPLAY_ORDER,
  STATUS_LABELS,
  USE_PERMISSION_CLASSES,
  answerableQuestions,
  baseRateScopeText,
  definitionBody,
  existingUseLabel,
  factValueText,
  formatPct,
  groupOpenQuestions,
  groupRuleLines,
  isApprovalStatus,
  matchedByText,
  outcomeBucket,
  outcomeLabel,
  rowRuleGroups,
  sentenceCase,
  showsApprovalRate,
  siteHistoryCountLine,
  siteHistoryDate,
  siteHistoryKindCounts,
  siteHistoryShownLine,
  splitFacts,
  type RuleItem,
} from "@/lib/memo";
import type { HeadlineFinding, Memo, MemoApprovalRow, MemoFact, RuleLine, SiteHistoryEntry, SourceNote } from "@/lib/api-types";

export function SectionHeading({ id, eyebrow, title, hint }: { id: string; eyebrow: string; title: string; hint?: string }) {
  return (
    <div className="mb-4">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-signal">{eyebrow}</p>
      <h2 id={id} className="mt-1 text-xl font-semibold sm:text-2xl">
        {title}
      </h2>
      {hint && <p className="mt-1 text-sm text-muted-foreground">{hint}</p>}
    </div>
  );
}

/**
 * One fact the rules read: its name, its value (or "Not known") and where it came from. Where the applicant's
 * words state it, they are quoted as sent; where a record shows it, the record is cited. Nothing here is written by
 * a model: the API builds each fact in code (apps/api/app/memo/evidence.py).
 */
export function FactItem({ fact: f, testId = "fact" }: { fact: MemoFact; testId?: string }) {
  const known = f.value !== null;
  return (
    <li className="grid gap-0.5 py-1.5 sm:grid-cols-[minmax(0,13rem)_minmax(0,1fr)] sm:gap-4" data-testid={testId} data-fact={f.fact} data-origin={f.origin}>
      <span className="text-xs text-muted-foreground sm:pt-0.5">{f.label}</span>
      <span className="min-w-0">
        <span className={cn("text-sm font-medium leading-snug", !known && "text-muted-foreground")} data-testid="fact-value">
          {factValueText(f)}
        </span>
        <Cite ids={f.citations ?? []} />
        {known && (
          <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground" data-testid="fact-origin">
            {f.origin_label}
            {f.quotes.length > 0 && (
              <>
                {": "}
                {f.quotes.map((q, i) => (
                  <span key={i}>
                    {i > 0 ? "; " : ""}
                    <q className="text-foreground/80" data-testid="fact-quote">
                      {q}
                    </q>
                  </span>
                ))}
              </>
            )}
          </span>
        )}
      </span>
    </li>
  );
}

/**
 * One rule line as the API sends it: the sentence, its [n] citations, then the code section the rule rests on
 * (a link when the API gives one). When the sentence already names the section in the same words, the section
 * is not printed again; the words in the sentence carry the link instead (the PDF applies the same rule in
 * rule_line_markup, apps/api/app/services/memo_pdf.py). No model writes these lines.
 */
function RuleLineItem({ line: l, testId = "rule-line" }: { line: RuleLine; testId?: string }) {
  const section = l.code_section;
  const at = section ? l.text.indexOf(section) : -1;
  const ref = !section ? null : l.source_url ? (
    // Inline, not inline-flex: a long section (two sources joined by ";") wraps with the sentence it sits in.
    <a href={l.source_url} target="_blank" rel="noreferrer noopener" className="text-signal hover:underline">
      {section}
      <ExternalLink className="ml-1 inline size-3 align-baseline" aria-hidden />
    </a>
  ) : (
    section
  );
  return (
    <li className="text-sm leading-relaxed" data-testid={testId} data-rule={l.rule_id}>
      {section && at >= 0 ? (
        <>
          {l.text.slice(0, at)}
          <span data-testid="rule-section">{ref}</span>
          {l.text.slice(at + section.length)}
        </>
      ) : (
        l.text
      )}
      <Cite ids={l.citations ?? []} />
      {section && at < 0 && (
        <span className="ml-1.5 font-mono text-[11px] text-muted-foreground" data-testid="rule-section">
          {ref}
        </span>
      )}
    </li>
  );
}

/**
 * The headline findings, first on the page (app.memo.pathway rule 9): what changes the business's plans at this
 * address, set by rule. Each shows its status, whether it depends on an answer not given, its sentence and the
 * trigger line it rests on. Nothing is shown when there is none (nor on memos stored before 2026-11-16).
 */
export function HeadlineFindings({ findings }: { findings: HeadlineFinding[] | undefined }) {
  if (!findings || findings.length === 0) return null;
  return (
    <section aria-labelledby="headline-findings" className="rounded-2xl border-2 border-signal/40 bg-card p-5" data-testid="headline-findings">
      <h2 id="headline-findings" className="text-[11px] font-semibold uppercase tracking-wider text-signal">
        {HEADLINE_HEADING}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">{HEADLINE_HINT}</p>
      <ul className="mt-3 space-y-4">
        {findings.map((h, i) => (
          <li key={`${i}-${h.kind}-${h.trigger}`} data-testid="headline-finding" data-kind={h.kind} data-definite={h.definite ? "true" : "false"} data-area={h.area}>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill status={h.status} size="sm" />
              <span className="text-xs font-medium text-muted-foreground" data-testid="headline-how">
                {h.definite ? HEADLINE_DEFINITE : HEADLINE_CONTINGENT}
              </span>
            </div>
            <p className="mt-1.5 text-base font-medium leading-relaxed text-foreground" data-testid="headline-sentence">
              {h.sentence}
              <Cite ids={h.citations} />
            </p>
            {h.basis.length > 0 && <RuleLines lines={h.basis} className="mt-1.5 text-sm text-muted-foreground" testId="headline-rule-line" />}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** A list of rule lines. `testId` names each line; a referral step is a rule line that is not part of the basis. */
export function RuleLines({ lines, className, testId }: { lines: RuleLine[]; className?: string; testId?: string }) {
  return (
    <ul className={cn("space-y-1.5", className)}>
      {lines.map((l, i) => (
        <RuleLineItem key={`${l.rule_id}-${i}`} line={l} testId={testId} />
      ))}
    </ul>
  );
}

/**
 * A row's rule lines with the lines of each trigger (zoning row) or change-of-use answer (building row) set
 * under its name and its answer (`groupRuleLines` in src/lib/memo.ts). The order is the API's.
 */
function GroupedRuleLines({ items, className }: { items: RuleItem[]; className?: string }) {
  return (
    <ul className={cn("space-y-1.5", className)}>
      {items.map((item, i) =>
        item.group ? (
          <li key={`${item.group.testId}-${item.group.key}`} className="py-0.5" data-testid={item.group.testId} data-key={item.group.key} data-value={item.group.value}>
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-medium leading-snug">
              <span data-testid={`${item.group.testId}-label`}>{item.group.label}</span>
              <span className="sr-only">: </span>
              <span className={cn("inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold leading-4", item.group.valueClass)} data-testid={`${item.group.testId}-value`}>
                {item.group.valueLabel}
              </span>
            </p>
            {item.group.lines.length > 0 && <RuleLines lines={item.group.lines} className="mt-1 border-l border-border pl-3" />}
          </li>
        ) : (
          <RuleLineItem key={`${item.line.rule_id}-${i}`} line={item.line} />
        ),
      )}
    </ul>
  );
}

const ROW_BORDER: Record<MemoApprovalRow["status"], string> = {
  allowed: "border-l-verified",
  further_review: "border-l-estimated",
  potential_blocker: "border-l-signal",
  not_permitted: "border-l-dead",
  insufficient_information: "border-l-ink/30",
};

/**
 * One block per approval the concept needs. The approval, the agency, the status and its note are set by rules in
 * the API. "Not given" names the inputs a row that is Insufficient information lacks. "Rules applied" lists the
 * rule lines that set the status: under the zoning row each trigger that applies is named with its control, and
 * under the building row the three change-of-use answers are named, each on its own line. "Facts the rules read"
 * lists what the rules read, each with where it came from. Last come the referral steps inside the approval, which
 * are not approvals. No model wrote any of it.
 */
export function ApprovalRows({ memo }: { memo: Memo }) {
  return (
    <ol className="space-y-4" data-testid="approvals">
      {memo.approvals.map((row) => (
        <li key={row.area} className={cn("rounded-xl border border-l-4 border-border bg-card p-5", ROW_BORDER[row.status] ?? "border-l-ink/30")} data-testid="approval-row" data-area={row.area} data-status={row.status}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground" data-testid="approval-area">
                {row.area_label}
              </p>
              <h3 className="mt-0.5 font-semibold leading-snug" data-testid="approval-name">
                {row.approval}
              </h3>
              <p className="mt-0.5 text-xs text-muted-foreground" data-testid="approval-agency">
                {row.agency}
              </p>
            </div>
            <div className="flex flex-col items-start gap-1 sm:items-end">
              <StatusPill status={row.status} />
              {/* The fixed qualifier the rules print after the status. Read aloud: "Further review: Code and Planning practice differ". */}
              {row.status_note?.trim() && (
                <p className="max-w-xs text-xs font-medium leading-snug text-foreground/80 sm:text-right" data-testid="status-note">
                  <span className="sr-only">{STATUS_LABELS[row.status] ?? row.status}: </span>
                  {row.status_note.trim()}
                </p>
              )}
            </div>
          </div>
          {row.missing_inputs && row.missing_inputs.length > 0 && (
            <div className="mt-3 rounded-lg border border-dashed border-border px-3 py-2.5" data-testid="missing-inputs">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{MISSING_INPUTS_HEADING}</p>
              <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm leading-relaxed">
                {row.missing_inputs.map((input) => (
                  <li key={input} className="first-letter:uppercase" data-testid="missing-input">
                    {input}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {/* Guarded: a report written by an API build from before the rule table has no rule lines. */}
          {row.basis && row.basis.length > 0 && (
            <div className="mt-3 rounded-lg border border-border bg-paper-deep/40 px-3 py-2.5" data-testid="rules-applied">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Rules applied</p>
              <GroupedRuleLines items={groupRuleLines(row.basis, rowRuleGroups(row.area, memo.pathway))} className="mt-1.5" />
            </div>
          )}
          {row.facts && row.facts.length > 0 && (
            <div className="mt-3 rounded-lg border border-border px-3 py-2" data-testid="row-facts">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{FACTS_READ_HEADING}</p>
              <ul className="mt-1 divide-y divide-border/70">
                {row.facts.map((f) => (
                  <FactItem key={f.fact} fact={f} testId="row-fact" />
                ))}
              </ul>
            </div>
          )}
          {row.referral_steps && row.referral_steps.length > 0 && (
            <div className="mt-4 border-t border-border pt-4" data-testid="referral-steps">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{REFERRAL_STEPS_HEADING}</p>
              <p className="mt-1 text-xs text-muted-foreground" data-testid="referral-steps-note">
                {REFERRAL_STEPS_NOTE}
              </p>
              <RuleLines lines={row.referral_steps} className="mt-2" testId="referral-step" />
            </div>
          )}
          {row.history_note && (
            <p className="mt-4 inline-flex items-start gap-1.5 rounded-lg border border-dashed border-border px-3 py-2 text-xs text-muted-foreground" data-testid="history-note">
              <History className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {row.history_note}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}

/**
 * Every fact the rules read about the business: the known ones with where each came from, then the ones nothing
 * gave, shown as "Not known". The rules never fill a fact that is not known with a guess.
 */
export function FactsSection({ memo }: { memo: Memo }) {
  const { known, unknown } = splitFacts(memo.facts);
  return (
    <div className="space-y-4" data-testid="facts">
      {memo.description && (
        <blockquote className="rounded-xl border border-border bg-paper-deep/40 px-4 py-3 text-sm leading-relaxed" data-testid="facts-description">
          <p className="mb-1 inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            <Quote className="size-3.5" aria-hidden /> Your description
          </p>
          <p className="text-foreground/90">{memo.description}</p>
        </blockquote>
      )}
      <div className="rounded-xl border border-border bg-card px-4 py-2">
        {known.length === 0 ? (
          <p className="py-2 text-sm text-muted-foreground">No fact the rules read was given.</p>
        ) : (
          <ul className="divide-y divide-border/70" data-testid="facts-known">
            {known.map((f) => (
              <FactItem key={f.fact} fact={f} />
            ))}
          </ul>
        )}
      </div>
      {unknown.length > 0 && (
        <div className="rounded-xl border border-dashed border-border px-4 py-2" data-testid="facts-unknown">
          <ul className="divide-y divide-border/70">
            {unknown.map((f) => (
              <FactItem key={f.fact} fact={f} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/**
 * What the records cannot establish, grouped by what would settle it, then the API's one fixed line on what
 * public records cannot show (`records_limits`; absent on a report made before rule table v2).
 */
export function CouldNotEstablish({
  memo,
  answerHref = null,
  answerAction = null,
  answerNote = null,
  answerSlot = null,
}: {
  memo: Memo;
  /** The old flow: the new-memo form with the same input, which makes a new memo. */
  answerHref?: string | null;
  /** In place of that link: the button that opens the answer round's form on this memo. */
  answerAction?: React.ReactNode;
  /** A line under the box (why answering makes a new memo here). */
  answerNote?: string | null;
  /** Under the box: the answer round's form, when it is open. */
  answerSlot?: React.ReactNode;
}) {
  const groups = groupOpenQuestions(memo.could_not_establish);
  const answerable = answerableQuestions(memo.could_not_establish);
  return (
    <div className="space-y-4" data-testid="could-not-establish">
      {(answerHref || answerAction) && answerable.length > 0 && (
        <div className="rounded-xl border border-estimated/40 bg-estimated-soft px-5 py-4" data-testid="answer-questions">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm leading-relaxed">
              <span className="font-semibold">
                {answerable.length === 1 ? "One of these is a question you can answer." : `${answerable.length} of these are questions you can answer.`}
              </span>{" "}
              The rules never guess a missing input, so each row that needs one stays undecided until you give it.
            </p>
            {answerAction ?? (
              <Button asChild variant="outline" className="shrink-0">
                <Link href={answerHref ?? "/app/memo"} data-testid="answer-questions-link">
                  Answer and run again
                </Link>
              </Button>
            )}
          </div>
          {answerNote && (
            <p className="mt-2 text-xs text-muted-foreground" data-testid="answer-questions-note">
              {answerNote}
            </p>
          )}
        </div>
      )}
      {answerSlot}
      {groups.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border p-5 text-sm text-muted-foreground">The rules found nothing they could not establish from what was given.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {groups.map((g) => (
            <div key={g.needs} className="rounded-xl border border-border bg-card p-5" data-testid="open-question-group" data-needs={g.needs}>
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{g.label}</h3>
              <ul className="mt-2 space-y-3">
                {g.questions.map((q, i) => (
                  <li key={i} className="text-sm" data-testid="open-question">
                    <p className="leading-relaxed">{q.question}</p>
                    {q.ask && (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        <span className="font-semibold">Settled by · </span>
                        {q.ask}
                      </p>
                    )}
                    {isIntakeQuestionId(q.intake_question) && (
                      <p className="mt-0.5 text-xs text-muted-foreground" data-testid="open-question-intake" data-question={q.intake_question}>
                        <span className="font-semibold">You can answer it · </span>
                        {INTAKE_QUESTIONS[q.intake_question].question}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      {memo.records_limits && (
        <p className="rounded-xl border border-dashed border-border px-5 py-3 text-sm leading-relaxed text-muted-foreground" data-testid="records-limits">
          {memo.records_limits}
        </p>
      )}
    </div>
  );
}

/**
 * Outcome of one site record: the badge, plus the source's own status when it says more than the outcome does.
 * With no known outcome and no status the cell reads "not stated", the word the PDF uses (site_entry_outcome in
 * apps/api/app/memo/report.py).
 */
function SiteOutcome({ entry }: { entry: SiteHistoryEntry }) {
  const status = entry.status.trim();
  if (!entry.outcome || entry.outcome === "unknown") {
    return <span className="text-xs text-muted-foreground">{status || "not stated"}</span>;
  }
  return (
    <>
      <OutcomeBadge outcome={entry.outcome} />
      {status && outcomeBucket(status) !== outcomeBucket(entry.outcome) && <div className="mt-1 text-[11px] text-muted-foreground">{status}</div>}
    </>
  );
}

/**
 * Site history: every record on file at the report's own address or parcel, newest first, building work
 * included. The API builds the list (no model writes it) and sends at most 20 rows with the full count.
 * The page makes no claim of its own about what counts: a use decision at the site can also be a comparable
 * and sit in the outcome counts, so the only sentence on that is the API's `note`.
 */
export function SiteHistorySection({ memo }: { memo: Memo }) {
  const h = memo.site_history;
  const kinds = siteHistoryKindCounts(h.by_kind);
  const shown = siteHistoryShownLine(h);
  const matchedBy = matchedByText(h.matched_by);
  return (
    <div className="space-y-4" data-testid="site-history" data-total={h.total}>
      <div className="rounded-xl border border-border bg-card p-5">
        <p className="font-display text-xl font-semibold tabular" data-testid="site-history-count">
          {siteHistoryCountLine(h.total)}
        </p>
        {h.note && (
          <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-foreground/90" data-testid="site-history-note">
            {h.note}
          </p>
        )}
        {matchedBy && (
          <p className="mt-1.5 text-xs text-muted-foreground" data-testid="site-history-matched-by">
            Matched by: {matchedBy}.
          </p>
        )}
        {kinds.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-border pt-3 text-xs text-muted-foreground" data-testid="site-history-kinds">
            {kinds.map((k) => (
              <li key={k.kind} className="inline-flex items-center gap-1.5" data-kind={k.kind}>
                <RecordKindBadge kind={k.kind} label={k.label} testId="site-history-kind-count" />
                <span className="font-mono tabular">{k.n.toLocaleString("en-US")}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {h.entries.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <table className="w-full min-w-[780px] border-collapse text-sm" data-testid="site-history-table">
            <thead>
              <tr className="border-b border-border bg-paper-deep/50 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                <th scope="col" className="px-3 py-2.5">Date</th>
                <th scope="col" className="px-3 py-2.5">Kind</th>
                <th scope="col" className="px-3 py-2.5">What</th>
                <th scope="col" className="px-3 py-2.5">Outcome</th>
                <th scope="col" className="px-3 py-2.5">Source</th>
              </tr>
            </thead>
            <tbody>
              {h.entries.map((e) => {
                const when = siteHistoryDate(e);
                return (
                  <tr key={e.application_id} className="border-b border-border align-top last:border-b-0 odd:bg-transparent even:bg-paper-deep/20" data-testid="site-history-row" data-kind={e.record_kind}>
                    <td className="whitespace-nowrap px-3 py-3 font-mono text-xs tabular" data-testid="site-history-date">
                      {when ? (
                        <>
                          <div>{formatDate(when.date)}</div>
                          <div className="text-muted-foreground">{when.which}</div>
                        </>
                      ) : (
                        <span className="text-muted-foreground">undated</span>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <RecordKindBadge kind={e.record_kind} label={e.record_kind_label} />
                    </td>
                    <td className="min-w-64 px-3 py-3">
                      <div className="font-medium leading-snug">{e.permit_type}</div>
                      {e.address && <p className="text-xs text-muted-foreground">{e.address}</p>}
                      {e.description && <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{e.description}</p>}
                      <RecordedFacts useTypes={e.use_types} hoursClose={e.hours_close} conditions={e.conditions} />
                    </td>
                    <td className="px-3 py-3" data-testid="site-history-outcome">
                      <SiteOutcome entry={e} />
                    </td>
                    <td className="px-3 py-3 text-xs">
                      <div className="whitespace-nowrap">
                        {e.source_url ? (
                          <a href={e.source_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 font-mono text-[11px] text-signal hover:underline" data-testid="site-history-link">
                            {e.application_id} <ExternalLink className="size-3" aria-hidden />
                          </a>
                        ) : (
                          <span className="font-mono text-[11px]">{e.application_id}</span>
                        )}
                        <Cite ids={[e.citation_id]} />
                      </div>
                      <div className="mt-0.5 text-muted-foreground">{e.source_label || e.source}</div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {shown && (
        <p className="text-xs text-muted-foreground" data-testid="site-history-shown">
          {shown}
        </p>
      )}
    </div>
  );
}

/** A district control as the API sends it: "principal" / "conditional" / "prohibited" / "unknown", or the table's own letters. */
function PermissionChip({ label, value }: { label: string; value: string }) {
  const v = value.trim().toUpperCase();
  const permitted = v === "P" || v.startsWith("PERMIT") || v.startsWith("PRINCIPAL");
  const conditional = v === "C" || v.startsWith("COND");
  const prohibited = v === "NP" || v.startsWith("NOT") || v.startsWith("PROHIB");
  const cls = permitted
    ? "border-verified/40 bg-verified-soft text-verified"
    : conditional
      ? "border-estimated/50 bg-estimated-soft text-estimated"
      : prohibited
        ? "border-dead/40 bg-dead-soft text-dead"
        : "border-border bg-muted text-foreground";
  const text = permitted ? "Permitted" : conditional ? "Conditional use" : prohibited ? "Not permitted" : v === "UNKNOWN" ? "Not on file" : value;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold", cls)}>
      <span className="font-normal text-current/80">{label}</span> {text}
    </span>
  );
}

// Same words as NOTE_PREFIX in apps/api/app/memo/pathway.py; the heading above the notes already says them.
const NOTE_PREFIX = "Note on file, not evaluated by the rules:";

/**
 * The pathway the API looked up by rule for this concept at this address: the use, the district, the control on
 * a new use of that kind, the use the records show now and whether going from one to the other is a change of
 * use. The approval rows above take their statuses from the same answer. Notes are lines on file for the
 * district and its special use districts that the rules do not evaluate.
 */
function PathwayFacts({ memo }: { memo: Memo }) {
  const p = memo.pathway;
  const facts: { key: string; label: string; value: React.ReactNode }[] = [
    { key: "use", label: "Proposed use", value: sentenceCase(p.use_label) },
    { key: "district", label: "Zoning district", value: p.district ?? NO_DISTRICT },
    {
      key: "permission",
      label: "Control on a new use",
      value: <span className={cn("inline-flex rounded-full border px-2.5 py-0.5 text-xs font-semibold", USE_PERMISSION_CLASSES[p.permission] ?? "border-border bg-muted text-foreground")}>{p.permission_label}</span>,
    },
    { key: "existing_use", label: "Existing use", value: existingUseLabel(p.existing_use) },
    { key: "change_of_use", label: "Change of use", value: sentenceCase(p.change_of_use_label) },
  ];
  return (
    <div className="rounded-xl border border-border bg-card p-5 lg:col-span-2" data-testid="pathway" data-permission={p.permission} data-change-of-use={p.change_of_use}>
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Pathway for this concept</p>
      <p className="mt-1 text-xs text-muted-foreground">{PATHWAY_HINT}</p>
      <dl className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-5">
        {facts.map((f) => (
          <div key={f.key} data-testid="pathway-fact" data-fact={f.key}>
            <dt className="text-xs text-muted-foreground">{f.label}</dt>
            <dd className="mt-0.5 text-sm font-medium leading-snug">{f.value}</dd>
          </div>
        ))}
      </dl>
      {p.notes && p.notes.length > 0 && (
        <div className="mt-4 border-t border-border pt-3" data-testid="pathway-notes">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Notes on file, not evaluated by the rules</p>
          <RuleLines lines={p.notes.map((n) => (n.text.startsWith(NOTE_PREFIX) ? { ...n, text: n.text.slice(NOTE_PREFIX.length).trimStart() } : n))} className="mt-1.5" />
        </div>
      )}
    </div>
  );
}

export function ZoningPanel({ memo }: { memo: Memo }) {
  const z = memo.zoning;
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]" data-testid="zoning-panel">
      {/* Guarded: a report written by an API build from before the rule table has no pathway. */}
      {memo.pathway && <PathwayFacts memo={memo} />}
      <div className="rounded-xl border border-border bg-card p-5">
        <p className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          <Landmark className="size-3.5" aria-hidden /> Zoning district
        </p>
        {z ? (
          <>
            <p className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="font-display text-2xl font-semibold">{z.district}</span>
              <span className="text-sm text-muted-foreground">{z.name}</span>
              <Cite ids={[z.citation_id]} />
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <PermissionChip label="Bar" value={z.bar_permission} />
              <PermissionChip label="Restaurant" value={z.restaurant_permission} />
            </div>
            <p className="mt-3 text-sm leading-relaxed text-foreground/90">{z.rules}</p>
            <p className="mt-2 text-xs text-muted-foreground">
              {/^planning code/i.test(z.code_section.trim()) ? z.code_section : `Planning Code ${z.code_section}`}
              {memo.parcel ? ` · Parcel ${memo.parcel}` : ""}
            </p>
          </>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">No zoning district was returned for this parcel. Confirm with the Planning Information Map before relying on this report.</p>
        )}
      </div>
      <div className="rounded-xl border border-border bg-card p-5">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Overlays at this address</p>
        {memo.overlays.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">No special use districts or overlays apply.</p>
        ) : (
          <ul className="mt-2 space-y-3">
            {memo.overlays.map((o) => (
              <li key={`${o.name}-${o.code_section}`} className="text-sm">
                <p className="font-medium leading-snug">
                  {o.name}
                  <Cite ids={[o.citation_id]} />
                </p>
                <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="outline" className="text-[10px] uppercase">
                    {o.kind.replace(/_/g, " ")}
                  </Badge>
                  <span>{o.code_section}</span>
                </p>
                <p className="mt-1 text-xs leading-relaxed text-foreground/85">{o.effect}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/**
 * The outcome counts: dated Planning decisions near the address with a known outcome, counted in code (N is always
 * shown; a rate only when N is 10 or more). Each decision counted is listed with a link to its record, and what was
 * left out is counted on its own line.
 */
export function OutcomeCounts({ memo }: { memo: Memo }) {
  const b = memo.base_rate;
  const decided = b.approved + b.approved_with_conditions + b.denied + b.withdrawn;
  const rate = showsApprovalRate(b) ? b.approval_rate_pct : null;
  // Same order as the API's own list: grant-only, not use decisions, undated.
  const excluded = [
    b.excluded_grant_only > 0 ? `${b.excluded_grant_only} grant-only ${b.excluded_grant_only === 1 ? "record" : "records"} (Entertainment Commission permits, ABC licences)` : null,
    // Labelled records near the address that are not a use decision about a food, drink or entertainment premises.
    b.excluded_not_use_decision > 0 ? `${b.excluded_not_use_decision === 1 ? "1 not a use decision" : `${b.excluded_not_use_decision} not use decisions`} (referrals, building work and other records)` : null,
    b.excluded_undated > 0 ? `${b.excluded_undated} undated ${b.excluded_undated === 1 ? "record" : "records"}` : null,
  ].filter((x): x is string => x !== null);
  const segments = [
    { key: "approved", n: b.approved, cls: "bg-verified", label: "Approved" },
    { key: "conditions", n: b.approved_with_conditions, cls: "bg-estimated", label: "With conditions" },
    { key: "denied", n: b.denied, cls: "bg-dead", label: "Denied" },
    { key: "withdrawn", n: b.withdrawn, cls: "bg-muted-foreground/50", label: "Withdrawn or cancelled" },
  ];
  const counted = b.counted ?? [];
  return (
    <div className="space-y-4" data-testid="outcome-counts">
      <div className="rounded-xl border border-border bg-card p-4" data-testid="base-rate" data-rate-shown={rate !== null ? "true" : "false"}>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-sm font-medium" data-testid="base-rate-scope">
            Outcome counts · {baseRateScopeText(b.scope)}
            <Cite ids={[b.citation_id]} />
          </p>
          <p className="font-mono text-xs text-muted-foreground tabular" data-testid="base-rate-n">
            {rate !== null ? `${formatPct(rate)} approved · ` : ""}N = {b.total}
          </p>
        </div>
        <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-muted" role="img" aria-label={segments.map((s) => `${s.label} ${s.n}`).join(", ")}>
          {segments.map((s) => (
            <div key={s.key} className={s.cls} style={{ width: `${decided > 0 ? (s.n / decided) * 100 : 0}%` }} />
          ))}
        </div>
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {segments.map((s) => (
            <li key={s.key} className="inline-flex items-center gap-1.5">
              <span className={cn("size-2.5 rounded-full", s.cls)} aria-hidden /> {s.label} <span className="font-mono tabular">{s.n}</span>
            </li>
          ))}
        </ul>
        {excluded.length > 0 && (
          <p className="mt-2 text-xs text-muted-foreground" data-testid="base-rate-excluded">
            Not counted: {excluded.join("; ")}.
          </p>
        )}
        {counted.length > 0 && (
          <details className="mt-3 border-t border-border pt-3" data-testid="counted-decisions">
            <summary className="cursor-pointer select-none text-sm font-medium text-signal hover:underline">
              {COUNTED_HEADING} ({counted.length})
            </summary>
            <ul className="mt-2 divide-y divide-border/70 text-sm">
              {counted.map((d) => (
                <li key={d.application_id} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2" data-testid="counted-decision">
                  <span className="min-w-0">
                    <span className="font-medium">{d.address ?? "Address not recorded"}</span>
                    <span className="block text-xs text-muted-foreground">
                      {d.permit_type} · {d.decided_at ? `decided ${formatDate(d.decided_at)}` : "undated"} · {outcomeLabel(d.outcome)}
                    </span>
                  </span>
                  {d.source_url ? (
                    <a href={d.source_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 font-mono text-[11px] text-signal hover:underline">
                      {d.application_id} <ExternalLink className="size-3" aria-hidden />
                    </a>
                  ) : (
                    <span className="font-mono text-[11px]">{d.application_id}</span>
                  )}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}

/** "What each source leaves out", listed under the comparables table. */
export function SourceNotes({ notes }: { notes: SourceNote[] }) {
  if (notes.length === 0) return null;
  return (
    <div className="rounded-xl border border-border bg-card p-4" data-testid="source-notes">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">What each source leaves out</p>
      <dl className="mt-2 space-y-2 text-sm">
        {notes.map((n) => (
          <div key={n.source} className="grid gap-0.5 sm:grid-cols-[14rem_minmax(0,1fr)] sm:gap-4" data-testid="source-note" data-source={n.source}>
            <dt className="font-medium">{n.label}</dt>
            <dd className="leading-relaxed text-muted-foreground">{n.leaves_out}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** The status definitions, taken from the memo itself. */
export function HowToRead({ memo }: { memo: Memo }) {
  const statusKeys = [...STATUS_DISPLAY_ORDER.filter((k) => k in memo.status_definitions), ...Object.keys(memo.status_definitions).filter((k) => !isApprovalStatus(k))];
  return (
    <div className="rounded-xl border border-border bg-card p-5" data-testid="how-to-read">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Status of each approval</h3>
      <dl className="mt-3 grid gap-3 lg:grid-cols-2">
        {statusKeys.map((k) => (
          <div key={k} data-testid="status-definition" data-status={k}>
            <dt>{isApprovalStatus(k) ? <StatusPill status={k} size="sm" /> : <span className="text-sm font-semibold">{k}</span>}</dt>
            <dd className="mt-1 text-sm leading-relaxed text-foreground/85">{definitionBody(isApprovalStatus(k) ? STATUS_LABELS[k] : k, memo.status_definitions[k])}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function Disclaimers({ memo }: { memo: Memo }) {
  return (
    <aside className="rounded-xl border border-border bg-paper-deep/50 p-4 text-xs text-muted-foreground" data-testid="disclaimers">
      <p className="mb-1.5 inline-flex items-center gap-1.5 font-semibold uppercase tracking-wide">
        <Info className="size-3.5" aria-hidden /> Please read
      </p>
      <ul className="list-disc space-y-1 pl-5">
        {memo.disclaimers.map((d, i) => (
          <li key={i}>{d}</li>
        ))}
      </ul>
      <p className="mt-2 font-mono text-[10px]">
        Generated {new Date(memo.generated_at).toLocaleString("en-US")} · records as of {formatDate(memo.data_as_of)} ·{" "}
        {Object.entries(memo.model_versions)
          .map(([k, v]) => `${k} ${v}`)
          .join(" · ")}
      </p>
    </aside>
  );
}
