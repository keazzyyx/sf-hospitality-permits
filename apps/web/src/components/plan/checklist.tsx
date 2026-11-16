"use client";

import { useMemo, useState } from "react";
import { AlertOctagon, ChevronDown, ExternalLink, Info } from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { useApp } from "@/components/app/app-context";
import { ConfidenceBadge, CriticalPathBadge, UrlStatusFlag } from "@/components/plan/confidence-badge";
import { Checkbox } from "@/components/ui/checkbox";
import { api, describeApiError } from "@/lib/api";
import { capture } from "@/lib/analytics";
import { groupBy } from "@/lib/catalog";
import { formatDate, formatDaysRange, formatUsdRange } from "@/lib/format";
import type { PlanRecord, PlanStep, PlanStepRecord } from "@/lib/api-types";

export function Checklist({ record, onRecordChange }: { record: PlanRecord; onRecordChange: (next: PlanRecord) => void }) {
  const { accessToken } = useApp();
  const plan = record.plan;
  const [pending, setPending] = useState<Set<string>>(new Set());

  const steps = useMemo(() => (plan ? plan.steps.slice().sort((a, b) => a.order - b.order) : []), [plan]);
  const byKey = useMemo(() => new Map(record.steps.map((r) => [r.step_key, r])), [record.steps]);
  const nameById = useMemo(() => new Map(steps.map((s) => [s.id, s.name])), [steps]);
  const tracks = useMemo(() => groupBy(steps, (s) => s.track), [steps]);
  const done = record.steps.filter((r) => r.done).length;

  if (!plan) return null;

  async function toggle(step: PlanStep, rec: PlanStepRecord, next: boolean) {
    const apply = (value: boolean, done_at: string | null) =>
      onRecordChange({
        ...record,
        steps: record.steps.map((r) => (r.id === rec.id ? { ...r, done: value, done_at } : r)),
      });
    apply(next, next ? new Date().toISOString() : null);
    setPending((p) => new Set(p).add(rec.id));
    try {
      const { step: saved } = await api.patchStep(accessToken, record.id, rec.id, { done: next });
      onRecordChange({ ...record, steps: record.steps.map((r) => (r.id === saved.id ? saved : r)) });
      capture("step_toggled", { plan_id: record.id, step_key: step.id, done: next, on_critical_path: step.on_critical_path });
    } catch (err) {
      apply(!next, rec.done_at);
      toast.error("Could not save that step", { description: describeApiError(err) });
    } finally {
      setPending((p) => {
        const n = new Set(p);
        n.delete(rec.id);
        return n;
      });
    }
  }

  return (
    <div className="space-y-8">
      <p className="text-sm text-muted-foreground">
        {done} of {steps.length} steps done · ordered by dependency, grouped into parallel tracks. Items marked{" "}
        <span className="font-semibold text-signal">critical path</span> directly move your opening date.
      </p>
      {tracks.map((t) => (
        <section key={t.key} aria-labelledby={`track-${t.key}`}>
          <div className="mb-3 flex items-baseline justify-between">
            <h2 id={`track-${t.key}`} className="text-base font-semibold">
              {t.key}
            </h2>
            <span className="text-xs text-muted-foreground">
              {t.items.filter((s) => byKey.get(s.id)?.done).length}/{t.items.length} done
            </span>
          </div>
          <ol className="space-y-3">
            {t.items.map((step) => {
              const rec = byKey.get(step.id);
              return (
                <StepCard
                  key={step.id}
                  step={step}
                  rec={rec}
                  nameById={nameById}
                  saving={rec ? pending.has(rec.id) : false}
                  onToggle={(v) => rec && toggle(step, rec, v)}
                />
              );
            })}
          </ol>
        </section>
      ))}
    </div>
  );
}

