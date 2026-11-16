"use client";

import { useMemo } from "react";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { cn } from "cn";
import { Badge } from "@/components/ui/badge";
import type { Plan } from "@/lib/api-types";

const SEVERITY_RANK = { high: 0, medium: 1, low: 2 } as const;

export function BlockersView({ plan }: { plan: Plan }) {
  const nameById = useMemo(() => new Map(plan.steps.map((s) => [s.id, s.name])), [plan.steps]);
  const blockers = useMemo(
    () => plan.blockers.slice().sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || b.impact_days_max - a.impact_days_max),
    [plan.blockers],
  );

  if (blockers.length === 0) {
    return (
      <div className="rounded-xl border border-verified/30 bg-verified-soft p-6 text-sm">
        <p className="inline-flex items-center gap-2 font-semibold text-verified">
          <ShieldCheck className="size-4" aria-hidden /> No notable blockers identified
        </p>
        <p className="mt-1 text-foreground/80">Keep an eye on the stall-risk notes in the checklist anyway; agencies change process without warning.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {blockers.length} risk{blockers.length === 1 ? "" : "s"} that commonly delay openings like yours, sorted by severity. Impact is the typical slip if it happens.
      </p>
      <ul className="grid gap-4 lg:grid-cols-2">
        {blockers.map((b) => (
          <li
            key={b.id}
            className={cn(
              "rounded-xl border bg-card p-5",
              b.severity === "high" ? "border-dead/40 border-l-4 border-l-dead" : b.severity === "medium" ? "border-estimated/40 border-l-4 border-l-estimated" : "border-border border-l-4 border-l-ink/30",
            )}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h3 className="inline-flex items-start gap-2 font-semibold leading-snug">
                <ShieldAlert className={cn("mt-0.5 size-4 shrink-0", b.severity === "high" ? "text-dead" : b.severity === "medium" ? "text-estimated" : "text-muted-foreground")} aria-hidden />
                {b.title}
              </h3>
              <div className="flex flex-wrap gap-1.5">
                <Badge variant="outline" className={cn("capitalize", b.severity === "high" && "border-dead/30 bg-dead-soft text-dead", b.severity === "medium" && "border-estimated/40 bg-estimated-soft text-estimated")}>
                  {b.severity} severity
                </Badge>
                <Badge variant="outline" className="capitalize">
                  {b.likelihood}
                </Badge>
              </div>
            </div>
            <p className="mt-2 font-mono text-xs text-muted-foreground tabular">
              Impact if it happens: {b.impact_days_min}–{b.impact_days_max} days
            </p>
            <p className="mt-3 text-sm leading-relaxed">{b.description}</p>
            <div className="mt-3 rounded-lg bg-muted p-3 text-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Mitigation</p>
              <p className="mt-1 leading-relaxed">{b.mitigation}</p>
            </div>
            {b.related_step_ids.length > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                <span className="text-xs text-muted-foreground">Affects:</span>
                {b.related_step_ids.map((id) => (
                  <span key={id} className="rounded-full border border-border bg-background px-2 py-0.5 text-xs">
                    {nameById.get(id) ?? id}
                  </span>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
