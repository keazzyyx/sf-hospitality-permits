"use client";

import { useState } from "react";
import { History, Loader2, RefreshCw } from "lucide-react";
import { IntakeQuestions } from "@/components/memo/intake-questions";
import { StatusPill } from "@/components/memo/status-pill";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format";
import { INTAKE_QUESTIONS, cleanIntakeAnswers, intakeAnswersFromForm, intakeFormErrors, intakeFormFromAnswers, isIntakeQuestionId } from "@/lib/intake";
import {
  ANSWERS_CANCEL,
  ANSWERS_FORM_NOTE,
  ANSWERS_FORM_TITLE,
  ANSWERS_SUBMIT,
  ANSWERS_UNCHANGED,
  ANSWER_ROUND_LIMIT,
  EARLIER_VERSIONS_HEADING,
  EARLIER_VERSIONS_HINT,
  NO_ANSWERS_GIVEN,
  answersRoundsLeftLine,
  earlierVersionLabel,
} from "@/lib/memo";
import type { IntakeAnswers, IntakeQuestionId, MemoRecord, MemoRevision } from "@/lib/api-types";

/**
 * "Answer and run again" on the memo page (owner decision of 2026-11-16): the intake questions, filled in with the
 * answers the memo has, posted to `POST /v1/memos/{id}/answers`. The same memo is run again, free; the page stays.
 * Only the questions are sent: the address and the description stay as they are (changing the description is a new
 * memo, from the Re-run link).
 */
export function AnswerRoundForm({
  record,
  asked = [],
  onAnswer,
  onCancel,
  busy = false,
  error = null,
}: {
  record: MemoRecord;
  asked?: readonly IntakeQuestionId[];
  onAnswer: (answers: IntakeAnswers) => void;
  onCancel?: () => void;
  busy?: boolean;
  error?: string | null;
}) {
  const [form, setForm] = useState(() => intakeFormFromAnswers(record.intake));
  const [problem, setProblem] = useState<string | null>(null);
  const left = record.answers_rounds_left ?? ANSWER_ROUND_LIMIT;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const errors = intakeFormErrors(form);
    if (errors.length > 0) {
      setProblem(errors.join(" "));
      return;
    }
    const answers = intakeAnswersFromForm(form);
    if (!answers || JSON.stringify(answers) === JSON.stringify(cleanIntakeAnswers(record.intake))) {
      setProblem(ANSWERS_UNCHANGED);
      return;
    }
    setProblem(null);
    onAnswer(answers);
  }

  const shown = problem ?? error;
  return (
    <form onSubmit={submit} className="rounded-2xl border border-border bg-card p-5 sm:p-6" aria-label={ANSWERS_FORM_TITLE} data-testid="answer-round-form">
      <IntakeQuestions value={form} onChange={setForm} asked={asked} heading={ANSWERS_FORM_TITLE} hint={ANSWERS_FORM_NOTE} />
      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-muted-foreground" data-testid="answer-rounds-left">
          {answersRoundsLeftLine(left)}
        </p>
        <div className="flex flex-wrap gap-2">
          {onCancel && (
            <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
              {ANSWERS_CANCEL}
            </Button>
          )}
          <Button type="submit" disabled={busy} data-testid="answer-round-submit">
            {busy ? <Loader2 className="animate-spin" /> : <RefreshCw />} {ANSWERS_SUBMIT}
          </Button>
        </div>
      </div>
      {shown && (
        <p role="alert" className="mt-4 rounded-lg border border-dead/30 bg-dead-soft p-3 text-sm text-dead" data-testid="answer-round-error">
          {shown}
        </p>
      )}
    </form>
  );
}

/** One answer as the form showed it (the API's question ids; a skipped question is not listed). */
function answerText(id: IntakeQuestionId, value: unknown): string {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return value.toLocaleString("en-US");
  const options = (INTAKE_QUESTIONS[id] as { answers?: readonly { value: string; label: string }[] }).answers ?? [];
  const label = (v: unknown) => options.find((o) => o.value === v)?.label ?? String(v);
  return Array.isArray(value) ? value.map(label).join(", ") : label(value);
}

function AnswersGiven({ intake }: { intake: IntakeAnswers | null }) {
  const given = Object.entries(intake ?? {}).filter(([id, v]) => isIntakeQuestionId(id) && v !== null && v !== undefined) as [IntakeQuestionId, unknown][];
  if (given.length === 0) return <p className="text-xs text-muted-foreground">{NO_ANSWERS_GIVEN}</p>;
  return (
    <ul className="space-y-0.5 text-xs text-muted-foreground">
      {given.map(([id, v]) => (
        <li key={id}>
          {INTAKE_QUESTIONS[id].question} <span className="font-medium text-foreground">{answerText(id, v)}</span>
        </li>
      ))}
    </ul>
  );
}

/** The versions answer rounds replaced, oldest first (`GET /v1/memos/{id}/revisions`). */
export function EarlierVersions({ revisions }: { revisions: MemoRevision[] }) {
  if (revisions.length === 0) return null;
  return (
    <section className="rounded-2xl border border-border bg-card p-5" data-testid="earlier-versions" aria-labelledby="earlier-versions-title">
      <p id="earlier-versions-title" className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        <History className="size-3.5" aria-hidden /> {EARLIER_VERSIONS_HEADING}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">{EARLIER_VERSIONS_HINT}</p>
      <ol className="mt-3 space-y-4">
        {revisions.map((rev) => (
          <li key={rev.round} className="border-t border-border pt-3 first:border-t-0 first:pt-0" data-testid="earlier-version" data-round={rev.round}>
            <p className="text-sm font-medium">
              {earlierVersionLabel(rev.round)}
              <span className="ml-2 text-xs font-normal text-muted-foreground">{formatDate(rev.generated_at ?? rev.replaced_at)}</span>
            </p>
            {rev.teaser && (
              <div className="mt-1.5 flex flex-col gap-2 sm:flex-row sm:items-start">
                <StatusPill status={rev.teaser.overall_status} size="sm" />
                <p className="text-sm leading-relaxed">{rev.teaser.overall_line}</p>
              </div>
            )}
            <div className="mt-1.5">
              <AnswersGiven intake={rev.intake} />
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
