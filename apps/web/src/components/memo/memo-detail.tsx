"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { BadgeCheck, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/components/app/app-context";
import { isPro, MemoView } from "@/components/memo/memo-view";
import type { MemoOfferMode } from "@/components/memo/memo-offers";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnswerRound } from "@/hooks/use-answer-round";
import { api, describeApiError, isApiError } from "@/lib/api";
import { capture } from "@/lib/analytics";
import { isLegacyRecord, memoSlug, overallStatusOf } from "@/lib/memo";
import type { GeoJsonFeatureCollection, MemoRecord } from "@/lib/api-types";

/** Fetches `GET /v1/memos/{id}` (+ map.geojson when full) and wires unlock / checkout / export / delete into `MemoView`. */
export function MemoDetail({ id }: { id: string }) {
  const { accessToken, me, refreshMe } = useApp();
  const router = useRouter();
  const params = useSearchParams();
  const [record, setRecord] = useState<MemoRecord | null>(null);
  const [geojson, setGeojson] = useState<GeoJsonFeatureCollection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [unlocking, setUnlocking] = useState(false);
  const [checkoutBusy, setCheckoutBusy] = useState<MemoOfferMode | null>(null);
  const [exporting, setExporting] = useState(false);
  const [afterCheckout, setAfterCheckout] = useState(false);
  const teaserTracked = useRef(false);
  const checkoutHandled = useRef(false);
  // "Answer and run again": the same memo, free; the page stays (useAnswerRound)
  const answers = useAnswerRound({ token: accessToken, record, onRecord: setRecord });

  const load = useCallback(async () => {
    try {
      const { memo } = await api.memo(accessToken, id);
      setRecord(memo);
      setError(null);
      return memo;
    } catch (err) {
      if (isApiError(err) && err.status === 404) setNotFound(true);
      else setError(describeApiError(err));
      return null;
    }
  }, [accessToken, id]);

  useEffect(() => {
    void load();
  }, [load]);

  // Still generating server-side (e.g. opened from a bulk batch): poll until it settles.
  useEffect(() => {
    if (record?.status !== "generating") return;
    const t = setInterval(() => void load(), 4000);
    return () => clearInterval(t);
  }, [record?.status, load]);

  // Overlay polygons for the map (full access only).
  useEffect(() => {
    if (!record || record.access !== "full" || !record.memo || isLegacyRecord(record)) return;
    let cancelled = false;
    api
      .memoGeojson(accessToken, record.id)
      .then((fc) => {
        if (!cancelled) setGeojson(fc);
      })
      .catch(() => {
        // The map still renders the subject, rings and comparables without overlays.
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, record]);

  useEffect(() => {
    if (!record || record.status !== "ready" || teaserTracked.current) return;
    if (record.access === "teaser" && !isLegacyRecord(record)) {
      teaserTracked.current = true;
      capture("memo_teaser_viewed", {
        memo_id: record.id,
        overall_status: record.teaser?.overall_status ?? null,
        comparable_count: record.teaser?.comparable_count ?? null,
        approvals_count: record.teaser?.approvals_count ?? null,
        blockers_count: record.teaser?.blockers_count ?? null,
      });
    }
  }, [record]);

  const unlock = useCallback(async () => {
    setUnlocking(true);
    try {
      const { memo } = await api.unlockMemo(accessToken, id);
      setRecord(memo);
      capture("memo_unlocked", { memo_id: id, overall_status: overallStatusOf(memo), via: me?.is_admin ? "admin" : isPro(me) ? "pro" : "credit" });
      toast.success("Memo unlocked", { description: "The full memo, map and PDF export are now available." });
      void refreshMe();
    } catch (err) {
      if (isApiError(err) && err.isPaywall) {
        capture("memo_paywall_hit", { source: "unlock", memo_id: id });
        toast.error("No memo credit on this account", { description: "Buy a memo or start Pro to unlock it." });
        void refreshMe();
      } else {
        toast.error("Could not unlock", { description: describeApiError(err) });
      }
    } finally {
      setUnlocking(false);
      setAfterCheckout(false);
    }
  }, [accessToken, id, me, refreshMe]);

  // Returned from Stripe: refresh entitlement, then unlock automatically.
  useEffect(() => {
    if (checkoutHandled.current || !record) return;
    const checkout = params.get("checkout");
    if (!checkout) return;
    checkoutHandled.current = true;
    router.replace(`/app/memos/${encodeURIComponent(id)}`);
    if (checkout === "success") {
      capture("upgrade", { mode: params.get("mode") ?? "memo", memo_id: id });
      if (record.access === "teaser" && !isLegacyRecord(record)) {
        setAfterCheckout(true);
        void refreshMe().then(() => unlock());
      }
    } else if (checkout === "cancelled") {
      toast.info("Checkout cancelled", { description: "No charge was made. The teaser stays available." });
    }
  }, [params, record, id, router, refreshMe, unlock]);

  async function checkout(mode: MemoOfferMode) {
    capture("memo_paywall_hit", { source: "memo_page", action: "checkout_click", mode, memo_id: id });
    setCheckoutBusy(mode);
    try {
      const origin = window.location.origin;
      const { url } = await api.checkout(accessToken, {
        mode,
        success_url: `${origin}/app/memos/${encodeURIComponent(id)}?checkout=success&mode=${mode}`,
        cancel_url: `${origin}/app/memos/${encodeURIComponent(id)}?checkout=cancelled`,
      });
      window.location.assign(url);
    } catch (err) {
      setCheckoutBusy(null);
      toast.error("Could not start checkout", { description: describeApiError(err) });
    }
  }

  async function exportPdf() {
    if (!record) return;
    setExporting(true);
    try {
      const blob = await api.exportMemoPdf(accessToken, record.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `permit-memo-${memoSlug(record)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
      capture("memo_pdf_exported", { memo_id: record.id, overall_status: overallStatusOf(record) });
    } catch (err) {
      toast.error("Export failed", { description: describeApiError(err) });
    } finally {
      setExporting(false);
    }
  }

  async function remove() {
    try {
      await api.deleteMemo(accessToken, id);
      toast.success("Memo deleted");
      router.push("/app/memos");
      router.refresh();
    } catch (err) {
      toast.error("Could not delete", { description: describeApiError(err) });
    }
  }

  if (notFound) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-10 text-center">
        <h1 className="text-xl font-semibold">Memo not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">It may have been deleted, or the link belongs to another account.</p>
        <Button className="mt-5" onClick={() => router.push("/app/memos")}>
          Back to memos
        </Button>
      </div>
    );
  }

  if (error && !record) {
    return (
      <div role="alert" className="rounded-xl border border-dead/30 bg-dead-soft p-5 text-sm text-dead">
        <p className="font-semibold">Could not load this memo</p>
        <p className="mt-1">{error}</p>
        <Button variant="outline" size="sm" className="mt-3 border-dead/40 text-dead hover:bg-dead/10" onClick={() => void load()}>
          Retry
        </Button>
      </div>
    );
  }

  if (!record) {
    return (
      <div className="space-y-4" aria-busy>
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-9 w-96 max-w-full" />
        <Skeleton className="h-28" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <MemoView
      record={record}
      me={me}
      geojson={geojson}
      actions={{
        onUnlock: () => void unlock(),
        onCheckout: (mode) => void checkout(mode),
        onExportPdf: () => void exportPdf(),
        onDelete: remove,
        onAnswer: (given) => {
          capture("memo_answers_rerun", { memo_id: id, round: (record.answers_round ?? 0) + 1, answered: Object.keys(given).length });
          void answers.submit(given);
        },
      }}
      busy={{ unlock: unlocking, checkout: checkoutBusy, export: exporting, answer: answers.busy }}
      revisions={answers.revisions}
      answerError={answers.error}
      notice={
        afterCheckout ? (
          <div className="flex items-center gap-3 rounded-xl border border-verified/30 bg-verified-soft p-4 text-sm text-verified" role="status">
            {unlocking ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <BadgeCheck className="size-4" aria-hidden />}
            Payment received. Unlocking the full memo…
          </div>
        ) : null
      }
    />
  );
}
