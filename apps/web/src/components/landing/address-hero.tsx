"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowRight, Loader2, Sparkles } from "lucide-react";
import { AddressAutocomplete } from "@/components/memo/address-autocomplete";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSession } from "@/hooks/use-session";
import { capture } from "@/lib/analytics";
import { memoQuery, savePendingMemo } from "@/lib/pending-memo";
import type { GeocodeSuggestion } from "@/lib/api-types";

const MIN_DESCRIPTION = 12;
const CONCEPTS = [
  { label: "Wine bar", text: "40-seat wine bar, small kitchen, open until 1am, occasional live music" },
  { label: "Cocktail bar", text: "Cocktail bar with DJ on weekends, 60 seats, open until 2am" },
  { label: "Cafe", text: "Daytime cafe with pastries from a commissary, beer and wine, closes 6pm" },
  { label: "Restaurant", text: "Full-service restaurant, full liquor, 90 seats, sidewalk tables" },
];

/**
 * Landing hero form: address (autocomplete via GET /v1/geocode) + concept → `/memo?…`.
 * Signed-out visitors get the input saved under `pp_pending_memo` and are sent to `/login?next=/memo`.
 */
export function AddressHero() {
  const router = useRouter();
  const { user, loading, configured } = useSession();
  const [address, setAddress] = useState("");
  const [selected, setSelected] = useState<GeocodeSuggestion | null>(null);
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const addr = address.trim();
    const text = description.trim();
    if (addr.length < 5) {
      setError("Enter the street address you are considering (number, street, San Francisco).");
      return;
    }
    if (text.length < MIN_DESCRIPTION) {
      setError("Describe the concept in a sentence: seats, kitchen, alcohol, closing time, music.");
      textareaRef.current?.focus();
      return;
    }
    setError(null);
    setBusy(true);
    const input = { address: addr, description: text, lat: selected?.lat ?? null, lng: selected?.lng ?? null };
    savePendingMemo(input);
    capture("memo_started", { source: "landing", signed_in: Boolean(user), has_coords: selected !== null, length: text.length });
    const signedIn = configured && !loading && Boolean(user);
    if (signedIn) router.push(`/memo?${memoQuery(input)}`);
    else router.push("/login?next=%2Fmemo");
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-2xl border border-border bg-card p-4 shadow-[0_1px_0_rgba(20,27,45,0.04),0_12px_40px_-24px_rgba(20,27,45,0.35)] sm:p-6"
      aria-label="Check an address"
      data-testid="address-hero"
    >
      <Label htmlFor="hero-address" className="text-base font-semibold">
        The address you are considering
      </Label>
      <p className="mt-1 text-sm text-muted-foreground">San Francisco for now. Pick a suggestion so we pin the parcel.</p>
      <AddressAutocomplete
        id="hero-address"
        value={address}
        onChange={setAddress}
        onSelect={setSelected}
        selected={selected}
        placeholder="2500 Mission St, San Francisco"
        className="mt-2"
        aria-describedby="hero-address-help"
      />
      <p id="hero-address-help" className="sr-only">
        Suggestions appear as you type. Use the arrow keys and Enter to pick one.
      </p>

      <Label htmlFor="hero-description" className="mt-5 block text-base font-semibold">
        The concept
      </Label>
      <Textarea
        ref={textareaRef}
        id="hero-description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={3}
        maxLength={2000}
        placeholder="40-seat wine bar, small kitchen, open until 1am, occasional live music"
        className="mt-2 min-h-24 resize-y bg-background text-base leading-relaxed"
        aria-describedby="hero-concept-help"
      />
      <div id="hero-concept-help" className="mt-3 flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <Sparkles className="size-3.5" aria-hidden /> Try one:
        </span>
        {CONCEPTS.map((c) => (
          <button
            key={c.label}
            type="button"
            onClick={() => {
              setDescription(c.text);
              setError(null);
            }}
            className="rounded-full border border-border bg-background px-3 py-1 text-xs font-medium text-foreground transition-colors hover:border-ink/40 hover:bg-accent"
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-muted-foreground">Free account · your first memo teasers are free · no card</p>
        <Button type="submit" size="lg" className="h-11 px-6 text-base" disabled={busy} data-testid="hero-submit">
          {busy ? <Loader2 className="animate-spin" /> : null}
          Check this address <ArrowRight />
        </Button>
      </div>

      {error && (
        <p role="alert" className="mt-4 flex items-start gap-2 rounded-lg border border-dead/30 bg-dead-soft p-3 text-sm text-dead">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {error}
        </p>
      )}
    </form>
  );
}
