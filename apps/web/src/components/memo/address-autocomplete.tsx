"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Loader2, MapPin } from "lucide-react";
import { cn } from "cn";
import { Input } from "@/components/ui/input";
import { api, isApiError } from "@/lib/api";
import type { GeocodeSuggestion } from "@/lib/api-types";

const DEBOUNCE_MS = 220;
const MIN_QUERY = 3;

export interface AddressAutocompleteProps {
  id?: string;
  value: string;
  onChange: (text: string) => void;
  /** Fired when the user picks a suggestion (keyboard or mouse). `null` when the typed text no longer matches it. */
  onSelect: (s: GeocodeSuggestion | null) => void;
  selected: GeocodeSuggestion | null;
  placeholder?: string;
  className?: string;
  inputClassName?: string;
  autoFocus?: boolean;
  disabled?: boolean;
  "aria-describedby"?: string;
}

/**
 * Address field backed by `GET /v1/geocode?q=` (debounced). Keyboard: ArrowUp/Down move,
 * Enter picks, Escape closes. Each suggestion shows the parcel and zip when the API has them.
 */
export function AddressAutocomplete({
  id,
  value,
  onChange,
  onSelect,
  selected,
  placeholder = "Street address in San Francisco",
  className,
  inputClassName,
  autoFocus,
  disabled,
  "aria-describedby": describedBy,
}: AddressAutocompleteProps) {
  const reactId = useId();
  const inputId = id ?? `address-${reactId}`;
  const listId = `${inputId}-listbox`;
  const [suggestions, setSuggestions] = useState<GeocodeSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const skipNextLookup = useRef(false);

  const lookup = useCallback(async (q: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    try {
      const { suggestions: list } = await api.geocode(q, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setSuggestions(list);
      setActive(list.length > 0 ? 0 : -1);
      setOpen(true);
      setNote(list.length === 0 ? "No San Francisco addresses match yet. Keep typing the street number and name." : null);
    } catch (err) {
      if (controller.signal.aborted) return;
      setSuggestions([]);
      setActive(-1);
      setOpen(true);
      setNote(
        isApiError(err) && err.code === "rate_limited"
          ? "Too many lookups in a minute. Pause a moment and keep typing."
          : "Address lookup is unavailable right now. You can still type the full address and continue.",
      );
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setBusy(false);
      }
    }
  }, []);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (skipNextLookup.current) {
      skipNextLookup.current = false;
      return;
    }
    const q = value.trim();
    if (q.length < MIN_QUERY) {
      abortRef.current?.abort();
      setSuggestions([]);
      setOpen(false);
      setNote(null);
      setBusy(false);
      return;
    }
    timerRef.current = setTimeout(() => void lookup(q), DEBOUNCE_MS);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [value, lookup]);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function pick(s: GeocodeSuggestion) {
    skipNextLookup.current = true;
    onChange(s.address);
    onSelect(s);
    setSuggestions([]);
    setOpen(false);
    setActive(-1);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || suggestions.length === 0) {
      if (e.key === "ArrowDown" && suggestions.length > 0) setOpen(true);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === "Enter") {
      if (active >= 0) {
        e.preventDefault();
        pick(suggestions[active]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  }

  const showList = open && (suggestions.length > 0 || note);

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <div className="relative">
        <MapPin className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input
          id={inputId}
          type="text"
          role="combobox"
          autoComplete="off"
          spellCheck={false}
          aria-autocomplete="list"
          aria-expanded={Boolean(showList)}
          aria-controls={listId}
          aria-activedescendant={open && active >= 0 ? `${listId}-opt-${active}` : undefined}
          aria-describedby={describedBy}
          placeholder={placeholder}
          value={value}
          autoFocus={autoFocus}
          disabled={disabled}
          onChange={(e) => {
            onChange(e.target.value);
            if (selected && e.target.value !== selected.address) onSelect(null);
          }}
          onFocus={() => {
            if (suggestions.length > 0) setOpen(true);
          }}
          onKeyDown={onKeyDown}
          className={cn("h-11 bg-background pl-9 pr-9 text-base", inputClassName)}
        />
        {busy && <Loader2 className="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground" aria-hidden />}
      </div>
      {selected && (
        <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground" data-testid="address-selected">
          <span className="inline-flex items-center gap-1 text-verified">
            <span className="size-1.5 rounded-full bg-verified" aria-hidden /> {selected.normalized_address}
          </span>
          {selected.parcel && <span className="font-mono">Parcel {selected.parcel}</span>}
          {selected.zip_code && <span className="font-mono">{selected.zip_code}</span>}
        </p>
      )}
      {showList && (
        <ul
          id={listId}
          role="listbox"
          aria-label="Address suggestions"
          className="absolute left-0 right-0 top-full z-30 mt-1 max-h-72 overflow-y-auto rounded-lg border border-border bg-popover p-1 shadow-lg"
          data-testid="address-suggestions"
        >
          {suggestions.map((s, i) => (
            <li
              key={`${s.normalized_address}-${i}`}
              id={`${listId}-opt-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(s);
              }}
              className={cn(
                "flex cursor-pointer items-start gap-2.5 rounded-md px-2.5 py-2 text-sm",
                i === active ? "bg-accent text-accent-foreground" : "text-foreground",
              )}
            >
              <MapPin className="mt-0.5 size-4 shrink-0 text-signal" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{s.address}</span>
                <span className="mt-0.5 flex flex-wrap gap-x-3 font-mono text-[11px] text-muted-foreground">
                  {s.parcel ? <span>Parcel {s.parcel}</span> : <span>No parcel</span>}
                  {s.zip_code && <span>{s.zip_code}</span>}
                  <span>{Math.round(s.confidence * 100)}% match</span>
                </span>
              </span>
            </li>
          ))}
          {suggestions.length === 0 && note && (
            <li role="option" aria-selected={false} aria-disabled className="px-2.5 py-2 text-sm text-muted-foreground">
              {note}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
