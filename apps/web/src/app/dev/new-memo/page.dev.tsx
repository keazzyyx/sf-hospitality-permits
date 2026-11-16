"use client";

import { Suspense } from "react";
import type { User } from "@supabase/supabase-js";
import { AppProvider } from "@/components/app/app-context";
import { NewMemo } from "@/components/memo/new-memo";

/**
 * Development-only: the real new-memo form (`/app/memo`) outside the signed-in app, so e2e/intake.spec.ts can
 * fill it and read the create request it sends. The `.dev.tsx` page extension is registered in next.config.ts
 * only when NODE_ENV !== "production", so this route never ships in a production build. The user and token are
 * placeholders; every API call the page makes is answered by the test.
 */
const DEV_USER = { id: "00000000-0000-4000-8000-000000000000", email: "dev@example.com" } as unknown as User;

export default function NewMemoDevPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
      <p className="mb-6 rounded-lg border border-estimated/40 bg-estimated-soft px-3 py-2 text-xs text-foreground/80" data-testid="dev-banner">
        Development preview · the new-memo form · no backend
      </p>
      <AppProvider user={DEV_USER} accessToken="dev-token">
        <Suspense fallback={null}>
          <NewMemo />
        </Suspense>
      </AppProvider>
    </main>
  );
}
