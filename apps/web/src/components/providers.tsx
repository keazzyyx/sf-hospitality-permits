"use client";

import { useEffect } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { useSession } from "@/hooks/use-session";
import { capture, identify, initAnalytics } from "@/lib/analytics";
import { markSignupTracked } from "@/lib/pending-preview";

function AnalyticsBridge() {
  const { user } = useSession();

  useEffect(() => {
    initAnalytics();
  }, []);

  useEffect(() => {
    if (!user) return;
    identify(user.id, { email: user.email ?? undefined });
    if (markSignupTracked(user.id)) {
      capture("signup", { provider: user.app_metadata?.provider ?? "email" });
    }
  }, [user]);

  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <TooltipProvider delayDuration={150}>
      <AnalyticsBridge />
      {children}
      <Toaster position="bottom-right" richColors closeButton />
    </TooltipProvider>
  );
}
