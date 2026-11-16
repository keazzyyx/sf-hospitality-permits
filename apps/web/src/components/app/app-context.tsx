"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { User } from "@supabase/supabase-js";
import { api, describeApiError } from "@/lib/api";
import { resetAnalytics } from "@/lib/analytics";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import type { Me } from "@/lib/api-types";

export interface AppContextValue {
  user: User;
  accessToken: string;
  me: Me | null;
  meLoading: boolean;
  meError: string | null;
  refreshMe: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AppContext = createContext<AppContextValue | null>(null);

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}

export function AppProvider({
  user,
  accessToken,
  children,
}: {
  user: User;
  accessToken: string;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [meLoading, setMeLoading] = useState(true);
  const [meError, setMeError] = useState<string | null>(null);
  const tokenRef = useRef(accessToken);
  tokenRef.current = accessToken;

  const refreshMe = useCallback(async () => {
    setMeLoading(true);
    try {
      const { profile } = await api.me(tokenRef.current);
      setMe(profile);
      setMeError(null);
    } catch (err) {
      setMeError(describeApiError(err));
    } finally {
      setMeLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshMe();
  }, [refreshMe]);

  const signOut = useCallback(async () => {
    const supabase = getSupabaseBrowserClient();
    await supabase?.auth.signOut();
    resetAnalytics();
    router.replace("/");
    router.refresh();
  }, [router]);

  const value = useMemo<AppContextValue>(
    () => ({ user, accessToken, me, meLoading, meError, refreshMe, signOut }),
    [user, accessToken, me, meLoading, meError, refreshMe, signOut],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
