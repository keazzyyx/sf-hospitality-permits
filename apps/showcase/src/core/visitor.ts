// Remembers that a visitor has been through something (the gate, the story), so a return visit can skip it.
// localStorage where it works; otherwise the answer lasts for the page only.

const PREFIX = "showcase:visited:";
const memory = new Set<string>();

/** True when markVisited(key) was called before, on this device. */
export function hasVisited(key: string): boolean {
  if (memory.has(key)) return true;
  try {
    return window.localStorage.getItem(PREFIX + key) !== null;
  } catch {
    return false;
  }
}

/** Remember the visit (with the time, in case a prototype wants "seen this week"). */
export function markVisited(key: string): void {
  memory.add(key);
  try {
    window.localStorage.setItem(PREFIX + key, new Date().toISOString());
  } catch {
    // private mode or blocked storage: remembered for this page only
  }
}

/** Forget the visit, so the next load plays the full experience again. */
export function reset(key: string): void {
  memory.delete(key);
  try {
    window.localStorage.removeItem(PREFIX + key);
  } catch {
    // nothing stored, nothing to remove
  }
}
