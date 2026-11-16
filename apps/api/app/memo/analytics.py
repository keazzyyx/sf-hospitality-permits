"""Deterministic numbers for the memo: comparable ranking, base rate, density.

The model interprets these; it never computes them.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass
from typing import cast

from precedent.models import Application, Business, Overlay
from precedent.store.base import Nearby, ZoningInfo

from app.models.memo import PATHWAY_RECORD_KINDS, RecordKind
from app.models.profile import BusinessProfile

ON_SALE_TYPES = {
    "40",
    "41",
    "42",
    "47",
    "48",
    "49",
    "51",
    "52",
    "57",
    "58",
    "59",
    "61",
    "64",
    "70",
    "75",
    "78",
    "86",
}
FT_500_M = 152.4
FT_1000_M = 304.8


def concept_use_types(profile: BusinessProfile) -> list[str]:
    uses: list[str] = []
    if profile.business_type == "bar":
        uses.append("bar")
    if profile.business_type in {"restaurant", "cafe", "catering"} or (
        profile.serves_food and profile.business_type != "bar"
    ):
        uses.append("restaurant" if profile.business_type != "cafe" else "cafe")
    if profile.business_type == "hotel":
        uses.append("hotel")
    if profile.dancing or (profile.business_type == "bar" and profile.closes_after_2am):
        uses.append("nightclub")
    if profile.live_entertainment or profile.amplified_sound or profile.dancing:
        uses.append("live_entertainment")
    if profile.outdoor_seating or profile.sidewalk_or_parklet:
        uses.append("outdoor_seating")
    return uses or ["other"]


def concept_needs_cua(profile: BusinessProfile, zoning: ZoningInfo | None, overlays: list[Overlay]) -> bool:
    if profile.business_type == "bar" and zoning and zoning.bar_permission in {"conditional", "prohibited"}:
        return True
    if profile.closes_after_2am:
        return True
    return any(o.kind == "alcohol_sud" and profile.serves_alcohol for o in overlays)


@dataclass(frozen=True)
class Scored:
    app: Application
    distance_m: float
    score: float
    reasons: tuple[str, ...]


def similarity(app: Application, distance_m: float, profile: BusinessProfile, today: dt.date) -> Scored:
    """0..1: use-type overlap (0.40), distance (0.25), recency (0.15), hours (0.10), decided (0.10)."""
    want = set(concept_use_types(profile))
    have = set(app.use_types)
    reasons: list[str] = []
    overlap = len(want & have) / len(want | have) if (want | have) else 0.0
    if overlap:
        reasons.append(f"use overlap {sorted(want & have)}")
    dist = max(0.0, 1.0 - distance_m / 1000.0)
    date = app.decided_at or app.filed_at
    years = (today - date).days / 365.25 if date else 10.0
    recency = max(0.0, 1.0 - years / 10.0)
    if years <= 5:
        reasons.append(f"decided {date}" if app.decided_at else f"filed {date}")
    want_late = profile.closes_after_midnight
    hours = (
        1.0
        if (app.late_night is not None and app.late_night == want_late)
        else (0.5 if app.late_night is None else 0.0)
    )
    if app.late_night and want_late:
        reasons.append("also late-night")
    decided = 1.0 if app.outcome in {"approved", "approved_with_conditions", "denied"} else 0.4
    kind_bonus = 0.0
    if app.kind == "cua":
        kind_bonus = 0.05
    score = min(
        1.0, 0.40 * overlap + 0.25 * dist + 0.15 * recency + 0.10 * hours + 0.10 * decided + kind_bonus
    )
    return Scored(app=app, distance_m=distance_m, score=round(score, 3), reasons=tuple(reasons))


def rank_candidates(
    nearby: list[Nearby[Application]], profile: BusinessProfile, today: dt.date, *, limit: int = 20
) -> list[Scored]:
    """The comparable candidates, best first. ABC licences are never candidates. A labelled Planning row is a
    candidate only when it is a use decision or an agency referral about a food, drink or entertainment
    premises (`is_pathway_candidate`); rows without labels are ranked as before."""
    scored = [
        similarity(n.item, n.distance_m, profile, today)
        for n in nearby
        if n.item.kind != "abc_license" and is_pathway_candidate(n.item)
    ]
    scored = [s for s in scored if s.score > 0.15]
    scored.sort(key=lambda s: (-s.score, s.distance_m, s.app.id))
    return scored[:limit]


CANDIDATE_WINDOW = 200  # rows the comparables are ranked from: the nearest non-licence rows within 1,000 ft


def fill_candidate_window(
    nearest: list[Nearby[Application]], wider: list[Nearby[Application]], *, limit: int = CANDIDATE_WINDOW
) -> list[Nearby[Application]]:
    """`nearest` (the `limit` nearest non-licence rows) topped up from `wider` (every row within 1,000 ft the
    base rate reads) until it holds `limit` rows that may be comparables.

    Labelled building work, other records and records about other premises can never be comparables
    (`is_pathway_candidate`), yet on a crowded block they fill the nearest rows and push the real use
    decisions out. The rows added are the nearest ones in `wider` that may be comparables and are not ABC
    licences, each id once; the rows of `nearest` are all kept, in order. With no labels every row may be a
    comparable, so nothing is added and the result is `nearest`."""
    have = {n.item.id for n in nearest}
    missing = limit - sum(1 for n in nearest if n.item.kind != "abc_license" and is_pathway_candidate(n.item))
    added: list[Nearby[Application]] = []
    for n in sorted(wider, key=lambda n: (n.distance_m, n.item.id)):
        if len(added) >= missing:
            break
        if n.item.id in have or n.item.kind == "abc_license" or not is_pathway_candidate(n.item):
            continue
        have.add(n.item.id)
        added.append(n)
    return [*nearest, *added]


@dataclass(frozen=True)
class BaseRate:
    """Counts of dated Planning decisions near the address. `total` is N; a rate exists only when N >= 10."""

    approved: int
    approved_with_conditions: int
    denied: int
    withdrawn: int
    total: int
    window_years: int
    scope: str
    excluded_grant_only: int = 0
    excluded_undated: int = 0
    excluded_not_use_decision: int = 0
    # the decisions counted (the N), so the report can list each with its source link
    counted: tuple[Application, ...] = ()

    @property
    def rate_shown(self) -> bool:
        return self.total >= MIN_RATE_CASES

    @property
    def approval_rate_pct(self) -> float | None:
        """Approvals as a share of N (withdrawals count against it). None when N is under 10."""
        if not self.rate_shown:
            return None
        return round(100.0 * (self.approved + self.approved_with_conditions) / self.total, 1)


# The pool: Planning applications only. Entertainment Commission permits and ABC licences are lists of grants
# (no denials, no withdrawals, mostly no dates), so they can never show a failure and never enter a rate.
PLANNING_SOURCES = frozenset({"datasf_planning", "sf_planning_hearings"})
BASE_RATE_KINDS = frozenset({"cua", "planning_other"})
ENTERTAINMENT_KINDS = frozenset(
    {"entertainment_poe", "entertainment_llp", "entertainment_sound", "entertainment_other"}
)
GRANT_ONLY_SOURCES = frozenset({"datasf_entertainment", "abc"})
GRANT_ONLY_KINDS = frozenset({*ENTERTAINMENT_KINDS, "abc_license"})
# the base-rate reader sees both groups, each read with its own limit (`read_base_rate_rows` in
# app.tools.precedent_tools): the pool itself, and the grant-only rows it reports as left out
DECIDED_OUTCOMES = frozenset({"approved", "approved_with_conditions", "denied", "withdrawn"})
MIN_RATE_CASES = 10  # no approval rate is ever derived from fewer dated decisions than this
MIN_BASE_RATE_CASES = 5  # below this the window widens from 5 to 10 years
BASE_RATE_LIMIT = 1000  # records within 1,000 ft read for the base rate
FALLBACK_WINDOW_YEARS = 10


def is_grant_only(a: Application) -> bool:
    return a.source in GRANT_ONLY_SOURCES or a.kind in GRANT_ONLY_KINDS


# ---- record labels ---------------------------------------------------------------------------------
# A classifier writes three labels into a Planning row's `extra`: `premises` (the record is about one food,
# drink or entertainment premises), `use_class`, and `record_kind`. Rows that have not been through it carry
# none of them, and every rule below then falls back to what it did before the labels existed.
LABELLED_RECORD_KINDS = frozenset({"use_decision", "agency_referral", "building_work", "other"})


def is_labelled(a: Application) -> bool:
    """The record has been through the record classifier."""
    return "record_kind" in a.extra


def premises(a: Application) -> bool:
    """The classifier says the record is about one food, drink or entertainment premises."""
    return a.extra.get("premises") is True


def record_kind(a: Application) -> RecordKind:
    """What a record is. ABC rows are licences and Entertainment Commission rows are permits whatever their
    labels say; a Planning row is what the classifier called it, or `not_labelled`."""
    if a.kind == "abc_license" or a.source == "abc":
        return "licence"
    if a.source == "datasf_entertainment" or a.kind in ENTERTAINMENT_KINDS:
        return "entertainment_permit"
    label = a.extra.get("record_kind")
    if isinstance(label, str) and label in LABELLED_RECORD_KINDS:
        return cast(RecordKind, label)
    return "not_labelled"


def _labelled_planning_row(a: Application) -> bool:
    """A labelled row the label rules apply to: not an ABC licence or an Entertainment Commission permit."""
    return is_labelled(a) and not is_grant_only(a)


def is_pathway_candidate(a: Application) -> bool:
    """May this row be a comparable? Labelled Planning rows: only a use decision or an agency referral about
    a food, drink or entertainment premises. Everything else (unlabelled rows, Entertainment Commission
    permits): yes, as before the labels existed."""
    if not _labelled_planning_row(a):
        return True
    return premises(a) and record_kind(a) in PATHWAY_RECORD_KINDS


def _is_use_decision(a: Application) -> bool:
    """May this row enter the base rate, as far as its labels go? Labelled Planning rows: only a use decision
    about a food, drink or entertainment premises. Agency referrals are out: Planning answers nearly every
    referral "permitted", which is a different pathway from a contested use decision. Unlabelled rows: yes."""
    if not _labelled_planning_row(a):
        return True
    return premises(a) and record_kind(a) == "use_decision"


def _planning_row(a: Application) -> bool:
    """The kind and source test of the base rate: a Planning application, not a grant-only record."""
    return not is_grant_only(a) and a.source in PLANNING_SOURCES and a.kind in BASE_RATE_KINDS


def _comparable_planning_row(a: Application, want: set[str]) -> bool:
    """A Planning application that shares a use type with the concept, has a decided outcome and, when it is
    labelled, is a use decision about a food, drink or entertainment premises."""
    return (
        _planning_row(a)
        and _is_use_decision(a)
        and bool(want & set(a.use_types))
        and a.outcome in DECIDED_OUTCOMES
    )


def _dated(a: Application) -> bool:
    """Both dates present and in order. A row decided before it was filed is a data error, not a dated decision."""
    return a.filed_at is not None and a.decided_at is not None and a.decided_at >= a.filed_at


def _unique(apps: list[Nearby[Application]]) -> list[Application]:
    seen: set[str] = set()
    out: list[Application] = []
    for n in apps:
        if n.item.id not in seen:
            seen.add(n.item.id)
            out.append(n.item)
    return out


def base_rate_pool(
    apps: list[Nearby[Application]], profile: BusinessProfile, today: dt.date, window_years: int
) -> list[Application]:
    """Applications that count toward the base rate within `window_years`.

    Eligible: a Planning application (CUA or other Planning entitlement, whether or not a Commission motion
    enriched it) that shares a use type with the concept, has a decided outcome (approved, approved with
    conditions, denied, withdrawn), carries BOTH a filing date and a decision date with the decision not
    before the filing (the same rule as `days_to_decision`), and was decided inside the window. Entertainment
    Commission permits and ABC licences are never eligible, and neither is a Planning row missing either date
    or decided before it was filed. A row the record classifier has labelled is eligible only when it is a use
    decision about a food, drink or entertainment premises: agency referrals, building work and other records
    are out. Rows without labels are treated as before. See `base_rate`, which counts what was left out.
    """
    want = set(concept_use_types(profile))
    cutoff = today - dt.timedelta(days=365 * window_years)
    return [
        a
        for a in _unique(apps)
        if _comparable_planning_row(a, want)
        and a.filed_at is not None
        and a.decided_at is not None
        and a.decided_at >= a.filed_at  # decided before filed is a data error, not a dated decision
        and cutoff <= a.decided_at <= today
    ]


def base_rate(
    apps: list[Nearby[Application]],
    profile: BusinessProfile,
    today: dt.date,
    *,
    zoning_district: str | None,
    window_years: int = 5,
) -> BaseRate:
    """Outcome counts for comparable, dated Planning decisions near the address.

    Pool: see `base_rate_pool`. When fewer than 5 cases fall inside `window_years`, the window widens to
    10 years and the scope says so. Scope = same zoning district when known and it alone has >= 5 cases,
    else the 1,000 ft radius. The scope string always prints N; `rate_shown` (and with it
    `approval_rate_pct`) is true only when N >= 10.

    What was left out is counted, each row under exactly one heading, checked in this order:
    `excluded_grant_only` (nearby Entertainment Commission permits and ABC licences),
    `excluded_not_use_decision` (labelled Planning rows that are not a use decision about a food, drink or
    entertainment premises: referrals, building work, other records, other premises), `excluded_undated`
    (comparable decided Planning rows that lack a filing or decision date or whose decision date is before the
    filing date). The scope string lists them only when `excluded_not_use_decision` is above 0, so a store
    without labels prints the same scope as before. Deterministic: same inputs, same numbers."""
    years = window_years
    pool = base_rate_pool(apps, profile, today, years)
    widened = ""
    if len(pool) < MIN_BASE_RATE_CASES and window_years < FALLBACK_WINDOW_YEARS:
        years = FALLBACK_WINDOW_YEARS
        pool = base_rate_pool(apps, profile, today, years)
        widened = f" (fewer than {MIN_BASE_RATE_CASES} in the last {window_years})"
    where = "within 1,000 ft"
    if zoning_district:
        same = [a for a in pool if a.zoning_district == zoning_district]
        if len(same) >= MIN_BASE_RATE_CASES:
            pool, where = same, f"in zoning district {zoning_district} (within 1,000 ft)"
    n = len(pool)
    scope = f"N = {n} dated decision{'s' if n != 1 else ''} {where}, last {years} years{widened}"
    if n < MIN_RATE_CASES:
        scope += "; too few for a rate"
    want = set(concept_use_types(profile))
    rows = _unique(apps)
    grant_only = sum(1 for a in rows if is_grant_only(a))
    not_use_decision = sum(1 for a in rows if _planning_row(a) and not _is_use_decision(a))
    undated = sum(1 for a in rows if _comparable_planning_row(a, want) and not _dated(a))
    if not_use_decision:
        scope += "; " + left_out_clause(grant_only, not_use_decision, undated)
    c = Counter(a.outcome for a in pool)
    return BaseRate(
        approved=c["approved"],
        approved_with_conditions=c["approved_with_conditions"],
        denied=c["denied"],
        withdrawn=c["withdrawn"],
        total=n,
        window_years=years,
        scope=scope,
        excluded_grant_only=grant_only,
        excluded_undated=undated,
        excluded_not_use_decision=not_use_decision,
        counted=tuple(sorted(pool, key=lambda a: a.id)),
    )


def left_out_clause(grant_only: int, not_use_decision: int, undated: int) -> str:
    """'left out: 14 permits and licences, 31 records that are not use decisions for this kind of business,
    3 undated' (zero counts are skipped). The permits and licences are Entertainment Commission permits and ABC
    licences. The second count also holds use decisions about other kinds of premises."""
    parts = [
        ("1 permit or licence" if grant_only == 1 else f"{grant_only} permits and licences")
        if grant_only
        else "",
        (
            "1 record that is not a use decision for this kind of business"
            if not_use_decision == 1
            else f"{not_use_decision} records that are not use decisions for this kind of business"
        )
        if not_use_decision
        else "",
        f"{undated} undated" if undated else "",
    ]
    return "left out: " + ", ".join(p for p in parts if p)


def rate_payload(rate: BaseRate) -> dict[str, object]:
    """The base rate as the model and the verify stage see it (properties included)."""
    return {
        "approved": rate.approved,
        "approved_with_conditions": rate.approved_with_conditions,
        "denied": rate.denied,
        "withdrawn": rate.withdrawn,
        "total": rate.total,
        "window_years": rate.window_years,
        "scope": rate.scope,
        "rate_shown": rate.rate_shown,
        "approval_rate_pct": rate.approval_rate_pct,
        "excluded_grant_only": rate.excluded_grant_only,
        "excluded_undated": rate.excluded_undated,
        "excluded_not_use_decision": rate.excluded_not_use_decision,
    }


@dataclass(frozen=True)
class Density:
    radius_m: int
    food_or_drink_businesses: int
    bars: int
    abc_on_sale_licenses: int
    abc_licenses_1000ft: int
    undue_concentration_flag: bool
    note: str


def density(
    businesses: list[Nearby[Business]],
    licenses_500: list[Nearby[Application]],
    licenses_1000: list[Nearby[Application]],
) -> Density:
    food = sum(1 for n in businesses if n.item.is_food_or_drink and n.distance_m <= FT_500_M)
    bars = sum(1 for n in businesses if n.item.is_bar and n.distance_m <= FT_500_M)
    on_sale = sum(
        1
        for n in licenses_500
        if (n.item.license_type or "") in ON_SALE_TYPES and n.item.status.lower().startswith("act")
    )
    all_1000 = sum(1 for n in licenses_1000 if n.item.status.lower().startswith("act"))
    flag = on_sale >= 4 or bars >= 3
    # A count within 500 ft, not ABC's test: whether a public convenience or necessity finding is needed is said
    # only on the alcohol licence row, from the census tract and the transaction (app.memo.rows, app.memo.tracts).
    note = (
        "ABC's undue-concentration test compares on-sale licenses in the census tract with the county ratio and "
        "crime reporting district; this count of active on-sale licenses within 500 ft is a proxy, not that "
        "test. The alcohol licence row says what the census tract shows."
    )
    return Density(
        radius_m=int(FT_500_M),
        food_or_drink_businesses=food,
        bars=bars,
        abc_on_sale_licenses=on_sale,
        abc_licenses_1000ft=all_1000,
        undue_concentration_flag=flag,
        note=note,
    )
