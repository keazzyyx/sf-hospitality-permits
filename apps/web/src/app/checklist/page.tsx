import type { Metadata } from "next";
import Link from "next/link";
import { BadgeCheck, LinkIcon, ListChecks, MapPin, MessageSquareText, Scale, Waypoints } from "lucide-react";
import { HeroPlanner } from "@/components/landing/hero-planner";
import { LeadCapture } from "@/components/landing/lead-capture";
import { SiteFooter } from "@/components/site/site-footer";
import { SiteHeader } from "@/components/site/site-header";
import { APP_NAME } from "@/lib/brand";
import { SUPPORTED_CITIES } from "@/lib/catalog";

export const metadata: Metadata = {
  title: "Free permit checklist — every permit, in the right order, with a week-by-week plan to opening day",
  description:
    "Describe your restaurant, bar, cafe, food truck or hotel and get every permit that applies, sequenced into a week-by-week plan. Free, no card.",
};

const STEPS = [
  {
    icon: MessageSquareText,
    title: "Describe the business",
    body: "One paragraph: concept, city, seats, kitchen, alcohol, hours, music, patio. We ask a question or two only when the answer changes which permits apply.",
  },
  {
    icon: ListChecks,
    title: "Get every permit that applies",
    body: "Federal, state, county and city requirements matched to your profile from a maintained catalog, each with the agency, fee range, timeline and why it applies to you.",
  },
  {
    icon: Waypoints,
    title: "Follow the critical path",
    body: "Dependencies resolved into parallel tracks, a Gantt timeline, week-by-week actions, the blockers that usually stall openings, and a PDF for your lender or landlord.",
  },
];

const TRUST = [
  {
    icon: BadgeCheck,
    title: "A confidence badge on every item",
    body: "Verified means we confirmed the fee, timeline and link on the agency page. Estimated means it is inferred and you should double-check it.",
  },
  {
    icon: LinkIcon,
    title: "We check that every application link is live",
    body: "Agency sites move constantly. Each plan re-checks the application URLs and flags any that no longer resolve.",
  },
  {
    icon: Scale,
    title: "Not legal advice",
    body: `${APP_NAME} is a planning tool. Confirm requirements with the issuing agency or a licensed professional before you commit money.`,
  },
];

export default function ChecklistPage() {
  return (
    <>
      <SiteHeader />
      <main id="main">
        <section id="build" className="paper-grid scroll-mt-20 border-b border-border">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 pb-16 pt-14 sm:px-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:items-start lg:gap-14 lg:pb-24 lg:pt-20">
            <div className="max-w-xl lg:sticky lg:top-24">
              <p className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-xs font-medium text-muted-foreground">
                <span className="size-1.5 rounded-full bg-signal" aria-hidden />
                Free tier · for restaurants, bars, cafes, food trucks and hotels
              </p>
              <h1 className="mt-5 text-4xl font-semibold leading-[1.05] sm:text-5xl lg:text-[3.4rem]">
                Every permit, in the right order, with a week-by-week plan to opening day.
              </h1>
              <p className="mt-5 text-lg leading-relaxed text-muted-foreground">
                Describe what you are opening. {APP_NAME} works out which licenses apply, what has to happen before
                what, how long each one takes, what it costs, and what is most likely to stall you.
              </p>
              <p className="mt-4 text-sm text-muted-foreground">
                Already have an address in San Francisco?{" "}
                <Link href="/" className="font-medium text-signal underline-offset-2 hover:underline">
                  Get a Location Risk Memo
                </Link>
                : every approval your concept needs at that address, with the rules and records behind each, and
                what&apos;s still unknown.
              </p>
              <dl className="mt-8 grid grid-cols-3 gap-4 border-t border-border pt-6">
                <div>
                  <dt className="text-xs text-muted-foreground">Cities with verified catalogs</dt>
                  <dd className="mt-1 font-display text-2xl font-semibold tabular">{SUPPORTED_CITIES.length}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Free plans per account</dt>
                  <dd className="mt-1 font-display text-2xl font-semibold tabular">3</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Time to a first preview</dt>
                  <dd className="mt-1 font-display text-2xl font-semibold tabular">~1 min</dd>
                </div>
              </dl>
            </div>
            <HeroPlanner />
          </div>
        </section>

        <section id="how-it-works" className="scroll-mt-20 border-b border-border">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
            <div className="max-w-2xl">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-signal">How it works</p>
              <h2 className="mt-2 text-3xl font-semibold sm:text-4xl">From a paragraph to a sequenced plan</h2>
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

        <section id="cities" className="scroll-mt-20 border-b border-border bg-paper-deep/50">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:py-20">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-signal">Supported cities</p>
              <h2 className="mt-2 text-3xl font-semibold sm:text-4xl">Verified catalogs in {SUPPORTED_CITIES.length} cities</h2>
              <p className="mt-3 max-w-lg text-muted-foreground">
                Each city catalog is checked against the issuing agencies and dated. Anywhere else gets a generic
                federal + state + typical-city checklist marked Estimated.
              </p>
              <ul className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-2 xl:grid-cols-3">
                {SUPPORTED_CITIES.map((c) => (
                  <li key={c.slug} className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm">
                    <MapPin className="size-3.5 text-signal" aria-hidden />
                    <span className="font-medium">{c.name}</span>
                    <span className="ml-auto font-mono text-xs text-muted-foreground">{c.state}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-2xl border border-border bg-card p-6 lg:self-start">
              <h3 className="text-lg font-semibold">Not on the list yet?</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Leave your email and city. We add cities by demand and will tell you the day yours is verified.
              </p>
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
