/**
 * The landing-page preview is anonymous. When the visitor signs up we carry the
 * preview over so the first plan is generated from the same inputs (and the API
 * can reuse the triage/intake work via `preview_id`).
 */
export const PENDING_PREVIEW_KEY = "pp_pending_preview";
export const SIGNUP_FLAG_KEY = "pp_signup_tracked";

export interface PendingPreview {
  preview_id: string;
  description: string;
  target_open_date: string | null;
  saved_at: string;
}

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function savePendingPreview(p: Omit<PendingPreview, "saved_at">): void {
  const s = storage();
  if (!s) return;
  try {
    s.setItem(PENDING_PREVIEW_KEY, JSON.stringify({ ...p, saved_at: new Date().toISOString() }));
  } catch {
    // storage full or blocked; the user can simply re-enter the description
  }
}

export function readPendingPreview(): PendingPreview | null {
  const s = storage();
  if (!s) return null;
  try {
    const raw = s.getItem(PENDING_PREVIEW_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PendingPreview>;
    if (!parsed || typeof parsed.description !== "string" || typeof parsed.preview_id !== "string") return null;
    return {
      preview_id: parsed.preview_id,
      description: parsed.description,
      target_open_date: typeof parsed.target_open_date === "string" ? parsed.target_open_date : null,
      saved_at: typeof parsed.saved_at === "string" ? parsed.saved_at : new Date(0).toISOString(),
    };
  } catch {
    return null;
  }
}

export function clearPendingPreview(): void {
  const s = storage();
  if (!s) return;
  try {
    s.removeItem(PENDING_PREVIEW_KEY);
  } catch {
    // ignore
  }
}

/** Returns true the first time it is called for this browser (used to fire `signup` once). */
export function markSignupTracked(userId: string): boolean {
  const s = storage();
  if (!s) return false;
  try {
    const key = `${SIGNUP_FLAG_KEY}:${userId}`;
    if (s.getItem(key)) return false;
    s.setItem(key, new Date().toISOString());
    return true;
  } catch {
    return false;
  }
}
