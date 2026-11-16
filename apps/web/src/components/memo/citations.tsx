"use client";

import { createContext, useContext, useMemo } from "react";
import { ExternalLink } from "lucide-react";
import { cn } from "cn";
import { Badge } from "@/components/ui/badge";
import { buildCitationIndex, CITATION_KIND_CLASSES, CITATION_KIND_LABELS, footnoteId, type CitationIndex } from "@/lib/memo";
import type { Citation } from "@/lib/api-types";

const CitationContext = createContext<CitationIndex | null>(null);

/** Provides the memo's citation numbering to every `<Cite>` below it. */
export function CitationProvider({ citations, children }: { citations: Citation[]; children: React.ReactNode }) {
  const index = useMemo(() => buildCitationIndex(citations), [citations]);
  return <CitationContext.Provider value={index}>{children}</CitationContext.Provider>;
}

export function useCitationIndex(): CitationIndex {
  const ctx = useContext(CitationContext);
  if (ctx) return ctx;
  return { numbers: new Map(), ordered: [] };
}

function scrollToFootnote(e: React.MouseEvent<HTMLAnchorElement>, n: number) {
  const el = document.getElementById(footnoteId(n));
  if (!el) return;
  e.preventDefault();
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("ring-2", "ring-signal/60");
  window.setTimeout(() => el.classList.remove("ring-2", "ring-signal/60"), 1600);
  history.replaceState(null, "", `#${footnoteId(n)}`);
}

/**
 * Renders `citations: string[]` as [n] superscripts that resolve to `memo.citations` by id.
 * Unknown ids are skipped rather than rendered as dangling references.
 */
export function Cite({ ids, className }: { ids: string[]; className?: string }) {
  const { numbers, ordered } = useCitationIndex();
  const refs = Array.from(new Set(ids))
    .map((id) => numbers.get(id))
    .filter((n): n is number => typeof n === "number")
    .sort((a, b) => a - b);
  if (refs.length === 0) return null;
  return (
    <sup className={cn("ml-0.5 inline-flex gap-0.5 align-super text-[0.68em] font-medium leading-none", className)} data-testid="citation-refs">
      {refs.map((n) => (
        <a
          key={n}
          href={`#${footnoteId(n)}`}
          onClick={(e) => scrollToFootnote(e, n)}
          className="rounded px-0.5 text-signal underline-offset-2 hover:bg-signal-soft hover:underline"
          title={ordered[n - 1]?.label}
          aria-label={`Citation ${n}: ${ordered[n - 1]?.label ?? ""}`}
        >
          [{n}]
        </a>
      ))}
    </sup>
  );
}

export function CitationKindBadge({ kind, className }: { kind: Citation["kind"]; className?: string }) {
  return (
    <Badge variant="outline" className={cn("text-[10px] uppercase tracking-wide", CITATION_KIND_CLASSES[kind], className)}>
      {CITATION_KIND_LABELS[kind]}
    </Badge>
  );
}

/** Numbered footnote list: kind badge, label, excerpt and a link to the public record. */
export function CitationList({ className }: { className?: string }) {
  const { ordered } = useCitationIndex();
  if (ordered.length === 0) return null;
  return (
    <ol className={cn("space-y-3", className)} data-testid="citation-list">
      {ordered.map((c, i) => {
        const n = i + 1;
        return (
          <li
            key={c.id}
            id={footnoteId(n)}
            className="scroll-mt-24 rounded-lg border border-border bg-card p-3 text-sm transition-shadow"
            data-testid="citation-footnote"
          >
            <div className="flex flex-wrap items-start gap-2">
              <span className="font-mono text-xs text-muted-foreground tabular">[{n}]</span>
              <CitationKindBadge kind={c.kind} />
              <span className="min-w-0 flex-1 font-medium leading-snug">{c.label}</span>
              <a
                href={c.source_url}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex shrink-0 items-center gap-1 text-xs text-signal hover:underline"
              >
                Open record <ExternalLink className="size-3" aria-hidden />
              </a>
            </div>
            {c.excerpt && <blockquote className="mt-2 border-l-2 border-border pl-3 text-muted-foreground">“{c.excerpt}”</blockquote>}
            <p className="mt-1.5 break-all font-mono text-[10px] text-muted-foreground/70">{c.id}</p>
          </li>
        );
      })}
    </ol>
  );
}
