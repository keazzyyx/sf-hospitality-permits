import { CircleAlert, CircleCheck, CircleDashed, CircleHelp, CircleX } from "lucide-react";
import { cn } from "cn";
import { RECORD_KIND_CLASSES, STATUS_CLASSES, STATUS_LABELS, isRecordKind, recordKindLabel } from "@/lib/memo";
import type { ApprovalStatus } from "@/lib/api-types";

const ICONS: Record<ApprovalStatus, typeof CircleCheck> = {
  allowed: CircleCheck,
  further_review: CircleDashed,
  potential_blocker: CircleAlert,
  not_permitted: CircleX,
  insufficient_information: CircleHelp,
};

/**
 * Status pill for one approval row or the overall line: Allowed, Further review, Potential blocker,
 * Not permitted, Insufficient information.
 */
export function StatusPill({ status, size = "md", className }: { status: ApprovalStatus; size?: "sm" | "md" | "lg"; className?: string }) {
  const Icon = ICONS[status] ?? CircleHelp;
  return (
    <span
      data-testid="status-pill"
      data-status={status}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border font-semibold",
        size === "sm" && "h-6 px-2 text-[11px]",
        size === "md" && "h-7 px-2.5 text-xs",
        size === "lg" && "h-9 px-3.5 text-sm",
        STATUS_CLASSES[status] ?? STATUS_CLASSES.insufficient_information,
        className,
      )}
    >
      <Icon className={size === "lg" ? "size-4" : "size-3.5"} aria-hidden />
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

/**
 * What kind of record a row is: Use decision, Agency referral, Building work, ABC licence and so on.
 * Neutral on purpose (a kind is not a status); building work is a dashed outline so it reads apart from use decisions.
 */
export function RecordKindBadge({ kind, label, className, testId = "record-kind" }: { kind: string; label?: string | null; className?: string; testId?: string }) {
  return (
    <span
      data-testid={testId}
      data-kind={kind}
      className={cn(
        "inline-flex shrink-0 items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4",
        isRecordKind(kind) ? RECORD_KIND_CLASSES[kind] : RECORD_KIND_CLASSES.other,
        className,
      )}
    >
      {recordKindLabel(kind, label)}
    </span>
  );
}

/** Muted tag for memos stored before report format 3 (lists and tables). */
export function EarlierFormatTag({ className }: { className?: string }) {
  return (
    <span
      data-testid="earlier-format-tag"
      className={cn("inline-flex h-6 shrink-0 items-center whitespace-nowrap rounded-full border border-border bg-muted px-2 text-[11px] font-medium text-muted-foreground", className)}
    >
      Earlier format
    </span>
  );
}
