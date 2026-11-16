"""Typed, dated access to the control data (app.memo.controls).

Every test reads the bundled file through the module, or reads the same file raw to check the module against it.
No database, no model, no network. Nothing is printed.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import itertools
import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from precedent.sources.datasf_zoning import zoning_controls

from app.memo import controls as c
from app.memo.pathway import parse_hours

D = dt.date
ONE_DAY = dt.timedelta(days=1)
PERMISSIONS = {"principal", "conditional", "not_permitted"}
THE_32 = [
    "C-2", "CRNC", "CVR", "CCB", "NCD-POLK", "NCD-LOWER POLK STREET", "NCT-FILLMORE", "NCD-NORTH BEACH",
    "NCD-BROADWAY", "NCT-MISSION", "NCT-24TH-MISSION", "NCT-VALENCIA", "NCD-IRVING", "NCD-INNER SUNSET",
    "NCD-INNER CLEMENT", "NCD-CASTRO", "NCD-HAIGHT", "NCD-WEST PORTAL", "NCD-LAKESIDE VILLAGE", "NCD-BAYVIEW",
    "NCD-PACIFIC", "NC-1", "NC-2", "NC-3", "NCT-3", "RC-4", "RM-3", "RH-2", "MUR", "UMU", "C-3-G", "RH DTR",
]  # fmt: skip
STORIES = ("first", "second", "third_or_above", "basement")
SAMPLE_DATES = (None, D(2022, 6, 1))


@pytest.fixture(scope="module")
def raw() -> dict[str, Any]:
    return json.loads(c.DATA_PATH.read_text(encoding="utf-8"))


def row_accessor(row: str) -> Callable[[str, dt.date | None], Any]:
    """The accessor for a district row, as a function of (district, date). Use rows are read at the first story."""
    if row in c.USES:
        return lambda district, on: c.use_control(district, row, "first", on)
    return {
        "formula_retail": c.formula_retail,
        "use_size": c.use_size,
        "outdoor_activity_area": c.outdoor_activity_area,
        "hours": c.hours,
    }[row]


def every_result(district: str, on: dt.date | None) -> list[Any]:
    out: list[Any] = [c.use_control(district, use, story, on) for use in c.USES for story in STORIES]
    out += [
        c.formula_retail(district, on),
        c.use_size(district, on),
        c.outdoor_activity_area(district, on),
        c.hours(district, on),
    ]
    return out


# ---- loading ------------------------------------------------------------------------------------------
@pytest.fixture
def fresh_cache() -> Iterator[None]:
    c._data.cache_clear()
    yield
    c._data.cache_clear()


def test_the_file_is_read_once(fresh_cache: None) -> None:
    for district in THE_32[:5]:
        every_result(district, None)
        every_result(district, D(2023, 1, 1))
    c.special_rules("mission_alcohol_sud", None)
    c.citywide_rules("laundromat_removal", D(2024, 1, 1))
    info = c._data.cache_info()
    assert info.misses == 1
    assert info.hits > 10
    assert c._data() is c._data()


def test_a_missing_file_is_a_clear_error(
    fresh_cache: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setattr(c, "DATA_PATH", tmp_path / "sf_dated_controls.json")
    with pytest.raises(
        c.ControlDataError, match=r"file is missing.*sf_dated_controls\.json.*assemble_dated_controls"
    ):
        c.covers("NCD-POLK")
    # a failed read is not remembered: once the file is there, the next call reads it
    (tmp_path / "sf_dated_controls.json").write_text("{not json")
    with pytest.raises(c.ControlDataError, match="not valid JSON"):
        c.districts()
    (tmp_path / "sf_dated_controls.json").write_text('{"districts": {}, "citywide": {}}')
    with pytest.raises(c.ControlDataError, match="no 'special_districts' object"):
        c.districts()
    (tmp_path / "sf_dated_controls.json").write_text("[]")
    with pytest.raises(c.ControlDataError, match="not a JSON object"):
        c.districts()
    monkeypatch.undo()
    c._data.cache_clear()
    assert c.covers("NCD-POLK")


def test_the_32_districts_and_no_other() -> None:
    assert list(c.districts()) == THE_32
    assert all(c.covers(d) for d in THE_32)
    for other in ("NC-S", "NCD-UPPER FILLMORE", "PDR-1-G", "ncd-polk", "", "RH-1"):
        assert not c.covers(other)
        with pytest.raises(KeyError, match="not in the dated control data"):
            c.use_control(other, "bar", "first", None)
        with pytest.raises(KeyError):
            c.hours(other, None)
    assert c.read_on() == D(2026, 11, 10)


def test_unknown_use_or_story_is_refused() -> None:
    with pytest.raises(ValueError, match="no row"):
        c.use_control("NCD-POLK", "cafe", "first", None)
    with pytest.raises(ValueError, match="story"):
        c.use_control("NCD-POLK", "bar", "mezzanine", None)


# ---- version_on ---------------------------------------------------------------------------------------
VERSIONS = (
    {"from": None, "to": "2024-05-26", "v": 1},
    {"from": "2024-05-27", "to": "2025-10-05", "v": 2},
    {"from": "2025-10-06", "to": None, "v": 3},
)


@pytest.mark.parametrize(
    ("on", "v", "before"),
    [
        (None, 3, False),
        (D(2021, 12, 31), 1, True),
        (D(1999, 1, 1), 1, True),
        (D(2022, 1, 1), 1, False),
        (D(2024, 5, 26), 1, False),
        (D(2024, 5, 27), 2, False),
        (D(2025, 10, 5), 2, False),
        (D(2025, 10, 6), 3, False),
        (D(2031, 1, 1), 3, False),
    ],
)
def test_version_on(on: dt.date | None, v: int, before: bool) -> None:
    found = c.version_on(VERSIONS, on)
    assert found is not None
    assert (found.version["v"], found.index, found.before_data_start) == (v, v - 1, before)


def test_version_on_takes_a_datetime_as_its_day() -> None:
    found = c.version_on(VERSIONS, dt.datetime(2024, 5, 26, 23, 59))
    assert found is not None and found.version["v"] == 1


def test_version_on_says_none_when_no_version_covers_the_date() -> None:
    began_later = ({"from": "2024-01-14", "to": "2025-12-14"},)
    assert c.version_on(began_later, D(2024, 1, 13)) is None
    assert (
        c.version_on(began_later, D(2021, 1, 1)) is None
    )  # not in force on 2022-01-01: no first version to give
    assert c.version_on(began_later, D(2025, 12, 15)) is None
    assert c.version_on(began_later, None) is None  # ended: there is no version in force today
    assert c.version_on(began_later, D(2024, 1, 14)) is not None
    assert c.version_on((), None) is None
    assert c.version_on((), D(2024, 1, 1)) is None


def test_versions_on_file_do_not_overlap_or_leave_a_gap(raw: dict[str, Any]) -> None:
    """What version_on relies on: district rows and citywide rules run from null to null without a break; a
    special district rule may begin late or end, but its versions are contiguous."""

    def contiguous(versions: list[dict[str, Any]]) -> bool:
        return all(
            D.fromisoformat(a["to"]) + ONE_DAY == D.fromisoformat(b["from"])
            for a, b in itertools.pairwise(versions)
        )

    for district, dist in raw["districts"].items():
        assert set(dist["rows"]) == set(c.ROWS), district
        for row, versions in dist["rows"].items():
            assert versions[0]["from"] is None and versions[-1]["to"] is None, (district, row)
            assert contiguous(versions), (district, row)
    for key in c.citywide_keys():
        versions = raw["citywide"][key]
        assert versions[0]["from"] is None and versions[-1]["to"] is None, key
        assert contiguous(versions), key
    for key, special in raw["special_districts"].items():
        by_id: dict[str, list[dict[str, Any]]] = {}
        for rule in special["rules"]:
            by_id.setdefault(rule["rule_id"], []).append(rule)
        for rule_id, versions in by_id.items():
            assert contiguous(versions), (key, rule_id)


# ---- either side of every change ----------------------------------------------------------------------
def test_polk_nighttime_entertainment_changed_on_2024_05_27() -> None:
    before = [c.use_control("NCD-POLK", "nighttime_entertainment", s, D(2024, 5, 26)) for s in STORIES[:3]]
    after = [c.use_control("NCD-POLK", "nighttime_entertainment", s, D(2024, 5, 27)) for s in STORIES[:3]]
    assert [x.permission for x in before] == ["conditional", "not_permitted", "not_permitted"]
    assert [x.permission for x in after] == ["principal", "conditional", "not_permitted"]
    assert [x.differs_today for x in before] == [True, True, False]
    assert [x.permission_today for x in before] == ["principal", "conditional", "not_permitted"]
    assert not any(x.differs_today for x in after)

    first_before, first_after = before[0], after[0]
    assert first_before.source.in_force_from is None
    assert first_before.source.in_force_to == D(2024, 5, 26)
    assert first_before.source.ordinance is None
    assert first_before.source.quote == "Entertainment, Nighttime | § 102 | C | NP | NP"
    assert first_before.source.url.startswith("https://web.archive.org/")
    assert first_before.source.in_force_text == "in force since before 2022-01-01 until 2024-05-26"
    assert first_before.same_since is None

    assert first_after.source.in_force_from == D(2024, 5, 27)
    assert first_after.source.in_force_to is None
    assert first_after.source.ordinance == "Ord. 85-24, File No. 231221"
    assert first_after.source.quote == "Entertainment, Nighttime | § 102 | P | C | NP"
    assert first_after.source.section == "Planning Code § 723"
    assert first_after.source.source_url.startswith("https://gocodebook.com/")
    assert first_after.source.in_force_text == "in force from 2024-05-27 (Ord. 85-24, File No. 231221)"
    assert first_after.same_since == D(2024, 5, 27)
    assert after[2].same_since is None  # the third story was NP before and after
    assert not first_after.governed and first_after.governing_row is None
    # today is the later version; only the Historic Buildings passage (from 2026-04-11) is added
    today = c.use_control("NCD-POLK", "nighttime_entertainment", "first", None)
    assert first_after.historic_buildings is None and today.historic_buildings is not None
    assert dataclasses.replace(today, historic_buildings=None) == first_after


def test_24th_mission_bar_changed_on_2024_01_14() -> None:
    before = [c.use_control("NCT-24TH-MISSION", "bar", s, D(2024, 1, 13)) for s in STORIES[:3]]
    after = [c.use_control("NCT-24TH-MISSION", "bar", s, D(2024, 1, 14)) for s in STORIES[:3]]
    assert [x.permission for x in before] == ["not_permitted", "not_permitted", "not_permitted"]
    assert [x.permission for x in after] == ["conditional", "not_permitted", "not_permitted"]
    assert [x.differs_today for x in before] == [True, False, False]
    assert before[0].source.quote == "Bar | §§ 102, 202.2(a) | NP | NP | NP"
    assert after[0].source.quote == "Bar | §§ 102, 202.2(a) | C(2)(3) | NP | NP"
    assert after[0].source.ordinance == "Ord. 249-23, File No. 230701"
    assert after[0].source.in_force_from == D(2024, 1, 14)
    assert after[0].source.section == "Planning Code § 763"
    # the numbered notes on the cell are in the note, as text
    assert "Note 2: additional limitations apply in the Calle 24 Special Use District" in after[0].source.note
    assert "Note 3: additional limitations apply in the Mission Alcoholic Beverage" in after[0].source.note
    assert before[0].source.note.startswith("No numbered note on the cells.")


def test_nc1_use_size_changed_on_2025_10_06() -> None:
    before, after = c.use_size("NC-1", D(2025, 10, 5)), c.use_size("NC-1", D(2025, 10, 6))
    assert (before.principal_below_sqft, before.not_permitted_from_sqft) == (3000, None)
    assert (after.principal_below_sqft, after.not_permitted_from_sqft) == (3001, None)
    # the exact boundary, on both sides of the change
    assert [before.size_control(a) for a in (0, 2999, 3000, 3001, 500_000)] == [
        "principal", "principal", "conditional", "conditional", "conditional",
    ]  # fmt: skip
    assert [after.size_control(a) for a in (0, 2999, 3000, 3001, 500_000)] == [
        "principal", "principal", "principal", "conditional", "conditional",
    ]  # fmt: skip
    assert before.differs_today and not after.differs_today
    assert before.division is None and before.exemption == ""
    assert after.division == c.Division(True, "§ 121.2(b)", "no Net Addition of Gross Floor Area")
    assert "may be divided into two or more smaller" in after.exemption
    assert (
        before.source.quote == "Use Size | § 102 | P up to 2,999 square feet; C 3,000 square feet and above"
    )
    assert after.source.ordinance == "Ord. 173-25, File No. 250634"
    assert after.source.in_force_from == D(2025, 10, 6) == after.same_since
    assert before.source.in_force_to == D(2025, 10, 5)
    assert after.extra["cells_changed_from_previous"] is True
    assert c.use_size("NC-1", None) == after


@pytest.mark.parametrize("district", THE_32)
def test_either_side_of_every_change_in_every_row(district: str, raw: dict[str, Any]) -> None:
    """For each change on file: the last day of the earlier version answers with that version, the next day with
    the later one."""
    for row, versions in raw["districts"][district]["rows"].items():
        read = row_accessor(row)
        for earlier, later in itertools.pairwise(versions):
            last_day = D.fromisoformat(earlier["to"])
            first_day = D.fromisoformat(later["from"])
            assert first_day == last_day + ONE_DAY
            a, b = read(district, last_day), read(district, first_day)
            assert a.source.in_force_to == last_day and a.source.quote == earlier["quote"], (row, last_day)
            assert b.source.in_force_from == first_day and b.source.quote == later["quote"], (row, first_day)
            assert a.source.url == earlier["url"] and b.source.url == later["url"]
            assert b.source.ordinance == later["ordinance"]
            assert not a.source.before_data_start and not b.source.before_data_start
        assert read(district, None).source.quote == versions[-1]["quote"]
        assert read(district, D(2022, 1, 1)).source.quote == versions[0]["quote"]


def test_polk_use_size_through_all_five_versions() -> None:
    def controls_at(on: dt.date) -> list[str | None]:
        size = c.use_size("NCD-POLK", on)
        return [size.size_control(a) for a in (1999, 2000, 2001, 3000, 3001, 3999, 4000)]

    P, C, NP = "principal", "conditional", "not_permitted"  # noqa: N806
    assert controls_at(D(2023, 3, 11)) == [P, C, C, C, C, C, NP]
    assert controls_at(D(2023, 3, 12)) == [P, C, C, C, C, C, NP]  # the note changed; the thresholds did not
    assert controls_at(D(2025, 10, 5)) == [P, C, C, C, C, C, NP]
    assert controls_at(D(2025, 10, 6)) == [P, P, C, C, C, C, C]  # the NP band was removed
    assert controls_at(D(2025, 12, 14)) == [P, P, C, C, C, C, C]
    assert controls_at(D(2025, 12, 15)) == [P, P, P, P, C, C, C]
    middle = c.use_size("NCD-POLK", D(2024, 9, 1))
    assert middle.source.in_force_from == D(2024, 8, 12)  # the version began with a change to Note 2 only
    assert middle.same_since is None  # the thresholds had been the same since before 2022
    assert middle.differs_today
    assert "Legacy Business" in middle.exemption
    assert c.use_size("NCD-POLK", D(2025, 12, 1)).same_since == D(2025, 10, 6)


def test_a_version_that_changed_a_note_only() -> None:
    cell = c.use_control("NCD-POLK", "limited_restaurant", "first", D(2024, 9, 1))
    assert cell.permission == "principal"
    assert cell.source.in_force_from == D(2024, 8, 12)
    assert cell.source.ordinance == "Ord. 169-24, File No. 240411"
    assert cell.same_since is None and not cell.differs_today
    assert cell.source.note.startswith(
        "Cells unchanged; Ord. 169-24 added the reference to § 121.2 and Note 2"
    )


# ---- NA cells, read through the governing row ---------------------------------------------------------
def test_rc4_bar_is_read_from_the_governing_row() -> None:
    before = [c.use_control("RC-4", "bar", s, D(2025, 8, 31)) for s in STORIES[:3]]
    after = [c.use_control("RC-4", "bar", s, D(2025, 9, 1)) for s in STORIES[:3]]
    assert [x.permission for x in before] == ["principal", "conditional", "conditional"]
    assert [x.permission for x in after] == ["principal", "principal", "principal"]
    for cell in before + after:
        assert cell.governed
        assert cell.governing_row == "Retail Sales and Service Uses*"
        assert cell.extra["governed_by"]["row"] == "Retail Sales and Service Uses*"
    assert [x.differs_today for x in before] == [False, True, True]
    assert before[1].source.quote == "Retail Sales and Service Uses* | §§ 102, 202.2(a) | P (4) | P (4)"
    assert after[1].source.ordinance == "Ord. 124-25, File No. 250542"
    assert after[1].source.section == "Planning Code § 209.3"
    assert "Table 209.3 has no Bar row" in after[1].source.note


def test_umu_cells_are_read_from_the_governing_rows() -> None:
    for on in (D(2022, 6, 1), D(2023, 6, 2), D(2023, 6, 3), None):
        for use in ("bar", "restaurant", "limited_restaurant"):
            cell = c.use_control("UMU", use, "second", on)
            assert (cell.permission, cell.governed) == ("principal", True)
    old = c.use_control("UMU", "bar", "first", D(2023, 6, 2))
    new = c.use_control("UMU", "bar", "first", D(2023, 6, 3))
    assert old.governing_row == "All Retail Sales and Services that are not listed below"
    assert new.governing_row == "Retail Sales and Service Uses*"
    assert (
        new.same_since is None and not old.differs_today
    )  # the table was rewritten; the cell reads the same
    # Nighttime Entertainment had its own row in the old table and has none in the new one
    own = c.use_control("UMU", "nighttime_entertainment", "first", D(2023, 6, 2))
    governed = c.use_control("UMU", "nighttime_entertainment", "first", D(2023, 6, 3))
    assert (own.permission, own.governed, own.governing_row) == ("principal", False, None)
    assert (governed.permission, governed.governed) == ("principal", True)
    assert governed.governing_row == "Entertainment, Arts and Recreation Uses*"
    assert governed.same_since is None


def test_other_rows_are_read_through_the_governing_row_too() -> None:
    dtr = c.formula_retail("RH DTR", None)
    assert (dtr.control, dtr.applies_to, dtr.applies_to_all, dtr.governed) == ("principal", "all", True, True)
    assert dtr.governing_row == "All Non-Residential Uses Permitted, except as described below"
    outdoor = c.outdoor_activity_area("RH DTR", None)
    assert (outdoor.in_front, outdoor.elsewhere, outdoor.governed) == ("principal", "principal", True)
    assert outdoor.elsewhere_principal_if_202_2_a_7 is False
    assert outdoor.extra["governed_by"]["basis"].startswith("inferred")
    # no row and nothing governing: no answer, and not "permitted"
    for district in ("RH-2", "RM-3"):
        none = c.outdoor_activity_area(district, D(2024, 5, 26))
        assert (none.in_front, none.elsewhere, none.governed, none.governing_row) == (None, None, False, None)
        assert none.differs_today
        assert c.outdoor_activity_area(district, D(2024, 5, 27)).in_front is not None


# ---- stories ------------------------------------------------------------------------------------------
def test_basement_reads_as_first_and_says_so() -> None:
    for district in THE_32:
        for use in c.USES:
            for on in (None, D(2022, 6, 1), D(2024, 6, 1)):
                first = c.use_control(district, use, "first", on)
                basement = c.use_control(district, use, "basement", on)
                assert basement.basement_read_as_first and not first.basement_read_as_first
                assert (basement.story, basement.column) == ("basement", "first")
                assert dataclasses.replace(basement, story="first", basement_read_as_first=False) == first


def test_third_story_and_above() -> None:
    bar = c.use_control("NCD-POLK", "bar", "third_or_above", None)
    assert (bar.permission, bar.column, bar.story) == ("not_permitted", "third", "third_or_above")
    assert c.use_control("NCD-POLK", "bar", "first", None).permission == "conditional"
    assert c.use_control("NCD-POLK", "bar", "second", None).permission == "not_permitted"
    restaurant = [c.use_control("NCD-POLK", "restaurant", s, None).permission for s in STORIES]
    assert restaurant == ["principal", "principal", "not_permitted", "principal"]
    assert not bar.basement_read_as_first


# ---- hours --------------------------------------------------------------------------------------------
def in_force(versions: list[dict[str, Any]], on: dt.date | None) -> dict[str, Any]:
    found = c.version_on(versions, on)
    assert found is not None
    return dict(found.version)


def minute(text: str) -> int:
    return int(text[:2]) * 60 + int(text[3:])


def test_hours_wrap_midnight() -> None:
    polk = c.hours("NCD-POLK", None)
    assert [(w.permission, w.start, w.end, w.printed) for w in polk.windows] == [
        ("principal", 360, 120, True),
        ("conditional", 120, 360, True),
    ]
    assert not polk.no_limit and polk.not_stated == ()
    expected = {
        "06:00": "principal", "12:00": "principal", "23:59": "principal", "00:00": "principal",
        "01:59": "principal", "02:00": "conditional", "03:00": "conditional", "05:59": "conditional",
    }  # fmt: skip
    assert {t: polk.permission_at(minute(t)) for t in expected} == expected
    assert polk.permission_at(1440) == "principal"  # 24:00 reads as 00:00
    assert polk.text == "P 06:00-02:00; C 02:00-06:00"
    assert all(polk.permission_at(m) in PERMISSIONS for m in range(1440))


def test_a_window_that_ends_at_midnight() -> None:
    rh2 = c.hours("RH-2", D(2022, 6, 1))
    assert [w.text for w in rh2.windows] == ["P 06:00-22:00", "C 22:00-00:00", "NP 00:00-06:00"]
    assert rh2.permission_at(minute("21:59")) == "principal"
    assert rh2.permission_at(minute("22:00")) == "conditional"
    assert rh2.permission_at(minute("23:59")) == "conditional"
    assert rh2.permission_at(0) == "not_permitted"
    assert rh2.permission_at(minute("05:59")) == "not_permitted"
    assert rh2.differs_today
    assert [w.text for w in c.hours("RH-2", None).windows] == ["P 06:00-22:00", "NP 22:00-06:00"]
    assert c.hours("RH-2", D(2024, 1, 14)).same_since == D(2024, 1, 14)


def test_a_minute_no_window_covers_is_none_and_never_permitted() -> None:
    for district in ("CRNC", "CVR", "NCD-LAKESIDE VILLAGE"):
        control = c.hours(district, None)
        assert control.text == "P 06:00-23:00; C 23:00-02:00"
        assert not control.no_limit
        assert control.permission_at(minute("22:59")) == "principal"
        assert control.permission_at(minute("01:59")) == "conditional"
        for silent in ("02:00", "03:00", "05:59"):
            assert control.permission_at(minute(silent)) is None
        assert control.permission_at(minute("06:00")) == "principal"
    assert c.hours("NCD-LAKESIDE VILLAGE", None).not_stated == ((120, 360),)
    assert c.hours("CRNC", None).not_stated == ()


def test_a_window_the_row_does_not_print_is_marked() -> None:
    nc1 = c.hours("NC-1", None)
    assert [(w.text, w.printed) for w in nc1.windows] == [
        ("P 06:00-23:00", True),
        ("C 23:00-02:00", True),
        ("NP 02:00-06:00", False),
    ]
    assert nc1.permission_at(minute("03:00")) == "not_permitted"
    assert nc1.text.endswith("NP 02:00-06:00 (not printed in the row)")
    assert "NP" not in nc1.source.quote
    unprinted = [w for d in THE_32 for on in SAMPLE_DATES for w in c.hours(d, on).windows if not w.printed]
    assert len(unprinted) == 2  # NC-1, today and in 2022: the only one


def test_no_hours_control(raw: dict[str, Any]) -> None:
    for district in ("CCB", "NCT-MISSION", "NC-3", "C-2", "RC-4", "MUR"):
        control = c.hours(district, None)
        assert control.no_limit and control.windows == () and control.text == "no limit"
        assert all(control.permission_at(m) is None for m in (0, 180, 720, 1439))
    # the data's convention: an empty list of windows is a district with no hours control, and the note says so
    for district, dist in raw["districts"].items():
        for version in dist["rows"]["hours"]:
            assert bool(version["windows"]) != ("no hours control" in version["note"].lower()), district


# ---- formula retail -----------------------------------------------------------------------------------
def test_formula_retail() -> None:
    polk = c.formula_retail("NCD-POLK", None)
    assert (polk.control, polk.applies_to, polk.applies_to_all, polk.not_permitted_for) == (
        "conditional", "all", True, (),
    )  # fmt: skip
    assert polk.source.quote == "Formula Retail | §§ 102, 303.1 | C" and not polk.governed
    for district in ("CRNC", "CCB", "NCD-BROADWAY", "NCD-IRVING"):
        control = c.formula_retail(district, None)
        assert control.control == "conditional"
        assert control.not_permitted_for == ("Restaurant", "Limited Restaurant")

    # RM-3: three versions, each reaching different uses
    old = c.formula_retail("RM-3", D(2024, 1, 13))
    assert (old.control, old.governed, old.applies_to_all) == ("conditional", True, False)
    assert old.applies_to.startswith(
        "Limited Corner Commercial Uses (§ 231) and Limited Commercial Uses (§ 186)"
    )
    middle = c.formula_retail("RM-3", D(2024, 1, 14))
    assert (middle.control, middle.applies_to, middle.applies_to_all) == (
        "not_permitted", "Limited Corner Commercial Uses", False,
    )  # fmt: skip
    assert middle.extra["limited_commercial_use_sec_186_control"] == "C"
    new = c.formula_retail("RM-3", D(2024, 5, 27))
    assert (new.control, new.applies_to_all, new.governed) == ("not_permitted", True, False)
    assert (old.differs_today, middle.differs_today, new.differs_today) == (True, True, False)

    # rules for part of a district stay in `extra`, dated with the version
    mission_before = c.formula_retail("NCT-MISSION", D(2024, 1, 13))
    assert mission_before.extra["formula_retail_restaurant_rule"]["control"] == "NP"
    assert mission_before.extra["formula_retail_restaurant_rule"]["section"] == "781.5(b)(1)"
    assert c.formula_retail("NCT-MISSION", D(2024, 1, 14)).extra["formula_retail_restaurant_rule"] is None
    assert "principal_exception" not in c.formula_retail("RC-4", D(2025, 5, 31)).extra
    assert c.formula_retail("RC-4", D(2025, 6, 1)).extra["principal_exception"]["control"] == "P"
    geary = c.formula_retail("NC-3", None).extra["not_permitted_for_in_subarea"]
    assert [rule["uses"] for rule in geary] == [
        ("Bar", "Restaurant", "Limited Restaurant", "pet supply store")
    ]
    # a version that changed a sub-area rule only does not count as a change of the district's control
    assert c.formula_retail("NC-3", None).same_since is None


# ---- use size, outdoor activity area ------------------------------------------------------------------
def test_use_size_without_a_threshold_gives_no_answer() -> None:
    for district in ("RM-3", "RH-2", "MUR"):
        for on in SAMPLE_DATES:
            size = c.use_size(district, on)
            assert not size.has_threshold
            assert [size.size_control(a) for a in (1, 5_000, 1_000_000)] == [None, None, None]
    assert c.use_size("RM-3", None).extra["limited_corner_commercial_use_cap_sqft"] == 2500


def test_use_size_caps_and_what_stays_in_extra() -> None:
    c2 = c.use_size("C-2", None)
    assert [c2.size_control(a) for a in (50_000, 50_001, 120_000, 120_001)] == [
        "principal", "conditional", "conditional", "not_permitted",
    ]  # fmt: skip
    c3g = c.use_size("C-3-G", None)
    assert c3g.size_control(90_000) == "principal" and c3g.size_control(500_000) == "conditional"
    assert c3g.extra["not_permitted_only_if"].startswith("over 120,000 gross sq ft AND sells groceries")
    # RC-4 lost its cap and moved its threshold by one square foot on 2025-10-06
    before, after = c.use_size("RC-4", D(2025, 10, 5)), c.use_size("RC-4", D(2025, 10, 6))
    assert [before.size_control(a) for a in (5_999, 6_000, 120_000, 120_001)] == [
        "principal", "conditional", "conditional", "not_permitted",
    ]  # fmt: skip
    assert [after.size_control(a) for a in (6_000, 6_001, 120_001)] == [
        "principal",
        "conditional",
        "conditional",
    ]
    assert after.division == c.Division(True, "§ 121.5", "no Net Addition of Gross Floor Area")
    # UMU: the Historic Buildings exemption is its own version, from 2026-04-11
    assert "Historic Building" not in c.use_size("UMU", D(2026, 4, 10)).exemption
    umu = c.use_size("UMU", D(2026, 4, 11))
    assert "Historic Building" in umu.exemption and umu.source.ordinance == "Ord. 37-26, File No. 250886"
    assert (
        umu.same_since is None
        and umu.size_control(3_999) == "principal"
        and umu.size_control(4_000) == "conditional"
    )


def test_outdoor_activity_area() -> None:
    polk = c.outdoor_activity_area("NCD-POLK", None)
    assert (polk.in_front, polk.elsewhere, polk.elsewhere_principal_if_202_2_a_7) == (
        "principal", "conditional", True,
    )  # fmt: skip
    assert polk.source.quote.startswith(
        "Outdoor Activity Area | §§ 102, 145.2, 202.2 | P if located in front"
    )
    rc4 = c.outdoor_activity_area("RC-4", None)
    assert (rc4.in_front, rc4.elsewhere, rc4.elsewhere_principal_if_202_2_a_7) == (
        "principal",
        "conditional",
        False,
    )
    assert not polk.governed and polk.same_since is None and not polk.differs_today


# ---- a date before the data starts --------------------------------------------------------------------
def test_a_date_before_2022_gets_the_first_version_and_says_so() -> None:
    early = D(2021, 6, 30)
    for district in THE_32:
        for then, first in zip(
            every_result(district, early), every_result(district, c.DATA_START), strict=True
        ):
            assert then.source.before_data_start is True
            assert first.source.before_data_start is False
            assert then.source.in_force_from is None
            assert dataclasses.replace(then, source=first.source) == first
    for on in (c.DATA_START, D(2024, 1, 1), None):
        assert not c.use_control("NCD-POLK", "bar", "first", on).source.before_data_start
    # rules: only those already in force on 2022-01-01, each flagged
    early_rules = c.special_rules("mission_alcohol_sud", early)
    assert early_rules and all(r.source.before_data_start for r in early_rules)
    assert "mission.music_venue_type_90" not in {r.rule_id for r in early_rules}  # began 2024-01-14
    assert [r.rule_id for r in early_rules] == [
        r.rule_id for r in c.special_rules("mission_alcohol_sud", c.DATA_START)
    ]
    (laundromat,) = c.citywide_rules("laundromat_removal", early)
    assert laundromat.source.before_data_start and laundromat.in_force


# ---- every district answers every row -----------------------------------------------------------------
@pytest.mark.parametrize("district", THE_32)
@pytest.mark.parametrize("on", SAMPLE_DATES, ids=["today", "2022-06-01"])
def test_every_district_answers_all_eight_rows(
    district: str, on: dt.date | None, raw: dict[str, Any]
) -> None:
    rows = raw["districts"][district]["rows"]
    for use in c.USES:
        for story in STORIES:
            cell = c.use_control(district, use, story, on)
            assert (
                cell.permission in PERMISSIONS
            )  # every cell on file is readable, through a governing row or not
            assert cell.permission_today in PERMISSIONS
            assert cell.governed == (cell.governing_row is not None)
            assert cell.differs_today == (cell.permission != cell.permission_today)
            if on is None:
                assert not cell.differs_today
            else:
                assert cell.historic_buildings is None  # § 202.11 was not in force in 2022
    formula = c.formula_retail(district, on)
    assert formula.control in PERMISSIONS and formula.applies_to
    assert formula.applies_to_all == (formula.applies_to == "all")
    assert all(isinstance(u, str) for u in formula.not_permitted_for)
    size = c.use_size(district, on)
    assert size.principal_below_sqft is None or size.principal_below_sqft > 0
    if size.not_permitted_from_sqft is not None:
        assert size.principal_below_sqft is not None
        assert size.not_permitted_from_sqft > size.principal_below_sqft
    assert size.size_control(1) in PERMISSIONS | {None}
    assert isinstance(size.exemption, str)
    outdoor = c.outdoor_activity_area(district, on)
    assert outdoor.in_front in PERMISSIONS | {None} and outdoor.elsewhere in PERMISSIONS | {None}
    assert (outdoor.in_front is None) == (outdoor.elsewhere is None)
    control = c.hours(district, on)
    assert control.no_limit == (not control.windows)
    for m in range(0, 1440, 15):
        assert control.permission_at(m) in PERMISSIONS | {None}
    assert [[c._LETTERS[w.permission], w.start, w.end] for w in control.windows] == [
        [p, minute(a), minute(b)] for p, a, b in in_force(rows["hours"], on)["windows"]
    ]

    for result in every_result(district, on):
        src = result.source
        # enough for a sentence and a citation
        assert src.section.startswith("Planning Code § ")
        assert src.quote and src.url.startswith("https://") and src.source_url.startswith("https://")
        assert src.read_on == D(2026, 11, 10)
        assert src.in_force_text.startswith("in force ")
        assert (src.ordinance is None) == (src.in_force_from is None)
        assert not src.before_data_start
        if on is None:
            assert src.in_force_to is None and not result.differs_today
        else:
            assert src.in_force_from is None or c.DATA_START < src.in_force_from <= on
        assert result.same_since is None or result.same_since <= (src.in_force_from or c.DATA_START)
        assert isinstance(src.note, str)
        hash(result)
        json.dumps(c.plain(result.extra))
        with pytest.raises(TypeError):
            result.extra["first"] = "P"
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.district = "elsewhere"


def test_section_follows_a_renumbered_table() -> None:
    assert c.use_control("MUR", "bar", "first", D(2023, 6, 2)).source.section == "Planning Code § 841"
    assert c.use_control("MUR", "bar", "first", D(2023, 6, 3)).source.section == "Planning Code § 833"
    assert c.hours("MUR", D(2021, 1, 1)).source.section == "Planning Code § 841"
    assert c.formula_retail("MUR", None).source.section == "Planning Code § 833"


@pytest.mark.parametrize(
    ("section", "label"),
    [
        ("723", "Planning Code § 723"),
        ("209.3", "Planning Code § 209.3"),
        ("249.60(f)(1)", "Planning Code § 249.60(f)(1)"),
        ("722, Zoning Control Table Note (5)", "Planning Code § 722, Zoning Control Table Note (5)"),
        ("303(e); 174", "Planning Code §§ 303(e); 174"),
        ("145.2(a), (b); 202.2(a)(7)", "Planning Code §§ 145.2(a), (b); 202.2(a)(7)"),
        ("781.9(c)(2); Table 719 Note (4)", "Planning Code § 781.9(c)(2); Table 719 Note (4)"),
        (
            "102 (Bar; Restaurant; Restaurant, Limited)",
            "Planning Code § 102 (Bar; Restaurant; Restaurant, Limited)",
        ),
        ("202.12 [repealed]", "Planning Code § 202.12 [repealed]"),
        (
            "California Business and Professions Code § 23958.4(a), (b), (f); § 23790",
            "California Business and Professions Code § 23958.4(a), (b), (f); § 23790",
        ),
    ],
)
def test_section_label(section: str, label: str) -> None:
    assert c.section_label(section) == label


# ---- Historic Buildings (§ 202.11, from 2026-04-11) ---------------------------------------------------
def test_the_historic_buildings_passage_is_given_only_from_its_date() -> None:
    day_before = c.use_control("NCD-POLK", "bar", "first", D(2026, 4, 10))
    first_day = c.use_control("NCD-POLK", "bar", "first", D(2026, 4, 11))
    today = c.use_control("NCD-POLK", "bar", "first", None)
    assert day_before.historic_buildings is None
    assert first_day.historic_buildings == today.historic_buildings
    assert first_day.historic_buildings is not None
    assert first_day.historic_buildings.startswith(
        "Historic Buildings, from 2026-04-11 (Ord. 37-26, File No. 250886"
    )
    assert first_day.historic_buildings.endswith("The cells recorded here are the general ones.")
    assert "a C cell reads P and an NP cell reads C" in first_day.historic_buildings
    # the cell itself is the general one, the same on both days; the note is the same text on both days
    assert day_before.permission == first_day.permission == "conditional"
    assert day_before.source == first_day.source
    assert first_day.historic_buildings in day_before.source.note
    # where the district's controls are left unchanged in Historic Buildings, the passage says so
    mission = c.use_control("NCT-24TH-MISSION", "bar", "first", None).historic_buildings
    assert mission is not None and mission.endswith("so these cells still apply in Historic Buildings.")


def test_historic_buildings_passages_across_the_data() -> None:
    without: list[tuple[str, str]] = []
    for district in THE_32:
        for use in c.USES:
            for on in (D(2022, 6, 1), D(2025, 1, 1), D(2026, 4, 10)):
                assert c.use_control(district, use, "first", on).historic_buildings is None
            cell = c.use_control(district, use, "first", None)
            if cell.historic_buildings is None:
                assert "Historic Buildings, from" not in cell.source.note
                without.append((district, use))
                continue
            assert cell.historic_buildings.startswith("Historic Buildings")
            assert cell.historic_buildings in cell.source.note
            for tail in ("Reconciliation", "Reconciler:", "Settled 2026-11-10", "governed_by gives"):
                assert tail not in cell.historic_buildings
    # today's notes with no Historic Buildings passage (the readers wrote none)
    assert without == [
        ("CRNC", "limited_restaurant"),
        ("CVR", "limited_restaurant"),
        ("CCB", "limited_restaurant"),
        ("CCB", "nighttime_entertainment"),
        ("NCD-HAIGHT", "limited_restaurant"),
        ("RH DTR", "bar"),
        ("RH DTR", "restaurant"),
        ("RH DTR", "limited_restaurant"),
        ("RH DTR", "nighttime_entertainment"),
    ]


# ---- special district and citywide rules --------------------------------------------------------------
def by_id(rules: tuple[c.Rule, ...]) -> dict[str, c.Rule]:
    out = {r.rule_id: r for r in rules}
    assert len(out) == len(rules)  # one version per rule on any date
    return out


def test_special_district_metadata() -> None:
    assert c.special_district_keys() == (
        "mission_alcohol_sud", "north_beach_sud", "haight_alcohol_rusd", "third_street_alcohol_rud",
        "soma_youth_family_sud", "calle_24_sud", "lower_haight_alcohol_rud",
    )  # fmt: skip
    mission = c.special_district("mission_alcohol_sud")
    assert mission.name == "Mission Alcoholic Beverage Special Use District"
    assert mission.section.startswith("249.60")
    assert "Mission Alcohol Restrict" in mission.overlay_hint
    assert c.special_district("north_beach_sud").extra["repeal"]["effective"] == "2025-12-15"
    assert c.special_district("lower_haight_alcohol_rud").extra["reaches_bars_or_restaurants"] is False
    for call in (c.special_district, lambda k: c.special_rules(k, None), lambda k: c.citywide_rules(k, None)):
        with pytest.raises(KeyError, match="not in the dated control data"):
            call("nowhere")


def test_special_rules_either_side_of_their_changes() -> None:
    before = by_id(c.special_rules("north_beach_sud", D(2025, 12, 14)))
    after = by_id(c.special_rules("north_beach_sud", D(2025, 12, 15)))
    lr = "north_beach.prior_use.limited_restaurant"
    assert (before[lr].control, after[lr].control) == ("conditional", "principal")
    assert before[lr].source.section == "Planning Code § 780.3(c)(1), (c)(1)(C)"
    assert after[lr].source.section == "Planning Code § 722, Zoning Control Table (Restaurant, Limited row)"
    assert after[lr].source.ordinance == "Ord. 217-25, File No. 250682"
    assert after[lr].source.in_force_from == D(2025, 12, 15) and before[lr].source.in_force_to == D(
        2025, 12, 14
    )
    assert after[lr].applies_to == "Limited Restaurant (new), First Story"
    # rules that ended with the repeal, and rules that only existed for a while
    ended = {"north_beach.conditional_use_extra_finding", "north_beach.music_venue_type_90"}
    assert ended <= set(before) and not ended & set(after)
    assert "north_beach.music_venue_type_90" not in by_id(c.special_rules("north_beach_sud", D(2024, 1, 13)))
    assert "north_beach.music_venue_type_90" in by_id(c.special_rules("north_beach_sud", D(2024, 1, 14)))
    assert after["north_beach.storefront_merger"].extra["conditional_up_to_sqft"] == 3000
    assert before["north_beach.hours"].extra["windows"] == (("P", "06:00", "02:00"), ("NP", "02:00", "06:00"))

    haight = "haight.new_on_sale_establishment"
    assert by_id(c.special_rules("haight_alcohol_rusd", D(2024, 1, 13)))[haight].control == "not_permitted"
    assert by_id(c.special_rules("haight_alcohol_rusd", D(2024, 1, 14)))[haight].control == "conditional"
    third = "third.type_42_bayview_ncd"
    assert by_id(c.special_rules("third_street_alcohol_rud", D(2025, 4, 6)))[third].control == "not_permitted"
    assert by_id(c.special_rules("third_street_alcohol_rud", D(2025, 4, 7)))[third].control == "conditional"
    soma = "soma_yf.restaurant"
    old, new = (
        by_id(c.special_rules("soma_youth_family_sud", on))[soma] for on in (D(2023, 6, 2), D(2023, 6, 3))
    )
    assert (old.control, new.control) == ("conditional", "conditional")
    assert old.source.section == "Planning Code § 249.40A(c)(1)(A)(v)"
    assert new.source.section == "Planning Code § 249.38(c)(1)(A)(v)"


def test_special_rules_are_typed() -> None:
    mission = by_id(c.special_rules("mission_alcohol_sud", None))
    cu = mission["mission.restaurant_cu_sub_area"]
    assert (cu.scope, cu.key, cu.control, cu.kind, cu.in_force) == (
        "special_district", "mission_alcohol_sud", "conditional", None, True,
    )  # fmt: skip
    assert cu.source.section == "Planning Code § 249.60(f)(1)"
    assert cu.applies_to is not None and cu.applies_to.startswith("Restaurant (§ 102)")
    licence = mission["mission.new_bar_licence_from_bar_in_district"]
    assert licence.control == "requirement"  # a condition, not a permission
    assert mission["mission.existing_liquor_establishment_temporary_closure"].extra["max_closure_days"] == 120
    assert mission["mission.new_liquor_store"].control == "not_permitted"
    assert mission["mission.music_venue_type_90"].source.in_force_from == D(2024, 1, 14)


@pytest.mark.parametrize(
    "on", [None, D(2021, 1, 1), D(2022, 6, 1), D(2024, 1, 14), D(2025, 12, 15), D(2026, 8, 23)]
)
def test_every_special_district_answers(on: dt.date | None, raw: dict[str, Any]) -> None:
    for key in c.special_district_keys():
        rules = c.special_rules(key, on)
        ids = list(by_id(rules))
        on_file = list(dict.fromkeys(r["rule_id"] for r in raw["special_districts"][key]["rules"]))
        assert ids == [i for i in on_file if i in set(ids)]  # the file's order
        assert rules, key
        for rule in rules:
            assert rule.control in {"principal", "conditional", "not_permitted", "requirement"}
            assert rule.rule and rule.rule_id and rule.source.quote and rule.source.url.startswith("https://")
            assert rule.source.source_url == rule.source.url
            assert rule.source.section.startswith(("Planning Code § ", "Planning Code §§ "))
            assert rule.source.before_data_start == (on is not None and on < c.DATA_START)
            if on is not None and on >= c.DATA_START:
                assert rule.source.in_force_from is None or rule.source.in_force_from <= on
                assert rule.source.in_force_to is None or on <= rule.source.in_force_to
            if on is None:
                assert rule.source.in_force_to is None
            json.dumps(c.plain(rule.extra))
            hash(rule)


def test_citywide_rules() -> None:
    assert set(c.citywide_keys()) >= {
        "laundromat_removal", "enlarge_or_intensify", "amend_prior_conditions", "neighbourhood_notification",
        "formula_retail_definition",
    }  # fmt: skip
    # laundromat removal: in force to 2024-12-20, then on file as lapsed, then repealed
    (in_force,) = c.citywide_rules("laundromat_removal", D(2024, 12, 20))
    (lapsed,) = c.citywide_rules("laundromat_removal", D(2024, 12, 21))
    (repealed,) = c.citywide_rules("laundromat_removal", None)
    assert (in_force.in_force, lapsed.in_force, repealed.in_force) == (True, False, False)
    assert in_force.extra["facts"]["control_for_change_of_use_or_demolition_of_a_laundromat"] == "C"
    assert lapsed.extra["facts"]["control_for_change_of_use_or_demolition_of_a_laundromat"] is None
    assert in_force.source.section == "Planning Code §§ 202.12; 102 (Laundromat)"
    assert repealed.source.section == "Planning Code § 202.12 [repealed]"
    assert repealed.source.in_force_from == D(2026, 3, 16)
    assert (in_force.scope, in_force.key, in_force.rule_id, in_force.control, in_force.kind) == (
        "citywide", "laundromat_removal", "laundromat_removal", None, "approval_required",
    )  # fmt: skip
    # neighbourhood notification is a step inside an approval, and stopped being triggered by a change of use
    (notice_before,) = c.citywide_rules("neighbourhood_notification", D(2024, 1, 13))
    (notice_after,) = c.citywide_rules("neighbourhood_notification", D(2024, 1, 14))
    assert notice_before.kind == notice_after.kind == "step_within_approval"
    assert notice_before.extra["facts"]["change_of_use_triggers_section_311"] is True
    assert notice_after.extra["facts"]["change_of_use_triggers_section_311"] is False
    assert notice_after.source.ordinance == "Ord. 248-23, File No. 230446, App. 12/14/2023, Eff. 1/14/2024"
    # the general use size rule changed its wording on the same day as the district rows
    (size_before,) = c.citywide_rules("use_size_general", D(2025, 10, 5))
    (size_after,) = c.citywide_rules("use_size_general", D(2025, 10, 6))
    assert size_before.extra["facts"]["conditional_at_exact_figure"] is True
    assert size_after.extra["facts"]["conditional_at_exact_figure"] is False
    (occupancy,) = c.citywide_rules("change_of_occupancy", None)
    assert occupancy.source.section.startswith("California Building Code 2025 edition")


@pytest.mark.parametrize("on", [None, D(2021, 1, 1), D(2022, 6, 1), D(2024, 12, 21), D(2026, 4, 11)])
def test_every_citywide_rule_answers(on: dt.date | None) -> None:
    for key in c.citywide_keys():
        (rule,) = c.citywide_rules(key, on)
        assert rule.kind in {"approval_required", "step_within_approval", "definition"}
        assert rule.control is None and rule.applies_to is None
        assert rule.rule and rule.source.quote and rule.source.url.startswith("https://")
        assert isinstance(rule.extra["facts"], type(rule.extra)) and rule.extra["facts"]
        assert rule.in_force or key == "laundromat_removal"
        assert rule.source.before_data_start == (on is not None and on < c.DATA_START)
        json.dumps(c.plain(rule.extra))
        hash(rule)


# ---- determinism --------------------------------------------------------------------------------------
def snapshot() -> list[Any]:
    out: list[Any] = []
    for district in THE_32:
        for on in (None, D(2021, 1, 1), D(2022, 6, 1), D(2024, 5, 27), D(2025, 10, 6)):
            out += every_result(district, on)
    for key in c.special_district_keys():
        out.append(c.special_district(key))
        out += [c.special_rules(key, on) for on in (None, D(2022, 6, 1), D(2025, 12, 14))]
    out += [c.citywide_rules(key, on) for key in c.citywide_keys() for on in (None, D(2022, 6, 1))]
    out.append(c.consistency_report(zoning_controls()))
    return out


def test_same_inputs_same_answer(fresh_cache: None) -> None:
    first = snapshot()
    again = snapshot()
    assert first == again
    c._data.cache_clear()  # a fresh read of the file gives the same answers
    reread = snapshot()
    assert first == reread
    as_text = [repr(c.plain(dataclasses.asdict(x)) if dataclasses.is_dataclass(x) else x) for x in first]
    assert as_text == [
        repr(c.plain(dataclasses.asdict(x)) if dataclasses.is_dataclass(x) else x) for x in reread
    ]


def test_plain_gives_back_what_the_file_held(raw: dict[str, Any]) -> None:
    assert c.plain(c._data()) == raw
    version = raw["districts"]["NC-3"]["rows"]["formula_retail"][-1]
    extra = c.formula_retail("NC-3", None).extra
    assert c.plain(extra) == {
        k: v for k, v in version.items() if k not in c._PROVENANCE_KEYS and k not in c._FORMULA_KEYS
    }
    assert "settled" in c.use_size("NCD-POLK", None).extra  # the reconciliation record is kept, unchanged


# ---- consistency with the table the product uses now --------------------------------------------------
def test_consistency_with_the_product_table() -> None:
    """Today's first-story Bar and Restaurant cells and hours windows, against the zoning control table the
    product reads. The differences are pinned: a new one, or one that goes away, fails here."""
    product = zoning_controls()
    assert set(THE_32) <= set(product)
    report = c.consistency_report(product)
    assert all(d.field == "hours" for d in report)  # every Bar and Restaurant first-story cell agrees
    assert [(d.district, d.product_value, d.dated_value, d.same_effect) for d in report] == [
        ("C-2", "no value", "no limit", True),
        (
            "NC-1",
            "P 6 a.m.–11 p.m.; C 11 p.m.–2 a.m.",
            "P 06:00-23:00; C 23:00-02:00; NP 02:00-06:00 (not printed in the row)",
            False,
        ),
        ("RC-4", "no value", "no limit", True),
        (
            "RM-3",
            "Limited Corner Commercial / § 186 uses: P 6 a.m.–10 p.m.",
            "P 06:00-22:00; NP 22:00-06:00",
            False,
        ),
        ("C-3-G", "no value", "no limit", True),
    ]
    for d in report:
        assert d.quote and d.section.startswith("Planning Code § ") and d.url.startswith("https://")
    nc1 = next(d for d in report if d.district == "NC-1")
    assert nc1.quote == "Hours of Operation | § 102 | P 6 a.m. - 11 p.m.; C 11 p.m. - 2 a.m."
    rm3 = next(d for d in report if d.district == "RM-3")
    assert rm3.quote.endswith("P 6:00 a.m. to 10:00 p.m.; NP 10:00 p.m. to 6:00 a.m.")
    # the product's own parser reads every hours text it has for these districts
    for district in THE_32:
        text = product[district]["hours"]
        assert text is None or parse_hours(text) is not None, district


def test_consistency_report_finds_a_difference_when_there_is_one() -> None:
    product = {k: dict(v) for k, v in zoning_controls().items()}
    baseline = c.consistency_report(product)
    product["NCD-POLK"]["bar_permission"] = "principal"  # the code says C
    product["NCT-24TH-MISSION"]["restaurant_permission"] = "prohibited"  # the code says C
    product["RC-4"]["bar_permission"] = "unknown"  # the governing row says P
    product["NCD-CASTRO"]["hours"] = "P 6 a.m.–2 a.m.; NP 2 a.m.–6 a.m."  # the code says C from 2 to 6 a.m.
    product["NCT-FILLMORE"]["hours"] = "open late"  # cannot be parsed; the code says no limit
    del product["UMU"]
    found = {(d.district, d.field): d for d in c.consistency_report(product) if d not in baseline}
    assert set(found) == {
        ("NCD-POLK", "bar_permission"),
        ("NCT-24TH-MISSION", "restaurant_permission"),
        ("RC-4", "bar_permission"),
        ("NCD-CASTRO", "hours"),
        ("NCT-FILLMORE", "hours"),
        ("UMU", "district"),
    }
    polk = found["NCD-POLK", "bar_permission"]
    assert (polk.product_value, polk.dated_value) == ("principal", "conditional")
    assert polk.quote == "Bar | §§ 102, 202.2(a) | C(1) | NP | NP" and polk.section == "Planning Code § 723"
    mission = found["NCT-24TH-MISSION", "restaurant_permission"]
    assert (mission.product_value, mission.dated_value) == ("prohibited", "conditional")
    rc4 = found["RC-4", "bar_permission"]
    assert rc4.dated_value == "principal (governing row: Retail Sales and Service Uses*)"
    castro = found["NCD-CASTRO", "hours"]
    assert castro.dated_value == "P 06:00-02:00; C 02:00-06:00" and not castro.same_effect
    assert found["NCT-FILLMORE", "hours"].dated_value == "no limit"
    assert not found["NCT-FILLMORE", "hours"].same_effect
    assert found["UMU", "district"].product_value == "not in the product table"


# ---- entry groups: approvals and referral steps are separate entries (spec section 3a) -----------------
FOUR_PERMITS = (
    "place_of_entertainment",
    "limited_live_performance",
    "fixed_place_outdoor_amplified_sound",
    "extended_hours_premises",
)


def _permit(rule: c.Rule) -> str:
    return str(rule.extra.get("permit") or "")


def _agency(rule: c.Rule) -> str:
    return str(rule.extra.get("agency") or "")


def test_entry_groups_are_not_versioned_rules() -> None:
    assert set(c.citywide_entry_groups()) == set(c.CITYWIDE_ENTRY_GROUPS)
    assert not set(c.citywide_keys()) & set(c.CITYWIDE_ENTRY_GROUPS)
    assert "ordinance_118_25" in c.citywide_record_keys()
    record = c.citywide_record("ordinance_118_25")
    assert record["effective"] == "2025-08-17" and record["approved"] == "2025-07-17"


@pytest.mark.parametrize(
    "on", [D(2022, 6, 1), D(2024, 1, 13), D(2024, 1, 14), D(2025, 8, 16), D(2025, 8, 17), None]
)
def test_the_four_entertainment_permits_are_approvals_on_every_date(on: dt.date | None) -> None:
    approvals = c.citywide_entries("entertainment_permits", on, kind="approval_required")
    permits = {_permit(r) for r in approvals}
    assert set(FOUR_PERMITS) <= permits, permits
    assert all(r.kind == "approval_required" and r.in_force for r in approvals)


def test_ordinance_118_25_removed_referrals_not_approvals() -> None:
    def steps(on: dt.date | None) -> set[tuple[str, str]]:
        return {
            (_permit(r), _agency(r))
            for r in c.citywide_entries("entertainment_permits", on, kind="referral_step")
        }

    before, after = steps(D(2025, 8, 16)), steps(D(2025, 8, 17))
    gone = before - after
    assert any(p == "place_of_entertainment" and "Building" in a for p, a in gone), gone
    assert any(p == "limited_live_performance" and "Planning" in a for p, a in gone), gone
    assert any(p == "fixed_place_outdoor_amplified_sound" and "Planning" in a for p, a in gone), gone
    assert any(p == "extended_hours_premises" and "Building" in a for p, a in gone), gone
    # Planning still reviews Place of Entertainment and Extended-Hours Premises applications.
    assert any(p == "place_of_entertainment" and "Planning" in a for p, a in after)
    assert any(p == "extended_hours_premises" and "Planning" in a for p, a in after)
    # A removed referral is reported as ended, and stays a referral step.
    ended = [
        r
        for r in c.citywide_entries(
            "entertainment_permits", D(2025, 8, 17), kind="referral_step", include_ended=True
        )
        if not r.in_force
    ]
    assert ended and all(r.kind == "referral_step" for r in ended)


def test_citywide_rules_returns_every_entry_of_an_entry_group() -> None:
    assert c.citywide_rules("other_referrals", None) == c.citywide_entries("other_referrals", None)
    assert all(r.kind == "referral_step" for r in c.citywide_entries("other_referrals", None))
