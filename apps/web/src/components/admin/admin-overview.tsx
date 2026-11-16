"use client";

import { useCallback, useEffect, useState } from "react";
import { Database, Loader2, RefreshCw, ShieldOff } from "lucide-react";
import { cn } from "cn";
import { useApp } from "@/components/app/app-context";
import { APP_NAME } from "@/lib/brand";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, describeApiError, isApiError } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { STATUS_BAR_CLASSES, STATUS_LABELS, isApprovalStatus } from "@/lib/memo";
import type { AdminOverview } from "@/lib/api-types";

function fmtDateTime(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function ago(s: string | null | undefined): string {
  if (!s) return "";
  const ms = Date.now() - new Date(s).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "";
  const h = Math.floor(ms / 3_600_000);
  if (h < 1) return `${Math.max(1, Math.floor(ms / 60_000))} min ago`;
  if (h < 48) return `${h} h ago`;
  return `${Math.floor(h / 24)} d ago`;
}

function statusClass(status: string): string {
  const s = status.toLowerCase();
  if (s.includes("ok") || s.includes("success") || s.includes("done") || s.includes("complete")) return "border-verified/30 bg-verified-soft text-verified";
  if (s.includes("fail") || s.includes("error")) return "border-dead/30 bg-dead-soft text-dead";
  if (s.includes("run") || s.includes("progress")) return "border-estimated/40 bg-estimated-soft text-estimated";
  return "border-border bg-muted text-muted-foreground";
}

function Tile({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 font-display text-2xl font-semibold tabular">{typeof value === "number" ? value.toLocaleString("en-US") : value}</p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function CountTable({ title, counts, emptyLabel }: { title: string; counts: Record<string, number>; emptyLabel: string }) {
  const rows = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  return (
    <div className="rounded-xl border border-border bg-card">
      <p className="border-b border-border px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{title}</p>
      {rows.length === 0 ? (
        <p className="px-4 py-3 text-sm text-muted-foreground">{emptyLabel}</p>
      ) : (
        <table className="w-full text-sm">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k} className="border-b border-border last:border-b-0">
                <td className="px-4 py-1.5 font-mono text-xs">{k}</td>
                <td className="px-4 py-1.5 text-right font-mono text-xs tabular">{v.toLocaleString("en-US")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Bars({ title, counts, total, colorFor, labelFor }: { title: string; counts: Record<string, number>; total?: number; colorFor?: (key: string) => string; labelFor?: (key: string) => string | undefined }) {
  const rows = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const denom = total ?? rows.reduce((s, [, n]) => s + n, 0);
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{title}</p>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">Nothing yet.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {rows.map(([k, n]) => {
            const pct = denom > 0 ? Math.round((n / denom) * 100) : 0;
            return (
              <li key={k} className="grid grid-cols-[minmax(0,1fr)_3rem] items-center gap-3 text-sm">
                <div>
                  <div className="flex justify-between text-xs">
                    <span className="truncate">{labelFor?.(k) ?? titleCase(k)}</span>
                    <span className="font-mono tabular text-muted-foreground">{pct}%</span>
                  </div>
                  <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted">
                    <div className={cn("h-full rounded-full", colorFor ? colorFor(k) : "bg-ink")} style={{ width: `${pct}%` }} />
                  </div>
                </div>
                <span className="text-right font-mono text-xs tabular">{n}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** `/app/admin`: `GET /v1/admin/overview`. Dense and plain on purpose. */
export function AdminOverviewView() {
  const { accessToken } = useApp();
  const [data, setData] = useState<AdminOverview | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      setData(await api.adminOverview(accessToken));
      setError(null);
    } catch (err) {
      if (isApiError(err) && (err.status === 403 || err.code === "forbidden")) setForbidden(true);
      else setError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void load();
  }, [load]);

  if (forbidden) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-10 text-center" data-testid="admins-only">
        <ShieldOff className="mx-auto size-8 text-muted-foreground" aria-hidden />
        <h1 className="mt-4 text-xl font-semibold">Admins only</h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">This page shows ingestion and product health for the {APP_NAME} team. Your account is not on the admin list.</p>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div role="alert" className="rounded-xl border border-dead/30 bg-dead-soft p-5 text-sm text-dead">
        <p className="font-semibold">Could not load the overview</p>
        <p className="mt-1">{error}</p>
        <Button variant="outline" size="sm" className="mt-3 border-dead/40 text-dead hover:bg-dead/10" onClick={() => void load()}>
          Retry
        </Button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4" aria-busy>
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-40" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const runs = Object.entries(data.ingestion.last_runs).sort((a, b) => (b[1].started_at ?? "").localeCompare(a[1].started_at ?? ""));
  const tableCount = Object.values(data.ingestion.counts).reduce((s, n) => s + n, 0);

  return (
    <div className="space-y-8" data-testid="admin-overview">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold sm:text-3xl">Admin overview</h1>
          <p className="mt-1 inline-flex items-center gap-1.5 text-sm text-muted-foreground">
            <Database className="size-3.5" aria-hidden /> backend <code className="font-mono text-xs">{data.ingestion.backend}</code>
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => void load()} disabled={busy}>
          {busy ? <Loader2 className="animate-spin" /> : <RefreshCw />} Refresh
        </Button>
      </header>

      <section className="space-y-3" aria-labelledby="adm-ingest">
        <h2 id="adm-ingest" className="text-base font-semibold">
          Ingestion
        </h2>
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-border bg-paper-deep/50 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2">Source</th>
                <th className="px-3 py-2">Last run</th>
                <th className="px-3 py-2">Finished</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Fetched</th>
                <th className="px-3 py-2 text-right">Upserted</th>
                <th className="px-3 py-2">Error</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center text-muted-foreground">
                    No ingestion runs recorded yet.
                  </td>
                </tr>
              )}
              {runs.map(([source, r]) => (
                <tr key={source} className="border-b border-border align-top last:border-b-0">
                  <td className="px-3 py-2 font-mono text-xs">{source}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs">
                    {fmtDateTime(r.started_at)} <span className="text-muted-foreground">{ago(r.started_at)}</span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs">{fmtDateTime(r.finished_at)}</td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className={statusClass(r.status)}>
                      {r.status}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs tabular">{r.rows_fetched.toLocaleString("en-US")}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs tabular">{r.rows_upserted.toLocaleString("en-US")}</td>
                  <td className="max-w-xs px-3 py-2 font-mono text-[11px] text-dead">{r.error ?? <span className="text-muted-foreground">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <CountTable title={`Rows by table · ${tableCount.toLocaleString("en-US")} total`} counts={data.ingestion.counts} emptyLabel="No tables reported." />
          <CountTable title="Rows by source" counts={data.ingestion.by_source} emptyLabel="No sources reported." />
        </div>
      </section>

      <section className="space-y-3" aria-labelledby="adm-memos">
        <h2 id="adm-memos" className="text-base font-semibold">
          Memos
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Tile label="Total memos" value={data.memos.total} />
          <Tile label="Full (unlocked)" value={data.memos.full} hint={data.memos.total > 0 ? `${Math.round((data.memos.full / data.memos.total) * 100)}% of total` : undefined} />
          <Tile label="Teaser only" value={data.memos.teaser} />
          <Tile label="Last 7 days" value={data.memos.last_7_days} />
        </div>
        <Bars
          title="By overall status"
          counts={data.memos.by_overall_status ?? {}}
          labelFor={(k) => (isApprovalStatus(k) ? STATUS_LABELS[k] : undefined)}
          colorFor={(k) => (isApprovalStatus(k) ? STATUS_BAR_CLASSES[k] : "bg-ink")}
        />
      </section>

      <section className="space-y-3" aria-labelledby="adm-feedback">
        <h2 id="adm-feedback" className="text-base font-semibold">
          Feedback
        </h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <Tile label="Responses" value={data.feedback.total} />
          <Tile label="Emails sent" value={data.feedback.emails_sent} />
          <Tile label="Response rate" value={data.feedback.response_rate_pct === null ? "—" : `${data.feedback.response_rate_pct.toFixed(1)}%`} />
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <Bars
            title="By outcome"
            counts={data.feedback.by_outcome}
            colorFor={(k) => (k.includes("denied") ? "bg-dead" : k.includes("condition") ? "bg-estimated" : k.includes("approved") ? "bg-verified" : "bg-muted-foreground/60")}
          />
          <Bars title="By concept" counts={data.feedback.by_concept} />
        </div>
      </section>

      <section className="space-y-3" aria-labelledby="adm-users">
        <h2 id="adm-users" className="text-base font-semibold">
          Users
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Tile label="Total users" value={data.users.total} />
          <Tile label="Pro" value={data.users.pro} hint={data.users.total > 0 ? `${((data.users.pro / data.users.total) * 100).toFixed(1)}% of users` : undefined} />
        </div>
      </section>
    </div>
  );
}
