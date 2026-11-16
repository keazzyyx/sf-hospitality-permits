"use client";

import type { PostHog } from "posthog-js";
import { env } from "@/lib/env";

/** The exact event vocabulary from docs/api-contract.md and docs/api-contract-memo.md. */
export type AnalyticsEvent =
  | "plan_started"
  | "plan_completed"
  | "signup"
  | "paywall_hit"
  | "upgrade"
  | "preview_started"
  | "preview_completed"
  | "clarification_shown"
  | "step_toggled"
  | "pdf_exported"
  | "lead_captured"
  // Location Risk Memo (docs/api-contract-memo.md)
  | "memo_started"
  | "memo_completed"
  | "memo_teaser_viewed"
  | "memo_unlocked"
  | "memo_paywall_hit"
  | "memo_pdf_exported"
  | "memo_answers_rerun"
  | "bulk_uploaded"
  | "feedback_submitted";

type Queued =
  | { kind: "capture"; event: AnalyticsEvent; props?: Record<string, unknown> }
  | { kind: "identify"; userId: string; props?: Record<string, unknown> }
  | { kind: "reset" };

let client: PostHog | null = null;
let loading: Promise<void> | null = null;
const queue: Queued[] = [];

export function analyticsEnabled(): boolean {
  return typeof window !== "undefined" && Boolean(env.posthogKey);
}

function flush() {
  if (!client) return;
  for (const item of queue.splice(0)) {
    if (item.kind === "capture") client.capture(item.event, item.props);
    else if (item.kind === "identify") client.identify(item.userId, item.props);
    else client.reset();
  }
}

/**
 * Initialise PostHog once, only when a key is configured. The SDK is loaded on
 * demand so unconfigured deployments never ship it. Safe to call repeatedly.
 */
export function initAnalytics(): void {
  if (client || loading || !analyticsEnabled()) return;
  loading = import("posthog-js")
    .then(({ default: posthog }) => {
      posthog.init(env.posthogKey, {
        api_host: env.posthogHost,
        capture_pageview: true,
        capture_pageleave: true,
        persistence: "localStorage+cookie",
        autocapture: false,
      });
      client = posthog;
      flush();
    })
    .catch(() => {
      // Analytics must never break the product.
      queue.length = 0;
    });
}

function enqueue(item: Queued) {
  if (!analyticsEnabled()) return;
  queue.push(item);
  if (client) flush();
  else initAnalytics();
}

export function capture(event: AnalyticsEvent, props?: Record<string, unknown>): void {
  enqueue({ kind: "capture", event, props });
}

export function identify(userId: string, props?: Record<string, unknown>): void {
  enqueue({ kind: "identify", userId, props });
}

export function resetAnalytics(): void {
  enqueue({ kind: "reset" });
}
