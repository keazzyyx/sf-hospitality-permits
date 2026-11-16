"use client";

import { useState } from "react";
import { Loader2, Mail } from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, describeApiError } from "@/lib/api";
import { capture } from "@/lib/analytics";

export function LeadCapture({
  defaultCity = "",
  description,
  compact = false,
  className,
}: {
  defaultCity?: string;
  description?: string;
  compact?: boolean;
  className?: string;
}) {
  const [email, setEmail] = useState("");
  const [city, setCity] = useState(defaultCity);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await api.lead({
        email: email.trim(),
        city: city.trim() || undefined,
        description: description?.slice(0, 2000) || undefined,
      });
      capture("lead_captured", { city: city.trim() || null, source: compact ? "preview" : "landing" });
      toast.success("You're on the list", { description: `We'll email you when ${city.trim() || "your city"} is supported.` });
      setDone(true);
    } catch (err) {
      toast.error("Could not save that", { description: describeApiError(err) });
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className={cn("rounded-lg border border-verified/30 bg-verified-soft p-4 text-sm text-verified", className)}>
        Thanks — we will let you know the moment {city.trim() || "your city"} is live.
      </div>
    );
  }

  return (
    <form onSubmit={submit} className={cn("grid gap-3", compact ? "sm:grid-cols-[1fr_1fr_auto]" : "sm:grid-cols-[1.4fr_1fr_auto]", className)}>
      <div className="grid gap-1.5">
        <Label htmlFor={`lead-email-${compact ? "c" : "l"}`} className={compact ? "sr-only" : undefined}>
          Email
        </Label>
        <Input
          id={`lead-email-${compact ? "c" : "l"}`}
          type="email"
          required
          autoComplete="email"
          placeholder="you@restaurant.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`lead-city-${compact ? "c" : "l"}`} className={compact ? "sr-only" : undefined}>
          City
        </Label>
        <Input
          id={`lead-city-${compact ? "c" : "l"}`}
          type="text"
          placeholder="Portland, OR"
          value={city}
          onChange={(e) => setCity(e.target.value)}
        />
      </div>
      <Button type="submit" disabled={busy} className={compact ? undefined : "sm:self-end"}>
        {busy ? <Loader2 className="animate-spin" /> : <Mail />}
        Notify me
      </Button>
    </form>
  );
}
