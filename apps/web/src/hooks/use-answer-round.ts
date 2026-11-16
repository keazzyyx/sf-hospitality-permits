"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useGenerationStream } from "@/hooks/use-generation-stream";
import { api, describeErrorCode, isApiError } from "@/lib/api";
import type { IntakeAnswers, MemoRecord, MemoRevision } from "@/lib/api-types";

/**
 * An answer round on the memo page (owner decision of 2026-11-16): `POST /v1/memos/{id}/answers` with the answers
 * only, streamed like a run, on the same memo. While it runs the page shows the memo as being updated; when it ends
 * the page takes the updated record (or, when the stream drops, reads the memo again, which polls while it is
 * generating) and the versions the rounds replaced (`GET /v1/memos/{id}/revisions`).
 */
export function useAnswerRound({
  token,
  record,
  onRecord,
}: {
  token: string;
  record: MemoRecord | null;
  onRecord: (record: MemoRecord) => void;
}) {
  const { state, start } = useGenerationStream();
  const [revisions, setRevisions] = useState<MemoRevision[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const handled = useRef<string | null>(null);
  const id = record?.id ?? null;
  const rounds = record?.answers_round ?? 0;

  const loadRevisions = useCallback(async () => {
    if (!id) return;
    try {
      const { revisions: list } = await api.memoRevisions(token, id);
      setRevisions(list);
    } catch {
      // the list of earlier versions is extra: the memo itself is shown without it
    }
  }, [token, id]);

  useEffect(() => {
    if (rounds > 0) void loadRevisions();
    else setRevisions(null);
  }, [rounds, loadRevisions]);

  const submit = useCallback(
    async (answers: IntakeAnswers) => {
      if (!record) return;
      setError(null);
      handled.current = null;
      try {
        await start(`/v1/memos/${encodeURIComponent(record.id)}/answers`, answers, { token });
      } catch (err) {
        // refused before the round started (a round running, none left, the same answers, too many requests)
        if (isApiError(err)) setError(describeErrorCode(err.code, err.message));
      }
    },
    [record, start, token],
  );

  // the round started: the memo shows as being updated until it ends
  useEffect(() => {
    if (state.status === "streaming" && state.memoId && record && record.id === state.memoId && !record.answers_running) {
      onRecord({ ...record, status: "generating", answers_running: true, error: null });
    }
  }, [state.status, state.memoId, record, onRecord]);

  useEffect(() => {
    const key = `${state.status}:${state.memo?.updated_at ?? ""}:${state.error?.code ?? ""}`;
    if (handled.current === key) return;
    if (state.status === "done" && state.memo) {
      handled.current = key;
      onRecord(state.memo);
    } else if (state.status === "error" && state.memoId && id) {
      // the round ended without its memo (it failed and left the memo as it was, or the stream dropped while it
      // goes on): read the memo again
      handled.current = key;
      void api
        .memo(token, id)
        .then(({ memo }) => onRecord(memo))
        .catch(() => undefined);
    }
  }, [state.status, state.memo, state.memoId, state.error, id, token, onRecord]);

  return { submit, busy: state.status === "streaming", error, revisions, stages: state.stages };
}
