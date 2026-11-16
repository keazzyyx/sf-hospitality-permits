import type { Metadata } from "next";
import { FeedbackForm } from "@/components/feedback/feedback-form";
import { SiteFooter } from "@/components/site/site-footer";
import { SiteHeader } from "@/components/site/site-header";

export const metadata: Metadata = {
  title: "How did it go?",
  robots: { index: false, follow: false },
};

export default async function FeedbackPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <>
      <SiteHeader />
      <main id="main" className="paper-grid border-b border-border">
        <div className="mx-auto max-w-2xl px-4 py-12 sm:px-6 lg:py-16">
          <FeedbackForm token={token} />
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
