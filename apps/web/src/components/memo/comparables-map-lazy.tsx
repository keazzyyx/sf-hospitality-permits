"use client";

import dynamic from "next/dynamic";
import { Loader2 } from "lucide-react";
import type { ComparablesMapProps } from "@/components/memo/comparables-map";

const ComparablesMap = dynamic(() => import("@/components/memo/comparables-map"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[380px] items-center justify-center rounded-xl border border-border bg-paper-deep/50 text-sm text-muted-foreground sm:h-[440px]" role="status">
      <Loader2 className="mr-2 size-4 animate-spin text-signal" aria-hidden /> Loading map…
    </div>
  ),
});

/** Leaflet touches `window` at import time, so the map is loaded on the client only. */
export function ComparablesMapLazy(props: ComparablesMapProps) {
  return (
    <div data-testid="comparables-map" className="overflow-hidden rounded-xl border border-border bg-card p-2">
      <ComparablesMap {...props} />
    </div>
  );
}
