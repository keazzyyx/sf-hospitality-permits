/**
 * The landing-page address check requires sign-in. When a visitor is signed out we
 * keep what they typed so `/app/memo` can resume the memo automatically after login.
 */
import type { IntakeAnswers } from "@/lib/api-types";
import { ANSWER_PARAM, ASK_PARAM, cleanIntakeAnswers, setIntakeQuery } from "@/lib/intake";

export const PENDING_MEMO_KEY = "pp_pending_memo";

export interface PendingMemo {
  address: string;
  description: string;
  lat: number | null;
  lng: number | null;
  /** The optional intake answers, when any was given (absent in memos saved before the intake questions). */
  intake?: IntakeAnswers | null;
  /** The earlier-format memo this input re-runs (`rerun_of` on the create request), when it is a re-run. */
  rerun_of?: string | null;
  saved_at: string;
}

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function savePendingMemo(p: Omit<PendingMemo, "saved_at">): void {
  const s = storage();
  if (!s) return;
  try {
    s.setItem(PENDING_MEMO_KEY, JSON.stringify({ ...p, saved_at: new Date().toISOString() }));
  } catch {
    // storage full or blocked; the user can re-enter the address
  }
}

export function readPendingMemo(): PendingMemo | null {
  const s = storage();
  if (!s) return null;
  try {
    const raw = s.getItem(PENDING_MEMO_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PendingMemo>;
    if (!parsed || typeof parsed.address !== "string" || typeof parsed.description !== "string") return null;
    return {
      address: parsed.address,
      description: parsed.description,
      lat: typeof parsed.lat === "number" ? parsed.lat : null,
      lng: typeof parsed.lng === "number" ? parsed.lng : null,
      intake: cleanIntakeAnswers(parsed.intake),
      rerun_of: typeof parsed.rerun_of === "string" && parsed.rerun_of ? parsed.rerun_of : null,
      saved_at: typeof parsed.saved_at === "string" ? parsed.saved_at : new Date(0).toISOString(),
    };
  } catch {
    return null;
  }
}

export function clearPendingMemo(): void {
  const s = storage();
  if (!s) return;
  try {
    s.removeItem(PENDING_MEMO_KEY);
  } catch {
    // ignore
  }
}

/**
 * Build the `/memo?...` (or `/app/memo?...`) query string for a memo input. With `ask` (the intake questions a
 * report named as not given) the link opens the form filled in and waits for those answers instead of starting the
 * report at once (`answer=1&ask=a,b`).
 */
export function memoQuery(input: { address: string; description: string; lat?: number | null; lng?: number | null; intake?: IntakeAnswers | null; rerunOf?: string | null; ask?: readonly string[] }): string {
  const q = new URLSearchParams();
  q.set("address", input.address);
  q.set("description", input.description);
  if (typeof input.lat === "number" && typeof input.lng === "number") {
    q.set("lat", String(input.lat));
    q.set("lng", String(input.lng));
  }
  setIntakeQuery(q, input.intake);
  if (input.rerunOf) q.set("rerun_of", input.rerunOf);
  if (input.ask && input.ask.length > 0) {
    q.set(ANSWER_PARAM, "1");
    q.set(ASK_PARAM, input.ask.join(","));
  }
  return q.toString();
}
