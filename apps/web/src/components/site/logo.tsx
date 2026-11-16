import Link from "next/link";
import { cn } from "cn";
import { APP_NAME } from "@/lib/brand";

export function Logo({ className, inverted = false, href = "/" }: { className?: string; inverted?: boolean; href?: string }) {
  return (
    <Link href={href} className={cn("inline-flex items-center gap-2.5 font-display text-lg font-semibold tracking-tight", className)} aria-label={`${APP_NAME} home`}>
      <span
        className={cn(
          "grid size-8 place-items-center rounded-lg text-base font-bold",
          inverted ? "bg-paper text-ink" : "bg-ink text-paper",
        )}
        aria-hidden
      >
        P
        <span className="ml-0.5 inline-block size-1.5 rounded-full bg-signal" />
      </span>
      <span className={inverted ? "text-paper" : "text-ink"}>{APP_NAME}</span>
    </Link>
  );
}
