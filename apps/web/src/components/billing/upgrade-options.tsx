"use client";

import { useState } from "react";
import { Check, Loader2, Lock } from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { useApp } from "@/components/app/app-context";
import { Button } from "@/components/ui/button";
import { api, describeApiError } from "@/lib/api";
import { capture } from "@/lib/analytics";

type Mode = "plan" | "subscription";

const OPTIONS: { mode: Mode; name: string; price: string; cadence: string; blurb: string; perks: string[]; featured?: boolean }[] = [
  {
    mode: "plan",
    name: "One checklist",
    price: "$29",
    cadence: "one time",
    blurb: "For a single opening. One full permit checklist with unlimited reruns and clarifications.",
    perks: ["1 additional checklist credit", "Unlimited reruns of that checklist", "PDF export", "Checklist and timeline forever"],
  },
  {
    mode: "subscription",
    name: "Unlimited checklists",
    price: "$49",
    cadence: "per month",
    blurb: "For operators and consultants planning more than one opening.",
    perks: ["Unlimited permit checklists", "Unlimited reruns", "PDF export", "Cancel any time from the billing page"],
    featured: true,
  },
];

export function UpgradeOptions({ source, className }: { source: string; className?: string }) {
  const { accessToken } = useApp();
  const [busy, setBusy] = useState<Mode | null>(null);

  async function checkout(mode: Mode) {
    setBusy(mode);
    try {
      const origin = window.location.origin;
      const { url } = await api.checkout(accessToken, {
        mode,
        success_url: `${origin}/app/billing?checkout=success&mode=${mode}`,
        cancel_url: `${origin}/app/billing?checkout=cancelled`,
      });
      window.location.assign(url);
    } catch (err) {
      setBusy(null);
      toast.error("Could not start checkout", { description: describeApiError(err) });
    }
  }

  return (
    <div className={cn("grid gap-4 md:grid-cols-2", className)}>
      {OPTIONS.map((o) => (
        <div
          key={o.mode}
          className={cn(
            "relative flex flex-col rounded-2xl border p-6",
            o.featured ? "border-ink bg-ink text-paper" : "border-border bg-card",
          )}
        >
          {o.featured && (
            <span className="absolute -top-3 left-6 rounded-full bg-signal px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-white">
              Most flexible
            </span>
          )}
          <h3 className="text-lg font-semibold">{o.name}</h3>
          <p className={cn("mt-1 text-sm", o.featured ? "text-paper/70" : "text-muted-foreground")}>{o.blurb}</p>
          <p className="mt-5 flex items-baseline gap-1.5">
            <span className="font-display text-4xl font-semibold tabular">{o.price}</span>
            <span className={cn("text-sm", o.featured ? "text-paper/70" : "text-muted-foreground")}>{o.cadence}</span>
          </p>
          <ul className="mt-5 space-y-2 text-sm">
            {o.perks.map((p) => (
              <li key={p} className="flex items-start gap-2">
                <Check className={cn("mt-0.5 size-4 shrink-0", o.featured ? "text-signal" : "text-verified")} aria-hidden />
                {p}
              </li>
            ))}
          </ul>
          <Button
            type="button"
            size="lg"
            className={cn("mt-6 w-full", o.featured && "bg-signal text-white hover:bg-signal/90")}
            variant={o.featured ? "default" : "outline"}
            disabled={busy !== null}
            onClick={() => {
              capture("paywall_hit", { source, action: "checkout_click", mode: o.mode });
              void checkout(o.mode);
            }}
          >
            {busy === o.mode ? <Loader2 className="animate-spin" /> : <Lock />}
            {o.mode === "plan" ? "Buy one checklist" : "Start unlimited checklists"}
          </Button>
        </div>
      ))}
    </div>
  );
}
