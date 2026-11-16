import type { Metadata } from "next";
import { BatchView } from "@/components/memo/batch-view";

export const metadata: Metadata = { title: "Batch" };

export default async function BatchPage({ params }: { params: Promise<{ batchId: string }> }) {
  const { batchId } = await params;
  return <BatchView batchId={batchId} />;
}
