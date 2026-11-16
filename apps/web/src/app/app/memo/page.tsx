import type { Metadata } from "next";
import { Suspense } from "react";
import { NewMemo } from "@/components/memo/new-memo";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "New memo" };

export default function NewMemoPage() {
  return (
    <Suspense fallback={<Skeleton className="h-72 w-full rounded-2xl" />}>
      <NewMemo />
    </Suspense>
  );
}
