"use client";

import { createBrowserClient } from "@supabase/ssr";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { env, isSupabaseConfigured } from "@/lib/env";

let client: SupabaseClient | null = null;
let otpClient: SupabaseClient | null = null;

/**
 * Browser Supabase client (singleton) with @supabase/ssr cookie storage, so the session it holds is
 * the same one the middleware and Route Handlers read. Returns null when env vars are missing.
 *
 * URL detection is off: sign-in links are completed server-side (/auth/callback) or explicitly on
 * /auth/complete, never by this client scanning the address bar.
 */
export function getSupabaseBrowserClient(): SupabaseClient | null {
  if (!isSupabaseConfigured) return null;
  if (!client) {
    client = createBrowserClient(env.supabaseUrl, env.supabaseAnonKey, {
      auth: { detectSessionInUrl: false },
    });
  }
  return client;
}

/**
 * Client used only to *request* magic links. @supabase/ssr pins the PKCE flow, which stores a code
 * verifier in the requesting browser and makes the emailed link fail anywhere else ("PKCE code
 * verifier not found"). This plain client runs the implicit flow and persists nothing: Supabase then
 * verifies the link itself and hands the session to /auth/complete in the URL fragment, which works
 * on any device. Token-hash links (supabase/templates) and the emailed code never touch it.
 */
export function getSupabaseOtpClient(): SupabaseClient | null {
  if (!isSupabaseConfigured) return null;
  if (!otpClient) {
    otpClient = createClient(env.supabaseUrl, env.supabaseAnonKey, {
      auth: { flowType: "implicit", persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
    });
  }
  return otpClient;
}

/** Current access token for `Authorization: Bearer`, or null when signed out / unconfigured. */
export async function getAccessToken(): Promise<string | null> {
  const supabase = getSupabaseBrowserClient();
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
