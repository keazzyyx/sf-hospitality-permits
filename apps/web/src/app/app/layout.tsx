import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { AppShell } from "@/components/app/app-shell";
import { APP_NAME } from "@/lib/brand";
import { isSupabaseConfigured } from "@/lib/env";
import { getServerUser } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: { default: "Memos", template: `%s · ${APP_NAME}` },
  robots: { index: false, follow: false },
};

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  if (!isSupabaseConfigured) redirect("/login?next=%2Fapp");
  const user = await getServerUser();
  if (!user) redirect("/login?next=%2Fapp");
  return <AppShell>{children}</AppShell>;
}
