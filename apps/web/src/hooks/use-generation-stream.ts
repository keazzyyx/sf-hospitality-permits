"use client";

import { useCallback, useReducer, useRef } from "react";
import { asStreamEvent, isApiError, streamSSE } from "@/lib/api";
import type {
  MemoRecord,
  MemoStageName,
  NeedsClarificationEvent,
  PlanRecord,
  PreviewResult,
  StageEvent,
  StageName,
  ToolEvent,
} from "@/lib/api-types";

export interface StageProgress extends StageEvent {
  tools: ToolEvent[];
}

export interface StreamError {
  code: string;
  message: string;
  status: number | null;
  extra: Record<string, unknown>;
}

export interface GenerationState {
  status: "idle" | "streaming" | "clarify" | "done" | "error";
  stages: StageProgress[];
  /** Plan streams only: memo streams (report format 2) send no text events, so this stays empty. */
  narrative: string;
  planId: string | null;
  memoId: string | null;
  clarification: NeedsClarificationEvent | null;
  preview: PreviewResult | null;
  plan: PlanRecord | null;
  memo: MemoRecord | null;
  error: StreamError | null;
}

type Action =
  | { type: "start" }
  | { type: "plan_created"; planId: string }
  | { type: "stage"; data: StageEvent }
  | { type: "tool"; data: ToolEvent }
  | { type: "narrative"; delta: string }
  | { type: "needs_clarification"; data: NeedsClarificationEvent }
  | { type: "preview"; data: PreviewResult }
  | { type: "plan"; data: PlanRecord }
  | { type: "memo_created"; memoId: string }
  | { type: "memo"; data: MemoRecord }
  | { type: "error"; error: StreamError }
  | { type: "ended" }
  | { type: "reset" };

export const initialGenerationState: GenerationState = {
  status: "idle",
  stages: [],
  narrative: "",
  planId: null,
  memoId: null,
  clarification: null,
  preview: null,
  plan: null,
  memo: null,
  error: null,
};

function upsertStage(stages: StageProgress[], data: StageEvent): StageProgress[] {
  const idx = stages.findIndex((s) => s.stage === data.stage);
  if (idx === -1) return [...stages, { ...data, tools: [] }];
  const next = stages.slice();
  next[idx] = { ...next[idx], ...data };
  return next;
}

function upsertTool(stages: StageProgress[], data: ToolEvent): StageProgress[] {
  let next = stages;
  if (!next.some((s) => s.stage === data.stage)) {
    next = [...next, { stage: data.stage, status: "started", message: "", tools: [] }];
  }
  return next.map((s) => {
    if (s.stage !== data.stage) return s;
    const ti = s.tools.findIndex((t) => t.tool === data.tool && t.status === "started");
    const tools = s.tools.slice();
    if (ti !== -1 && data.status === "completed") tools[ti] = data;
    else tools.push(data);
    return { ...s, tools };
  });
}

function reducer(state: GenerationState, action: Action): GenerationState {
  switch (action.type) {
    case "start":
      return { ...initialGenerationState, planId: state.planId, memoId: state.memoId, status: "streaming" };
    case "plan_created":
      return { ...state, planId: action.planId };
    case "stage":
      return { ...state, stages: upsertStage(state.stages, action.data) };
    case "tool":
      return { ...state, stages: upsertTool(state.stages, action.data) };
    case "narrative":
      return { ...state, narrative: state.narrative + action.delta };
    case "needs_clarification":
      return {
        ...state,
        status: "clarify",
        clarification: action.data,
        planId: action.data.plan_id ?? state.planId,
        memoId: action.data.memo_id ?? state.memoId,
      };
    case "preview":
      return { ...state, status: "done", preview: action.data };
    case "plan":
      return { ...state, status: "done", plan: action.data, planId: action.data.id };
    case "memo_created":
      return { ...state, memoId: action.memoId };
    case "memo":
      return { ...state, status: "done", memo: action.data, memoId: action.data.id };
    case "error":
      return { ...state, status: "error", error: action.error };
    case "ended":
      // Stream closed without a terminal event.
      return state.status === "streaming"
        ? {
            ...state,
            status: "error",
            error: {
              code: "stream_ended",
              message: "The connection closed before the result finished. Please try again.",
              status: null,
              extra: {},
            },
          }
        : state;
    case "reset":
      return initialGenerationState;
    default:
      return state;
  }
}

