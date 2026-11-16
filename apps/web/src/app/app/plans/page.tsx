import type { Metadata } from "next";
import { PlansList } from "@/components/app/plans-list";

export const metadata: Metadata = { title: "Permit checklists" };

export default function PlansPage() {
  return <PlansList />;
}
