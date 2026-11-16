"""Neatlogs helpers: PII masking, span attributes, hashed user ids, local doctor.

No `anthropic` import here either - this module is imported before `neatlogs.init()`.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from opentelemetry import trace

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# US-style phone numbers: (415) 555-0123, 415-555-0123, 415.555.0123, +1 415 555 0123
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")

_SENSITIVE_KEY_FRAGMENTS = ("api_key", "authorization", "secret", "token", "password")


def redact_text(value: str) -> str:
    value = EMAIL_RE.sub("[email]", value)
    return PHONE_RE.sub("[phone]", value)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    return value


def mask_pii(span: dict[str, Any]) -> dict[str, Any] | None:
    """Neatlogs `mask=` hook: receives the full span dict, returns the redacted span.

    Redacts emails and phone numbers from every string attribute (including the JSON
    strings Neatlogs stores in `input.value` / `output.value`) and drops any attribute
    whose key looks like a credential. Returning the dict keeps the span; returning None
    would drop it entirely.
    """
    attrs = span.get("attributes")
    if isinstance(attrs, dict):
        cleaned: dict[str, Any] = {}
        for key, value in attrs.items():
            lowered = str(key).lower()
            if any(frag in lowered for frag in _SENSITIVE_KEY_FRAGMENTS):
                cleaned[key] = "[redacted]"
                continue
            cleaned[key] = _redact_value(value)
        span["attributes"] = cleaned
    for list_key in ("events", "logs"):
        items = span.get(list_key)
        if isinstance(items, list):
            span[list_key] = [_redact_value(item) for item in items]
    return span


def hash_user_id(user_id: str, salt: str) -> str:
    """Stable, non-reversible identifier used as the `user_id` span attribute."""
    return hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()[:24]


def _current_span() -> trace.Span:
    """The span a `@neatlogs.span` body is running in.

    neatlogs.init() without a tracer_provider keeps its spans on a private provider ("isolated" mode) and
    threads the active span through a private context key, leaving OTel's global current span untouched, so
    `trace.get_current_span()` returns a non-recording placeholder inside our tool / agent spans and every
    attribute written to it is dropped. Resolve the neatlogs span first; fall back to the global span."""
    try:
        from neatlogs._wrap_utils import active_neatlogs_context

        ctx = active_neatlogs_context()
        if ctx is not None:
            span = trace.get_current_span(ctx)
            if span.is_recording():
                return span
    except Exception:  # private SDK helper moved or changed: degrade to the global span
        pass
    return trace.get_current_span()


def set_span_attributes(**attrs: Any) -> None:
    """Attach filterable attributes to the current Neatlogs/OTel span (no-op when not recording)."""
    span = _current_span()
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, (str, bool, int, float)):
            span.set_attribute(key, value)
        else:
            span.set_attribute(key, json.dumps(value, sort_keys=True, default=str))


def local_doctor() -> dict[str, Any]:
    """Run Neatlogs' network-free local diagnostic (same as `python -m neatlogs doctor --local`)."""
    try:
        from neatlogs.__main__ import _standalone_local

        result = _standalone_local()
        checks = [
            {"name": c.get("name"), "status": c.get("status"), "reason_code": c.get("reason_code")}
            for c in result.get("checks", [])
        ]
        return {
            "status": result.get("status", "unknown"),
            "mode": result.get("mode"),
            "sdk_version": (result.get("runtime") or {}).get("sdk_version"),
            "span_count": (result.get("capture") or {}).get("span_count"),
            "checks": checks,
            "first_failure": result.get("first_failure"),
        }
    except Exception as exc:  # pragma: no cover - defensive: health must never 500
        return {"status": "fail", "error": f"{type(exc).__name__}: {exc}"}
