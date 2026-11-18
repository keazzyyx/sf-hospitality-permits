import type { ConditionsData } from "./types";

export interface LoadProgress {
  /** Bytes read so far (after decompression). */
  loaded: number;
  /** The size being read towards, when it is known. */
  total: number | null;
  /** loaded / total, 0 to 1; null when the total is not known. */
  ratio: number | null;
}

/** The data, as a promise that also reports how far the download is. */
export interface DataHandle extends Promise<ConditionsData> {
  onProgress(cb: (p: LoadProgress) => void): () => void;
  /** Say this caller no longer needs the data. When every caller of loadConditions() for the URL has released it
   *  and the download is still running, the download is cancelled (and a later call starts a new one). */
  release(): void;
}

export interface LoadOptions {
  /** Do not reuse an earlier download of the same URL: fetch it again (what "Try again" does). */
  fresh?: boolean;
}

const cache = new Map<string, DataHandle>();

/**
 * Fetch the conditions data once per URL (later calls share the same download).
 *
 * Progress is real: bytes read over Content-Length. When the transfer is compressed, Content-Length (if there is
 * one) counts compressed bytes while the reader gives decompressed ones, so `sizeHint` (the file's size, known at
 * build time) is the total instead; without either, the total is null and the page shows an open-ended rule.
 */
export function loadConditions(url: string, sizeHint?: number, options: LoadOptions = {}): DataHandle {
  const key = new URL(url, location.href).href;
  const cached = options.fresh ? undefined : cache.get(key);
  if (cached) {
    users.set(cached, (users.get(cached) ?? 0) + 1);
    return cached;
  }

  const listeners = new Set<(p: LoadProgress) => void>();
  // nothing read yet: zero of the expected size, when one is known
  let last: LoadProgress = sizeHint && sizeHint > 0 ? { loaded: 0, total: sizeHint, ratio: 0 } : { loaded: 0, total: null, ratio: null };
  const report = (loaded: number, total: number | null): void => {
    last = { loaded, total, ratio: total ? Math.min(1, loaded / total) : null };
    for (const cb of listeners) cb(last);
  };
  const abort = new AbortController();
  let settled = false;

  const promise = (async (): Promise<ConditionsData> => {
    const res = await fetch(key, { signal: abort.signal });
    if (!res.ok) throw new Error(`Could not load the data (${res.status}).`);
    const encoded = (res.headers.get("content-encoding") ?? "identity").toLowerCase() !== "identity";
    const length = Number(res.headers.get("content-length"));
    const total = !encoded && length > 0 ? length : sizeHint && sizeHint > 0 ? sizeHint : null;
    if (!res.body) {
      const data = (await res.json()) as ConditionsData;
      report(total ?? 1, total ?? 1);
      return data;
    }
    const reader = res.body.getReader();
    const chunks: Uint8Array<ArrayBuffer>[] = [];
    let loaded = 0;
    report(0, total);
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      loaded += value.byteLength;
      report(loaded, total);
    }
    const data = JSON.parse(await new Blob(chunks).text()) as ConditionsData;
    report(loaded, loaded);
    return data;
  })();

  const handle = promise as DataHandle;
  handle.onProgress = cb => {
    listeners.add(cb);
    cb(last);
    return () => listeners.delete(cb);
  };
  handle.release = () => {
    const left = (users.get(handle) ?? 0) - 1;
    users.set(handle, Math.max(0, left));
    if (left > 0 || settled) return;
    // nobody is waiting for it any more: stop the download and forget it
    if (cache.get(key) === handle) cache.delete(key);
    abort.abort();
  };
  users.set(handle, 1);
  // a failed download is not kept: the next call tries again
  promise.then(
    () => { settled = true; },
    () => {
      settled = true;
      if (cache.get(key) === handle) cache.delete(key);
    },
  );
  cache.set(key, handle);
  return handle;
}

/** How many callers of loadConditions() still want each download. */
const users = new WeakMap<DataHandle, number>();

/** True when `x` is a promise that also reports progress (a DataHandle). */
export function hasProgress(x: unknown): x is DataHandle {
  return typeof (x as { onProgress?: unknown } | null)?.onProgress === "function";
}
