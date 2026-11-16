"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { BadgeCheck, ExternalLink, Loader2, MapPinned, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/components/app/app-context";
import { UpgradeOptions } from "@/components/billing/upgrade-options";
import { MemoOffers, type MemoOfferMode } from "@/components/memo/memo-offers";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, describeApiError } from "@/lib/api";
import { capture } from "@/lib/analytics";
import { formatDate } from "@/lib/format";

export function BillingView() {
  const { accessToken, me, meLoading, refreshMe } = useApp();
  const params = useSearchParams();
  const router = useRouter();
  const [portalBusy, setPortalBusy] = useState(false);
  const [memoBusy, setMemoBusy] = useState<MemoOfferMode | null>(null);
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    const checkout = params.get("checkout");
    if (!checkout) return;
    handled.current = true;
    if (checkout === "success") {
      capture("upgrade", { mode: params.get("mode") ?? "unknown" });
      toast.success("Payment received", { description: "Your entitlement is updated. Build away." });
      void refreshMe();
    } else if (checkout === "cancelled") {
      toast.info("Checkout cancelled", { description: "No charge was made." });
    }
    router.replace("/app/billing");
  }, [params, refreshMe, router]);

  async function openPortal() {
    setPortalBusy(true);
    try {
      const { url } = await api.portal(accessToken, { return_url: `${window.location.origin}/app/billing` });
      window.location.assign(url);
    } catch (err) {
      setPortalBusy(false);
      toast.error("Could not open the billing portal", { description: describeApiError(err) });
    }
  }

  async function memoCheckout(mode: MemoOfferMode) {
    capture("memo_paywall_hit", { source: "billing", action: "checkout_click", mode });
    setMemoBusy(mode);
    try {
      const { url } = await api.checkout(accessToken, {
        mode,
        success_url: `${window.location.origin}/app/billing?checkout=success&mode=${mode}`,
        cancel_url: `${window.location.origin}/app/billing?checkout=cancelled`,
      });
      window.location.assign(url);
    } catch (err) {
      setMemoBusy(null);
      toast.error("Could not start checkout", { description: describeApiError(err) });
    }
  }

  const kind = me?.entitlement.kind;
  const pro = me?.pro_status === "active" || me?.pro_status === "trialing";
  const proLabel = me?.pro_status ? me.pro_status.replace(/_/g, " ") : "not active";

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold sm:text-3xl">Billing</h1>
        <p className="mt-1 text-sm text-muted-foreground">Location Risk Memos are $499 each or unlimited on Pro. Permit checklists stay free for your first three.</p>
      </header>

      <Card className="gap-3 rounded-2xl" aria-labelledby="memo-entitlement-title" data-testid="memo-entitlement">
        <CardHeader>
          <CardTitle id="memo-entitlement-title" className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            <MapPinned className="size-3.5" aria-hidden /> Location Risk Memos
          </CardTitle>
        </CardHeader>
        <CardContent>
          {meLoading && !me ? (
            <Skeleton className="h-16 w-full" />
          ) : me ? (
            <div className="flex flex-wrap items-end justify-between gap-4">
              <dl className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-3">
                <div>
                  <dt className="text-xs text-muted-foreground">Pro status</dt>
                  <dd className="mt-0.5 inline-flex items-center gap-1.5 font-display text-xl font-semibold capitalize">
                    {pro && <Sparkles className="size-4 text-signal" aria-hidden />}
                    {proLabel}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Memo credits</dt>
                  <dd className="mt-0.5 font-display text-xl font-semibold tabular">{me.memo_credits}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Free teasers left</dt>
                  <dd className="mt-0.5 font-display text-xl font-semibold tabular">{me.free_teasers_remaining}</dd>
                </div>
              </dl>
              {pro && (
                <Button variant="outline" onClick={openPortal} disabled={portalBusy}>
                  {portalBusy ? <Loader2 className="animate-spin" /> : <ExternalLink />}
                  Manage Pro
                </Button>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Could not load your memo entitlement. Refresh to try again.</p>
          )}
        </CardContent>
      </Card>

      {!pro && (
        <section aria-labelledby="memo-offers-title" className="space-y-4">
          <h2 id="memo-offers-title" className="text-base font-semibold">
            Memo offers
          </h2>
          <MemoOffers onSelect={(mode) => void memoCheckout(mode)} busy={memoBusy} />
        </section>
      )}

      <Card className="gap-3 rounded-2xl" aria-labelledby="entitlement-title">
        <CardHeader>
          <CardTitle id="entitlement-title" className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Permit checklists (free tier)
          </CardTitle>
        </CardHeader>
        <CardContent>
        {meLoading && !me ? (
          <Skeleton className="h-16 w-full" />
        ) : me ? (
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="inline-flex items-center gap-2 font-display text-2xl font-semibold">
                {kind === "subscription" ? (
                  <>
                    <BadgeCheck className="size-6 text-verified" aria-hidden /> Unlimited checklists
                  </>
                ) : kind === "credits" ? (
                  `${me.entitlement.plan_credits} checklist credit${me.entitlement.plan_credits === 1 ? "" : "s"}`
                ) : (
                  `${me.free_plans_remaining} of ${me.free_limit} free checklists left`
                )}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {me.plans_created} checklist{me.plans_created === 1 ? "" : "s"} created so far
                {kind === "subscription" && me.entitlement.current_period_end
                  ? ` · ${me.entitlement.subscription_status === "trialing" ? "trial ends" : "renews"} ${formatDate(me.entitlement.current_period_end)}`
                  : ""}
                {kind !== "subscription" && me.entitlement.plan_credits > 0 && kind !== "credits" ? ` · ${me.entitlement.plan_credits} credits banked` : ""}
              </p>
            </div>
            {(kind === "subscription" || me.entitlement.subscription_status) && (
              <Button variant="outline" onClick={openPortal} disabled={portalBusy}>
                {portalBusy ? <Loader2 className="animate-spin" /> : <ExternalLink />}
                Manage subscription
              </Button>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Could not load your entitlement. Refresh to try again.</p>
        )}
        </CardContent>
      </Card>

      {kind !== "subscription" && (
        <section aria-labelledby="upgrade-title" className="space-y-4">
          <h2 id="upgrade-title" className="text-base font-semibold">
            Checklist offers
          </h2>
          <UpgradeOptions source="billing" />
          <p className="text-xs text-muted-foreground">Payments are processed by Stripe. Prices in USD; taxes may apply at checkout.</p>
        </section>
      )}
    </div>
  );
}
