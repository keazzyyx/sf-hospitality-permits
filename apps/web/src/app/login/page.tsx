import type { Metadata } from "next";
import { Suspense } from "react";
import { LoginForm } from "@/components/auth/login-form";
import { Logo } from "@/components/site/logo";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <main className="grid min-h-dvh lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <aside className="ink-panel hidden flex-col justify-between p-10 lg:flex">
        <Logo inverted />
        <div className="max-w-md space-y-6">
          <blockquote className="font-display text-2xl font-medium leading-snug text-paper">
            “The health permit needs the building permit which needs the zoning letter. Nobody tells you that until
            you are three months in.”
          </blockquote>
          <ul className="space-y-2 text-sm text-paper/70">
            <li>· Free memo teasers and 3 free checklists, no password, no card</li>
            <li>· Every rule with its code section, every fact with where it came from</li>
            <li>· Your address or preview is waiting on the other side</li>
          </ul>
        </div>
        <p className="text-xs text-paper/50">Not legal advice. Confirm requirements with the issuing agency.</p>
      </aside>
      <section className="paper-grid flex items-center justify-center px-4 py-12 sm:px-6">
        <div className="w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <Logo />
          </div>
          <Suspense fallback={<Skeleton className="h-72 w-full rounded-2xl" />}>
            <LoginForm />
          </Suspense>
        </div>
      </section>
    </main>
  );
}
