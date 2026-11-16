import Link from "next/link";
import { Logo } from "@/components/site/logo";
import { APP_NAME } from "@/lib/brand";
import { env } from "@/lib/env";

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-paper-deep/60">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 sm:flex-row sm:items-start sm:justify-between sm:px-6">
        <div className="space-y-3">
          <Logo />
          <p className="max-w-sm text-sm text-muted-foreground">
            Location Risk Memos for San Francisco hospitality concepts, plus a free permit checklist anywhere in the
            US. Not legal advice — every memo cites the public record; confirm with the issuing agency.
          </p>
        </div>
        <nav className="grid grid-cols-2 gap-x-10 gap-y-2 text-sm sm:grid-cols-3" aria-label="Footer">
          <Link href="/#how-it-works" className="text-muted-foreground hover:text-foreground">How it works</Link>
          <Link href="/#pricing" className="text-muted-foreground hover:text-foreground">Pricing</Link>
          <Link href="/checklist" className="text-muted-foreground hover:text-foreground">Free permit checklist</Link>
          <Link href="/login" className="text-muted-foreground hover:text-foreground">Sign in</Link>
          <Link href="/privacy" className="text-muted-foreground hover:text-foreground">Privacy</Link>
          <Link href="/terms" className="text-muted-foreground hover:text-foreground">Terms</Link>
          {env.contactEmail ? (
            <a href={`mailto:${env.contactEmail}`} className="text-muted-foreground hover:text-foreground">Contact</a>
          ) : null}
        </nav>
      </div>
      <div className="mx-auto max-w-6xl px-4 pb-8 text-xs text-muted-foreground sm:px-6">
        © {new Date().getFullYear()} {APP_NAME}. Approval statuses are set by rules from public records and shown with
        the rules and records behind them; fees and timelines are estimates and change without notice.
      </div>
    </footer>
  );
}
