import type { Metadata } from "next";
import { Suspense } from "react";
import { MemoDetail } from "@/components/memo/memo-detail";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "Memo" };

export default async function MemoPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense fallback={<Skeleton className="h-72 w-full rounded-2xl" />}>
      <MemoDetail id={id} />
    </Suspense>
  );
}
