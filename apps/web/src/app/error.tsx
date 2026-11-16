"use client";

import { useEffect } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/site/logo";
import { env } from "@/lib/env";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="paper-grid flex min-h-dvh flex-col items-center justify-center px-4 text-center">
      <Logo />
      <h1 className="mt-10 text-3xl font-semibold">Something broke on our side</h1>
      <p className="mt-2 max-w-md text-muted-foreground">
        Your plans are safe. Try again
        {env.contactEmail ? `, and if this keeps happening email ${env.contactEmail}` : ""}
        {error.digest ? ` (reference ${error.digest})` : ""}.
      </p>
      <div className="mt-6 flex gap-3">
        <Button onClick={reset}>Try again</Button>
        <Button asChild variant="outline">
          <Link href="/">Back to home</Link>
        </Button>
      </div>
    </main>
  );
}
