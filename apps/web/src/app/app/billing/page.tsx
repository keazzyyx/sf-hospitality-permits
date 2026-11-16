import type { Metadata } from "next";
import { Suspense } from "react";
import { BillingView } from "@/components/billing/billing-view";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "Billing" };

export default function BillingPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full rounded-2xl" />}>
      <BillingView />
    </Suspense>
  );
}
