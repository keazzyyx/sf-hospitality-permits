"use client";

import { useMemo } from "react";
import type { Plan, PlanStep } from "@/lib/api-types";

const NODE_W = 196;
const NODE_H = 46;
const GAP_X = 72;
const GAP_Y = 14;
const PAD = 16;

interface Node {
  step: PlanStep;
  layer: number;
  row: number;
  x: number;
  y: number;
}

function layout(steps: PlanStep[]) {
  const byId = new Map(steps.map((s) => [s.id, s]));
  const depth = new Map<string, number>();
  const visiting = new Set<string>();
  const getDepth = (id: string): number => {
    const cached = depth.get(id);
    if (cached !== undefined) return cached;
    if (visiting.has(id)) return 0; // cycle guard
    visiting.add(id);
    const s = byId.get(id);
    const prereqs = s ? s.prerequisites.filter((p) => byId.has(p)) : [];
    const d = prereqs.length === 0 ? 0 : 1 + Math.max(...prereqs.map(getDepth));
    visiting.delete(id);
    depth.set(id, d);
    return d;
  };
  steps.forEach((s) => getDepth(s.id));

  const layers = new Map<number, PlanStep[]>();
  for (const s of steps) {
    const d = depth.get(s.id) ?? 0;
    const arr = layers.get(d) ?? [];
    arr.push(s);
    layers.set(d, arr);
  }
  const nodes = new Map<string, Node>();
  let maxRows = 0;
  Array.from(layers.keys())
    .sort((a, b) => a - b)
    .forEach((layer) => {
      const arr = (layers.get(layer) ?? []).sort((a, b) => a.track.localeCompare(b.track) || a.order - b.order);
      maxRows = Math.max(maxRows, arr.length);
      arr.forEach((step, row) => {
        nodes.set(step.id, { step, layer, row, x: PAD + layer * (NODE_W + GAP_X), y: PAD + row * (NODE_H + GAP_Y) });
      });
    });
  const layerCount = layers.size;
  return {
    nodes,
    width: PAD * 2 + layerCount * NODE_W + Math.max(0, layerCount - 1) * GAP_X,
    height: PAD * 2 + maxRows * NODE_H + Math.max(0, maxRows - 1) * GAP_Y,
  };
}

export function DependencyGraph({ plan }: { plan: Plan }) {
  const { nodes, width, height } = useMemo(() => layout(plan.steps), [plan.steps]);
  const critical = useMemo(() => new Set(plan.timeline.critical_path), [plan.timeline.critical_path]);
  const edges = useMemo(() => {
    const out: { from: Node; to: Node; critical: boolean }[] = [];
    for (const n of nodes.values()) {
      for (const p of n.step.prerequisites) {
        const from = nodes.get(p);
        if (from) out.push({ from, to: n, critical: critical.has(from.step.id) && critical.has(n.step.id) });
      }
    }
    return out;
  }, [nodes, critical]);
  const unlocks = useMemo(() => {
    const m = new Map<string, PlanStep[]>();
    for (const s of plan.steps) for (const p of s.prerequisites) m.set(p, [...(m.get(p) ?? []), s]);
    return m;
  }, [plan.steps]);

  return (
    <div className="space-y-8">
      <section aria-labelledby="dag-title">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 id="dag-title" className="text-base font-semibold">
            What unlocks what
          </h2>
          <p className="text-xs text-muted-foreground">Left to right: a permit can be submitted once everything pointing into it is approved. Orange = critical path.</p>
        </div>
        <div className="overflow-x-auto rounded-xl border border-border bg-card p-2">
          <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Permit dependency graph" className="block max-w-none font-sans">
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
              </marker>
            </defs>
            {edges.map((e, i) => {
              const x1 = e.from.x + NODE_W;
              const y1 = e.from.y + NODE_H / 2;
              const x2 = e.to.x;
              const y2 = e.to.y + NODE_H / 2;
              const c = (x2 - x1) / 2;
              return (
                <path
                  key={i}
                  d={`M${x1},${y1} C${x1 + c},${y1} ${x2 - c},${y2} ${x2},${y2}`}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={e.critical ? 2.5 : 1.25}
                  className={e.critical ? "text-signal" : "text-ink/30"}
                  markerEnd="url(#arrow)"
                />
              );
            })}
            {Array.from(nodes.values()).map((n) => {
              const crit = critical.has(n.step.id);
              return (
                <g key={n.step.id} transform={`translate(${n.x},${n.y})`}>
                  <rect width={NODE_W} height={NODE_H} rx={8} className={crit ? "fill-signal-soft stroke-signal" : "fill-background stroke-border"} strokeWidth={crit ? 2 : 1} />
                  <text x={12} y={19} className="fill-foreground text-[12px] font-semibold">
                    <tspan>{n.step.name.length > 26 ? `${n.step.name.slice(0, 25)}…` : n.step.name}</tspan>
                  </text>
                  <text x={12} y={35} className="fill-muted-foreground text-[10.5px]">
                    <tspan>{n.step.track}</tspan>
                    <tspan dx={6} className="font-mono">{n.step.typical_timeline_days.max}d</tspan>
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      </section>

      <section aria-labelledby="unlock-title">
        <h2 id="unlock-title" className="mb-3 text-base font-semibold">
          Unlock list
        </h2>
        <ul className="divide-y divide-border rounded-xl border border-border bg-card">
          {plan.steps
            .slice()
            .sort((a, b) => a.order - b.order)
            .map((s) => {
              const next = unlocks.get(s.id) ?? [];
              return (
                <li key={s.id} className="flex flex-col gap-1 p-3 text-sm sm:flex-row sm:items-baseline sm:gap-4">
                  <span className="font-medium sm:w-72 sm:shrink-0">
                    <span className="mr-2 font-mono text-xs text-muted-foreground">{String(s.order).padStart(2, "0")}</span>
                    {s.name}
                  </span>
                  <span className="text-muted-foreground">
                    {next.length === 0 ? "Unlocks nothing else — can finish any time before opening" : `unlocks ${next.map((n) => n.name).join(", ")}`}
                  </span>
                </li>
              );
            })}
        </ul>
      </section>
    </div>
  );
}
