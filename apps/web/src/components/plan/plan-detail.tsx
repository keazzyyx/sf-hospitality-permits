"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Info, Loader2, MapPinOff, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/components/app/app-context";
import { BlockersView } from "@/components/plan/blockers";
import { Checklist } from "@/components/plan/checklist";
import { DependencyGraph } from "@/components/plan/dependencies";
import { FeesView } from "@/components/plan/fees";
import { PlanHeader } from "@/components/plan/plan-header";
import { TimelineView } from "@/components/plan/timeline";
import { ClarifyForm, type ClarifyAnswers } from "@/components/stream/clarify-form";
import { NarrativeBox, StageProgressList } from "@/components/stream/stage-progress";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useGenerationStream } from "@/hooks/use-generation-stream";
import { api, describeApiError, describeErrorCode, isApiError } from "@/lib/api";
import { capture } from "@/lib/analytics";
import type { PlanRecord } from "@/lib/api-types";

export function PlanDetail({ id }: { id: string }) {
  const { accessToken } = useApp();
  const router = useRouter();
  const [record, setRecord] = useState<PlanRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const { state, start } = useGenerationStream();
  const [clarifyError, setClarifyError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { plan } = await api.plan(accessToken, id);
      setRecord(plan);
      setError(null);
    } catch (err) {
      if (isApiError(err) && err.status === 404) setNotFound(true);
      else setError(describeApiError(err));
    }
  }, [accessToken, id]);

  useEffect(() => {
    void load();
  }, [load]);

  // A plan still generating server-side: poll until it settles.
  useEffect(() => {
    if (record?.status !== "generating") return;
    const t = setInterval(() => void load(), 3000);
    return () => clearInterval(t);
  }, [record?.status, load]);

  useEffect(() => {
    if (state.status === "done" && state.plan) {
      capture("plan_completed", { plan_id: state.plan.id, version: state.plan.version, after_clarification: true });
      setRecord(state.plan);
    }
  }, [state.status, state.plan]);

  async function clarify(answers: ClarifyAnswers) {
    setClarifyError(null);
    try {
      await start(`/v1/plans/${encodeURIComponent(id)}/clarify`, { answers }, { token: accessToken });
    } catch (err) {
      if (isApiError(err)) setClarifyError(describeErrorCode(err.code, err.message));
    }
  }

  if (notFound) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-10 text-center">
        <h1 className="text-xl font-semibold">Plan not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">It may have been deleted, or the link belongs to another account.</p>
        <Button className="mt-5" onClick={() => router.push("/app/plans")}>
          Back to checklists
        </Button>
      </div>
    );
  }

  if (error && !record) {
    return (
      <div role="alert" className="rounded-xl border border-dead/30 bg-dead-soft p-5 text-sm text-dead">
        <p className="font-semibold">Could not load this plan</p>
        <p className="mt-1">{error}</p>
        <Button variant="outline" size="sm" className="mt-3 border-dead/40 text-dead hover:bg-dead/10" onClick={load}>
          Retry
        </Button>
      </div>
    );
  }

  if (!record) {
    return (
      <div className="space-y-4" aria-busy>
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-9 w-96 max-w-full" />
        <Skeleton className="h-24" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const plan = record.plan;
  const streaming = state.status === "streaming";

  return (
    <div className="space-y-6">
      <PlanHeader record={record} onUpdated={(next) => setRecord(next)} />

      {record.status === "pending_clarification" && record.clarification && state.status !== "streaming" && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <div className="rounded-xl border border-border bg-card p-5 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">This plan is waiting on your answers</p>
            <p className="mt-1">We paused before matching permits because a few details change what applies.</p>
            {clarifyError && <p className="mt-3 text-dead">{clarifyError}</p>}
          </div>
          <ClarifyForm
            key={record.clarification.questions.map((q) => q.id).join("|")}
            questions={record.clarification.questions}
            profile={record.profile}
            busy={false}
            onSubmit={(a) => void clarify(a)}
          />
        </div>
      )}

      {(streaming || state.status === "clarify") && (
        <div className="grid gap-6 rounded-xl border border-border bg-card p-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <div>
            <p className="mb-3 inline-flex items-center gap-2 text-sm font-medium">
              {streaming && <Loader2 className="size-4 animate-spin text-signal" aria-hidden />}
              {streaming ? "Building your plan" : "One more round of questions"}
            </p>
            <StageProgressList stages={state.stages} streaming={streaming} />
          </div>
          <div className="space-y-4">
            {state.status === "clarify" && state.clarification && (
              <ClarifyForm
                key={state.clarification.questions.map((q) => q.id).join("|")}
                questions={state.clarification.questions}
                profile={state.clarification.profile}
                busy={false}
                onSubmit={(a) => void clarify(a)}
              />
            )}
            <NarrativeBox text={state.narrative} streaming={streaming} />
          </div>
        </div>
      )}

      {state.status === "error" && state.error && (
        <p role="alert" className="flex items-start gap-2 rounded-lg border border-dead/30 bg-dead-soft p-3 text-sm text-dead">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {describeErrorCode(state.error.code, state.error.message)}
        </p>
      )}

      {record.status === "generating" && (
        <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-5 text-sm">
          <Loader2 className="size-4 animate-spin text-signal" aria-hidden />
          This plan is still generating. The page refreshes itself.
        </div>
      )}

      {record.status === "failed" && (
        <div role="alert" className="rounded-xl border border-dead/30 bg-dead-soft p-5 text-sm text-dead">
          <p className="font-semibold">Generation failed</p>
          <p className="mt-1">{record.error ?? "Something went wrong while building this plan. Rerun it to try again; reruns are free."}</p>
        </div>
      )}

      {plan && (
        <>
          {!plan.city_supported && (
            <div className="flex items-start gap-3 rounded-xl border border-estimated/40 bg-estimated-soft p-4 text-sm">
              <MapPinOff className="mt-0.5 size-4 shrink-0 text-estimated" aria-hidden />
              <div>
                <p className="font-semibold">Generic plan — this city is not in our verified catalog yet</p>
                <p className="mt-1 text-foreground/80">
                  {plan.unsupported_city_note ?? "Federal and state items are accurate; city items are typical requirements that you must confirm with your local agencies."}
                </p>
              </div>
            </div>
          )}

          <section className="rounded-xl border border-border bg-card p-5">
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Summary</h2>
            <div className="mt-2 space-y-3 text-sm leading-relaxed">
              {plan.summary.split(/\n{2,}/).map((para, i) => (
                <p key={i}>{para}</p>
              ))}
            </div>
            {record.profile && record.profile.assumptions.length > 0 && (
              <details className="mt-4 text-sm">
                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                  {record.profile.assumptions.length} assumption{record.profile.assumptions.length === 1 ? "" : "s"} we made
                </summary>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
                  {record.profile.assumptions.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              </details>
            )}
          </section>

          <Tabs defaultValue="checklist" className="gap-5">
            <TabsList className="h-auto w-full flex-wrap justify-start gap-1 bg-transparent p-0">
              {[
                ["checklist", `Checklist · ${plan.steps.length}`],
                ["timeline", `Timeline · ${plan.timeline.weeks.length} wks`],
                ["dependencies", "Dependencies"],
                ["fees", "Fees"],
                ["blockers", `Blockers · ${plan.blockers.length}`],
              ].map(([value, label]) => (
                <TabsTrigger key={value} value={value} className="rounded-full border border-border bg-card px-3.5 py-1.5 text-sm data-[state=active]:border-ink data-[state=active]:bg-ink data-[state=active]:text-paper data-[state=active]:shadow-none">
                  {label}
                </TabsTrigger>
              ))}
            </TabsList>
            <TabsContent value="checklist">
              <Checklist record={record} onRecordChange={setRecord} />
            </TabsContent>
            <TabsContent value="timeline">
              <TimelineView plan={plan} />
            </TabsContent>
            <TabsContent value="dependencies">
              <DependencyGraph plan={plan} />
            </TabsContent>
            <TabsContent value="fees">
              <FeesView plan={plan} />
            </TabsContent>
            <TabsContent value="blockers">
              <BlockersView plan={plan} />
            </TabsContent>
          </Tabs>

          {plan.disclaimers.length > 0 && (
            <aside className="rounded-xl border border-border bg-paper-deep/50 p-4 text-xs text-muted-foreground">
              <p className="mb-1.5 inline-flex items-center gap-1.5 font-semibold uppercase tracking-wide">
                <Info className="size-3.5" aria-hidden /> Please read
              </p>
              <ul className="list-disc space-y-1 pl-5">
                {plan.disclaimers.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
              <p className="mt-2 font-mono text-[10px]">
                Generated {new Date(plan.generated_at).toLocaleString("en-US")} · {Object.entries(plan.model_versions).map(([k, v]) => `${k} ${v}`).join(" · ")}
              </p>
            </aside>
          )}
        </>
      )}

      <div className="flex justify-end border-t border-border pt-6">
        <DeletePlan id={record.id} title={record.title} />
      </div>
    </div>
  );
}

function DeletePlan({ id, title }: { id: string; title: string }) {
  const { accessToken } = useApp();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true);
    try {
      await api.deletePlan(accessToken, id);
      toast.success("Plan deleted");
      router.push("/app/plans");
      router.refresh();
    } catch (err) {
      setBusy(false);
      toast.error("Could not delete", { description: describeApiError(err) });
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-dead">
          <Trash2 /> Delete plan
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete this plan?</DialogTitle>
          <DialogDescription>“{title}” and its checklist progress will be removed permanently. This does not refund a free plan.</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
            Keep it
          </Button>
          <Button variant="destructive" onClick={remove} disabled={busy}>
            {busy && <Loader2 className="animate-spin" />} Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
