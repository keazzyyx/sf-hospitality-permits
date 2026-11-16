import { redirect } from "next/navigation";

/**
 * `/memo?address=…&description=…` is the public entry point from the landing page. The memo flow is
 * authenticated, so this forwards to `/app/memo` with the same query; the middleware sends signed-out
 * visitors to `/login?next=…` and `/app/memo` resumes from the query (or `pp_pending_memo`) after login.
 */
export default async function MemoRedirectPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    const value = Array.isArray(v) ? v[0] : v;
    if (typeof value === "string" && value.length > 0) q.set(k, value);
  }
  const query = q.toString();
  redirect(query ? `/app/memo?${query}` : "/app/memo");
}
