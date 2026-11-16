import type { Metadata } from "next";
import { NewPlan } from "@/components/app/new-plan";

export const metadata: Metadata = { title: "New plan" };

export default function NewPlanPage() {
  return <NewPlan />;
}
