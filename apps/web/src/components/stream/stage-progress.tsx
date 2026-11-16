"use client";

import { Check, Loader2, Wrench } from "lucide-react";
import { cn } from "cn";
import { STAGE_LABELS, type StageProgress } from "@/hooks/use-generation-stream";
import type { StageName } from "@/lib/api-types";

export function StageProgressList({
  stages,
  streaming,
  className,
  labels,
  connectingLabel = "Connecting to the planner…",
}: {
  stages: StageProgress[];
  streaming: boolean;
  className?: string;
  /** Override stage labels (memo streams reuse stage names with different wording). */
  labels?: Partial<Record<StageName, string>>;
  connectingLabel?: string;
}) {
  const labelFor = (stage: StageName) => labels?.[stage] ?? STAGE_LABELS[stage] ?? stage;
  if (stages.length === 0 && streaming) {
    return (
      <div className={cn("flex items-center gap-3 text-sm text-muted-foreground", className)} role="status">
        <Loader2 className="size-4 animate-spin text-signal" aria-hidden />
        {connectingLabel}
      </div>
    );
  }

  return (
    <ol className={cn("space-y-3", className)} aria-live="polite">
      {stages.map((s) => {
        const done = s.status === "completed";
        return (
          <li key={s.stage} className="flex gap-3">
            <span
              className={cn(
                "mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border",
                done ? "border-verified bg-verified text-white" : "border-signal/50 bg-signal-soft text-signal",
              )}
              aria-hidden
            >
              {done ? <Check className="size-3" /> : <Loader2 className="size-3 animate-spin" />}
            </span>
            <div className="min-w-0 flex-1">
              <p className={cn("text-sm", done ? "text-muted-foreground" : "font-medium text-foreground")}>
                {s.message || labelFor(s.stage)}
                {done && typeof s.elapsed_ms === "number" && (
                  <span className="ml-2 font-mono text-[11px] text-muted-foreground/80 tabular">
                    {(s.elapsed_ms / 1000).toFixed(1)}s
                  </span>
                )}
              </p>
              {s.tools.length > 0 && (
                <ul className="mt-1 space-y-0.5">
                  {s.tools.map((t, i) => (
                    <li
                      key={`${t.tool}-${i}`}
                      className="flex items-center gap-1.5 text-xs text-muted-foreground/90"
                    >
                      <Wrench className="size-3 shrink-0 opacity-60" aria-hidden />
                      <span className="truncate">{t.message || t.tool.replace(/_/g, " ")}</span>
                      {typeof t.rows === "number" && (
                        <span className="shrink-0 rounded-full border border-border bg-background px-1.5 font-mono text-[10px] tabular" data-testid="tool-rows">
                          {t.rows.toLocaleString("en-US")} {t.rows === 1 ? "row" : "rows"}
                        </span>
                      )}
                      {t.status === "started" && <Loader2 className="size-3 animate-spin opacity-60" aria-hidden />}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function NarrativeBox({ text, streaming, title = "Plan narrative" }: { text: string; streaming: boolean; title?: string }) {
  if (!text) return null;
  return (
    <div className="rounded-lg border border-border bg-card p-4" data-testid="narrative-box">
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{title}</p>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
        {text}
        {streaming && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-signal align-text-bottom" aria-hidden />}
      </p>
    </div>
  );
}
