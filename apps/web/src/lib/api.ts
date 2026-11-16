import { APP_NAME } from "@/lib/brand";
import { env } from "@/lib/env";
import type {
  AdminOverview,
  BulkBatch,
  BulkUploadResult,
  CheckoutMode,
  FeedbackInfo,
  FeedbackOutcome,
  GeocodeSuggestion,
  GeoJsonFeatureCollection,
  Me,
  MemoRecord,
  MemoRevision,
  MemoSummary,
  PlanRecord,
  PlanStepRecord,
  PlanSummary,
  StreamEvent,
  StreamEventName,
} from "@/lib/api-types";

/** Normalised API error. `code` matches the contract's snake_case error codes. */
export class ApiError extends Error {
  status: number;
  code: string;
  extra: Record<string, unknown>;

  constructor(status: number, code: string, message: string, extra: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.extra = extra;
  }

  get isPaywall() {
    return this.status === 402 || this.code === "paywall" || this.code === "paywall_memo";
  }

  get isMemoPaywall() {
    return this.code === "paywall_memo" || (this.status === 402 && this.code !== "paywall");
  }
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError;
}

/** Human-friendly copy for well-known error codes (contract + a few client-side ones). */
export function describeErrorCode(code: string, fallback?: string): string {
  switch (code) {
    case "rate_limited":
      return "You have hit the preview limit for now (10 per hour). Give it a little while and try again, or create a free account to keep going.";
    case "not_hospitality":
      return `${APP_NAME} only plans hospitality businesses: restaurants, bars, cafes, food trucks, hotels and caterers. Try describing one of those.`;
    case "unauthorized":
      return "Your session has expired. Sign in again to continue.";
    case "paywall":
      return "You have used your free plans. Upgrade to keep building.";
    case "paywall_memo":
      return "You have used your free memo previews. Buy a memo or go Pro to keep checking addresses.";
    case "address_not_found":
      return "We could not place that address. Pick one of the suggestions as you type, or add the street number and zip code.";
    case "outside_coverage":
      return "Location Risk Memos cover San Francisco only for now. Los Angeles and New York are next; leave your email on the home page and we will tell you when they are live.";
    case "pro_required":
      return "Bulk upload is part of Pro. Upgrade on the billing page to check up to 25 addresses at once.";
    case "forbidden":
      return `This page is for ${APP_NAME} admins only.`;
    case "not_found":
      return fallback || "We could not find that record.";
    case "generation_failed":
      return "Plan generation failed on our side. Nothing was charged; please try again in a moment.";
    case "network":
      return `We could not reach the ${APP_NAME} API. Check your connection and try again.`;
    case "validation_error":
      return fallback || "Some of the inputs were not accepted. Check them and try again.";
    default:
      return fallback || "Something went wrong.";
  }
}

export function describeApiError(err: unknown): string {
  if (isApiError(err)) return describeErrorCode(err.code, err.message);
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}

async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // non-JSON error body
  }
  const detail =
    body && typeof body === "object" && "detail" in body
      ? (body as { detail: unknown }).detail
      : body;
  if (detail && typeof detail === "object") {
    const { code, message, ...extra } = detail as Record<string, unknown>;
    return new ApiError(
      res.status,
      typeof code === "string" ? code : `http_${res.status}`,
      typeof message === "string" ? message : res.statusText || "Request failed",
      extra,
    );
  }
  if (typeof detail === "string") return new ApiError(res.status, `http_${res.status}`, detail);
  return new ApiError(res.status, `http_${res.status}`, res.statusText || "Request failed");
}

