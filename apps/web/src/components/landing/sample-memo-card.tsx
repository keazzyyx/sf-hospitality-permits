import { Lock, MapPin } from "lucide-react";
import { StatusPill } from "@/components/memo/status-pill";
import { OutcomeBadge, SimilarityBar } from "@/components/memo/comparables-table";
import { MEMO_FIXTURE_FULL } from "@/lib/fixtures/memo-fixture";
import { FACTS_READ_HEADING, factValueText, formatDistance, showsApprovalRate, splitFacts } from "@/lib/memo";

/**
 * "What's in a memo": a static sample built from the same shapes the API returns. The comparable
 * cases are blurred the way a teaser blurs them. Server component; no data fetching.
 */
export function SampleMemoCard() {
  const memo = MEMO_FIXTURE_FULL;
  const rows = memo.approvals.slice(0, 3);
  const baseRate = memo.base_rate;
  const comps = memo.comparable_cases.slice(0, 3);
  const facts = splitFacts(memo.facts).known.slice(0, 3);
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-[0_1px_0_rgba(20,27,45,0.04),0_18px_50px_-30px_rgba(20,27,45,0.45)]" data-testid="sample-memo">
      <div className="border-b border-border bg-paper-deep/40 px-5 py-4">
        <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          <span>Sample memo</span>
          <span aria-hidden>·</span>
          <span className="font-mono normal-case tracking-normal">records as of {memo.data_as_of}</span>
        </div>
        <p className="mt-2 inline-flex items-start gap-2 font-semibold leading-snug">
          <MapPin className="mt-0.5 size-4 shrink-0 text-signal" aria-hidden /> {memo.address}
        </p>
        <p className="mt-0.5 text-sm text-muted-foreground">“{memo.description}”</p>
      </div>

      <div className="space-y-5 p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
          <StatusPill status={memo.overall.status} size="lg" />
          <p className="text-sm leading-relaxed text-foreground/90">
            {memo.overall.line}
            <sup className="ml-0.5 text-[0.68em] font-medium text-signal">[1][2]</sup>
          </p>
        </div>

        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Approvals this concept needs</p>
          <ol className="mt-2 space-y-2">
            {rows.map((r) => (
              <li key={r.area} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-background p-3 text-sm">
                <p className="min-w-0 font-medium leading-snug">
                  <span className="block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{r.area_label}</span>
                  {r.approval}
                </p>
                <StatusPill status={r.status} size="sm" />
              </li>
            ))}
          </ol>
        </div>

        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{FACTS_READ_HEADING}</p>
          <ul className="mt-2 space-y-1.5 text-sm">
            {facts.map((f) => (
              <li key={f.fact} className="flex items-start gap-2">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-ink" aria-hidden />
                <span>
                  <span className="font-medium">{f.label}:</span> {factValueText(f)}
                  {f.quotes.length > 0 && <span className="block text-xs text-muted-foreground">from your words “{f.quotes[0]}”</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Comparable cases within 1,000 ft</p>
          <ul className="mt-2 space-y-2 blur-[3px] saturate-50 select-none" aria-hidden>
            {comps.map((c) => (
              <li key={c.application_id} className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 rounded-lg border border-border bg-background px-3 py-2 text-sm">
                <span className="min-w-0">
                  <span className="block truncate font-medium">{c.address}</span>
                  <span className="block font-mono text-[11px] text-muted-foreground">
                    {formatDistance(c.distance_m)}
                    {c.hours_close ? ` · closes ${c.hours_close}` : ` · ${c.permit_type}`}
                  </span>
                </span>
                <OutcomeBadge outcome={c.outcome} />
                <SimilarityBar score={c.similarity_score} />
              </li>
            ))}
          </ul>
          <div className="absolute inset-x-0 bottom-0 top-6 flex items-center justify-center">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-ink bg-ink px-3 py-1.5 text-xs font-semibold text-paper shadow-lg">
              <Lock className="size-3.5" aria-hidden /> {memo.comparable_cases.length} cases with decisions · in the full memo
            </span>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 border-t border-border pt-4 text-center">
          <div>
            <p className="font-display text-xl font-semibold tabular">{showsApprovalRate(baseRate) ? `${baseRate.approval_rate_pct}%` : `N = ${baseRate.total}`}</p>
            <p className="text-[11px] text-muted-foreground">{showsApprovalRate(baseRate) ? `approval rate nearby (N = ${baseRate.total})` : "comparable outcomes nearby"}</p>
          </div>
          <div>
            <p className="font-display text-xl font-semibold tabular">{memo.approvals.length}</p>
            <p className="text-[11px] text-muted-foreground">approvals, each set by rule</p>
          </div>
          <div>
            <p className="font-display text-xl font-semibold tabular">{memo.citations.length}</p>
            <p className="text-[11px] text-muted-foreground">records cited</p>
          </div>
        </div>
      </div>
    </div>
  );
}
