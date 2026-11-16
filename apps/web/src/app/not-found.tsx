import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/site/logo";

export default function NotFound() {
  return (
    <main className="paper-grid flex min-h-dvh flex-col items-center justify-center px-4 text-center">
      <Logo />
      <p className="mt-10 font-mono text-xs uppercase tracking-wider text-muted-foreground">404</p>
      <h1 className="mt-2 text-3xl font-semibold">That page is not in the plan</h1>
      <p className="mt-2 max-w-md text-muted-foreground">
        The link may be out of date, or the plan it pointed to was deleted.
      </p>
      <div className="mt-6 flex gap-3">
        <Button asChild>
          <Link href="/">Back to home</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/app">My plans</Link>
        </Button>
      </div>
    </main>
  );
}
