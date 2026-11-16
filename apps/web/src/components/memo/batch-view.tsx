"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Download, Loader2, RefreshCw } from "lucide-react";
import { useApp } from "@/components/app/app-context";
import { EarlierFormatTag, StatusPill } from "@/components/memo/status-pill";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, describeApiError, isApiError } from "@/lib/api";
import { formatDate, statusLabel } from "@/lib/format";
import { csvEscape, STATUS_DISPLAY_ORDER } from "@/lib/memo";
import type { MemoSummary } from "@/lib/api-types";

const POLL_MS = 5000;

function exportCsv(batchId: string, memos: MemoSummary[]) {
  const lines = [
    ["address", "concept", "status", "overall_status", "comparable_count", "memo_url"].join(","),
    ...memos.map((m) =>
      [m.address, m.concept, m.status, m.legacy_format ? "earlier_format" : (m.overall_status ?? ""), m.comparable_count ?? "", `${window.location.origin}/app/memos/${m.id}`].map((v) => csvEscape(String(v))).join(","),
    ),
  ];
  const blob = new Blob([lines.join("\n") + "\n"], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `permit-memo-batch-${batchId.slice(0, 8)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** `/app/memos/bulk/[batchId]`: polls `GET /v1/memos/bulk/{batch_id}` every 5 s until every memo settles. */
export function BatchView({ batchId }: { batchId: string }) {
  const { accessToken } = useApp();
  const [memos, setMemos] = useState<MemoSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [lastPolled, setLastPolled] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.bulkBatch(accessToken, batchId);
      setMemos(res.memos);
      setError(null);
      setLastPolled(new Date());
    } catch (err) {
      if (isApiError(err) && err.status === 404) setNotFound(true);
      else setError(describeApiError(err));
    }
  }, [accessToken, batchId]);

  useEffect(() => {
    void load();
  }, [load]);

  const pending = memos?.filter((m) => m.status === "generating" || m.status === "pending_clarification").length ?? 0;

  useEffect(() => {
    if (memos === null || pending === 0 || notFound) return;
    const t = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(t);
  }, [memos, pending, notFound, load]);

  if (notFound) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-10 text-center">
        <h1 className="text-xl font-semibold">Batch not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">It may belong to another account, or the upload never completed.</p>
        <Button asChild className="mt-5">
          <Link href="/app/memos/bulk">Upload a CSV</Link>
        </Button>
      </div>
    );
  }

  const total = memos?.length ?? 0;
  const done = total - pending;
  const byStatus = (memos ?? []).reduce<Record<string, number>>((acc, m) => {
    if (m.overall_status && !m.legacy_format) acc[m.overall_status] = (acc[m.overall_status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link href="/app/memos" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-3.5" aria-hidden /> All memos
          </Link>
          <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">
            Batch <span className="font-mono text-xl text-muted-foreground">{batchId.slice(0, 8)}</span>
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            {memos === null ? (
              "Loading…"
            ) : pending > 0 ? (
              <>
                <Loader2 className="size-3.5 animate-spin text-signal" aria-hidden />
                {done} of {total} finished · refreshing every 5 seconds
              </>
            ) : (
              `${total} memo${total === 1 ? "" : "s"} · all finished`
            )}
            {lastPolled && <span className="font-mono text-xs">· checked {lastPolled.toLocaleTimeString("en-US")}</span>}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={() => void load()}>
            <RefreshCw /> Refresh
          </Button>
          <Button type="button" variant="outline" onClick={() => memos && exportCsv(batchId, memos)} disabled={!memos || memos.length === 0}>
            <Download /> Export CSV
          </Button>
        </div>
      </header>

      {total > 0 && (
        <div className="flex flex-wrap gap-2" aria-label="Overall status summary">
          {STATUS_DISPLAY_ORDER.map((v) => (
            <span key={v} className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-sm">
              <StatusPill status={v} size="sm" /> <span className="font-mono tabular">{byStatus[v] ?? 0}</span>
            </span>
          ))}
          {pending > 0 && (
            <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-sm">
              <Loader2 className="size-3.5 animate-spin text-signal" aria-hidden /> {pending} in progress
            </span>
          )}
        </div>
      )}

      {error && (
        <div role="alert" className="rounded-lg border border-dead/30 bg-dead-soft p-4 text-sm text-dead">
          {error}
        </div>
      )}

      {memos === null && !error && <Skeleton className="h-64 rounded-xl" />}

      {memos && (
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <table className="w-full min-w-[820px] text-sm" data-testid="batch-table">
            <thead>
              <tr className="border-b border-border bg-paper-deep/50 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2.5">#</th>
                <th className="px-3 py-2.5">Address</th>
                <th className="px-3 py-2.5">Concept</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">Overall status</th>
                <th className="px-3 py-2.5 text-right">Comparables</th>
                <th className="px-3 py-2.5">Created</th>
                <th className="px-3 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {memos.map((m, i) => (
                <tr key={m.id} className="border-b border-border align-top last:border-b-0">
                  <td className="px-3 py-3 font-mono text-xs text-muted-foreground tabular">{i + 1}</td>
                  <td className="px-3 py-3 font-medium">{m.address}</td>
                  <td className="max-w-xs px-3 py-3 text-muted-foreground">{m.concept}</td>
                  <td className="px-3 py-3">
                    <Badge
                      variant="outline"
                      className={
                        m.status === "ready"
                          ? "border-verified/30 bg-verified-soft text-verified"
                          : m.status === "failed"
                            ? "border-dead/30 bg-dead-soft text-dead"
                            : "border-estimated/40 bg-estimated-soft text-estimated"
                      }
                    >
                      {(m.status === "generating" || m.status === "pending_clarification") && <Loader2 className="size-3 animate-spin" aria-hidden />}
                      {statusLabel(m.status)}
                    </Badge>
                  </td>
                  <td className="px-3 py-3">{m.legacy_format ? <EarlierFormatTag /> : m.overall_status ? <StatusPill status={m.overall_status} size="sm" /> : <span className="text-xs text-muted-foreground">—</span>}</td>
                  <td className="px-3 py-3 text-right font-mono text-xs tabular">{m.comparable_count ?? "—"}</td>
                  <td className="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground">{formatDate(m.created_at)}</td>
                  <td className="px-3 py-3 text-right">
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/app/memos/${m.id}`}>Open</Link>
                    </Button>
                  </td>
                </tr>
              ))}
              {memos.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-3 py-8 text-center text-sm text-muted-foreground">
                    No memos in this batch. Every row may have been skipped; check the CSV header and try again.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
