"use client";

import Link from "next/link";
import { ArrowRight, Building2, CalendarRange, Lock, MapPinOff } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfidenceBadge } from "@/components/plan/confidence-badge";
import { LeadCapture } from "@/components/landing/lead-capture";
import { categoryLabel, groupBy, sortCategories } from "@/lib/catalog";
import { formatDaysRange, formatUsdRange, pluralize } from "@/lib/format";
import type { PreviewResult } from "@/lib/api-types";

export function PreviewResults({ preview, description }: { preview: PreviewResult; description: string }) {
  // The first `permit_count` permits apply; any after them are not determined (they depend on a fact the
  // description does not give, such as what alcohol will be served) and are listed apart, with their condition.
  const applying = preview.permits.slice(0, preview.permit_count);
  const notDetermined = preview.permits.slice(preview.permit_count);
  const groups = sortCategories(groupBy(applying, (p) => p.category));
  const verified = applying.filter((p) => p.confidence === "verified").length;
  const where = [preview.profile.city_name, preview.profile.state].filter(Boolean).join(", ");
  const loginHref = "/login?next=%2Fapp%2Fnew";

  return (
    <div className="space-y-6" data-testid="preview-results">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-signal">Preview</p>
          <h2 className="mt-1 text-2xl font-semibold sm:text-3xl">
            {pluralize(preview.permit_count, "permit")} for your {preview.profile.business_type.replace(/_/g, " ")}
            {where ? ` in ${where}` : ""}
          </h2>
          <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <CalendarRange className="size-4" aria-hidden />
              Roughly {formatDaysRange(preview.estimated_total_days)} on the longest chain
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Building2 className="size-4" aria-hidden />
              {verified} of {preview.permit_count} verified against agency pages
            </span>
          </p>
        </div>
      </div>

      {!preview.city_supported && (
        <div className="rounded-xl border border-estimated/40 bg-estimated-soft p-5">
          <div className="flex items-start gap-3">
            <MapPinOff className="mt-0.5 size-5 shrink-0 text-estimated" aria-hidden />
            <div className="space-y-3">
              <div>
                <p className="font-semibold text-foreground">We do not have a verified catalog for this city yet</p>
                <p className="mt-1 text-sm text-foreground/80">
                  {preview.unsupported_city_note ??
                    "This is a generic checklist built from federal, state and typical city requirements. Fees, timelines and links will need confirming with your local agencies."}
                </p>
              </div>
              <LeadCapture compact defaultCity={where} description={description} />
            </div>
          </div>
        </div>
      )}

      {preview.profile.assumptions.length > 0 && (
        <div className="rounded-lg border border-border bg-card/70 p-4 text-sm">
          <p className="mb-1.5 font-medium">What we assumed</p>
          <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
            {preview.profile.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}

      {notDetermined.length > 0 && (
        <div className="rounded-lg border border-estimated/40 bg-estimated-soft p-4 text-sm" data-testid="preview-not-determined">
          <p className="mb-1.5 font-medium">Not determined yet</p>
          <ul className="list-disc space-y-0.5 pl-5 text-foreground/80">
            {notDetermined.map((p) => (
              <li key={p.id}>
                <span className="font-medium text-foreground">{p.name}</span> ({p.issuing_agency}). {p.why_required}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-6">
        {groups.map((g) => (
          <section key={g.key} aria-labelledby={`cat-${g.key}`}>
            <h3 id={`cat-${g.key}`} className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              {categoryLabel(g.key)}
            </h3>
            <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
              {g.items.map((p) => (
                <li key={p.id} className="p-4 sm:p-5" data-testid="preview-permit">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-semibold leading-snug">{p.name}</p>
                      <p className="mt-0.5 text-sm text-muted-foreground">
                        {p.issuing_agency}
                        <Badge variant="outline" className="ml-2 align-middle text-[10px] uppercase">
                          {p.jurisdiction_level}
                        </Badge>
                      </p>
                    </div>
                    <ConfidenceBadge confidence={p.confidence} />
                  </div>
                  <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs text-muted-foreground tabular">
                    <div>
                      <dt className="inline">Timeline </dt>
                      <dd className="inline text-foreground">{formatDaysRange(p.typical_timeline_days)}</dd>
                    </div>
                    <div>
                      <dt className="inline">Fees </dt>
                      <dd className="inline text-foreground">{formatUsdRange(p.fee_range_usd)}</dd>
                    </div>
                  </dl>
                  <p className="mt-2 text-sm text-foreground/85">{p.why_required}</p>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <div className="relative overflow-hidden rounded-2xl ink-panel p-6 sm:p-8" data-testid="auth-gate">
        <div className="absolute -right-10 -top-10 size-40 rounded-full bg-signal/20 blur-3xl" aria-hidden />
        <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="max-w-xl space-y-2">
            <p className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-signal">
              <Lock className="size-3.5" aria-hidden /> Your full plan is ready
            </p>
            <h3 className="text-xl font-semibold text-paper sm:text-2xl">
              Critical path, week-by-week schedule, fees, blockers and a PDF — unlock it with a free account.
            </h3>
            <p className="text-sm text-paper/70">
              3 free plans. No password, no credit card. We keep this preview so you pick up exactly where you left off.
            </p>
          </div>
          <Button asChild size="lg" className="shrink-0 bg-signal text-white hover:bg-signal/90">
            <Link href={loginHref}>
              Create a free account <ArrowRight />
            </Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
