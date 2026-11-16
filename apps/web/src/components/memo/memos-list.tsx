"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Layers, Lock, MapPinned, Plus, RefreshCw, Upload } from "lucide-react";
import { useApp } from "@/components/app/app-context";
import { isPro } from "@/components/memo/memo-view";
import { EarlierFormatTag, StatusPill } from "@/components/memo/status-pill";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, describeApiError } from "@/lib/api";
import { formatDate, statusLabel } from "@/lib/format";
import { readPendingMemo } from "@/lib/pending-memo";
import { readPendingPreview } from "@/lib/pending-preview";
import type { MemoSummary } from "@/lib/api-types";

export function MemoCard({ m }: { m: MemoSummary }) {
  return (
    <Link
      href={`/app/memos/${m.id}`}
      className="group flex h-full flex-col rounded-xl border border-border bg-card p-5 transition-all hover:-translate-y-0.5 hover:border-ink/40 hover:shadow-md focus-visible:ring-[3px] focus-visible:ring-ring/50"
      data-testid="memo-card"
    >
      <div className="flex items-start justify-between gap-3">
        <h2 className="line-clamp-2 font-semibold leading-snug">{m.address}</h2>
        {m.legacy_format ? (
          <EarlierFormatTag />
        ) : m.overall_status ? (
          <StatusPill status={m.overall_status} size="sm" />
        ) : (
          <Badge variant="outline" className={m.status === "failed" ? "border-dead/30 bg-dead-soft text-dead" : "border-estimated/40 bg-estimated-soft text-estimated"}>
            {statusLabel(m.status)}
          </Badge>
        )}
      </div>
      <p className="mt-1.5 line-clamp-2 text-sm text-muted-foreground">{m.concept}</p>
      <div className="mt-auto flex flex-wrap items-center gap-2 border-t border-border pt-3 text-xs text-muted-foreground">
        <Badge variant="outline" className={m.access === "full" ? "border-verified/30 bg-verified-soft text-verified" : "border-estimated/40 bg-estimated-soft text-estimated"}>
          {m.access === "full" ? "Full" : <><Lock className="size-3" aria-hidden /> Teaser</>}
        </Badge>
        {typeof m.comparable_count === "number" && <span>{m.comparable_count} comparable{m.comparable_count === 1 ? "" : "s"}</span>}
        {m.batch_id && (
          <span className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 font-mono text-[10px]">
            <Layers className="size-3" aria-hidden /> batch {m.batch_id.slice(0, 8)}
          </span>
        )}
        <span className="ml-auto">{formatDate(m.created_at)}</span>
      </div>
    </Link>
  );
}

export function MemosList() {
  const { accessToken, me } = useApp();
  const router = useRouter();
  const [memos, setMemos] = useState<MemoSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Inputs saved before sign-in are waiting: resume them straight away.
    if (readPendingMemo()) router.replace("/app/memo");
    else if (readPendingPreview()) router.replace("/app/new");
  }, [router]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const { memos: list } = await api.memos(accessToken);
      setMemos(list);
    } catch (err) {
      setError(describeApiError(err));
    }
  }, [accessToken]);

  useEffect(() => {
    void load();
  }, [load]);

  const pro = isPro(me);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold sm:text-3xl">Memos</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {me
              ? pro
                ? "Pro: unlimited memos, every one unlocked in full."
                : `${me.free_teasers_remaining} free ${me.free_teasers_remaining === 1 ? "teaser" : "teasers"} left${me.memo_credits > 0 ? ` · ${me.memo_credits} memo ${me.memo_credits === 1 ? "credit" : "credits"}` : ""}.`
              : "Each memo lists every approval your concept needs at an address, with the rules and records behind each, and what's still unknown."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link href="/app/memos/bulk">
              <Upload /> Bulk upload
            </Link>
          </Button>
          <Button asChild>
            <Link href="/app/memo">
              <Plus /> New memo
            </Link>
          </Button>
        </div>
      </div>

      {error && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dead/30 bg-dead-soft p-4 text-sm text-dead">
          <span>{error}</span>
          <Button variant="outline" size="sm" onClick={load} className="border-dead/40 text-dead hover:bg-dead/10">
            <RefreshCw /> Retry
          </Button>
        </div>
      )}

      {memos === null && !error && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy>
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-44 rounded-xl" />
          ))}
        </div>
      )}

      {memos && memos.length === 0 && (
        <div className="paper-grid rounded-2xl border border-dashed border-border p-10 text-center">
          <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-ink text-paper" aria-hidden>
            <MapPinned className="size-6" />
          </span>
          <h2 className="mt-5 text-xl font-semibold">No memos yet</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            Paste the address you are considering and the concept in one sentence. You get a status for each approval the concept needs, the evidence behind it and the comparable cases from the public record.
          </p>
          <Button asChild size="lg" className="mt-6">
            <Link href="/app/memo">
              Check my first address <ArrowRight />
            </Link>
          </Button>
        </div>
      )}

      {memos && memos.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {memos.map((m) => (
            <li key={m.id}>
              <MemoCard m={m} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
