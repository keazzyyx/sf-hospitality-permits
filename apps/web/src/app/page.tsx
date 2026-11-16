import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BadgeCheck, Check, Database, FileText, Gauge, ListChecks, MapPin, Scale, Search } from "lucide-react";
import { AddressHero } from "@/components/landing/address-hero";
import { LeadCapture } from "@/components/landing/lead-capture";
import { SampleMemoCard } from "@/components/landing/sample-memo-card";
import { SiteFooter } from "@/components/site/site-footer";
import { SiteHeader } from "@/components/site/site-header";
import { Button } from "@/components/ui/button";
import { APP_NAME } from "@/lib/brand";
import { SITE_CLAIM } from "@/lib/site-copy";

export const metadata: Metadata = {
  title: `${APP_NAME} — every approval your concept needs at an address`,
  description: SITE_CLAIM,
};

const STEPS = [
  {
    icon: Database,
    title: "Records",
    body: "We pull every Planning application, Entertainment Commission permit, ABC license and Planning Commission decision within 500 ft and 1,000 ft of the address, plus the zoning district and overlay rules at the parcel.",
  },
  {
    icon: Search,
    title: "Precedent",
    body: "Comparable cases are ranked by a fixed score: use, hours, distance, recency and whether the case was decided. Each one shows what the record says (its outcome, dates and the conditions on file) and links to the record.",
  },
  {
    icon: FileText,
    title: "Memo",
    body: "A status for each approval the concept needs, set by rules from the code and the records. Each status shows the rules applied with their code sections, the facts they read and where each came from, and what is not known. No sentence in the report is written by an AI model.",
  },
];

const MEMO_SECTIONS = [
  "Each approval you need, marked Allowed, Further review, Potential blocker, Not permitted or Insufficient information",
  "The rules applied to each approval, with the code section and a link to it",
  "The facts the rules read, each with where it came from, and what is not known",
  "The records on file at the address, with their uses, hours and conditions",
  "Comparable cases on a map and in a table, with outcomes, conditions and links",
  "Zoning, overlays and outcome counts, with every decision counted",
];

const TIERS = [
  {
    name: "Free",
    price: "$0",
    cadence: "",
    blurb: "See whether it is worth going further.",
    perks: ["Permit checklist for any US city", "Memo teaser: the overall status, its one-line reason, and how many approvals, blockers and comparable cases", "No card required"],
    cta: { label: "Check an address", href: "#check" },
  },
  {
    name: "Operator",
    price: "$499",
    cadence: "per memo",
    blurb: "One address you are about to commit to.",
    perks: ["The full memo, unlocked", "Comparable cases with decisions and a map", "Every rule and fact with its source, and what is still unknown", "PDF for your landlord, lender or attorney"],
    cta: { label: "Get a memo", href: "#check" },
    featured: true,
  },
  {
    name: "Pro",
    price: "$299",
    cadence: "per month",
    blurb: "Brokers and expediters comparing sites weekly.",
    perks: ["Unlimited memos", "Bulk CSV: up to 25 addresses per upload", "PDF export on every memo", "Cancel any time"],
    cta: { label: "Start Pro", href: "/login?next=%2Fapp%2Fbilling" },
  },
];

const TRUST = [
  {
    icon: BadgeCheck,
    title: "Every line points at its source",
    body: "Each rule line names its code section, and each fact from a record points at a Planning application, an ABC license or a Commission decision you can open yourself. What your description does not say is listed as not known, never guessed.",
  },
  {
    icon: Gauge,
    title: "Confidence is shown, not hidden",
    body: "Comparable cases carry a similarity score, and their outcomes are shown as counts with the sample size; a rate appears only when the sample is 10 or more, so you know how much weight the report deserves.",
  },
  {
    icon: Scale,
    title: "Not legal advice",
    body: "A memo is a research tool. Confirm with the Planning Department, the Entertainment Commission and ABC, or a licensed land-use attorney, before you sign.",
  },
];

