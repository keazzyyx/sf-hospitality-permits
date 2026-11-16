"use client";

import { ExternalLink } from "lucide-react";
import { cn } from "cn";
import { Badge } from "@/components/ui/badge";
import { Cite } from "@/components/memo/citations";
import { formatDate } from "@/lib/format";
import { RecordKindBadge } from "@/components/memo/status-pill";
import {
  decisionTimeLines,
  formatDistance,
  outcomeBucket,
  OUTCOME_CLASSES,
  outcomeLabel,
  showsRecordKind,
  similarityPct,
  TIMING_COLUMN,
  TIMING_HEADING,
  TIMING_HINT,
  timingCell,
} from "@/lib/memo";
import type { ComparableCase } from "@/lib/api-types";

export function OutcomeBadge({ outcome, className }: { outcome: string; className?: string }) {
  return (
    <Badge variant="outline" className={cn("whitespace-nowrap", OUTCOME_CLASSES[outcomeBucket(outcome)], className)} data-testid="outcome-badge">
      {outcomeLabel(outcome)}
    </Badge>
  );
}

export function SimilarityBar({ score }: { score: number }) {
  const pct = similarityPct(score);
  return (
    <div className="flex items-center gap-2" aria-label={`${pct}% similar`}>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-ink" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs tabular">{pct}%</span>
    </div>
  );
}

/**
 * What a record says about its use, its closing hour and its conditions, where it carries them. The conditions are
 * listed in full behind a disclosure, as the record states them.
 */