function StepCard({
  step,
  rec,
  nameById,
  saving,
  onToggle,
}: {
  step: PlanStep;
  rec: PlanStepRecord | undefined;
  nameById: Map<string, string>;
  saving: boolean;
  onToggle: (v: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const done = Boolean(rec?.done);
  const id = `step-${step.id.replace(/[^a-z0-9]/gi, "-")}`;

  return (
    <li
      className={cn(
        "rounded-xl border bg-card transition-colors",
        step.on_critical_path ? "border-l-4 border-l-signal border-border" : "border-border",
        done && "bg-paper-deep/40",
      )}
      data-step-id={step.id}
    >
      <div className="flex gap-3 p-4 sm:p-5">
        <div className="pt-0.5">
          <Checkbox
            id={id}
            checked={done}
            disabled={!rec || saving}
            onCheckedChange={(v) => onToggle(v === true)}
            aria-label={`Mark ${step.name} ${done ? "not done" : "done"}`}
            className="size-5 data-[state=checked]:border-verified data-[state=checked]:bg-verified"
          />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
            <div className="min-w-0">
              <label htmlFor={id} className={cn("cursor-pointer font-semibold leading-snug", done && "text-muted-foreground line-through decoration-muted-foreground/60")}>
                <span className="mr-2 font-mono text-xs text-muted-foreground">{String(step.order).padStart(2, "0")}</span>
                {step.name}
              </label>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {step.issuing_agency} · <span className="capitalize">{step.jurisdiction_level}</span>
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {step.on_critical_path && <CriticalPathBadge />}
              <ConfidenceBadge confidence={step.confidence} />
              <UrlStatusFlag status={step.url_status} />
            </div>
          </div>

          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs sm:grid-cols-4">
            <div>
              <dt className="text-muted-foreground">Timeline</dt>
              <dd className="font-mono tabular">{formatDaysRange(step.typical_timeline_days)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Fees</dt>
              <dd className="font-mono tabular">{formatUsdRange(step.fee_range_usd)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Scheduled</dt>
              <dd className="font-mono tabular">
                {formatDate(step.scheduled_start, { month: "short", day: "numeric" })} → {formatDate(step.scheduled_end, { month: "short", day: "numeric" })}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Slack</dt>
              <dd className={cn("font-mono tabular", step.slack_days === 0 && "text-signal")}>{step.slack_days === 0 ? "none" : `${step.slack_days} days`}</dd>
            </div>
          </dl>

          <p className="mt-3 text-sm leading-relaxed">{step.why_required}</p>

          {step.prerequisites.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground">After:</span>
              {step.prerequisites.map((p) => (
                <a key={p} href={`#step-${p.replace(/[^a-z0-9]/gi, "-")}`} className="rounded-full border border-border bg-background px-2 py-0.5 text-xs hover:border-ink/40">
                  {nameById.get(p) ?? p}
                </a>
              ))}
            </div>
          )}

          {step.stall_risk && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-estimated/40 bg-estimated-soft p-3 text-sm">
              <AlertOctagon className="mt-0.5 size-4 shrink-0 text-estimated" aria-hidden />
              <p>
                <span className="font-semibold">Stall risk. </span>
                {step.stall_risk}
              </p>
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            <a
              href={step.application_url}
              target="_blank"
              rel="noopener noreferrer"
              className={cn("inline-flex items-center gap-1 underline underline-offset-4", step.url_status === "dead" ? "text-dead" : "text-ink")}
            >
              Application page <ExternalLink className="size-3.5" aria-hidden />
            </a>
            {step.url_status === "dead" && (
              <span className="break-all font-mono text-xs text-muted-foreground">{step.application_url}</span>
            )}
            {step.notes && (
              <button type="button" onClick={() => setOpen((o) => !o)} className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground" aria-expanded={open}>
                <Info className="size-3.5" aria-hidden /> Notes <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} aria-hidden />
              </button>
            )}
          </div>
          {open && step.notes && <p className="mt-2 whitespace-pre-wrap rounded-lg bg-muted p-3 text-sm text-foreground/85">{step.notes}</p>}
        </div>
      </div>
    </li>
  );
}
