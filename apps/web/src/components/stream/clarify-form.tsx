"use client";

import { useState } from "react";
import { Loader2, MessageCircleQuestion } from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { BusinessProfile, ClarifyingQuestion } from "@/lib/api-types";

export type ClarifyAnswers = Record<string, string | number | boolean>;

function defaultAnswers(questions: ClarifyingQuestion[], profile: BusinessProfile | null): ClarifyAnswers {
  const out: ClarifyAnswers = {};
  for (const q of questions) {
    const current = profile ? profile[q.maps_to] : null;
    if (q.kind === "boolean" && typeof current === "boolean") out[q.id] = current;
    if (q.kind === "number" && typeof current === "number") out[q.id] = current;
    if (q.kind === "single_choice" && typeof current === "string" && q.options?.some((o) => o.value === current)) {
      out[q.id] = current;
    }
  }
  return out;
}

export function ClarifyForm({
  questions,
  profile,
  busy,
  onSubmit,
  className,
}: {
  questions: ClarifyingQuestion[];
  profile: BusinessProfile | null;
  busy: boolean;
  onSubmit: (answers: ClarifyAnswers) => void;
  className?: string;
}) {
  const [answers, setAnswers] = useState<ClarifyAnswers>(() => defaultAnswers(questions, profile));
  const set = (id: string, value: string | number | boolean) => setAnswers((a) => ({ ...a, [id]: value }));

  const missing = questions.filter((q) => q.required && (answers[q.id] === undefined || answers[q.id] === ""));

  return (
    <form
      className={cn("rounded-xl border border-signal/30 bg-card p-5 shadow-sm", className)}
      onSubmit={(e) => {
        e.preventDefault();
        if (missing.length > 0 || busy) return;
        onSubmit(answers);
      }}
    >
      <div className="mb-4 flex items-start gap-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-signal-soft text-signal" aria-hidden>
          <MessageCircleQuestion className="size-4" />
        </span>
        <div>
          <h3 className="text-base font-semibold">A few quick questions</h3>
          <p className="text-sm text-muted-foreground">
            These change which permits apply. Answer what you know; we will note any assumptions.
          </p>
        </div>
      </div>

      <div className="space-y-5">
        {questions.map((q) => (
          <fieldset key={q.id} className="space-y-2">
            <legend className="text-sm font-medium">
              {q.question}
              {q.required && <span className="ml-1 text-signal" aria-hidden>*</span>}
            </legend>
            <QuestionInput q={q} value={answers[q.id]} onChange={(v) => set(q.id, v)} />
          </fieldset>
        ))}
      </div>

      <div className="mt-5 flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          {missing.length > 0 ? `${missing.length} required answer${missing.length === 1 ? "" : "s"} left` : "All set"}
        </p>
        <Button type="submit" disabled={busy || missing.length > 0}>
          {busy && <Loader2 className="animate-spin" />}
          Continue
        </Button>
      </div>
    </form>
  );
}

function QuestionInput({
  q,
  value,
  onChange,
}: {
  q: ClarifyingQuestion;
  value: string | number | boolean | undefined;
  onChange: (v: string | number | boolean) => void;
}) {
  const inputId = `clarify-${q.id}`;
  switch (q.kind) {
    case "boolean":
      return (
        <div className="inline-flex rounded-md border border-input bg-background p-0.5" role="radiogroup" aria-label={q.question}>
          {[
            { v: true, label: "Yes" },
            { v: false, label: "No" },
          ].map((opt) => (
            <button
              key={String(opt.v)}
              type="button"
              role="radio"
              aria-checked={value === opt.v}
              onClick={() => onChange(opt.v)}
              className={cn(
                "h-8 min-w-16 rounded-[5px] px-4 text-sm font-medium transition-colors",
                value === opt.v ? "bg-ink text-paper" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      );
    case "number":
      return (
        <Input
          id={inputId}
          type="number"
          inputMode="numeric"
          min={0}
          className="max-w-40"
          value={typeof value === "number" ? value : ""}
          onChange={(e) => {
            const n = e.target.valueAsNumber;
            onChange(Number.isNaN(n) ? "" : n);
          }}
          aria-label={q.question}
        />
      );
    case "single_choice": {
      const options = q.options ?? [];
      if (options.length <= 4) {
        return (
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={q.question}>
            {options.map((o) => (
              <button
                key={o.value}
                type="button"
                role="radio"
                aria-checked={value === o.value}
                onClick={() => onChange(o.value)}
                className={cn(
                  "h-8 rounded-full border px-3.5 text-sm transition-colors",
                  value === o.value
                    ? "border-ink bg-ink text-paper"
                    : "border-input bg-background text-foreground hover:border-ink/50",
                )}
              >
                {o.label}
              </button>
            ))}
          </div>
        );
      }
      return (
        <Select value={typeof value === "string" ? value : undefined} onValueChange={onChange}>
          <SelectTrigger className="w-full max-w-sm" aria-label={q.question}>
            <SelectValue placeholder="Choose one" />
          </SelectTrigger>
          <SelectContent>
            {options.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }
    case "text":
    default:
      return (
        <>
          <Label htmlFor={inputId} className="sr-only">
            {q.question}
          </Label>
          <Input
            id={inputId}
            type="text"
            className="max-w-md"
            value={typeof value === "string" ? value : ""}
            onChange={(e) => onChange(e.target.value)}
          />
        </>
      );
  }
}
