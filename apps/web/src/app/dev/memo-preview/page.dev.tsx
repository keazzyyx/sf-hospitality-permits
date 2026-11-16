"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { MemoView } from "@/components/memo/memo-view";
import { MemoCard } from "@/components/memo/memos-list";
import { useAnswerRound } from "@/hooks/use-answer-round";
import type { Me, MemoRecord } from "@/lib/api-types";
import {
  MEMO_RECORD_FULL_ANSWERABLE,
  MEMO_RECORD_FULL_NOT_ANSWERABLE,
  MEMO_RECORD_TEASER_ANSWERABLE,
  ME_FIXTURE_CREDIT,
  ME_FIXTURE_FREE,
  ME_FIXTURE_PRO,
  MEMO_GEOJSON_FIXTURE,
  MEMO_RECORD_FULL,
  MEMO_RECORD_FULL_BEFORE_V2,
  MEMO_RECORD_FULL_HISTORY_EMPTY,
  MEMO_RECORD_FULL_HISTORY_LONG,
  MEMO_RECORD_FULL_HISTORY_ONE,
  MEMO_RECORD_FULL_NOT_PERMITTED,
  MEMO_RECORD_FULL_RATE,
  MEMO_RECORD_FULL_RULES_DATE,
  MEMO_RECORD_FULL_UNLABELLED,
  MEMO_RECORD_FAILED,
  MEMO_RECORD_FAILED_FREE_RERUN,
  MEMO_RECORD_LEGACY,
  MEMO_RECORD_LEGACY_LOCKED,
  MEMO_RECORD_LEGACY_RERUN_USED,
  MEMO_RECORD_TEASER,
  MEMO_RECORD_TEASER_WITH_MEMO,
  MEMO_SUMMARIES_FIXTURE,
} from "@/lib/fixtures/memo-fixture";

/**
 * Development-only preview of the memo page against the fixture. The `.dev.tsx` page extension is
 * registered in next.config.ts only when NODE_ENV !== "production", so this route never ships in a
 * production build. Used by e2e/smoke.spec.ts and for visual QA without a backend.
 *
 *   /dev/memo-preview?access=teaser|full|legacy&me=free|credit|pro
 *   /dev/memo-preview?access=legacy&variant=locked         (an earlier-format memo that was never unlocked)
 *   /dev/memo-preview?access=legacy&variant=rerun-used     (an unlocked earlier-format memo, free re-run used)
 *   /dev/memo-preview?access=failed                        (a failed memo)
 *   /dev/memo-preview?access=failed&variant=free-rerun     (the failed free re-run of an earlier-format memo)
 *   /dev/memo-preview?access=full&variant=rate             (a base rate with a percentage)
 *   /dev/memo-preview?access=full&variant=rules-date       (generated after its rules date: prints "Rules applied as of", as every v2 report does)
 *   /dev/memo-preview?access=full&variant=before-v2        (a report stored before rule table v2: none of its fields)
 *   /dev/memo-preview?access=full&variant=history-long     (37 records at the address, the newest 20 listed)
 *   /dev/memo-preview?access=full&variant=history-one      (one record at the address; change of use not established)
 *   /dev/memo-preview?access=full&variant=history-empty    (no records at the address; change of use not established)
 *   /dev/memo-preview?access=full&variant=unlabelled       (records that carry no kind labels yet)
 *   /dev/memo-preview?access=full&variant=not-permitted    (a use the district does not permit: no approval path)
 *   /dev/memo-preview?access=teaser&variant=memo-attached  (a teaser record that still carries the memo)
 *   /dev/memo-preview?access=full&status_note=<text>       (layout check only: prints <text> as the zoning row's
 *                                                           status note. No generated case carries a note and the
 *                                                           fixture types no rule-set value, so the text comes from
 *                                                           the URL and the banner says it is not rule output.)
 *   /dev/memo-preview?view=list   (memo cards, including one stored in the earlier report format)
 *   /dev/memo-preview?access=full|teaser&variant=answers  (a memo the API can run again with answers: the form posts
 *                                                          to POST /v1/memos/{id}/answers with a dev token, as the
 *                                                          memo page does; e2e/answers.spec.ts answers the API)
 *   /dev/memo-preview?access=full&variant=answers-unavailable  (made before answers could be added: the old link)
 */
