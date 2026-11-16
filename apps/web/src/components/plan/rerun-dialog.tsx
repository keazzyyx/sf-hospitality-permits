"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { useApp } from "@/components/app/app-context";
import { ClarifyForm, type ClarifyAnswers } from "@/components/stream/clarify-form";
import { NarrativeBox, StageProgressList } from "@/components/stream/stage-progress";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useGenerationStream } from "@/hooks/use-generation-stream";
import { capture } from "@/lib/analytics";
import { describeErrorCode, isApiError } from "@/lib/api";
import { toIsoDate } from "@/lib/format";
import type { BusinessProfile, PlanRecord } from "@/lib/api-types";

type ToggleKey = "serves_alcohol" | "live_entertainment" | "outdoor_seating" | "exterior_signage" | "closes_after_midnight";

const TOGGLES: { key: ToggleKey; label: string; hint: string }[] = [
  { key: "serves_alcohol", label: "Serves alcohol", hint: "Adds state and local liquor licensing" },
  { key: "live_entertainment", label: "Live music or performance", hint: "Entertainment and amplified-sound permits" },
  { key: "outdoor_seating", label: "Outdoor seating", hint: "Sidewalk cafe or parklet permits" },
  { key: "exterior_signage", label: "Exterior signage", hint: "Sign permit and design review" },
  { key: "closes_after_midnight", label: "Open after midnight", hint: "Late-hours permits and conditions" },
];

export function RerunDialog({ plan, onUpdated }: { plan: PlanRecord; onUpdated: (next: PlanRecord) => void }) {
  const { accessToken } = useApp();
  const { state, start, reset } = useGenerationStream();
  const [open, setOpen] = useState(false);
  const [description, setDescription] = useState(plan.description);
  const [targetDate, setTargetDate] = useState(plan.target_open_date ?? "");
  const [toggles, setToggles] = useState<Partial<Record<ToggleKey, boolean>>>({});
  const [error, setError] = useState<string | null>(null);
  const streaming = state.status === "streaming";
  const minDate = toIsoDate(new Date());

  useEffect(() => {
    if (!open) return;
    setDescription(plan.description);
    setTargetDate(plan.target_open_date ?? "");
    setToggles({});
    setError(null);
    reset();
  }, [open, plan.description, plan.target_open_date, reset]);

  useEffect(() => {
    if (state.status === "done" && state.plan) {
      capture("plan_completed", { plan_id: state.plan.id, version: state.plan.version, rerun: true });
      onUpdated(state.plan);
      setOpen(false);
    }
  }, [state.status, state.plan, onUpdated]);

  useEffect(() => {
    if (state.status === "clarify" && state.clarification) {
      capture("clarification_shown", { context: "rerun", questions: state.clarification.questions.length });
    }
  }, [state.status, state.clarification]);

  const profileValue = (key: ToggleKey): boolean => {
    if (key in toggles) return Boolean(toggles[key]);
    return Boolean(plan.profile?.[key]);
  };

  async function run() {
    setError(null);
    const overrides: Partial<BusinessProfile> = {};
    for (const t of TOGGLES) {
      if (t.key in toggles && toggles[t.key] !== Boolean(plan.profile?.[t.key])) overrides[t.key] = toggles[t.key];
    }
    const body: { description?: string; target_open_date?: string; profile_overrides?: Partial<BusinessProfile> } = {};
    if (description.trim() !== plan.description) body.description = description.trim();
    if ((targetDate || null) !== (plan.target_open_date ?? null)) body.target_open_date = targetDate || undefined;
    if (Object.keys(overrides).length > 0) body.profile_overrides = overrides;
    capture("plan_started", { rerun: true, plan_id: plan.id, overrides: Object.keys(overrides) });
    try {
      await start(`/v1/plans/${encodeURIComponent(plan.id)}/rerun`, body, { token: accessToken });
    } catch (err) {
      if (isApiError(err)) setError(describeErrorCode(err.code, err.message));
    }
  }

  async function clarify(answers: ClarifyAnswers) {
    setError(null);
    try {
      await start(`/v1/plans/${encodeURIComponent(plan.id)}/clarify`, { answers }, { token: accessToken });
    } catch (err) {
      if (isApiError(err)) setError(describeErrorCode(err.code, err.message));
    }
  }

  const busy = streaming || state.status === "clarify";

  return (
    <Dialog open={open} onOpenChange={(v) => (!streaming ? setOpen(v) : undefined)}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline">
          <RefreshCw /> Update inputs &amp; rerun
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Update inputs and rerun</DialogTitle>
          <DialogDescription>
            Produces version {plan.version + 1}. Steps you have already ticked stay ticked when they still apply. Reruns are free.
          </DialogDescription>
        </DialogHeader>

        {!busy ? (
          <div className="space-y-5">
            <div className="grid gap-1.5">
              <Label htmlFor="rerun-description">Description</Label>
              <Textarea id="rerun-description" rows={5} value={description} onChange={(e) => setDescription(e.target.value)} className="resize-y" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="rerun-target">Target open date</Label>
              <Input id="rerun-target" type="date" min={minDate} value={targetDate} onChange={(e) => setTargetDate(e.target.value)} className="sm:w-48" />
            </div>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Profile overrides</legend>
              <p className="text-xs text-muted-foreground">Force a detail the planner may have missed or assumed.</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {TOGGLES.map((t) => (
                  <label key={t.key} className="flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-background p-3 text-sm has-[[data-state=checked]]:border-ink/50">
                    <Checkbox checked={profileValue(t.key)} onCheckedChange={(v) => setToggles((s) => ({ ...s, [t.key]: v === true }))} className="mt-0.5" />
                    <span>
                      <span className="font-medium">{t.label}</span>
                      <span className="block text-xs text-muted-foreground">{t.hint}</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            {(error || state.status === "error") && (
              <p role="alert" className="flex items-start gap-2 rounded-lg border border-dead/30 bg-dead-soft p-3 text-sm text-dead">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
                {error ?? (state.error ? describeErrorCode(state.error.code, state.error.message) : "Something went wrong.")}
              </p>
            )}
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="button" onClick={run} disabled={description.trim().length < 12}>
                <RefreshCw /> Rerun plan
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-5">
            <p className="inline-flex items-center gap-2 text-sm font-medium">
              {streaming && <Loader2 className="size-4 animate-spin text-signal" aria-hidden />}
              {streaming ? "Rebuilding your plan" : "A couple of questions first"}
            </p>
            <StageProgressList stages={state.stages} streaming={streaming} />
            <NarrativeBox text={state.narrative} streaming={streaming} />
            {state.status === "clarify" && state.clarification && (
              <ClarifyForm
                key={state.clarification.questions.map((q) => q.id).join("|")}
                questions={state.clarification.questions}
                profile={state.clarification.profile}
                busy={false}
                onSubmit={(a) => void clarify(a)}
              />
            )}
            {error && (
              <p role="alert" className="flex items-start gap-2 rounded-lg border border-dead/30 bg-dead-soft p-3 text-sm text-dead">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {error}
              </p>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
