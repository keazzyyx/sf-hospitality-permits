import { CircleCheck, CircleDashed, Link2Off } from "lucide-react";
import { cn } from "cn";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Confidence, UrlStatus } from "@/lib/api-types";

export const ESTIMATED_TOOLTIP =
  "Fee/timeline not confirmed against the agency page; verify before relying on it";
export const VERIFIED_TOOLTIP = "Fee, timeline and application link confirmed against the agency page";

export function ConfidenceBadge({ confidence, className }: { confidence: Confidence; className?: string }) {
  const verified = confidence === "verified";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          data-confidence={confidence}
          className={cn(
            "inline-flex h-6 items-center gap-1 rounded-full border px-2 text-[11px] font-semibold uppercase tracking-wide",
            verified
              ? "border-verified/30 bg-verified-soft text-verified"
              : "border-estimated/40 bg-estimated-soft text-estimated",
            className,
          )}
        >
          {verified ? <CircleCheck className="size-3.5" aria-hidden /> : <CircleDashed className="size-3.5" aria-hidden />}
          {verified ? "Verified" : "Estimated"}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-64">{verified ? VERIFIED_TOOLTIP : ESTIMATED_TOOLTIP}</TooltipContent>
    </Tooltip>
  );
}

export function UrlStatusFlag({ status, className }: { status: UrlStatus; className?: string }) {
  if (status !== "dead") return null;
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1 rounded-full border border-dead/30 bg-dead-soft px-2 text-[11px] font-semibold uppercase tracking-wide text-dead",
        className,
      )}
    >
      <Link2Off className="size-3.5" aria-hidden />
      Link may be broken
    </span>
  );
}

export function CriticalPathBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1 rounded-full bg-signal px-2 text-[11px] font-semibold uppercase tracking-wide text-white",
        className,
      )}
    >
      Critical path
    </span>
  );
}
