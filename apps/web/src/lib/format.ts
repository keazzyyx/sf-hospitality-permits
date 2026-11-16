import type { Range } from "@/lib/api-types";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export function formatUsd(n: number): string {
  return usd.format(n);
}

export function formatUsdRange(r: Range): string {
  if (r.min === r.max) return formatUsd(r.min);
  return `${formatUsd(r.min)}–${formatUsd(r.max)}`;
}

export function formatDaysRange(r: Range): string {
  if (r.min === r.max) return `${r.min} ${r.min === 1 ? "day" : "days"}`;
  return `${r.min}–${r.max} days`;
}

/** Parse "YYYY-MM-DD" (or ISO datetime) as a local date without timezone drift. */
export function parseDate(s: string): Date {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return new Date(s);
}

export function formatDate(s: string | null | undefined, opts?: Intl.DateTimeFormatOptions): string {
  if (!s) return "—";
  const d = parseDate(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString("en-US", opts ?? { month: "short", day: "numeric", year: "numeric" });
}

export function formatShortDate(s: string): string {
  return formatDate(s, { month: "short", day: "numeric" });
}

export function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function daysBetween(a: string, b: string): number {
  const ms = parseDate(b).getTime() - parseDate(a).getTime();
  return Math.round(ms / 86_400_000);
}

export function addDays(s: string, days: number): string {
  const d = parseDate(s);
  d.setDate(d.getDate() + days);
  return toIsoDate(d);
}

export function pluralize(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function statusLabel(status: string): string {
  switch (status) {
    case "pending_clarification":
      return "Needs answers";
    case "generating":
      return "Generating";
    case "ready":
      return "Ready";
    case "failed":
      return "Failed";
    default:
      return titleCase(status);
  }
}
