import type { Metadata } from "next";
import { SiteFooter } from "@/components/site/site-footer";
import { SiteHeader } from "@/components/site/site-header";
import { APP_NAME } from "@/lib/brand";
import { env } from "@/lib/env";

export const metadata: Metadata = { title: "Terms" };

export default function TermsPage() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-signal">Terms</p>
        <h1 className="mt-2 text-3xl font-semibold">Terms of service</h1>
        <p className="mt-2 text-sm text-muted-foreground">Last updated October 2026</p>
        <div className="mt-8 space-y-6 text-[15px] leading-relaxed text-foreground/90">
          <section>
            <h2 className="text-lg font-semibold">Not legal advice</h2>
            <p className="mt-2">
              {APP_NAME} is a planning tool. Plans are generated from a maintained catalog of agency requirements
              and a model&apos;s reading of your description. They can be incomplete or out of date. Always confirm
              requirements, fees and timelines with the issuing agency or a licensed professional before relying on
              them. Items marked Estimated have not been confirmed against the agency page.
            </p>
          </section>
          <section>
            <h2 className="text-lg font-semibold">Your account and plans</h2>
            <p className="mt-2">
              Every account includes three free plans. Additional plans are available as a one-off purchase or a
              monthly subscription, billed through Stripe. Reruns and clarifications of an existing plan are free.
              Subscriptions can be cancelled at any time from the billing page and remain active until the end of
              the paid period.
            </p>
          </section>
          <section>
            <h2 className="text-lg font-semibold">Acceptable use</h2>
            <p className="mt-2">
              Use {APP_NAME} for planning hospitality businesses you operate or advise. Do not scrape, resell or
              bulk-generate plans, or attempt to circumvent the free-plan limit.
            </p>
          </section>
          <section>
            <h2 className="text-lg font-semibold">Liability</h2>
            <p className="mt-2">
              To the fullest extent permitted by law, {APP_NAME} is provided as-is and our total liability for any
              claim is limited to the amount you paid us in the twelve months before the claim.
              {env.contactEmail ? (
                <>
                  {" "}Questions:{" "}
                  <a className="underline" href={`mailto:${env.contactEmail}`}>{env.contactEmail}</a>.
                </>
              ) : null}
            </p>
          </section>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
