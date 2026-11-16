"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, Download, FileSpreadsheet, Loader2, Lock, Upload } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/components/app/app-context";
import { isPro } from "@/components/memo/memo-view";
import { Button } from "@/components/ui/button";
import { api, describeApiError, isApiError } from "@/lib/api";
import { capture } from "@/lib/analytics";
import { BULK_MAX_ROWS, bulkTemplateCsv, parseBulkCsv, type ParsedCsv } from "@/lib/memo";

function downloadTemplate() {
  const blob = new Blob([bulkTemplateCsv()], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "permit-memo-bulk-memos-template.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function ProUpsell({ title = "Bulk upload is part of Pro" }: { title?: string }) {
  return (
    <section className="relative overflow-hidden rounded-2xl border border-ink bg-ink p-6 text-paper sm:p-8" data-testid="pro-upsell">
      <div className="absolute -right-12 -top-12 size-48 rounded-full bg-signal/25 blur-3xl" aria-hidden />
      <div className="relative max-w-2xl">
        <p className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-signal">
          <Lock className="size-3.5" aria-hidden /> Pro · $299 per month
        </p>
        <h2 className="mt-1 text-xl font-semibold sm:text-2xl">{title}</h2>
        <p className="mt-2 text-sm text-paper/75">
          Upload a CSV of up to {BULK_MAX_ROWS} addresses with a concept for each and get a report on every site in one batch, unlocked in full. Built for brokers and expediters shortlisting space.
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Button asChild size="lg" className="bg-signal text-white hover:bg-signal/90">
            <Link href="/app/billing">Start Pro</Link>
          </Button>
          <Button type="button" variant="ghost" className="text-paper/80 hover:bg-paper/10 hover:text-paper" onClick={downloadTemplate}>
            <Download /> Download the CSV template
          </Button>
        </div>
      </div>
    </section>
  );
}

/** `/app/memos/bulk`: CSV upload (`address,description`, max 25 rows) → `POST /v1/memos/bulk` → batch page. */
export function BulkUpload() {
  const { accessToken, me, meLoading } = useApp();
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<ParsedCsv | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  if (!meLoading && me && !isPro(me)) {
    return (
      <div className="space-y-6">
        <header>
          <h1 className="text-2xl font-semibold sm:text-3xl">Bulk upload</h1>
          <p className="mt-1 text-sm text-muted-foreground">Check up to {BULK_MAX_ROWS} addresses at once.</p>
        </header>
        <ProUpsell />
      </div>
    );
  }

  async function pick(f: File | null) {
    setError(null);
    setFile(f);
    if (!f) {
      setParsed(null);
      return;
    }
    if (f.size > 1_000_000) {
      setParsed(null);
      setError("That file is larger than 1 MB. A 25-row CSV should be a few kilobytes.");
      return;
    }
    const text = await f.text();
    setParsed(parseBulkCsv(text));
  }

  async function upload() {
    if (!file || !parsed || parsed.rows.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.bulkUpload(accessToken, file);
      capture("bulk_uploaded", { batch_id: res.batch_id, rows: parsed.rows.length, created: res.memo_ids.length, skipped: res.skipped.length });
      toast.success(`${res.memo_ids.length} memo${res.memo_ids.length === 1 ? "" : "s"} queued`, {
        description: res.skipped.length > 0 ? `${res.skipped.length} row${res.skipped.length === 1 ? "" : "s"} skipped. Details on the batch page.` : "Each memo's overall status appears on the batch page as it finishes.",
      });
      router.push(`/app/memos/bulk/${encodeURIComponent(res.batch_id)}`);
    } catch (err) {
      setBusy(false);
      if (isApiError(err) && err.code === "pro_required") setError(describeApiError(err));
      else setError(describeApiError(err));
    }
  }

  const rowsOk = parsed ? parsed.rows.filter((r) => r.address && r.description).length : 0;
  const canUpload = Boolean(file && parsed && rowsOk > 0 && parsed.problems.every((p) => !p.startsWith("The first line")) && !busy);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold sm:text-3xl">Bulk upload</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            A CSV with the header <code className="rounded bg-muted px-1 font-mono text-xs">address,description</code>, one site per row, up to {BULK_MAX_ROWS} rows. Every memo in the batch is unlocked in full on Pro.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={downloadTemplate} data-testid="download-template">
          <Download /> CSV template
        </Button>
      </header>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void pick(e.dataTransfer.files?.[0] ?? null);
        }}
        className={`rounded-2xl border-2 border-dashed p-8 text-center transition-colors ${dragging ? "border-signal bg-signal-soft/50" : "border-border bg-card"}`}
      >
        <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-ink text-paper" aria-hidden>
          <FileSpreadsheet className="size-6" />
        </span>
        <p className="mt-4 font-medium">{file ? file.name : "Drop your CSV here"}</p>
        <p className="mt-1 text-sm text-muted-foreground">{file ? `${(file.size / 1024).toFixed(1)} KB` : "or choose a file from your computer"}</p>
        <input ref={inputRef} type="file" accept=".csv,text/csv" className="sr-only" id="bulk-file" onChange={(e) => void pick(e.target.files?.[0] ?? null)} />
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <Button type="button" variant="outline" onClick={() => inputRef.current?.click()}>
            <Upload /> {file ? "Choose a different file" : "Choose file"}
          </Button>
          {file && (
            <Button type="button" variant="ghost" onClick={() => void pick(null)}>
              Clear
            </Button>
          )}
        </div>
      </div>

      {parsed && (
        <section className="space-y-3" aria-label="Upload preview">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm">
              <span className="font-semibold">{rowsOk}</span> of {parsed.rows.length} row{parsed.rows.length === 1 ? "" : "s"} ready
              {parsed.rows.length > BULK_MAX_ROWS ? ` (first ${BULK_MAX_ROWS} will be processed)` : ""}
            </p>
            <Button type="button" onClick={upload} disabled={!canUpload} data-testid="bulk-submit">
              {busy ? <Loader2 className="animate-spin" /> : <Upload />} Queue {Math.min(rowsOk, BULK_MAX_ROWS)} memo{Math.min(rowsOk, BULK_MAX_ROWS) === 1 ? "" : "s"}
            </Button>
          </div>
          {parsed.problems.length > 0 && (
            <ul className="space-y-1 rounded-lg border border-estimated/40 bg-estimated-soft p-3 text-xs text-foreground/85">
              {parsed.problems.map((p, i) => (
                <li key={i} className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-estimated" aria-hidden /> {p}
                </li>
              ))}
            </ul>
          )}
          {parsed.rows.length > 0 && (
            <div className="overflow-x-auto rounded-xl border border-border bg-card">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-paper-deep/50 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    <th className="px-3 py-2">#</th>
                    <th className="px-3 py-2">Address</th>
                    <th className="px-3 py-2">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {parsed.rows.slice(0, BULK_MAX_ROWS).map((r) => (
                    <tr key={r.line} className={`border-b border-border last:border-b-0 ${!r.address || !r.description ? "bg-dead-soft/50" : ""}`}>
                      <td className="px-3 py-2 font-mono text-xs text-muted-foreground tabular">{r.line - 1}</td>
                      <td className="px-3 py-2">{r.address || <span className="text-dead">missing</span>}</td>
                      <td className="px-3 py-2 text-muted-foreground">{r.description || <span className="text-dead">missing</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {error && (
        <p role="alert" className="flex items-start gap-2 rounded-lg border border-dead/30 bg-dead-soft p-3 text-sm text-dead">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {error}
        </p>
      )}
    </div>
  );
}
