"use client";

import { useMemo } from "react";
import { ConfidenceBadge } from "@/components/plan/confidence-badge";
import { categoryLabel } from "@/lib/catalog";
import { formatUsd, formatUsdRange } from "@/lib/format";
import type { Plan } from "@/lib/api-types";

export function FeesView({ plan }: { plan: Plan }) {
  const fees = plan.fees;
  const stepById = useMemo(() => new Map(plan.steps.map((s) => [s.id, s])), [plan.steps]);
  const categories = useMemo(() => fees.by_category.slice().sort((a, b) => b.max - a.max), [fees.by_category]);
  const maxCat = Math.max(1, ...categories.map((c) => c.max));
  const estimatedTotal = useMemo(
    () => plan.steps.filter((s) => s.confidence === "estimated").reduce((acc, s) => acc + s.fee_range_usd.max, 0),
    [plan.steps],
  );

  return (
    <div className="space-y-8">
      <section className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-border bg-card p-4 sm:col-span-2">
          <p className="text-xs text-muted-foreground">Total application and first-year fees</p>
          <p className="mt-1 font-display text-3xl font-semibold tabular sm:text-4xl">
            {formatUsd(fees.total_min)} <span className="text-muted-foreground">–</span> {formatUsd(fees.total_max)}
          </p>
          {fees.notes && <p className="mt-2 text-sm text-muted-foreground">{fees.notes}</p>}
        </div>
        <div className="rounded-xl border border-estimated/40 bg-estimated-soft p-4">
          <p className="text-xs text-foreground/70">Of which unverified (Estimated items)</p>
          <p className="mt-1 font-display text-2xl font-semibold tabular text-estimated">up to {formatUsd(estimatedTotal)}</p>
          <p className="mt-1 text-xs text-foreground/70">Confirm these with the agency before budgeting.</p>
        </div>
      </section>

      <section aria-labelledby="fees-cat">
        <h2 id="fees-cat" className="mb-3 text-base font-semibold">
          By category
        </h2>
        <ul className="space-y-2.5 rounded-xl border border-border bg-card p-4">
          {categories.map((c) => (
            <li key={c.category} className="grid grid-cols-[minmax(0,140px)_1fr_auto] items-center gap-3 text-sm sm:grid-cols-[minmax(0,200px)_1fr_auto]">
              <span className="truncate">{categoryLabel(c.category)}</span>
              <div className="relative h-5 overflow-hidden rounded bg-muted" role="img" aria-label={`${categoryLabel(c.category)}: ${formatUsdRange(c)}`}>
                <div className="absolute inset-y-0 left-0 rounded bg-ink/25" style={{ width: `${(c.max / maxCat) * 100}%` }} />
                <div className="absolute inset-y-0 left-0 rounded bg-ink" style={{ width: `${(c.min / maxCat) * 100}%` }} />
              </div>
              <span className="font-mono text-xs tabular">{formatUsdRange(c)}</span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted-foreground">Dark bar = minimum, light bar = maximum.</p>
      </section>

      <section aria-labelledby="fees-step">
        <h2 id="fees-step" className="mb-3 text-base font-semibold">
          By step
        </h2>
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="bg-paper-deep/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">Step</th>
                <th className="px-4 py-2 font-medium">Agency</th>
                <th className="px-4 py-2 font-medium">Confidence</th>
                <th className="px-4 py-2 text-right font-medium">Fee range</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {fees.by_step
                .slice()
                .sort((a, b) => (stepById.get(a.step_id)?.order ?? 0) - (stepById.get(b.step_id)?.order ?? 0))
                .map((row) => {
                  const s = stepById.get(row.step_id);
                  return (
                    <tr key={row.step_id}>
                      <td className="px-4 py-2.5 font-medium">{s?.name ?? row.step_id}</td>
                      <td className="px-4 py-2.5 text-muted-foreground">{s?.issuing_agency ?? "—"}</td>
                      <td className="px-4 py-2.5">{s ? <ConfidenceBadge confidence={s.confidence} /> : "—"}</td>
                      <td className="px-4 py-2.5 text-right font-mono tabular">{formatUsdRange(row)}</td>
                    </tr>
                  );
                })}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-ink/20 font-semibold">
                <td className="px-4 py-2.5" colSpan={3}>
                  Total
                </td>
                <td className="px-4 py-2.5 text-right font-mono tabular">{formatUsd(fees.total_min)}–{formatUsd(fees.total_max)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>
    </div>
  );
}
