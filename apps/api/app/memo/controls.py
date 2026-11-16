"""Typed, dated access to the Planning Code control data (rule table v2).

The data is one bundled file, `data/sf_dated_controls.json`, built by scripts/validation/assemble_dated_controls.py
from two readings of the Planning Code (spec: docs/validation/rule-table-extension-spec.md, section 3). This
module reads it once and answers questions about it. It decides nothing about a concept: the rule engine does
that. Pure code: no clock (the date is always passed in), no randomness, no I/O after the first read.

HOW THE DATA IS READ

- Dates. Every row is a list of dated versions. `from` null means "already in force on 2022-01-01" (DATA_START);
  `to` null means "in force today". `on=None` always means today's version. The data does not go back before
  2022-01-01: a date before that gets the first version and `before_data_start=True` on the result's `source`.
- Cells. `P`, `C`, `NP` become "principal", "conditional", "not_permitted". A cell that is `NA` (the table has
  no such row) is read from the row that governs instead (`governed_by`); the result says so and names that row.
  Anything else is `None`: the cell could not be read. `None` is never "permitted".
- A version's start date is the date the row's TEXT last changed, which can be a change to a note only.
  `same_since` on every district result is the start of the unbroken run of versions that give the same typed
  answer (None: already so on 2022-01-01); `differs_today` says whether today's version gives a different one.
- `source.note` is the readers' note on the version, whole: the numbered table notes on the cells, sub-area
  controls, and how the version was established. It is prose. Fields of a version that this module does not
  type (sub-area controls, exceptions, the reconciliation record) are in `extra`, unchanged.
- Historic Buildings (Planning Code § 202.11, in force from 2026-04-11) changes how many cells read in a
  Historic Building. The data carries it inside the notes of versions that began earlier, so `UseControl`
  gives that passage separately (`historic_buildings`) and only for a date on or after HISTORIC_BUILDINGS_FROM.

Everything returned is frozen. Mappings are read-only and lists are tuples; `plain()` turns a value back
into dicts and lists (for JSON).
"""

from __future__ import annotations

import contextvars
import datetime as dt
import json
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast, get_args

from app.models.profile import Story

DATA_PATH = Path(__file__).resolve().parent / "data" / "sf_dated_controls.json"
# The data starts here: a version with "from": null was already in force on this date.
DATA_START = dt.date(2022, 1, 1)
# Planning Code § 202.11 (Ord. 37-26, File No. 250886, Eff. 4/11/2026): permitted uses in Historic Buildings.
HISTORIC_BUILDINGS_FROM = dt.date(2026, 4, 11)

Permission = Literal["principal", "conditional", "not_permitted"]
Use = Literal["bar", "restaurant", "limited_restaurant", "nighttime_entertainment"]
RuleControl = Literal["principal", "conditional", "not_permitted", "requirement"]

USES: tuple[Use, ...] = get_args(Use)
ROWS: tuple[str, ...] = (*USES, "formula_retail", "use_size", "outdoor_activity_area", "hours")

_PERMISSIONS: Mapping[str, Permission] = MappingProxyType(
    {"P": "principal", "C": "conditional", "NP": "not_permitted"}
)
_RULE_CONTROLS: Mapping[str, RuleControl] = MappingProxyType({**_PERMISSIONS, "requirement": "requirement"})
_LETTERS: Mapping[str, str] = MappingProxyType({v: k for k, v in _PERMISSIONS.items()})
# The table column each story is read from. The tables have no basement column: a basement is read as the
# first story, and the result says so (`basement_read_as_first`).
_STORY_COLUMN: Mapping[str, str] = MappingProxyType(
    {"first": "first", "second": "second", "third_or_above": "third", "basement": "first"}
)
_PROVENANCE_KEYS = frozenset({"from", "to", "note", "ordinance", "quote", "url", "read_on"})
_MINUTES_IN_DAY = 24 * 60


class ControlDataError(RuntimeError):
    """The bundled control data file is missing or is not what this module reads."""