function AnswersPreview({ initial, me }: { initial: MemoRecord; me: Me }) {
  const [record, setRecord] = useState<MemoRecord>(initial);
  const answers = useAnswerRound({ token: "dev-token", record, onRecord: setRecord });
  return (
    <MemoView
      record={record}
      me={me}
      actions={{ onUnlock: () => undefined, onCheckout: () => undefined, onExportPdf: () => undefined, onAnswer: (given) => void answers.submit(given) }}
      busy={{ answer: answers.busy }}
      revisions={answers.revisions}
      answerError={answers.error}
    />
  );
}

function Preview() {
  const params = useSearchParams();
  const accessParam = params.get("access");
  const access = accessParam === "teaser" ? "teaser" : accessParam === "legacy" ? "legacy" : accessParam === "failed" ? "failed" : "full";
  const meKey = params.get("me");
  const me = meKey === "credit" ? ME_FIXTURE_CREDIT : meKey === "pro" ? ME_FIXTURE_PRO : ME_FIXTURE_FREE;
  const variant = params.get("variant");
  const record =
    access === "failed"
      ? variant === "free-rerun"
        ? MEMO_RECORD_FAILED_FREE_RERUN
        : MEMO_RECORD_FAILED
      : access === "teaser"
      ? variant === "memo-attached"
        ? MEMO_RECORD_TEASER_WITH_MEMO
        : MEMO_RECORD_TEASER
      : access === "legacy"
        ? variant === "locked"
          ? MEMO_RECORD_LEGACY_LOCKED
          : variant === "rerun-used"
            ? MEMO_RECORD_LEGACY_RERUN_USED
            : MEMO_RECORD_LEGACY
        : variant === "rate"
          ? MEMO_RECORD_FULL_RATE
          : variant === "rules-date"
            ? MEMO_RECORD_FULL_RULES_DATE
            : variant === "before-v2"
              ? MEMO_RECORD_FULL_BEFORE_V2
          : variant === "history-long"
            ? MEMO_RECORD_FULL_HISTORY_LONG
            : variant === "history-one"
              ? MEMO_RECORD_FULL_HISTORY_ONE
              : variant === "history-empty"
                ? MEMO_RECORD_FULL_HISTORY_EMPTY
                : variant === "unlabelled"
                  ? MEMO_RECORD_FULL_UNLABELLED
                  : variant === "not-permitted"
                    ? MEMO_RECORD_FULL_NOT_PERMITTED
                    : MEMO_RECORD_FULL;
  const injectedNote = access === "full" ? (params.get("status_note") ?? "").trim() : "";
  const shown =
    injectedNote && record.memo
      ? { ...record, memo: { ...record.memo, approvals: record.memo.approvals.map((r) => (r.area === "zoning_use" ? { ...r, status_note: injectedNote } : r)) } }
      : record;
  if (params.get("view") === "list") {
    return (
      <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <p className="mb-6 rounded-lg border border-estimated/40 bg-estimated-soft px-3 py-2 text-xs text-foreground/80" data-testid="dev-banner">
          Development preview · fixture data · view=list
        </p>
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {MEMO_SUMMARIES_FIXTURE.map((m) => (
            <li key={m.id}>
              <MemoCard m={m} />
            </li>
          ))}
        </ul>
      </main>
    );
  }
  if (variant === "answers" || variant === "answers-unavailable") {
    const initial =
      variant === "answers-unavailable" ? MEMO_RECORD_FULL_NOT_ANSWERABLE : access === "teaser" ? MEMO_RECORD_TEASER_ANSWERABLE : MEMO_RECORD_FULL_ANSWERABLE;
    return (
      <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <p className="mb-6 rounded-lg border border-estimated/40 bg-estimated-soft px-3 py-2 text-xs text-foreground/80" data-testid="dev-banner">
          Development preview · fixture data · access={access} · variant={variant}
        </p>
        <AnswersPreview initial={initial} me={me} />
      </main>
    );
  }
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      <p className="mb-6 rounded-lg border border-estimated/40 bg-estimated-soft px-3 py-2 text-xs text-foreground/80" data-testid="dev-banner">
        Development preview · fixture data · access={access} · me={meKey ?? "free"}
        {variant ? ` · variant=${variant}` : ""}
        {injectedNote ? " · status note on the zoning row typed in the URL for a layout check; it is not rule output" : ""}
      </p>
      <MemoView
        record={shown}
        me={me}
        geojson={access === "full" ? MEMO_GEOJSON_FIXTURE : null}
        actions={{ onUnlock: () => undefined, onCheckout: () => undefined, onExportPdf: () => undefined, onDelete: () => undefined }}
      />
    </main>
  );
}

export default function MemoPreviewPage() {
  return (
    <Suspense fallback={null}>
      <Preview />
    </Suspense>
  );
}