export interface RequestOptions {
  token?: string | null;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

function buildHeaders(opts: RequestOptions, json: boolean): Headers {
  const headers = new Headers(opts.headers);
  if (json) headers.set("Content-Type", "application/json");
  headers.set("Accept", json ? "application/json" : "*/*");
  if (opts.token) headers.set("Authorization", `Bearer ${opts.token}`);
  return headers;
}

async function doFetch(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${env.apiUrl}${path}`, init);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "network", "Could not reach the API");
  }
}

/** Typed JSON request. Throws ApiError on non-2xx. */
export async function apiRequest<T>(
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
  opts: RequestOptions = {},
): Promise<T> {
  const res = await doFetch(path, {
    method,
    headers: buildHeaders(opts, true),
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: opts.signal,
    cache: "no-store",
  });
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Multipart upload (CSV bulk memos). The browser sets the multipart boundary. */
export async function apiUpload<T>(path: string, form: FormData, opts: RequestOptions = {}): Promise<T> {
  const headers = buildHeaders(opts, false);
  headers.set("Accept", "application/json");
  const res = await doFetch(path, { method: "POST", headers, body: form, signal: opts.signal, cache: "no-store" });
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as T;
}

/** Fetch a binary response (PDF export). */
export async function apiBlob(path: string, opts: RequestOptions = {}): Promise<Blob> {
  const res = await doFetch(path, {
    method: "GET",
    headers: buildHeaders(opts, false),
    signal: opts.signal,
    cache: "no-store",
  });
  if (!res.ok) throw await toApiError(res);
  return res.blob();
}

// ---------------------------------------------------------------------------
// Server-Sent Events over fetch (POST + Authorization header; EventSource cannot do either)
// ---------------------------------------------------------------------------

export interface StreamOptions {
  token?: string | null;
  signal?: AbortSignal;
  onEvent: (name: StreamEventName | string, data: unknown) => void;
}

interface Frame {
  event: string;
  data: string;
}

/**
 * Parse one SSE frame (the text between two blank lines). Handles comment lines,
 * multi-line `data:` fields (joined with "\n") and the optional space after the colon.
 */
function parseFrame(raw: string): Frame | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const idx = line.indexOf(":");
    const field = idx === -1 ? line : line.slice(0, idx);
    let value = idx === -1 ? "" : line.slice(idx + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

function dispatch(frame: Frame, onEvent: StreamOptions["onEvent"]) {
  let parsed: unknown = frame.data;
  try {
    parsed = JSON.parse(frame.data);
  } catch {
    // leave as raw string
  }
  onEvent(frame.event, parsed);
}

/**
 * POST `body` to `path` and consume the `text/event-stream` response, invoking
 * `onEvent(name, data)` for each `event:`/`data:` frame. Resolves when the stream ends.
 * Throws ApiError if the server rejects before streaming (401/402/429...).
 */
export async function streamSSE(path: string, body: unknown, opts: StreamOptions): Promise<void> {
  const res = await doFetch(path, {
    method: "POST",
    headers: (() => {
      const h = buildHeaders({ token: opts.token }, true);
      h.set("Accept", "text/event-stream");
      return h;
    })(),
    body: JSON.stringify(body ?? {}),
    signal: opts.signal,
    cache: "no-store",
  });
  if (!res.ok) throw await toApiError(res);
  if (!res.body) throw new ApiError(res.status, "empty_stream", "The server returned an empty stream");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flush = (final: boolean) => {
    // Normalise CRLF so a frame boundary is always "\n\n".
    buffer = buffer.replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const frame = parseFrame(raw);
      if (frame) dispatch(frame, opts.onEvent);
      boundary = buffer.indexOf("\n\n");
    }
    if (final && buffer.trim()) {
      const frame = parseFrame(buffer);
      if (frame) dispatch(frame, opts.onEvent);
      buffer = "";
    }
  };

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    flush(false);
  }
  buffer += decoder.decode();
  flush(true);
}

/** Narrow a raw `(name, data)` pair into the typed union when the name is known. */
export function asStreamEvent(name: string, data: unknown): StreamEvent | null {
  switch (name) {
    case "plan_created":
    case "stage":
    case "tool":
    case "narrative":
    case "needs_clarification":
    case "preview":
    case "plan":
    case "memo_created":
    case "answers_round":
    case "memo":
    case "error":
      return { event: name, data } as StreamEvent;
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Typed route helpers (JSON routes). Streaming routes are driven via streamSSE + useGenerationStream.
// ---------------------------------------------------------------------------

export const api = {
  me: (token: string) => apiRequest<{ profile: Me }>("GET", "/v1/me", undefined, { token }),
  plans: (token: string) => apiRequest<{ plans: PlanSummary[] }>("GET", "/v1/plans", undefined, { token }),
  plan: (token: string, id: string) =>
    apiRequest<{ plan: PlanRecord }>("GET", `/v1/plans/${encodeURIComponent(id)}`, undefined, { token }),
  patchStep: (token: string, planId: string, stepId: string, body: { done?: boolean; notes?: string }) =>
    apiRequest<{ step: PlanStepRecord }>(
      "PATCH",
      `/v1/plans/${encodeURIComponent(planId)}/steps/${encodeURIComponent(stepId)}`,
      body,
      { token },
    ),
  deletePlan: (token: string, id: string) =>
    apiRequest<void>("DELETE", `/v1/plans/${encodeURIComponent(id)}`, undefined, { token }),
  exportPdf: (token: string, id: string) => apiBlob(`/v1/plans/${encodeURIComponent(id)}/export.pdf`, { token }),
  lead: (body: { email: string; city?: string; state?: string; description?: string }) =>
    apiRequest<{ ok: true }>("POST", "/v1/leads", body),
  checkout: (token: string, body: { mode: CheckoutMode; success_url: string; cancel_url: string }) =>
    apiRequest<{ url: string }>("POST", "/v1/billing/checkout", body, { token }),
  portal: (token: string, body: { return_url: string }) =>
    apiRequest<{ url: string }>("POST", "/v1/billing/portal", body, { token }),

  // ---- Location Risk Memo (docs/api-contract-memo.md) ----
  geocode: (q: string, opts: { limit?: number; signal?: AbortSignal } = {}) =>
    apiRequest<{ suggestions: GeocodeSuggestion[] }>(
      "GET",
      `/v1/geocode?q=${encodeURIComponent(q)}&limit=${opts.limit ?? 8}`,
      undefined,
      { signal: opts.signal },
    ),
  memos: (token: string) => apiRequest<{ memos: MemoSummary[] }>("GET", "/v1/memos", undefined, { token }),
  memo: (token: string, id: string) =>
    apiRequest<{ memo: MemoRecord }>("GET", `/v1/memos/${encodeURIComponent(id)}`, undefined, { token }),
  unlockMemo: (token: string, id: string) =>
    apiRequest<{ memo: MemoRecord }>("POST", `/v1/memos/${encodeURIComponent(id)}/unlock`, undefined, { token }),
  deleteMemo: (token: string, id: string) =>
    apiRequest<void>("DELETE", `/v1/memos/${encodeURIComponent(id)}`, undefined, { token }),
  exportMemoPdf: (token: string, id: string) => apiBlob(`/v1/memos/${encodeURIComponent(id)}/export.pdf`, { token }),
  memoGeojson: (token: string, id: string) =>
    apiRequest<GeoJsonFeatureCollection>("GET", `/v1/memos/${encodeURIComponent(id)}/map.geojson`, undefined, { token }),
  /** The versions answer rounds replaced, oldest first. A round itself is a stream: `POST /v1/memos/{id}/answers`. */
  memoRevisions: (token: string, id: string) =>
    apiRequest<{ revisions: MemoRevision[] }>("GET", `/v1/memos/${encodeURIComponent(id)}/revisions`, undefined, { token }),
  bulkUpload: (token: string, file: File) => {
    const form = new FormData();
    form.append("file", file, file.name);
    return apiUpload<BulkUploadResult>("/v1/memos/bulk", form, { token });
  },
  bulkBatch: (token: string, batchId: string) =>
    apiRequest<BulkBatch>("GET", `/v1/memos/bulk/${encodeURIComponent(batchId)}`, undefined, { token }),
  feedback: (tokenParam: string) =>
    apiRequest<FeedbackInfo>("GET", `/v1/feedback/${encodeURIComponent(tokenParam)}`),
  submitFeedback: (tokenParam: string, body: { outcome: FeedbackOutcome; notes?: string }) =>
    apiRequest<{ ok: true }>("POST", `/v1/feedback/${encodeURIComponent(tokenParam)}`, body),
  adminOverview: (token: string) => apiRequest<AdminOverview>("GET", "/v1/admin/overview", undefined, { token }),
};
