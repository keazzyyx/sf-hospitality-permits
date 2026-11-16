"use client";

import { useEffect, useState } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/env";

export interface SessionState {
  /** true until the first getSession() resolves */
  loading: boolean;
  configured: boolean;
  session: Session | null;
  user: User | null;
  accessToken: string | null;
}

/** Live Supabase session for client components. Degrades to "unconfigured" without env vars. */
export function useSession(): SessionState {
  const [state, setState] = useState<SessionState>({
    loading: isSupabaseConfigured,
    configured: isSupabaseConfigured,
    session: null,
    user: null,
    accessToken: null,
  });

  useEffect(() => {
    const supabase = getSupabaseBrowserClient();
    if (!supabase) return;
    let cancelled = false;

    const apply = (session: Session | null) => {
      if (cancelled) return;
      setState({
        loading: false,
        configured: true,
        session,
        user: session?.user ?? null,
        accessToken: session?.access_token ?? null,
      });
    };

    supabase.auth.getSession().then(({ data }) => apply(data.session));
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => apply(session));

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, []);

  return state;
}
