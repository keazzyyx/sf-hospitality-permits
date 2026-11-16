import type { Metadata } from "next";
import { SiteFooter } from "@/components/site/site-footer";
import { SiteHeader } from "@/components/site/site-header";
import { env } from "@/lib/env";

export const metadata: Metadata = { title: "Privacy" };

export default function PrivacyPage() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-signal">Privacy</p>
        <h1 className="mt-2 text-3xl font-semibold">Privacy policy</h1>
        <p className="mt-2 text-sm text-muted-foreground">Last updated October 2026</p>
        <div className="mt-8 space-y-6 text-[15px] leading-relaxed text-foreground/90">
          <section>
            <h2 className="text-lg font-semibold">What we collect</h2>
            <p className="mt-2">
              Your email address (for sign-in), the business descriptions and answers you submit, the plans we
              generate for you, and which checklist steps you mark done. If you upgrade, Stripe processes your
              payment; we store only a customer reference and subscription status, never card numbers.
            </p>
          </section>
          <section>
            <h2 className="text-lg font-semibold">How we use it</h2>
            <p className="mt-2">
              To generate and store your permit plans, to send sign-in links, to improve the permit catalog (in
              aggregate, never attributed), and to understand product usage through privacy-respecting analytics.
              We do not sell personal data.
            </p>
          </section>
          <section>
            <h2 className="text-lg font-semibold">Who sees it</h2>
            <p className="mt-2">
              Our hosting and infrastructure providers (Vercel, Supabase), our payment processor (Stripe), the
              model providers that power plan generation (your description is sent to them to produce the plan),
              and our analytics provider (PostHog). Each acts under a data-processing agreement.
            </p>
          </section>
          <section>
            <h2 className="text-lg font-semibold">Your choices</h2>
            <p className="mt-2">
              Delete any plan from inside the app at any time. To delete your account and all associated data,
              {env.contactEmail ? (
                <>
                  {" "}email <a className="underline" href={`mailto:${env.contactEmail}`}>{env.contactEmail}</a> from the
                  address on the account
                </>
              ) : (
                " contact the operator of this site from the address on the account"
              )}
              ; we complete deletions within 30 days.
            </p>
          </section>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
