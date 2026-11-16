"use client";

import { Lock } from "lucide-react";
import { useApp } from "@/components/app/app-context";
import { UpgradeOptions } from "@/components/billing/upgrade-options";

export function PaywallCard({ plansCreated, freeLimit }: { plansCreated?: number; freeLimit?: number }) {
  const { me } = useApp();
  const created = plansCreated ?? me?.plans_created ?? 3;
  const limit = freeLimit ?? me?.free_limit ?? 3;
  return (
    <section className="space-y-6" data-testid="paywall">
      <div className="rounded-2xl border border-signal/30 bg-signal-soft p-5">
        <p className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-signal">
          <Lock className="size-3.5" aria-hidden /> Free plans used
        </p>
        <h2 className="mt-1 text-xl font-semibold">
          You have built {created} of {limit} free plans
        </h2>
        <p className="mt-1 text-sm text-foreground/80">
          Pick up where you left off: your description is kept and the plan starts the moment payment completes.
          Reruns and clarifications of existing plans stay free.
        </p>
      </div>
      <UpgradeOptions source="new_plan" />
    </section>
  );
}
