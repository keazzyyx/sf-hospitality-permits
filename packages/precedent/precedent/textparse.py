"""Shared text heuristics: use types, closing hours, conditions and opposition in permit descriptions."""

from __future__ import annotations

import re

from precedent.models import UseType

_USE_PATTERNS: list[tuple[UseType, re.Pattern[str]]] = [
    ("nightclub", re.compile(r"\b(nightclub|night club|dance ?hall|dancing|dj\b|cabaret)", re.I)),
    (
        "bar",
        re.compile(
            r"\b(bar|tavern|pub|saloon|taproom|tap room|wine bar|cocktail|lounge|brew ?pub|beer garden|type 4[28]|on-sale general public premises|on-sale beer and wine public premises)\b",
            re.I,
        ),
    ),
    (
        "restaurant",
        re.compile(
            r"\b(restaurant|eating place|bona fide|full[- ]service|limited[- ]restaurant|type 4[17]\b|diner|pizzeria|taqueria|bistro)\b",
            re.I,
        ),
    ),
    ("cafe", re.compile(r"\b(caf[eé]|coffee|bakery|tea house|ice cream)\b", re.I)),
    (
        "live_entertainment",
        re.compile(
            r"\b(live (music|entertainment|performance)|place of entertainment|limited live|amplified|concert|karaoke|comedy)\b",
            re.I,
        ),
    ),
    (
        "outdoor_seating",
        re.compile(
            r"\b(outdoor (seating|dining|activity)|sidewalk (seating|caf)|parklet|patio|rooftop)\b", re.I
        ),
    ),
    ("hotel", re.compile(r"\b(hotel|motel|hostel|tourist hotel|inn\b|bed and breakfast)", re.I)),
    (
        "retail_alcohol",
        re.compile(r"\b(liquor store|off-sale|type 2[01]\b|grocery|convenience store|market)\b", re.I),
    ),
    ("cannabis", re.compile(r"\b(cannabis|dispensary|marijuana|mcd)\b", re.I)),
]

_HOUR_RE = re.compile(
    r"(?:until|till|to|close[sd]? (?:at|by)|closing (?:at|time of)|hours? (?:of operation )?(?:until|to|of))\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)",
    re.I,
)
_HOUR_RANGE_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\s*(?:-|–|to)\s*(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)",
    re.I,
)

_CONDITION_PATTERNS = [
    re.compile(r"(?:no|without) (?:dancing|dj|amplified)", re.I),
    re.compile(r"security (?:plan|personnel|guard)", re.I),
    re.compile(r"(?:good neighbor|community liaison|noise|sound(?:proof)?ing|sound attenuation)", re.I),
    re.compile(
        r"(?:hours (?:of operation )?(?:limited|restricted|shall)|shall close|close by|closing time)", re.I
    ),
    re.compile(r"(?:no (?:alcohol|liquor) (?:sales|service) after|last call)", re.I),
    re.compile(r"(?:abc|type \d{2}) license (?:shall|must|limited)", re.I),
]
_OPPOSITION_RE = re.compile(
    r"\b(opposition|opposed|objection|protest(?:ed|s)?|letters? (?:in )?opposition|neighbors? (?:spoke|testified) against|dr request|discretionary review requested|appeal(?:ed)?)\b",
    re.I,
)
_SUPPORT_ONLY_RE = re.compile(r"\bno (?:opposition|objections?|public comment)\b|\bunopposed\b", re.I)


def classify_use_types(text: str) -> list[UseType]:
    found: list[UseType] = [use for use, pat in _USE_PATTERNS if pat.search(text or "")]
    return found or []


def _to_24h(hour: int, minute: int, meridiem: str) -> str:
    m = meridiem.lower().replace(".", "")
    h = hour % 12
    if m.startswith("p"):
        h += 12
    return f"{h:02d}:{minute:02d}"


def extract_closing_hour(text: str) -> str | None:
    """Latest closing time in the text as 'HH:MM' (24h); None when nothing parseable."""
    if not text:
        return None
    candidates: list[str] = []
    for m in _HOUR_RE.finditer(text):
        candidates.append(_to_24h(int(m.group(1)), int(m.group(2) or 0), m.group(3)))
    for m in _HOUR_RANGE_RE.finditer(text):
        candidates.append(_to_24h(int(m.group(4)), int(m.group(5) or 0), m.group(6)))
    if not candidates:
        return None

    def latest_key(hhmm: str) -> int:
        h, mm = map(int, hhmm.split(":"))
        # 00:00–06:00 count as "after midnight" → later than evening hours
        return (h + 24 if h < 6 else h) * 60 + mm

    return max(candidates, key=latest_key)


def is_late_night(hours_close: str | None) -> bool | None:
    if hours_close is None:
        return None
    h = int(hours_close.split(":")[0])
    return h < 6 or h >= 24


def extract_conditions(text: str) -> list[str]:
    """Sentences that read like imposed conditions."""
    out: list[str] = []
    for sentence in re.split(r"(?<=[.;])\s+", text or ""):
        s = sentence.strip()
        if 12 <= len(s) <= 400 and any(p.search(s) for p in _CONDITION_PATTERNS):
            out.append(s)
    return out[:12]


def detect_opposition(text: str) -> bool | None:
    if not text:
        return None
    if _SUPPORT_ONLY_RE.search(text):
        return False
    if _OPPOSITION_RE.search(text):
        return True
    return None
