"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, CalendarCheck2, MapPin, Plus, RefreshCw } from "lucide-react";
import { useApp } from "@/components/app/app-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { api, describeApiError } from "@/lib/api";
import { formatDate, statusLabel } from "@/lib/format";
import { readPendingPreview } from "@/lib/pending-preview";
import type { PlanSummary } from "@/lib/api-types";

function StatusBadge({ status }: { status: PlanSummary["status"] }) {
  const cls =
    status === "ready"
      ? "border-verified/30 bg-verified-soft text-verified"
      : status === "failed"
        ? "border-dead/30 bg-dead-soft text-dead"
        : "border-estimated/40 bg-estimated-soft text-estimated";
  return (
    <Badge variant="outline" className={cls}>
      {statusLabel(status)}
    </Badge>
  );
}

export function PlansList() {
  const { accessToken, me } = useApp();
  const router = useRouter();
  const [plans, setPlans] = useState<PlanSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // A preview run before sign-up is waiting: build it straight away.
    if (readPendingPreview()) router.replace("/app/new");
  }, [router]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const { plans: list } = await api.plans(accessToken);
      setPlans(list);
    } catch (err) {
      setError(describeApiError(err));
    }
  }, [accessToken]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold sm:text-3xl">Permit checklists</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {me
              ? me.is_admin
                ? "Owner account: unlimited checklists."
                : me.entitlement.kind === "subscription"
                ? "Unlimited checklists on your subscription."
                : `${me.free_plans_remaining} free checklist${me.free_plans_remaining === 1 ? "" : "s"} remaining${me.entitlement.plan_credits > 0 ? ` plus ${me.entitlement.plan_credits} credit${me.entitlement.plan_credits === 1 ? "" : "s"}` : ""}.`
              : "The free tier: every permit that applies, sequenced into a week-by-week plan."}
          </p>
        </div>
        <Button asChild>
          <Link href="/app/new">
            <Plus /> New checklist
          </Link>
        </Button>
      </div>

      {error && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dead/30 bg-dead-soft p-4 text-sm text-dead">
          <span>{error}</span>
          <Button variant="outline" size="sm" onClick={load} className="border-dead/40 text-dead hover:bg-dead/10">
            <RefreshCw /> Retry
          </Button>
        </div>
      )}

      {plans === null && !error && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy>
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-44 rounded-xl" />
          ))}
        </div>
      )}

      {plans && plans.length === 0 && (
        <div className="paper-grid rounded-2xl border border-dashed border-border p-10 text-center">
          <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-ink text-paper" aria-hidden>
            <CalendarCheck2 className="size-6" />
          </span>
          <h2 className="mt-5 text-xl font-semibold">No checklists yet</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            Describe the business you are opening and get every permit sequenced into a week-by-week plan. Your first
            three are free.
          </p>
          <Button asChild size="lg" className="mt-6">
            <Link href="/app/new">
              Build my first checklist <ArrowRight />
            </Link>
          </Button>
        </div>
      )}

      {plans && plans.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {plans.map((p) => {
            const pct = p.steps_total > 0 ? Math.round((p.steps_done / p.steps_total) * 100) : 0;
            return (
              <li key={p.id}>
                <Link
                  href={`/app/plans/${p.id}`}
                  className="group flex h-full flex-col rounded-xl border border-border bg-card p-5 transition-all hover:-translate-y-0.5 hover:border-ink/40 hover:shadow-md focus-visible:ring-[3px] focus-visible:ring-ring/50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <h2 className="line-clamp-2 font-semibold leading-snug">{p.title}</h2>
                    <StatusBadge status={p.status} />
                  </div>
                  <p className="mt-1.5 flex items-center gap-1.5 text-sm text-muted-foreground">
                    <MapPin className="size-3.5" aria-hidden />
                    {p.city_name ?? "City not detected"}
                    <span aria-hidden>·</span>
                    <span className="font-mono text-xs">v{p.version}</span>
                  </p>
                  <div className="mt-5 space-y-1.5">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>
                        {p.steps_done}/{p.steps_total} steps done
                      </span>
                      <span className="tabular">{pct}%</span>
                    </div>
                    <Progress value={pct} aria-label={`${pct}% of steps complete`} />
                  </div>
                  <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-border pt-3 text-xs">
                    <div>
                      <dt className="text-muted-foreground">Projected open</dt>
                      <dd className="mt-0.5 font-medium">{formatDate(p.projected_open_date)}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Target</dt>
                      <dd className="mt-0.5 font-medium">{formatDate(p.target_open_date)}</dd>
                    </div>
                  </dl>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