export function RecordedFacts({ useTypes, hoursClose, conditions, className }: { useTypes?: string[] | null; hoursClose?: string | null; conditions?: string[] | null; className?: string }) {
  const uses = useTypes ?? [];
  const conds = conditions ?? [];
  if (uses.length === 0 && !hoursClose && conds.length === 0) return null;
  return (
    <div className={cn("mt-1 space-y-0.5 text-xs text-muted-foreground", className)} data-testid="recorded-facts">
      {uses.length > 0 && <p>Use: {uses.map((u) => u.replace(/_/g, " ")).join(", ")}</p>}
      {hoursClose && <p>Closes: {hoursClose}</p>}
      {conds.length > 0 && (
        <details className="group" data-testid="record-conditions">
          <summary className="cursor-pointer select-none text-signal hover:underline">
            {conds.length} {conds.length === 1 ? "condition" : "conditions"} on file
          </summary>
          <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-foreground/85">
            {conds.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}

/**
 * Comparable cases in the order of the fixed ranking (no model picks them): distance, source with the record kind
 * under it (use decision or agency referral; nothing for any other kind, so nothing when the store has no labels),
 * type, use, filed/decided, days from filing for its own outcome, outcome, hours, the conditions on file (listed in
 * full behind a disclosure), opposition (only when the API supplies it), similarity, and the link to the source
 * record. On a phone each case is a card with the same facts; from the medium breakpoint up, a table.
 */
export function ComparablesTable({ cases, asOf, className }: { cases: ComparableCase[]; asOf?: string | null; className?: string }) {
  const sorted = cases.slice().sort((a, b) => b.similarity_score - a.similarity_score);
  // The API withholds the opposition flag until it passes validation; hide the column while it is absent.
  const showOpposition = sorted.some((c) => c.opposition_noted !== null);
  if (sorted.length === 0) {
    return (
      <div className={cn("rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground", className)}>
        No comparable applications were decided within 1,000 ft in the lookback window. The report leans on zoning and overlay rules instead.
      </div>
    );
  }
  return (
    <div className={cn("rounded-xl border border-border bg-card", className)}>
      <ol className="divide-y divide-border md:hidden" data-testid="comparables-cards">
        {sorted.map((c, i) => (
          <li key={c.application_id} className="space-y-1.5 p-4" data-testid="comparable-card">
            <div className="flex items-start justify-between gap-3">
              <p className="min-w-0 font-medium leading-snug">
                <span className="mr-1.5 font-mono text-xs text-muted-foreground">{i + 1}.</span>
                {c.address ?? "Address withheld"}
              </p>
              <OutcomeBadge outcome={c.outcome} />
            </div>
            <p className="text-xs text-muted-foreground">
              {c.permit_type} · {formatDistance(c.distance_m)} · {c.source_label || c.source}
            </p>
            <p className="font-mono text-xs tabular text-muted-foreground">
              filed {formatDate(c.filed_at)} · {c.decided_at ? `decided ${formatDate(c.decided_at)}` : "not decided"} · {timingCell(c, asOf)}
            </p>
            <RecordedFacts useTypes={c.use_types} hoursClose={c.hours_close} conditions={c.conditions} />
            <a href={c.source_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 font-mono text-[11px] text-signal hover:underline">
              {c.application_id} <ExternalLink className="size-3" aria-hidden />
            </a>
            <Cite ids={[c.citation_id]} />
          </li>
        ))}
      </ol>
      <div className="hidden overflow-x-auto md:block">
      <table className="w-full min-w-[1240px] border-collapse text-sm" data-testid="comparables-table">
        <thead>
          <tr className="border-b border-border bg-paper-deep/50 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            <th scope="col" className="w-80 min-w-80 px-3 py-2.5">Case</th>
            <th scope="col" className="px-3 py-2.5">Distance</th>
            <th scope="col" className="min-w-32 px-3 py-2.5">Source</th>
            <th scope="col" className="min-w-32 px-3 py-2.5">Type</th>
            <th scope="col" className="min-w-36 px-3 py-2.5">Use</th>
            <th scope="col" className="px-3 py-2.5">Filed / decided</th>
            <th scope="col" className="px-3 py-2.5 text-right">{TIMING_COLUMN}</th>
            <th scope="col" className="px-3 py-2.5">Outcome</th>
            <th scope="col" className="px-3 py-2.5">Hours</th>
            <th scope="col" className="px-3 py-2.5">Conditions</th>
            {showOpposition && <th scope="col" className="px-3 py-2.5">Opposition</th>}
            <th scope="col" className="px-3 py-2.5">Similarity</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((c) => (
            <tr key={c.application_id} className="group border-b border-border align-top last:border-b-0 odd:bg-transparent even:bg-paper-deep/20" data-testid="comparable-row">
              <td className="w-80 min-w-80 px-3 py-3">
                <div className="font-medium leading-snug">{c.address ?? "Address withheld"}</div>
                <a href={c.source_url} target="_blank" rel="noreferrer noopener" className="mt-0.5 inline-flex items-center gap-1 whitespace-nowrap font-mono text-[11px] text-signal hover:underline">
                  {c.application_id} <ExternalLink className="size-3" aria-hidden />
                </a>
                <Cite ids={[c.citation_id]} />
              </td>
              <td className="whitespace-nowrap px-3 py-3 font-mono text-xs tabular">{formatDistance(c.distance_m)}</td>
              <td className="px-3 py-3 text-xs">
                <span data-testid="comparable-source" data-source={c.source}>
                  {c.source_label || c.source}
                </span>
                {showsRecordKind(c.record_kind) && (
                  <div className="mt-1.5">
                    <RecordKindBadge kind={c.record_kind} label={c.record_kind_label} testId="comparable-kind" />
                  </div>
                )}
              </td>
              <td className="px-3 py-3 text-xs">{c.permit_type}</td>
              <td className="px-3 py-3">
                <div className="flex max-w-36 flex-wrap gap-1">
                  {c.use_types.map((u) => (
                    <span key={u} className="rounded-full border border-border bg-background px-1.5 py-0.5 text-[11px]">
                      {u.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              </td>
              <td className="whitespace-nowrap px-3 py-3 font-mono text-xs tabular">
                <div>{formatDate(c.filed_at)}</div>
                <div className="text-muted-foreground">{c.decided_at ? formatDate(c.decided_at) : "not decided"}</div>
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right font-mono text-xs tabular" data-testid="comparable-days">
                {timingCell(c, asOf)}
              </td>
              <td className="px-3 py-3">
                <OutcomeBadge outcome={c.outcome} />
              </td>
              <td className="whitespace-nowrap px-3 py-3 font-mono text-xs tabular">{c.hours_close ?? "—"}</td>
              <td className="min-w-40 px-3 py-3 text-xs" data-testid="comparable-conditions">
                {c.conditions.length > 0 ? <RecordedFacts conditions={c.conditions} className="mt-0" /> : <span className="text-muted-foreground" title="The source does not carry conditions for this case">–</span>}
              </td>
              {showOpposition && (
                <td className="px-3 py-3 text-xs">
                  {c.opposition_noted === null ? <span className="text-muted-foreground">Not recorded</span> : c.opposition_noted ? <span className="font-medium text-dead">Yes</span> : <span className="text-verified">None noted</span>}
                </td>
              )}
              <td className="px-3 py-3">
                <SimilarityBar score={c.similarity_score} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <div className="border-t border-border px-3 py-3 text-xs" data-testid="decision-times">
        <p className="font-semibold">{TIMING_HEADING}</p>
        <p className="mt-0.5 text-muted-foreground">{TIMING_HINT}</p>
        <ul className="mt-1.5 space-y-0.5">
          {decisionTimeLines(sorted, asOf).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