export interface StartOptions {
  token?: string | null;
}

/**
 * Drives one SSE generation (preview, plan, clarify, rerun) and exposes the
 * accumulated progress for the shared progress UI.
 */
export function useGenerationStream() {
  const [state, dispatch] = useReducer(reducer, initialGenerationState);
  const abortRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const reset = useCallback(() => {
    cancel();
    dispatch({ type: "reset" });
  }, [cancel]);

  /**
   * Start streaming. Resolves with the final state kind. Rejects only for
   * pre-stream HTTP errors (ApiError) so callers can special-case 402/429/422.
   */
  const start = useCallback(async (path: string, body: unknown, opts: StartOptions = {}) => {
    cancel();
    const controller = new AbortController();
    abortRef.current = controller;
    dispatch({ type: "start" });

    try {
      await streamSSE(path, body, {
        token: opts.token,
        signal: controller.signal,
        onEvent: (name, data) => {
          const ev = asStreamEvent(name, data);
          if (!ev) return;
          switch (ev.event) {
            case "plan_created":
              dispatch({ type: "plan_created", planId: ev.data.plan_id });
              break;
            case "stage":
              dispatch({ type: "stage", data: ev.data });
              break;
            case "tool":
              dispatch({ type: "tool", data: ev.data });
              break;
            case "narrative":
              dispatch({ type: "narrative", delta: ev.data.delta ?? "" });
              break;
            case "needs_clarification":
              dispatch({ type: "needs_clarification", data: ev.data });
              break;
            case "preview":
              dispatch({ type: "preview", data: ev.data });
              break;
            case "plan":
              dispatch({ type: "plan", data: ev.data });
              break;
            case "memo_created":
            case "answers_round":
              dispatch({ type: "memo_created", memoId: ev.data.memo_id });
              break;
            case "memo":
              dispatch({ type: "memo", data: ev.data });
              break;
            case "error":
              dispatch({
                type: "error",
                error: { code: ev.data.code, message: ev.data.message, status: null, extra: {} },
              });
              break;
          }
        },
      });
      dispatch({ type: "ended" });
    } catch (err) {
      if (controller.signal.aborted) return;
      if (isApiError(err)) {
        dispatch({
          type: "error",
          error: { code: err.code, message: err.message, status: err.status, extra: err.extra },
        });
        throw err;
      }
      dispatch({
        type: "error",
        error: {
          code: "network",
          message: err instanceof Error ? err.message : "Connection lost",
          status: null,
          extra: {},
        },
      });
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [cancel]);

  return { state, start, cancel, reset };
}

export type GenerationStream = ReturnType<typeof useGenerationStream>;

/** Default (permit checklist) stage labels. Memo streams pass `MEMO_STAGE_LABELS` to the progress list. */
export const STAGE_LABELS: Record<StageName, string> = {
  triage: "Checking this is a hospitality business",
  intake: "Reading your description",
  requirements: "Matching permits and licenses",
  timeline: "Sequencing the critical path",
  blocker: "Looking for what usually stalls openings",
  finalize: "Assembling your plan",
  records: "Pulling nearby records",
  precedent: "Ranking comparable cases",
};

/** Stage labels for `POST /v1/memos` and `/clarify` (stages: intake, records, precedent, finalize). */
export const MEMO_STAGE_LABELS: Record<MemoStageName, string> = {
  intake: "Reading your concept into facts",
  records: "Pulling records and applying the rules",
  precedent: "Ranking comparable cases by a fixed score",
  finalize: "Assembling the report",
};
