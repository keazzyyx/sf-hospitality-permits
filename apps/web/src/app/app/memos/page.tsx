import type { Metadata } from "next";
import { MemosList } from "@/components/memo/memos-list";

export const metadata: Metadata = { title: "Memos" };

export default function MemosPage() {
  return <MemosList />;
}