# ---- loading ------------------------------------------------------------------------------------------
class _Frozen(Mapping[str, Any]):
    """A read-only mapping. Unlike `types.MappingProxyType` it can be deep-copied and pickled, so a result that
    holds one works with `copy.deepcopy` and `dataclasses.asdict`. Equal to any mapping with the same items."""

    __slots__ = ("_items",)

    def __init__(self, items: Mapping[str, Any]) -> None:
        self._items = dict(items)

    def __getitem__(self, key: str) -> Any:
        return self._items[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return repr(self._items)

    def __copy__(self) -> _Frozen:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> _Frozen:
        return self  # nothing in it can change

    def __reduce__(self) -> tuple[type[_Frozen], tuple[dict[str, Any]]]:
        return (_Frozen, (self._items,))


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return _Frozen({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def plain(value: Any) -> Any:
    """A frozen value from this module as plain dicts and lists (what the JSON file held)."""
    if isinstance(value, Mapping):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [plain(v) for v in value]
    return value


@lru_cache(maxsize=1)
def _data() -> Mapping[str, Any]:
    """The whole file, read once and frozen. A failed read is not remembered."""
    try:
        text = DATA_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ControlDataError(
            f"the dated control data file is missing: {DATA_PATH} "
            "(it is built by scripts/validation/assemble_dated_controls.py)"
        ) from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ControlDataError(f"the dated control data file is not valid JSON: {DATA_PATH}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ControlDataError(f"the dated control data file is not a JSON object: {DATA_PATH}")
    for key in ("districts", "special_districts", "citywide"):
        if not isinstance(raw.get(key), dict):
            raise ControlDataError(f"the dated control data file has no {key!r} object: {DATA_PATH}")
    return cast(Mapping[str, Any], _freeze(raw))


# ---- the data as known on a past day (the backtest) ------------------------------------------------------------
# A report made as if on a past day must not know what changed after it. With KNOWN_ON set (only the backtest sets
# it, per case), the rules read the data as it could be known that day: a version or entry that began after it is
# not there, a version or entry in force that day has no known end (its end came from later legislation), and a
# name's "(repealed <date>)" note dated after it is removed. A live report never sets it and reads the file as is.
KNOWN_ON: contextvars.ContextVar[dt.date | None] = contextvars.ContextVar("controls_known_on", default=None)
# Ends fixed by the enacting ordinance itself, so known from the first day: Ord. 209-21 added § 202.12 "for the
# three years following" its effective date.
KNOWN_SUNSETS: frozenset[str] = frozenset({"laundromat_removal"})
_REPEALED_RE = re.compile(r"\s*\(repealed (\d{4}-\d{2}-\d{2})\)")
# a section label that names a later renumbering: "§ 1060.2(b)(4) until 2025-08-16, renumbered (b)(3) from ..."
_SECTION_UNTIL_RE = re.compile(r"\s+until (\d{4}-\d{2}-\d{2})(?:, renumbered .*? from \d{4}-\d{2}-\d{2})?")


def _view() -> Mapping[str, Any]:
    known = KNOWN_ON.get()
    return _data() if known is None else _known_on(known)


def _as_known(node: Any, on: dt.date, *, keep_ends: bool) -> Any:
    if isinstance(node, Mapping):
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k == "name" and isinstance(v, str):
                m = _REPEALED_RE.search(v)
                if m and dt.date.fromisoformat(m.group(1)) > on:
                    v = _REPEALED_RE.sub("", v)
            if k == "section" and isinstance(v, str):
                m = _SECTION_UNTIL_RE.search(v)
                if m and dt.date.fromisoformat(m.group(1)) >= on:
                    v = _SECTION_UNTIL_RE.sub("", v)
            out[k] = _as_known(v, on, keep_ends=keep_ends or k in KNOWN_SUNSETS)
        if "from" in out and "to" in out and not keep_ends:
            end = _date(out.get("to"))
            if end is not None and end >= on:
                out["to"] = None
        return out
    if isinstance(node, (list, tuple)):
        kept = []
        for v in node:
            if isinstance(v, Mapping) and "from" in v and "to" in v:
                start = _date(v.get("from"))
                if start is not None and start > on:
                    continue
            kept.append(_as_known(v, on, keep_ends=keep_ends))
        return kept
    return node


@lru_cache(maxsize=64)
def _known_on(on: dt.date) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], _freeze(_as_known(plain(_data()), on, keep_ends=False)))


def read_on() -> dt.date | None:
    """The date the code text was read for this file (the file's own `_read_on`)."""
    return _date(_data().get("_read_on"))


def districts() -> tuple[str, ...]:
    """The zoning district codes in the data, in the file's order."""
    return tuple(_view()["districts"])


def covers(district: str) -> bool:
    """Is the district in the data. Any other district is not covered by the dated rows."""
    return district in _view()["districts"]


def special_district_keys() -> tuple[str, ...]:
    return tuple(_view()["special_districts"])


# Citywide groups that are lists of separate entries, each dated on its own (one entry per permit and per
# agency it is referred to), not successive versions of one rule. Spec section 3a: an entry's `kind` is
# "approval_required" or "referral_step", and a referral step is never an approval.
CITYWIDE_ENTRY_GROUPS: frozenset[str] = frozenset({"entertainment_permits", "other_referrals"})


def _is_record(value: Any) -> bool:
    return isinstance(value, Mapping)


def citywide_keys() -> tuple[str, ...]:
    """The citywide rules that are one rule with dated versions. The entry groups (CITYWIDE_ENTRY_GROUPS) and
    the plain records (an ordinance's dates and summary) are listed by `citywide_entry_groups` and
    `citywide_record_keys`."""
    return tuple(
        k for k, v in _view()["citywide"].items() if k not in CITYWIDE_ENTRY_GROUPS and not _is_record(v)
    )


def citywide_entry_groups() -> tuple[str, ...]:
    return tuple(k for k in _view()["citywide"] if k in CITYWIDE_ENTRY_GROUPS)


def citywide_record_keys() -> tuple[str, ...]:
    return tuple(k for k, v in _view()["citywide"].items() if _is_record(v))


def citywide_record(key: str) -> Mapping[str, Any]:
    """A plain record under `citywide` that is not a dated rule, e.g. "ordinance_118_25" (its dates, what it
    removed, the quotes). Read-only."""
    value = _view()["citywide"].get(key)
    if not _is_record(value):
        raise KeyError(
            f"citywide record {key!r} is not in the dated control data; the records are {', '.join(citywide_record_keys())}"
        )
    return cast(Mapping[str, Any], value)


# ---- dates --------------------------------------------------------------------------------------------
def _date(text: Any) -> dt.date | None:
    return dt.date.fromisoformat(text) if isinstance(text, str) and text else None


def _day(on: dt.date | None) -> dt.date | None:
    return on.date() if isinstance(on, dt.datetime) else on


@dataclass(frozen=True)
class InForce:
    """One version out of a list of dated versions, as `version_on` found it."""

    version: Mapping[str, Any]
    index: int  # its place in the list
    # The date asked is before 2022-01-01, where the data starts. `version` is the first one on file, which was
    # in force on 2022-01-01; whether it was in force on the date asked is not known from this data.
    before_data_start: bool = False


def version_on(versions: Sequence[Mapping[str, Any]], on: dt.date | None) -> InForce | None:
    """The version in force on `on`; `on=None` is today's (the one whose "to" is null).

    A date before 2022-01-01 returns the first version, flagged `before_data_start`, when that version was
    already in force on 2022-01-01 ("from" null). None when no version on file covers the date: a rule that
    began later or has ended. District rows are contiguous from null to null, so they always answer."""
    on = _day(on)
    if not versions:
        return None
    if on is None:
        for i in range(len(versions) - 1, -1, -1):
            if versions[i].get("to") is None:
                return InForce(versions[i], i)
        return None
    if on < DATA_START:
        return InForce(versions[0], 0, before_data_start=True) if versions[0].get("from") is None else None
    for i, version in enumerate(versions):
        start, end = _date(version.get("from")), _date(version.get("to"))
        if (start is None or start <= on) and (end is None or on <= end):
            return InForce(version, i)
    return None


def _in_force(versions: Sequence[Mapping[str, Any]], on: dt.date | None, where: str) -> InForce:
    found = version_on(versions, on)
    if found is None:
        raise ControlDataError(f"no version of {where} covers {on.isoformat() if on else 'today'}")
    return found


def _same_since(
    versions: Sequence[Mapping[str, Any]], index: int, answer: Callable[[Mapping[str, Any]], Any]
) -> dt.date | None:
    here = answer(versions[index])
    while index > 0 and answer(versions[index - 1]) == here:
        index -= 1
    return _date(versions[index].get("from"))


# ---- provenance ---------------------------------------------------------------------------------------
def section_label(section: str) -> str:
    """'723' -> 'Planning Code § 723'. Several sections ('303(e); 174') -> 'Planning Code §§ 303(e); 174': a
    semicolon outside brackets followed by another section number. A section the data already names in full
    ('California Building Code 2019 edition, § 303.3') is unchanged."""
    text = section.strip()
    if not text[:1].isdigit():
        return text
    depth = 0
    several = False
    for i, ch in enumerate(text):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == ";" and depth == 0 and text[i + 1 :].lstrip()[:1].isdigit():
            several = True
    return f"Planning Code {'§§' if several else '§'} {text}"


@dataclass(frozen=True)
class Source:
    """Where an answer comes from: enough to write the sentence and the citation."""

    section: str  # as a label: "Planning Code § 723"
    quote: str  # the row or sentence relied on, verbatim
    url: str  # the page the quoted words were read on (an archived copy for an earlier version)
    source_url: str  # the section's page today (district rows); the same as `url` for the other rules
    ordinance: str | None  # the ordinance that began this version; None: already in force on 2022-01-01
    in_force_from: dt.date | None  # None: already in force on 2022-01-01
    in_force_to: dt.date | None  # None: in force today
    read_on: dt.date | None
    note: str  # the readers' note on the version, whole (numbered table notes included)
    before_data_start: bool  # the date asked is before 2022-01-01: this is the earliest version on file

    @property
    def in_force_text(self) -> str:
        """'in force since before 2022-01-01' / 'in force from 2024-05-27 (Ord. 85-24, File No. 231221)',
        with ' until 2025-10-05' when the version has ended."""
        if self.in_force_from is None:
            text = f"in force since before {DATA_START.isoformat()}"
        else:
            text = f"in force from {self.in_force_from.isoformat()}"
            if self.ordinance:
                text += f" ({self.ordinance})"
        if self.in_force_to is not None:
            text += f" until {self.in_force_to.isoformat()}"
        return text


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _source(
    version: Mapping[str, Any], *, section: str, source_url: str | None, before_data_start: bool
) -> Source:
    url = _text(version.get("url"))
    ordinance = version.get("ordinance")
    return Source(
        section=section_label(section),
        quote=_text(version.get("quote")),
        url=url,
        source_url=source_url or url,
        ordinance=ordinance if isinstance(ordinance, str) and ordinance else None,
        in_force_from=_date(version.get("from")),
        in_force_to=_date(version.get("to")),
        read_on=_date(version.get("read_on")),
        note=_text(version.get("note")),
        before_data_start=before_data_start,
    )


def _extra(version: Mapping[str, Any], typed: frozenset[str]) -> Mapping[str, Any]:
    return _Frozen({k: v for k, v in version.items() if k not in _PROVENANCE_KEYS and k not in typed})


# ---- districts ----------------------------------------------------------------------------------------
_FORMER_SECTION = re.compile(r"^(?P<section>\S+) \(until (?P<until>\d{4}-\d{2}-\d{2})\)$")


def _district(district: str) -> Mapping[str, Any]:
    try:
        return cast(Mapping[str, Any], _view()["districts"][district])
    except KeyError:
        raise KeyError(
            f"district {district!r} is not in the dated control data; ask covers() first"
        ) from None


def _district_section(dist: Mapping[str, Any], district: str, on: dt.date | None) -> str:
    """The section the district's table was in on the date (MUR was § 841 until 2023-06-02, § 833 after)."""
    former = dist.get("former_section")
    if former is not None and on is not None:
        m = _FORMER_SECTION.match(_text(former))
        if m is None:
            raise ControlDataError(f"former_section of {district!r} cannot be read: {former!r}")
        if on <= dt.date.fromisoformat(m.group("until")):
            return m.group("section")
    return _text(dist.get("section"))


@dataclass(frozen=True)
class _Row:
    """A district row on a date: the version in force, today's version, and the pieces every result shares."""

    versions: Sequence[Mapping[str, Any]]
    found: InForce
    today: Mapping[str, Any]
    source: Source

    @property
    def version(self) -> Mapping[str, Any]:
        return self.found.version

    def same_since(self, answer: Callable[[Mapping[str, Any]], Any]) -> dt.date | None:
        return _same_since(self.versions, self.found.index, answer)

    def differs_today(self, answer: Callable[[Mapping[str, Any]], Any]) -> bool:
        return bool(answer(self.version) != answer(self.today))


def _row(district: str, row: str, on: dt.date | None) -> _Row:
    on = _day(on)
    dist = _district(district)
    versions = cast(Sequence[Mapping[str, Any]], dist["rows"][row])
    where = f"{district} / {row}"
    found = _in_force(versions, on, where)
    source = _source(
        found.version,
        section=_district_section(dist, district, on),
        source_url=_text(dist.get("source_url")),
        before_data_start=found.before_data_start,
    )
    return _Row(versions, found, _in_force(versions, None, where).version, source)


def _permission(value: Any) -> Permission | None:
    return _PERMISSIONS.get(value) if isinstance(value, str) else None


def _governing(version: Mapping[str, Any]) -> Mapping[str, Any] | None:
    governed_by = version.get("governed_by")
    return governed_by if isinstance(governed_by, Mapping) else None


def _resolved(version: Mapping[str, Any], key: str) -> tuple[Any, str | None]:
    """The value of a cell, and the governing row's name when the cell is NA and another row governs."""
    value = version.get(key)
    if value != "NA":
        return value, None
    governed_by = _governing(version)
    if governed_by is None:
        return None, None
    return governed_by.get(key), _text(governed_by.get("row")) or None


# ---- the four use rows --------------------------------------------------------------------------------
_HISTORIC_START = re.compile(rf"Historic Buildings,? from {HISTORIC_BUILDINGS_FROM.isoformat()}")
# Where a note goes on to something else after the Historic Buildings passage (how it was read or settled).
_HISTORIC_ENDS = (
    " (Section 202.11 read",
    " Section 202.11 read at",
    " Reconciliation",
    " Reconciler:",
    " Settled 2026-11-10",
    " governed_by gives",
)


def _historic_passage(note: str) -> str | None:
    m = _HISTORIC_START.search(note)
    if m is None:
        return None
    passage = note[m.start() :]
    cut = min((i for i in (passage.find(end) for end in _HISTORIC_ENDS) if i > 0), default=len(passage))
    return passage[:cut].strip()


@dataclass(frozen=True)
class UseControl:
    """One cell of a district's zoning control table: a use at a story on a date."""

    district: str
    use: Use
    story: Story  # as asked
    column: Literal["first", "second", "third"]  # the table column read
    basement_read_as_first: bool  # the tables have no basement column; the first story was read
    permission: Permission | None  # None: the cell could not be read. Never "permitted".
    governed: bool  # the table has no row for this use; `governing_row` governs and its cell was read
    governing_row: str | None
    # The Historic Buildings passage of the note (§ 202.11), only for a date on or after 2026-04-11 and only
    # where the readers wrote one. It says how this cell reads in a Historic Building; it is not in `permission`.
    historic_buildings: str | None
    differs_today: bool  # today's version gives a different permission for this cell
    permission_today: Permission | None
    same_since: dt.date | None  # this cell has read the same since then; None: since before 2022-01-01
    source: Source
    extra: Mapping[str, Any] = field(hash=False)  # sub-area controls, exceptions and the like, unchanged


_USE_KEYS = frozenset({"first", "second", "third"})


def use_control(district: str, use: Use, story: Story, on: dt.date | None) -> UseControl:
    """The control for a bar, restaurant, limited restaurant or nighttime entertainment use at a story.

    Read `source.note` and `extra` too: a cell can be P with a numbered note that makes it C in part of the
    district (`extra["subarea_controls"]`), or NP with an exception by licence type (`extra["exceptions"]`)."""
    if use not in USES:
        raise ValueError(f"use {use!r} has no row in the dated control data; the rows are {', '.join(USES)}")
    if story not in _STORY_COLUMN:
        raise ValueError(f"story {story!r} is not one of {', '.join(_STORY_COLUMN)}")
    column = cast(Literal["first", "second", "third"], _STORY_COLUMN[story])
    row = _row(district, use, on)

    def answer(version: Mapping[str, Any]) -> Permission | None:
        return _permission(_resolved(version, column)[0])

    governing_row = _resolved(row.version, column)[1]
    on = _day(on)
    historic = _historic_passage(row.source.note) if on is None or on >= HISTORIC_BUILDINGS_FROM else None
    return UseControl(
        district=district,
        use=use,
        story=story,
        column=column,
        basement_read_as_first=story == "basement",
        permission=answer(row.version),
        governed=row.version.get(column) == "NA" and _governing(row.version) is not None,
        governing_row=governing_row,
        historic_buildings=historic,
        differs_today=row.differs_today(answer),
        permission_today=answer(row.today),
        same_since=row.same_since(answer),
        source=row.source,
        extra=_extra(row.version, _USE_KEYS),
    )


# ---- formula retail -----------------------------------------------------------------------------------
@dataclass(frozen=True)
class FormulaRetail:
    """The district's Formula Retail row on a date."""

    district: str
    control: Permission | None  # None: no control could be read
    # The uses the control reaches, as the data words it: "all", or a narrower class of uses ("Limited Corner
    # Commercial Uses"). When it is not "all", `control` says nothing about the other uses.
    applies_to: str
    applies_to_all: bool
    # Uses for which Formula Retail is not permitted anywhere in the district, whatever `control` says
    # ("Restaurant", "Limited Restaurant"). Rules for part of a district only are in `extra`
    # (not_permitted_for_in_subarea, formula_retail_restaurant_rule, in_central_soma_sud, principal_exception,
    # conditional_where, conflicting_text).
    not_permitted_for: tuple[str, ...]
    governed: bool  # the table has no Formula Retail row; `governing_row` governs
    governing_row: str | None
    differs_today: bool
    same_since: dt.date | None
    source: Source
    extra: Mapping[str, Any] = field(hash=False)


_FORMULA_KEYS = frozenset({"control", "applies_to", "not_permitted_for"})


def _formula_answer(version: Mapping[str, Any]) -> tuple[Permission | None, str, tuple[str, ...]]:
    control, applies_to = version.get("control"), version.get("applies_to")
    governed_by = _governing(version) if control == "NA" else None
    if governed_by is not None:
        # the governing rule's own words for what it reaches, where it gives them
        control = governed_by.get("control")
        applies_to = governed_by.get("applies_to") or applies_to
    named = version.get("not_permitted_for")
    return (
        _permission(control),
        _text(applies_to),
        tuple(str(u) for u in named) if isinstance(named, tuple) else (),
    )


def formula_retail(district: str, on: dt.date | None) -> FormulaRetail:
    row = _row(district, "formula_retail", on)
    control, applies_to, not_permitted_for = _formula_answer(row.version)
    return FormulaRetail(
        district=district,
        control=control,
        applies_to=applies_to,
        applies_to_all=applies_to == "all",
        not_permitted_for=not_permitted_for,
        governed=row.version.get("control") == "NA" and _governing(row.version) is not None,
        governing_row=_resolved(row.version, "control")[1],
        differs_today=row.differs_today(_formula_answer),
        same_since=row.same_since(_formula_answer),
        source=row.source,
        extra=_extra(row.version, _FORMULA_KEYS),
    )


# ---- use size -----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Division:
    """Dividing a use that is larger than the limit into smaller ones (§ 121.5 / § 121.2(b), from 2025-10-06)."""

    allowed_without_conditional_use: bool
    section: str
    condition: str


@dataclass(frozen=True)
class UseSize:
    """The district's use size row on a date. A use below `principal_below_sqft` is principal; from there up it
    is conditional; from `not_permitted_from_sqft` (None: no cap) it is not permitted."""

    district: str
    principal_below_sqft: int | None  # None: the district table states no size threshold
    not_permitted_from_sqft: int | None
    exemption: str  # who the limit does not apply to, in words; "" when none is recorded
    division: Division | None
    differs_today: bool  # today's thresholds differ
    same_since: dt.date | None  # the thresholds have been these since then; None: since before 2022-01-01
    source: Source
    extra: Mapping[str, Any] = field(hash=False)

    @property
    def has_threshold(self) -> bool:
        return self.principal_below_sqft is not None

    def size_control(self, area_sqft: int) -> Permission | None:
        """The control for a use of that floor area. None when the district table states no size threshold
        (no answer; not "permitted"). The exemption and `extra` (for example `not_permitted_only_if`) are not
        applied here."""
        if self.principal_below_sqft is None:
            return None
        if area_sqft < self.principal_below_sqft:
            return "principal"
        if self.not_permitted_from_sqft is not None and area_sqft >= self.not_permitted_from_sqft:
            return "not_permitted"
        return "conditional"


_SIZE_KEYS = frozenset(
    {"principal_below_sqft", "not_permitted_from_sqft", "exemption", "division_of_large_uses"}
)


def _sqft(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _size_answer(version: Mapping[str, Any]) -> tuple[int | None, int | None]:
    return _sqft(version.get("principal_below_sqft")), _sqft(version.get("not_permitted_from_sqft"))


def use_size(district: str, on: dt.date | None) -> UseSize:
    row = _row(district, "use_size", on)
    principal_below, not_permitted_from = _size_answer(row.version)
    raw = row.version.get("division_of_large_uses")
    division = (
        Division(
            allowed_without_conditional_use=raw.get("allowed_without_conditional_use") is True,
            section=_text(raw.get("section")),
            condition=_text(raw.get("condition")),
        )
        if isinstance(raw, Mapping)
        else None
    )
    return UseSize(
        district=district,
        principal_below_sqft=principal_below,
        not_permitted_from_sqft=not_permitted_from,
        exemption=_text(row.version.get("exemption")),
        division=division,
        differs_today=row.differs_today(_size_answer),
        same_since=row.same_since(_size_answer),
        source=row.source,
        extra=_extra(row.version, _SIZE_KEYS),
    )


# ---- outdoor activity area ----------------------------------------------------------------------------
@dataclass(frozen=True)
class OutdoorActivityArea:
    """The district's Outdoor Activity Area row on a date."""

    district: str
    in_front: Permission | None  # None: the district has no control on file for it
    elsewhere: Permission | None
    elsewhere_principal_if_202_2_a_7: bool  # an area elsewhere is principal when it meets § 202.2(a)(7)
    governed: bool
    governing_row: str | None
    differs_today: bool
    same_since: dt.date | None
    source: Source
    extra: Mapping[str, Any] = field(hash=False)


_OUTDOOR_KEYS = frozenset({"in_front", "elsewhere", "elsewhere_principal_if_202_2_a_7"})


def _outdoor_answer(version: Mapping[str, Any]) -> tuple[Permission | None, Permission | None, bool]:
    governed_by = _governing(version) if version.get("in_front") == "NA" else None
    flag = (governed_by or version).get("elsewhere_principal_if_202_2_a_7")
    return (
        _permission(_resolved(version, "in_front")[0]),
        _permission(_resolved(version, "elsewhere")[0]),
        flag is True,
    )


def outdoor_activity_area(district: str, on: dt.date | None) -> OutdoorActivityArea:
    row = _row(district, "outdoor_activity_area", on)
    in_front, elsewhere, flag = _outdoor_answer(row.version)
    return OutdoorActivityArea(
        district=district,
        in_front=in_front,
        elsewhere=elsewhere,
        elsewhere_principal_if_202_2_a_7=flag,
        governed=row.version.get("in_front") == "NA" and _governing(row.version) is not None,
        governing_row=_resolved(row.version, "in_front")[1],
        differs_today=row.differs_today(_outdoor_answer),
        same_since=row.same_since(_outdoor_answer),
        source=row.source,
        extra=_extra(row.version, _OUTDOOR_KEYS),
    )


# ---- hours of operation -------------------------------------------------------------------------------
def _clock(text: Any) -> int:
    """'06:00' -> 360."""
    if not isinstance(text, str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", text):
        raise ControlDataError(f"not a clock time in the dated control data: {text!r}")
    return int(text[:2]) * 60 + int(text[3:])


def _clock_text(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


@dataclass(frozen=True)
class HoursWindow:
    """One window of an hours control. Times are minutes after midnight; the window runs from `start` up to,
    not including, `end`. An `end` at or before `start` means it runs past midnight (06:00 to 02:00 is 360 to
    120)."""

    permission: Permission
    start: int
    end: int
    # False: the row does not print this window. The readers entered it from the § 102 definition of Hours of
    # Operation (the data's `windows_not_printed`), so it is an inference, not quoted words.
    printed: bool = True

    def covers(self, minute: int) -> bool:
        minute %= _MINUTES_IN_DAY
        if self.start < self.end:
            return self.start <= minute < self.end
        return minute >= self.start or minute < self.end

    @property
    def text(self) -> str:
        """'P 06:00-02:00'."""
        return f"{_LETTERS[self.permission]} {_clock_text(self.start)}-{_clock_text(self.end)}"


@dataclass(frozen=True)
class Hours:
    """The district's hours of operation control on a date."""

    district: str
    windows: tuple[HoursWindow, ...]  # in the order written; empty when `no_limit`
    # The data records no hours control for the district (the row reads "No limit", or the table has no hours
    # row). `permission_at` is then None for every minute: ask this first.
    no_limit: bool
    # Hours the row says nothing about, as (start, end) minutes, where the readers listed them.
    not_stated: tuple[tuple[int, int], ...]
    differs_today: bool
    same_since: dt.date | None
    source: Source
    extra: Mapping[str, Any] = field(hash=False)

    def permission_at(self, minute: int) -> Permission | None:
        """The control at that minute after midnight (0 to 1439; 1440 reads as 0). None when no window on
        file covers the minute. None is never "permitted": either the district has no hours control
        (`no_limit`) or the row is silent about that hour."""
        return next((w.permission for w in self.windows if w.covers(minute)), None)

    @property
    def text(self) -> str:
        """'P 06:00-02:00; C 02:00-06:00', or 'no limit'."""
        if self.no_limit:
            return "no limit"
        return "; ".join(w.text + ("" if w.printed else " (not printed in the row)") for w in self.windows)


_HOURS_KEYS = frozenset({"windows"})


def _windows(version: Mapping[str, Any]) -> tuple[HoursWindow, ...]:
    raw = version.get("windows")
    unprinted = version.get("windows_not_printed")
    out: list[HoursWindow] = []
    for item in raw if isinstance(raw, tuple) else ():
        if not (isinstance(item, tuple) and len(item) == 3 and _permission(item[0]) is not None):
            raise ControlDataError(f"not an hours window in the dated control data: {item!r}")
        out.append(
            HoursWindow(
                permission=_PERMISSIONS[item[0]],
                start=_clock(item[1]),
                end=_clock(item[2]),
                printed=not (isinstance(unprinted, tuple) and item in unprinted),
            )
        )
    return tuple(out)


def _hours_answer(version: Mapping[str, Any]) -> tuple[tuple[Permission, int, int], ...]:
    return tuple((w.permission, w.start, w.end) for w in _windows(version))


def hours(district: str, on: dt.date | None) -> Hours:
    row = _row(district, "hours", on)
    windows = _windows(row.version)
    silent = row.version.get("windows_not_stated")
    return Hours(
        district=district,
        windows=windows,
        no_limit=not windows,
        not_stated=tuple((_clock(a), _clock(b)) for a, b in silent) if isinstance(silent, tuple) else (),
        differs_today=row.differs_today(_hours_answer),
        same_since=row.same_since(_hours_answer),
        source=row.source,
        extra=_extra(row.version, _HOURS_KEYS),
    )


# ---- special district and citywide rules --------------------------------------------------------------
@dataclass(frozen=True)
class SpecialDistrict:
    key: str
    name: str
    section: str  # as the data words it; it can describe a renumbering ("249.40A until 2023-06-02; ...")
    overlay_hint: str  # how the district is named on the zoning map, to match it to an overlay
    extra: Mapping[str, Any] = field(hash=False)


@dataclass(frozen=True)
class Rule:
    """One dated rule of a special district, or one citywide rule, as it stood on a date."""

    scope: Literal["special_district", "citywide"]
    key: str  # the special district's key, or the citywide key
    rule_id: str  # the data's `rule_id`; a citywide rule has none of its own, so the citywide key
    rule: str  # the rule in words
    applies_to: str | None  # who or what it reaches (special district rules)
    # principal / conditional / not_permitted, or "requirement" (a condition, not a permission). None for a
    # citywide rule, whose terms are in `extra["facts"]`, and for a value this module does not know.
    control: RuleControl | None
    # The data's `kind`, citywide rules only: "approval_required", "step_within_approval" or "definition"
    # (spec section 3a: a step inside an approval is never an approval). None for special district rules.
    kind: str | None
    # False where the data keeps a version on file to say the rule had lapsed (laundromat removal after
    # 2024-12-20). A rule that is not in force asks for nothing.
    in_force: bool
    source: Source
    extra: Mapping[str, Any] = field(hash=False)  # facts, sources, windows, requirement, settled, ...


_SPECIAL_KEYS = frozenset({"rule_id", "rule", "applies_to", "control", "section"})
_CITYWIDE_KEYS = frozenset({"rule", "kind", "section", "in_force"})
_SPECIAL_DISTRICT_KEYS = frozenset({"name", "section", "overlay_hint", "rules"})


def _special(key: str) -> Mapping[str, Any]:
    try:
        return cast(Mapping[str, Any], _view()["special_districts"][key])
    except KeyError:
        known = ", ".join(special_district_keys())
        raise KeyError(
            f"special district {key!r} is not in the dated control data; the keys are {known}"
        ) from None


def special_district(key: str) -> SpecialDistrict:
    raw = _special(key)
    return SpecialDistrict(
        key=key,
        name=_text(raw.get("name")),
        section=_text(raw.get("section")),
        overlay_hint=_text(raw.get("overlay_hint")),
        extra=_Frozen({k: v for k, v in raw.items() if k not in _SPECIAL_DISTRICT_KEYS}),
    )


def special_rules(key: str, on: dt.date | None) -> tuple[Rule, ...]:
    """The rules of a special district in force on the date, in the file's order: one per `rule_id`, the
    version that covers the date. A rule that began later or had ended is left out."""
    by_id: dict[str, list[Mapping[str, Any]]] = {}
    for entry in _special(key)["rules"]:
        by_id.setdefault(_text(entry.get("rule_id")), []).append(entry)
    out: list[Rule] = []
    for rule_id, versions in by_id.items():
        found = version_on(versions, on)
        if found is None:
            continue
        version = found.version
        control = version.get("control")
        out.append(
            Rule(
                scope="special_district",
                key=key,
                rule_id=rule_id,
                rule=_text(version.get("rule")),
                applies_to=_text(version.get("applies_to")) or None,
                control=_RULE_CONTROLS.get(control) if isinstance(control, str) else None,
                kind=None,
                in_force=True,
                source=_source(
                    version,
                    section=_text(version.get("section")),
                    source_url=None,
                    before_data_start=found.before_data_start,
                ),
                extra=_extra(version, _SPECIAL_KEYS),
            )
        )
    return tuple(out)


def citywide_rules(key: str, on: dt.date | None) -> tuple[Rule, ...]:
    """The citywide rule under `key` as it stood on the date: one rule, or none when no version covers the
    date. Its terms are in `extra["facts"]`. Check `in_force`: a lapsed rule stays on file to say so."""
    try:
        versions = cast(Sequence[Mapping[str, Any]], _view()["citywide"][key])
    except KeyError:
        known = ", ".join(citywide_keys())
        raise KeyError(
            f"citywide rule {key!r} is not in the dated control data; the keys are {known}"
        ) from None
    if key in CITYWIDE_ENTRY_GROUPS:
        return citywide_entries(key, on)
    if _is_record(versions):
        raise KeyError(f"citywide key {key!r} is a plain record, not a dated rule: use citywide_record()")
    found = version_on(versions, on)
    if found is None:
        return ()
    version = found.version
    return (
        Rule(
            scope="citywide",
            key=key,
            rule_id=key,
            rule=_text(version.get("rule")),
            applies_to=None,
            control=None,
            kind=_text(version.get("kind")) or None,
            in_force=version.get("in_force") is not False,
            source=_source(
                version,
                section=_text(version.get("section")),
                source_url=None,
                before_data_start=found.before_data_start,
            ),
            extra=_extra(version, _CITYWIDE_KEYS),
        ),
    )


def citywide_run(key: str, on: dt.date | None, fact: str) -> Source | None:
    """The dates of one term of a citywide rule, like `same_since` for a district row: the `source` of the
    version in force on the date, with its start, its ordinance and its end widened to the unbroken run of
    versions whose `facts[fact]` is the same. A version that begins on a date when only other terms changed
    does not date this one. None when no version covers the date."""
    versions = cast(Sequence[Mapping[str, Any]], _view()["citywide"][key])
    found = version_on(versions, on)
    if found is None:
        return None

    def term(version: Mapping[str, Any]) -> Any:
        facts = version.get("facts")
        return facts.get(fact) if isinstance(facts, Mapping) else None

    here = term(found.version)
    first = last = found.index
    while first > 0 and term(versions[first - 1]) == here:
        first -= 1
    while last + 1 < len(versions) and term(versions[last + 1]) == here:
        last += 1
    source = _source(
        versions[first],
        section=_text(found.version.get("section")),
        source_url=None,
        before_data_start=found.before_data_start,
    )
    end = _date(versions[last].get("to"))
    return replace(
        source,
        url=_text(found.version.get("url")),
        source_url=_text(found.version.get("url")),
        in_force_to=end,
    )


def _entry_in_force(entry: Mapping[str, Any], on: dt.date | None) -> bool:
    start, end = _date(entry.get("from")), _date(entry.get("to"))
    on = _day(on)
    if on is None:
        return end is None
    if on < DATA_START:
        return start is None
    return (start is None or start <= on) and (end is None or on <= end)


def citywide_entries(
    key: str, on: dt.date | None, *, kind: str | None = None, include_ended: bool = False
) -> tuple[Rule, ...]:
    """The entries of an entry group (CITYWIDE_ENTRY_GROUPS) in force on the date, in the data's order. Each
    entry is dated on its own. `kind` filters to "approval_required" or "referral_step". With
    `include_ended=True`, entries that began on or before the date and had ended by it are returned too, with
    `in_force=False`, so a report can say "until <date> this was also sent to <agency>". An entry's permit,
    agency and other fields are in `extra`; `applies_to` is the data's own words."""
    if key not in CITYWIDE_ENTRY_GROUPS:
        raise KeyError(
            f"citywide entry group {key!r} is not one of {', '.join(sorted(CITYWIDE_ENTRY_GROUPS))}"
        )
    entries = cast(Sequence[Mapping[str, Any]], _view()["citywide"].get(key) or ())
    day = _day(on)
    out: list[Rule] = []
    for i, entry in enumerate(entries):
        entry_kind = _text(entry.get("kind")) or None
        if kind is not None and entry_kind != kind:
            continue
        live = _entry_in_force(entry, on)
        start, end = _date(entry.get("from")), _date(entry.get("to"))
        ended = (
            not live
            and end is not None
            and (day is None or end < day)
            and (start is None or day is None or start <= day)
        )
        if not live and not (include_ended and ended):
            continue
        parts = (
            key,
            _text(entry.get("permit")) or _text(entry.get("applies_to")),
            entry_kind or "",
            _text(entry.get("agency")),
            str(i),
        )
        out.append(
            Rule(
                scope="citywide",
                key=key,
                rule_id=":".join(part for part in parts if part),
                rule=_text(entry.get("rule")),
                applies_to=_text(entry.get("applies_to")) or None,
                control=None,
                kind=entry_kind,
                in_force=live,
                source=_source(
                    entry,
                    section=_text(entry.get("section")),
                    source_url=None,
                    before_data_start=day is not None and day < DATA_START,
                ),
                extra=_extra(entry, _CITYWIDE_KEYS | {"applies_to"}),
            )
        )
    return tuple(out)


# ---- consistency with the table the product uses now --------------------------------------------------
@dataclass(frozen=True)
class Difference:
    """One place where today's dated data and the product's zoning control table do not say the same thing."""

    district: str
    field: Literal["district", "bar_permission", "restaurant_permission", "hours"]
    product_value: str  # as the product table has it
    dated_value: str  # as today's version of the dated data has it
    quote: str  # the words of the code the dated data relies on
    section: str
    url: str
    # True when the two are recorded differently but lead to the same answer (the product table has no hours
    # value where the dated data records that the table has no hours row).
    same_effect: bool = False


_PRODUCT_PERMISSIONS: Mapping[str, str] = MappingProxyType(
    {"principal": "principal", "conditional": "conditional", "prohibited": "not_permitted"}
)


def consistency_report(product_table: Mapping[str, Mapping[str, Any]]) -> tuple[Difference, ...]:
    """Compare today's dated data with the table the product uses now, for every district in the dated data.

    `product_table` is the "zoning_controls" object of packages/precedent/precedent/static/sf_overlay_rules.json
    (district code -> {"bar_permission", "restaurant_permission", "hours", ...}). Compared: the first-story Bar
    and Restaurant cells, and the hours windows (the product's text is read by the product's own parser,
    `app.memo.pathway.parse_hours`; which uses the windows are written for is not compared). Neither file is
    changed. One `Difference` per field that differs, in the dated data's district order."""
    from app.memo.pathway import parse_hours  # here, not at the top: the engine imports this module

    out: list[Difference] = []
    for district in districts():
        product = product_table.get(district)
        if product is None:
            out.append(Difference(district, "district", "not in the product table", "covered", "", "", ""))
            continue
        for use, name in (("bar", "bar_permission"), ("restaurant", "restaurant_permission")):
            cell = use_control(district, cast(Use, use), "first", None)
            mine = cell.permission or "not readable"
            theirs = str(product.get(name))
            if _PRODUCT_PERMISSIONS.get(theirs) != cell.permission:
                out.append(
                    Difference(
                        district,
                        cast(Literal["bar_permission", "restaurant_permission"], name),
                        theirs,
                        mine + (f" (governing row: {cell.governing_row})" if cell.governed else ""),
                        cell.source.quote,
                        cell.source.section,
                        cell.source.url,
                    )
                )
        control = hours(district, None)
        text = product.get("hours")
        parsed = parse_hours(text) if isinstance(text, str) else None
        if parsed is None:
            theirs_windows: tuple[tuple[str, int, int], ...] | None = None
        else:
            theirs_windows = tuple((w.permission, w.start, w.end) for w in parsed.windows)
        mine_windows = tuple((_LETTERS[w.permission], w.start, w.end) for w in control.windows)
        if theirs_windows != mine_windows:
            out.append(
                Difference(
                    district,
                    "hours",
                    "no value" if text is None else str(text),
                    control.text,
                    control.source.quote,
                    control.source.section,
                    control.source.url,
                    same_effect=text is None and control.no_limit,
                )
            )
    return tuple(out)
