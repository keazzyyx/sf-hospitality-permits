"use client";

import { CalendarCheck2, CalendarX2, MapPin } from "lucide-react";
import { cn } from "cn";
import { ExportPdfButton } from "@/components/plan/export-button";
import { RerunDialog } from "@/components/plan/rerun-dialog";
import { Badge } from "@/components/ui/badge";
import { formatDate, statusLabel } from "@/lib/format";
import type { PlanRecord } from "@/lib/api-types";

export function PlanHeader({ record, onUpdated }: { record: PlanRecord; onUpdated: (next: PlanRecord) => void }) {
  const plan = record.plan;
  const tl = plan?.timeline;
  const city = [plan?.jurisdiction.city_name ?? record.profile?.city_name, plan?.jurisdiction.state ?? record.profile?.state]
    .filter(Boolean)
    .join(", ");

  return (
    <header className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant="outline"
              className={cn(
                record.status === "ready" && "border-verified/30 bg-verified-soft text-verified",
                record.status === "failed" && "border-dead/30 bg-dead-soft text-dead",
                (record.status === "generating" || record.status === "pending_clarification") && "border-estimated/40 bg-estimated-soft text-estimated",
              )}
            >
              {statusLabel(record.status)}
            </Badge>
            <span className="font-mono text-xs text-muted-foreground">v{record.version}</span>
            {city && (
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <MapPin className="size-3.5" aria-hidden /> {city}
              </span>
            )}
          </div>
          <h1 className="mt-2 text-2xl font-semibold sm:text-3xl">{record.title}</h1>
        </div>
        {record.status === "ready" && plan && (
          <div className="flex flex-wrap gap-2">
            <ExportPdfButton planId={record.id} title={record.title} version={record.version} />
            <RerunDialog plan={record} onUpdated={onUpdated} />
          </div>
        )}
      </div>

      {tl && (
        <dl className="grid gap-3 rounded-xl border border-border bg-card p-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-xs text-muted-foreground">Projected open</dt>
            <dd className="mt-0.5 font-display text-lg font-semibold">{formatDate(tl.projected_open_date)}</dd>
            <dd className="text-xs text-muted-foreground">
              {tl.total_days_min}–{tl.total_days_max} days from {formatDate(tl.start_date, { month: "short", day: "numeric" })}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Target open</dt>
            <dd className="mt-0.5 font-display text-lg font-semibold">{formatDate(tl.target_open_date)}</dd>
            <dd className="mt-0.5">
              {tl.feasible === null ? (
                <span className="text-xs text-muted-foreground">No target set</span>
              ) : tl.feasible ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-verified-soft px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-verified">
                  <CalendarCheck2 className="size-3" aria-hidden /> Feasible
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full bg-dead-soft px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-dead">
                  <CalendarX2 className="size-3" aria-hidden /> {tl.days_short ?? 0} days short
                </span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Optimistic open</dt>
            <dd className="mt-0.5 font-display text-lg font-semibold">{formatDate(tl.optimistic_open_date)}</dd>
            <dd className="text-xs text-muted-foreground">If every agency hits its minimum</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Critical path</dt>
            <dd className="mt-0.5 font-display text-lg font-semibold tabular">{tl.critical_path.length} steps</dd>
            <dd className="text-xs text-muted-foreground">{tl.parallel_tracks.length} parallel tracks</dd>
          </div>
        </dl>
      )}
    </header>
  );
}
