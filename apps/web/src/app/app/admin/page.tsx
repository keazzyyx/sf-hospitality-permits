import type { Metadata } from "next";
import { AdminOverviewView } from "@/components/admin/admin-overview";

export const metadata: Metadata = { title: "Admin" };

export default function AdminPage() {
  return <AdminOverviewView />;
}
