"use client";

import { Check, Loader2, Lock, Sparkles } from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";

export type MemoOfferMode = "memo" | "pro";

export const MEMO_OFFERS: {
  mode: MemoOfferMode;
  name: string;
  price: string;
  cadence: string;
  blurb: string;
  perks: string[];
  cta: string;
  featured?: boolean;
}[] = [
  {
    mode: "memo",
    name: "Operator",
    price: "$499",
    cadence: "per memo, one time",
    blurb: "For one address you are about to commit to. Buys one memo credit; unlock any memo with it.",
    perks: ["Full memo: each approval with its rules and the facts they read", "Comparables map and table, every record linked", "PDF export for your landlord, lender or attorney", "Re-run the same address as the concept changes"],
    cta: "Buy one memo · $499",
  },
  {
    mode: "pro",
    name: "Pro",
    price: "$299",
    cadence: "per month",
    blurb: "For brokers, expediters and multi-unit operators comparing sites every week.",
    perks: ["Unlimited memos, unlocked instantly", "Bulk CSV: up to 25 addresses per upload", "PDF export on every memo", "Cancel any time from the billing page"],
    cta: "Start Pro · $299/mo",
    featured: true,
  },
];

/**
 * The two memo offers (Operator $499 one-time, Pro $299/month). Pure: the parent decides what a
 * click does (Stripe Checkout, or an instant unlock when a credit or Pro is already there).
 */
export function MemoOffers({
  onSelect,
  busy,
  disabled,
  className,
  compact = false,
}: {
  onSelect: (mode: MemoOfferMode) => void;
  busy?: MemoOfferMode | null;
  disabled?: boolean;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div className={cn("grid gap-4 md:grid-cols-2", className)} data-testid="memo-offers">
      {MEMO_OFFERS.map((o) => (
        <div key={o.mode} className={cn("relative flex flex-col rounded-2xl border", compact ? "p-5" : "p-6", o.featured ? "border-ink bg-ink text-paper" : "border-border bg-card")}>
          {o.featured && (
            <span className="absolute -top-3 left-5 inline-flex items-center gap-1 rounded-full bg-signal px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-white">
              <Sparkles className="size-3" aria-hidden /> For teams
            </span>
          )}
          <h3 className="text-lg font-semibold">{o.name}</h3>
          <p className={cn("mt-1 text-sm", o.featured ? "text-paper/70" : "text-muted-foreground")}>{o.blurb}</p>
          <p className="mt-4 flex items-baseline gap-1.5">
            <span className={cn("font-display font-semibold tabular", compact ? "text-3xl" : "text-4xl")}>{o.price}</span>
            <span className={cn("text-sm", o.featured ? "text-paper/70" : "text-muted-foreground")}>{o.cadence}</span>
          </p>
          {!compact && (
            <ul className="mt-5 space-y-2 text-sm">
              {o.perks.map((p) => (
                <li key={p} className="flex items-start gap-2">
                  <Check className={cn("mt-0.5 size-4 shrink-0", o.featured ? "text-signal" : "text-verified")} aria-hidden />
                  {p}
                </li>
              ))}
            </ul>
          )}
          <Button
            type="button"
            size="lg"
            className={cn("mt-5 w-full", o.featured && "bg-signal text-white hover:bg-signal/90")}
            variant={o.featured ? "default" : "outline"}
            disabled={disabled || Boolean(busy)}
            onClick={() => onSelect(o.mode)}
            data-testid={`offer-${o.mode}`}
          >
            {busy === o.mode ? <Loader2 className="animate-spin" /> : <Lock />}
            {o.cta}
          </Button>
        </div>
      ))}
    </div>
  );
}