export default function LandingPage() {
  return (
    <>
      <SiteHeader />
      <main id="main">
        <section id="check" className="paper-grid scroll-mt-20 border-b border-border">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 pb-16 pt-14 sm:px-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:items-start lg:gap-14 lg:pb-24 lg:pt-20">
            <div className="max-w-xl lg:sticky lg:top-24">
              <p className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-xs font-medium text-muted-foreground">
                <span className="size-1.5 rounded-full bg-signal" aria-hidden />
                Location Risk Memo · San Francisco bars, restaurants and cafes
              </p>
              <h1 className="mt-5 text-3xl font-semibold leading-[1.1] sm:text-4xl lg:text-[2.75rem]">{SITE_CLAIM}</h1>
              <p className="mt-5 text-lg leading-relaxed text-muted-foreground">
                A memo built from SF Planning, Entertainment Commission, ABC and Planning Commission records: a status
                for each approval, the rules that set it with their code sections, the facts they read and where each
                came from, the records on file at the address, comparable cases nearby, and the approvals to file, in
                order.
              </p>
              <div className="mt-6 flex flex-wrap items-center gap-3">
                <Button asChild variant="outline" size="lg">
                  <Link href="/checklist" data-testid="checklist-cta">
                    <ListChecks /> Just need the free permit checklist?
                  </Link>
                </Button>
              </div>
              <dl className="mt-8 grid grid-cols-3 gap-4 border-t border-border pt-6">
                <div>
                  <dt className="text-xs text-muted-foreground">Record sources</dt>
                  <dd className="mt-1 font-display text-2xl font-semibold tabular">4</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Search radius</dt>
                  <dd className="mt-1 font-display text-2xl font-semibold tabular">1,000 ft</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Time to a report</dt>
                  <dd className="mt-1 font-display text-2xl font-semibold tabular">~2 min</dd>
                </div>
              </dl>
            </div>
            <AddressHero />
          </div>
        </section>

        <section id="how-it-works" className="scroll-mt-20 border-b border-border">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
            <div className="max-w-2xl">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-signal">How it works</p>
              <h2 className="mt-2 text-3xl font-semibold sm:text-4xl">Records → precedent → memo</h2>
            </div>
            <ol className="mt-10 grid gap-6 md:grid-cols-3">
              {STEPS.map((s, i) => (
                <li key={s.title} className="relative rounded-2xl border border-border bg-card p-6">
                  <div className="flex items-center justify-between">
                    <span className="grid size-10 place-items-center rounded-xl bg-ink text-paper" aria-hidden>
                      <s.icon className="size-5" />
                    </span>
                    <span className="font-mono text-xs text-muted-foreground">0{i + 1}</span>
                  </div>
                  <h3 className="mt-5 text-lg font-semibold">{s.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{s.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="memo" className="scroll-mt-20 border-b border-border bg-paper-deep/50">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:items-start lg:py-20">
            <div className="lg:sticky lg:top-24">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-signal">What is in a memo</p>
              <h2 className="mt-2 text-3xl font-semibold sm:text-4xl">Each approval, with the rule and the record behind it</h2>
              <p className="mt-3 text-muted-foreground">
                The teaser shows the overall status and the counts for free. The full memo opens everything below, exports to
                PDF, and can be re-run as the concept changes.
              </p>
              <ul className="mt-6 space-y-2.5">
                {MEMO_SECTIONS.map((m) => (
                  <li key={m} className="flex items-start gap-2.5 text-sm">
                    <Check className="mt-0.5 size-4 shrink-0 text-verified" aria-hidden />
                    {m}
                  </li>
                ))}
              </ul>
            </div>
            <SampleMemoCard />
          </div>
        </section>

        <section id="pricing" className="scroll-mt-20 border-b border-border">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
            <div className="max-w-2xl">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-signal">Pricing</p>
              <h2 className="mt-2 text-3xl font-semibold sm:text-4xl">One memo per address, or unlimited on Pro</h2>
            </div>
            <div className="mt-10 grid gap-4 md:grid-cols-3" data-testid="pricing">
              {TIERS.map((t) => (
                <div key={t.name} className={`relative flex flex-col rounded-2xl border p-6 ${t.featured ? "border-ink bg-ink text-paper" : "border-border bg-card"}`}>
                  {t.featured && (
                    <span className="absolute -top-3 left-6 rounded-full bg-signal px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-white">
                      Most chosen
                    </span>
                  )}
                  <h3 className="text-lg font-semibold">{t.name}</h3>
                  <p className={`mt-1 text-sm ${t.featured ? "text-paper/70" : "text-muted-foreground"}`}>{t.blurb}</p>
                  <p className="mt-5 flex items-baseline gap-1.5">
                    <span className="font-display text-4xl font-semibold tabular">{t.price}</span>
                    {t.cadence && <span className={`text-sm ${t.featured ? "text-paper/70" : "text-muted-foreground"}`}>{t.cadence}</span>}
                  </p>
                  <ul className="mt-5 space-y-2 text-sm">
                    {t.perks.map((p) => (
                      <li key={p} className="flex items-start gap-2">
                        <Check className={`mt-0.5 size-4 shrink-0 ${t.featured ? "text-signal" : "text-verified"}`} aria-hidden />
                        {p}
                      </li>
                    ))}
                  </ul>
                  <Button asChild size="lg" variant={t.featured ? "default" : "outline"} className={`mt-6 w-full ${t.featured ? "bg-signal text-white hover:bg-signal/90" : ""}`}>
                    <Link href={t.cta.href}>
                      {t.cta.label} <ArrowRight />
                    </Link>
                  </Button>
                </div>
              ))}
            </div>
            <p className="mt-4 text-xs text-muted-foreground">Prices in USD, processed by Stripe. A memo credit never expires; Pro renews monthly and cancels from the billing page.</p>
          </div>
        </section>

        <section id="coverage" className="scroll-mt-20 border-b border-border bg-paper-deep/50">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:py-20">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-signal">Coverage</p>
              <h2 className="mt-2 text-3xl font-semibold sm:text-4xl">San Francisco now. Los Angeles and New York next.</h2>
              <p className="mt-3 max-w-lg text-muted-foreground">
                Memos need a decade of decisions, licenses and overlay boundaries in one place. San Francisco is live; the
                free permit checklist already covers cities across the US.
              </p>
              <ul className="mt-6 grid gap-2 sm:grid-cols-3">
                {[
                  { name: "San Francisco", state: "CA", status: "Live" },
                  { name: "Los Angeles", state: "CA", status: "Next" },
                  { name: "New York", state: "NY", status: "Next" },
                ].map((c) => (
                  <li key={c.name} className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm">
                    <MapPin className={`size-3.5 ${c.status === "Live" ? "text-verified" : "text-muted-foreground"}`} aria-hidden />
                    <span className="font-medium">{c.name}</span>
                    <span className="ml-auto font-mono text-xs text-muted-foreground">{c.status === "Live" ? c.state : c.status}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-2xl border border-border bg-card p-6 lg:self-start">
              <h3 className="text-lg font-semibold">Need another city?</h3>
              <p className="mt-1 text-sm text-muted-foreground">Leave your email and the city. We open cities by demand and will tell you the day yours is live.</p>
              <LeadCapture className="mt-5" />
            </div>
          </div>
        </section>

        <section className="border-b border-border">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
            <div className="grid gap-6 md:grid-cols-3">
              {TRUST.map((t) => (
                <div key={t.title} className="flex gap-4">
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-border bg-card text-ink" aria-hidden>
                    <t.icon className="size-5" />
                  </span>
                  <div>
                    <h3 className="font-semibold">{t.title}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{t.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
