"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Logo } from "@/components/site/logo";
import { Button } from "@/components/ui/button";
import { useSession } from "@/hooks/use-session";

export function SiteHeader() {
  const { user, loading } = useSession();
  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-paper/85 backdrop-blur supports-[backdrop-filter]:bg-paper/70">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Logo />
        <nav className="flex items-center gap-1 sm:gap-2" aria-label="Primary">
          <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
            <Link href="/#how-it-works">How it works</Link>
          </Button>
          <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
            <Link href="/#pricing">Pricing</Link>
          </Button>
          <Button asChild variant="ghost" size="sm" className="hidden md:inline-flex">
            <Link href="/checklist">Free permit checklist</Link>
          </Button>
          {loading ? (
            <span className="h-8 w-24 rounded-md bg-muted" aria-hidden />
          ) : user ? (
            <Button asChild size="sm">
              <Link href="/app/memos">
                Open my memos <ArrowRight />
              </Link>
            </Button>
          ) : (
            <>
              <Button asChild variant="ghost" size="sm">
                <Link href="/login">Sign in</Link>
              </Button>
              <Button asChild size="sm">
                <Link href="/#check">Check an address</Link>
              </Button>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
