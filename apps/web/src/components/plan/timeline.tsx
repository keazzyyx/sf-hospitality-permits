"use client";

import { useMemo } from "react";
import { cn } from "cn";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { addDays, daysBetween, formatDate, toIsoDate } from "@/lib/format";
import type { Plan } from "@/lib/api-types";

const LABEL_W = 220;
const WEEK_W = 56;
const ROW_H = 36;

export function TimelineView({ plan }: { plan: Plan }) {
  const tl = plan.timeline;
  const steps = useMemo(() => plan.steps.slice().sort((a, b) => a.earliest_start_day - b.earliest_start_day || a.order - b.order), [plan.steps]);
  const nameById = useMemo(() => new Map(plan.steps.map((s) => [s.id, s.name])), [plan.steps]);

  const todayDay = daysBetween(tl.start_date, toIsoDate(new Date()));
  const targetDay = tl.target_open_date ? daysBetween(tl.start_date, tl.target_open_date) : null;
  const lastDay = Math.max(tl.total_days_max, ...steps.map((s) => s.earliest_finish_day), targetDay ?? 0, 7);
  const weeks = Math.ceil(lastDay / 7) + 1;
  const width = weeks * WEEK_W;
  const x = (day: number) => (Math.max(0, day) / (weeks * 7)) * width;

  return (
    <div className="space-y-10">
      <section aria-labelledby="gantt-title">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 id="gantt-title" className="text-base font-semibold">
            Schedule
          </h2>
          <ul className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
            <li className="inline-flex items-center gap-1.5"><span className="h-2.5 w-5 rounded-sm bg-signal" aria-hidden /> Critical path</li>
            <li className="inline-flex items-center gap-1.5"><span className="h-2.5 w-5 rounded-sm bg-ink/60" aria-hidden /> Has slack</li>
            <li className="inline-flex items-center gap-1.5"><span className="h-3 w-0.5 bg-verified" aria-hidden /> Today</li>
            <li className="inline-flex items-center gap-1.5"><span className="h-3 w-0.5 border-l-2 border-dashed border-dead" aria-hidden /> Target</li>
          </ul>
        </div>
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <div className="relative" style={{ minWidth: LABEL_W + width }}>
            {/* header */}
            <div className="sticky top-0 z-10 flex border-b border-border bg-card text-[11px] text-muted-foreground">
              <div className="shrink-0 border-r border-border px-3 py-2 font-medium" style={{ width: LABEL_W }}>
                Step
              </div>
              <div className="relative" style={{ width, height: 34 }}>
                {Array.from({ length: weeks }, (_, i) => (
                  <div key={i} className="absolute top-0 h-full border-l border-border/70 px-1.5 py-1.5" style={{ left: i * WEEK_W, width: WEEK_W }}>
                    <div className="font-mono">W{i + 1}</div>
                    <div className="truncate text-[10px] opacity-70">{formatDate(addDays(tl.start_date, i * 7), { month: "short", day: "numeric" })}</div>
                  </div>
                ))}
              </div>
            </div>
            {/* rows */}
            <ol>
              {steps.map((s, i) => {
                const left = x(s.earliest_start_day);
                const w = Math.max(6, x(s.earliest_finish_day) - left);
                return (
                  <li key={s.id} className={cn("flex items-center", i % 2 === 1 && "bg-paper-deep/30")} style={{ height: ROW_H }}>
                    <div className="flex h-full shrink-0 items-center gap-2 truncate border-r border-border px-3 text-xs" style={{ width: LABEL_W }} title={s.name}>
                      <span className="font-mono text-muted-foreground">{String(s.order).padStart(2, "0")}</span>
                      <span className={cn("truncate", s.on_critical_path && "font-semibold")}>{s.name}</span>
                    </div>
                    <div className="relative h-full" style={{ width }}>
                      {Array.from({ length: weeks }, (_, k) => (
                        <span key={k} className="absolute top-0 h-full border-l border-border/40" style={{ left: k * WEEK_W }} aria-hidden />
                      ))}
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div
                            className={cn("absolute top-1/2 h-4 -translate-y-1/2 rounded-sm", s.on_critical_path ? "bg-signal" : "bg-ink/60")}
                            style={{ left, width: w }}
                            role="img"
                            aria-label={`${s.name}: ${formatDate(s.scheduled_start)} to ${formatDate(s.scheduled_end)}`}
                          />
                        </TooltipTrigger>
                        <TooltipContent>
                          <p className="font-medium">{s.name}</p>
                          <p>{formatDate(s.scheduled_start)} → {formatDate(s.scheduled_end)}</p>
                          <p>{s.on_critical_path ? "Critical path" : `${s.slack_days} days of slack`}</p>
                        </TooltipContent>
                      </Tooltip>
                      {s.slack_days > 0 && !s.on_critical_path && (
                        <span className="absolute top-1/2 h-1 -translate-y-1/2 rounded-sm bg-ink/15" style={{ left: left + w, width: Math.max(0, x(s.latest_finish_day) - left - w) }} aria-hidden />
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
            {/* markers */}
            {todayDay >= 0 && todayDay <= weeks * 7 && (
              <div className="pointer-events-none absolute bottom-0 top-0 z-20 w-0.5 bg-verified" style={{ left: LABEL_W + x(todayDay) }} aria-hidden>
                <span className="absolute -top-0 left-1 rounded bg-verified px-1 text-[10px] font-semibold text-white">Today</span>
              </div>
            )}
            {targetDay !== null && (
              <div className="pointer-events-none absolute bottom-0 top-0 z-20 border-l-2 border-dashed border-dead" style={{ left: LABEL_W + x(targetDay) }} aria-hidden>
                <span className="absolute left-1 top-0 rounded bg-dead px-1 text-[10px] font-semibold text-white">Target</span>
              </div>
            )}
            <div className="pointer-events-none absolute bottom-0 top-0 z-20 border-l-2 border-ink" style={{ left: LABEL_W + x(tl.total_days_max) }} aria-hidden>
              <span className="absolute bottom-1 left-1 rounded bg-ink px-1 text-[10px] font-semibold text-paper">Projected open</span>
            </div>
          </div>
        </div>
        {tl.sequencing_rationale && <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{tl.sequencing_rationale}</p>}
      </section>

      <section aria-labelledby="weeks-title">
        <h2 id="weeks-title" className="mb-3 text-base font-semibold">
          Week by week
        </h2>
        <ol className="relative space-y-4 border-l border-border pl-6">
          {tl.weeks.map((w) => {
            const isCurrent = todayDay >= (w.week_number - 1) * 7 && todayDay < w.week_number * 7;
            return (
              <li key={w.week_number} className="relative">
                <span className={cn("absolute -left-[31px] top-1.5 grid size-5 place-items-center rounded-full border bg-card font-mono text-[10px]", isCurrent ? "border-verified text-verified" : "border-border text-muted-foreground")} aria-hidden>
                  {w.week_number}
                </span>
                <div className={cn("rounded-xl border bg-card p-4", isCurrent ? "border-verified/50" : "border-border")}>
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="font-semibold">
                      Week {w.week_number}
                      <span className="ml-2 text-sm font-normal text-muted-foreground">
                        {formatDate(w.start_date, { month: "short", day: "numeric" })} – {formatDate(w.end_date, { month: "short", day: "numeric" })}
                      </span>
                    </h3>
                    {isCurrent && <span className="text-[11px] font-semibold uppercase tracking-wide text-verified">This week</span>}
                  </div>
                  <p className="mt-1 text-sm font-medium text-foreground/90">{w.focus}</p>
                  {w.actions.length > 0 && (
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-foreground/85">
                      {w.actions.map((a, i) => (
                        <li key={i}>{a}</li>
                      ))}
                    </ul>
                  )}
                  {(w.step_ids_starting.length > 0 || w.step_ids_due.length > 0) && (
                    <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs">
                      {w.step_ids_starting.length > 0 && (
                        <p>
                          <span className="text-muted-foreground">Starting: </span>
                          {w.step_ids_starting.map((id) => nameById.get(id) ?? id).join(", ")}
                        </p>
                      )}
                      {w.step_ids_due.length > 0 && (
                        <p>
                          <span className="text-muted-foreground">Due: </span>
                          {w.step_ids_due.map((id) => nameById.get(id) ?? id).join(", ")}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}
