"""The confirmed review findings on the rows, the referrals and determinism (rule table v2), one test or more each.

Synthetic inputs with the builders of tests/test_pathway.py and tests/test_rows.py. No database, no model, no
network, no clock.
"""

from __future__ import annotations

import datetime as dt
import itertools
from typing import Any

from app.agents.memo_runner import required_areas
from app.memo import rows, tracts
from app.memo import triggers as tg
from app.memo.facts import MISSING_PHRASES, SiteFacts, SiteLicence
from app.memo.pathway import NOTHING_FILED_WHEN_ALLOWED, determine
from app.models.profile import BusinessProfile
from tests.test_pathway import (
    C2,
    COCKTAIL_BAR,
    PACIFIC,
    RESTAURANT,
    SITE_995,
    STATED,
    THIRD_ST_RUD,
    TYPE_48_AT_995,
    UMU,
    WINE_BAR,
    given,
    licence,
    patio,
    profile,
    row,
    run,
    trigger,
    zoning,
)
from tests.test_rows import alcohol, bar, building, changes, restaurant, site, texts, tract_lines

CHANGE = MISSING_PHRASES["changes_existing_business"]
NEW = {"alcohol_transaction": "new_licence"}
CASTRO = zoning("NCD-CASTRO", section="Planning Code § 715")
VALENCIA_TRACT = "208.01"  # over its authorised number of on-sale licences


# ---- a stated last use that is the use proposed -----------------------------------------------------------------
def test_a_stated_last_use_equal_to_the_use_proposed_is_not_read_as_new() -> None:
    d = run(given(COCKTAIL_BAR, existing_use_stated=["bar"], **STATED, **NEW), z=PACIFIC, overlays=[])
    t1 = trigger(d, "T1")
    assert t1.control == "not_decided" and t1.missing_inputs == [CHANGE]
    assert row(d, "zoning_use").status == "insufficient_information"
    assert CHANGE in row(d, "zoning_use").missing_inputs
    # nothing reads "not permitted" from a use that may be the one already there
    assert {row(d, a).status for a in ("alcohol", "health")} & {"not_permitted"} == set()
    castro = run(given(COCKTAIL_BAR, existing_use_stated=["bar"], **STATED, **NEW), z=CASTRO, overlays=[])
    assert trigger(castro, "T1").control == "not_decided"


# ---- the alcohol row where zoning bars the concept as described ---------------------------------------------------
def test_the_alcohol_row_follows_a_zoning_row_that_is_not_permitted_for_any_trigger() -> None:
    big = given(COCKTAIL_BAR, formula_retail=False, square_feet=6000, closing_hour="23:00", **NEW,
                existing_use_stated=["retail"], stories=["first"])  # fmt: skip
    d = run(big, z=CASTRO, overlays=[])
    assert trigger(d, "T7").control == "not_permitted"
    alcohol_row = row(d, "alcohol")
    assert (alcohol_row.status, alcohol_row.status_note, alcohol_row.referral_steps) == (
        "not_permitted",
        None,
        [],
    )
    assert alcohol_row.basis[-1].text.startswith(
        "Zoning does not permit the concept as described at this address (use size)"
    )
    # use size is not a prohibited use: Planning Code § 175(a) does not reach the City permits (the decision of
    # 2026-11-12 covers the use itself and formula retail only)
    for area in ("health", "building_change_of_use", "entertainment"):
        assert row(d, area).status != "not_permitted", area
        assert all(line.code_section != "Planning Code § 175(a)" for line in row(d, area).basis), area
    # a business that stays and is enlarged past the cap: the licence row goes on to the licence's own rules, as
    # before the decision (backtest case D05)
    stays = given(big, existing_use_stated=["bar"], changes_existing_business="enlarge_and_intensify")
    kept = run(stays, z=CASTRO, overlays=[])
    assert (trigger(kept, "T7").control, row(kept, "zoning_use").status) == ("not_permitted", "not_permitted")
    assert [
        row(kept, a).status != "not_permitted" for a in ("alcohol", "health", "building_change_of_use")
    ] == [True] * 3


# ---- the building row: silence is not "no change" --------------------------------------------------------------------
def test_building_occupancy_is_not_no_from_silence() -> None:
    silent = changes(restaurant(seats=200), s=site("restaurant"))
    assert silent.building_occupancy == "not_established"
    row_ = building(restaurant(seats=200), s=site("restaurant"))
    assert row_.status == "insufficient_information"
    assert CHANGE in row_.missing_inputs and rows.EXISTING_GROUP_PHRASE in row_.missing_inputs
    # the sentence names the occupancy question only: the change of use is decided ("no")
    assert row_.basis[-1].text.startswith("Without ")
    assert (
        "whether this is a change of occupancy, so they cannot say which building permit"
        in row_.basis[-1].text
    )
    stated = building(restaurant(changes_existing_business="none"), s=site("restaurant"))
    assert stated.status == "allowed"


def test_building_row_b3_names_only_the_open_question() -> None:
    enlarged = building(restaurant(changes_existing_business="enlarge"), s=site("restaurant"))
    assert enlarged.status == "insufficient_information"
    assert "cannot say whether this is a change of occupancy" in enlarged.basis[-1].text
    both = building(restaurant())
    assert "cannot say whether this is a change of use or of occupancy" in both.basis[-1].text


# ---- the alcohol row: a licence already held, the same type on file, the limb of § 23958.4(b) -----------------------
def test_a_licence_already_held_is_allowed_and_files_nothing() -> None:
    held = alcohol(bar(alcohol_transaction="licence_already_held"))
    assert held.status == "allowed" and held.referral_steps == []
    assert held.basis[-1].text.startswith("The business already holds the licence for these premises")
    assert "alcohol" in NOTHING_FILED_WHEN_ALLOWED
    d = run(given(COCKTAIL_BAR, alcohol_transaction="licence_already_held", changes_existing_business="none",
                  **STATED), z=C2, overlays=[], records=[TYPE_48_AT_995])  # fmt: skip
    assert row(d, "alcohol").status == "allowed" and "ABC licence" not in d.entitlement_path


def _with_licence(number: str) -> SiteFacts:
    shown = site("restaurant" if number in ("41", "47") else "bar")
    lic = SiteLicence("abc:1", number, None, None, "app:abc:1", "https://example.org/abc/1")
    return SiteFacts(shown.rules_date, (lic,), shown.existing_use, shown.existing_use_lines, ())


def test_the_same_licence_type_on_file_takes_the_tract_test_out() -> None:
    from tests.test_rows import OVER

    row_ = alcohol(restaurant(), s=_with_licence("41"), tract=OVER)
    assert row_.status == "further_review" and row_.status_note is None
    assert any("§ 23958.4(f)" in (line.code_section or "") for line in row_.basis)
    assert not any("convenience or necessity" in step.text.lower() for step in row_.referral_steps)
    other = alcohol(restaurant(), s=_with_licence("48"), tract=OVER)
    assert other.status_note == tracts.PCN_STATUS_NOTE


def test_a_licence_type_the_rules_cannot_place_in_a_limb_says_so() -> None:
    from tests.test_rows import OVER

    venue = alcohol(bar(licence_type="40"), tract=OVER)
    assert venue.status_note == tracts.PCN_STATUS_NOTE
    assert any("cannot tell which limb of § 23958.4(b)" in text for text in texts(venue.basis))
    assert not any(step.text.startswith("Public convenience or necessity") for step in venue.referral_steps)


def test_tract_figures_later_than_the_rules_date_set_no_note() -> None:
    early = alcohol(restaurant(), tract=VALENCIA_TRACT, on=dt.date(2022, 6, 1))
    assert early.status == "further_review" and early.status_note is None
    lines = tract_lines(early)
    assert len(lines) == 2 and lines[1].text.startswith(
        "These figures are later than the rules date (1 June 2022)"
    )
    now = alcohol(restaurant(), tract=VALENCIA_TRACT, on=dt.date(2026, 11, 10))
    assert now.status_note == tracts.PCN_STATUS_NOTE


# ---- neighbourhood notice: establishing a Formula Retail use ----------------------------------------------------------
def test_formula_retail_triggered_notice_before_2024_01_14() -> None:
    on = dt.date(2023, 6, 1)
    chain = changes(restaurant(formula_retail=True, existing_use_stated=["retail"]), district="NC-3", on=on)
    assert chain.neighbourhood_notice == "required"
    assert "establishing a Formula Retail use" in chain.neighbourhood_notice_lines[0].text
    unknown = changes(restaurant(existing_use_stated=["retail"]), district="NC-3", on=on,
                      findings=(_principal(),))  # fmt: skip
    assert unknown.neighbourhood_notice == "not_established"
    assert any("part of a chain" in line.text for line in unknown.neighbourhood_notice_lines)
    staying = changes(restaurant(formula_retail=True, changes_existing_business="none"), s=site("restaurant"),
                      district="NC-3", on=on)  # fmt: skip
    assert staying.neighbourhood_notice == "not_required"
    after = changes(restaurant(formula_retail=True, existing_use_stated=["retail"]), district="NC-3",
                    on=dt.date(2024, 1, 14))  # fmt: skip
    assert after.neighbourhood_notice == "not_required"


def _principal() -> Any:
    from tests.test_rows import PRINCIPAL

    return PRINCIPAL[0]


# ---- the entertainment row: the dance permit while it was an approval -------------------------------------------------
def test_the_dance_permit_before_ordinance_118_25() -> None:
    dancing = given(WINE_BAR, dancing=True, entertainment_kind="limited_live_performance", **STATED)
    before = row(run(dancing, z=C2, overlays=[], rules_date=dt.date(2025, 6, 1)), "entertainment")
    text = " ".join(texts(before.basis))
    assert "dancing by patrons needs no permit" not in text
    assert "a dance permit from the Entertainment Commission was needed" in text
    assert before.approval.endswith(", and dance permit")
    after = row(run(dancing, z=C2, overlays=[], rules_date=dt.date(2025, 8, 17)), "entertainment")
    assert "dance permit" not in " ".join(texts(after.basis)) + after.approval


# ---- the outdoor row: an area the description does not place ------------------------------------------------------------
def test_an_unplaced_outdoor_area_is_not_allowed() -> None:
    for z in (UMU, C2):
        d = run(patio(None), z=z, overlays=[])
        outdoor = row(d, "outdoor")
        assert trigger(d, "T9").control == "principal"
        assert (outdoor.status, outdoor.missing_inputs) == (
            "insufficient_information",
            ["where the outdoor area is"],
        )
        assert outdoor.basis[-1].text.startswith("The description does not say where the outdoor area is.")


# ---- required_areas reads the v2 fields --------------------------------------------------------------------------------
def test_required_areas_reads_the_v2_fields() -> None:
    base = {"serves_alcohol": True, "alcohol_type": "beer_wine"}
    assert "entertainment" in required_areas(profile("bar", closing_hour="03:30", **base))
    assert "entertainment" not in required_areas(profile("bar", closing_hour="01:30", **base))
    assert "entertainment" in required_areas(
        profile("bar", entertainment_kind="place_of_entertainment", **base)
    )
    assert "entertainment" in required_areas(
        profile("bar", entertainment_kind="limited_live_performance", **base)
    )
    assert "outdoor" in required_areas(profile("restaurant", outdoor_area="rear_or_side"))
    assert "outdoor" not in required_areas(profile("restaurant", outdoor_area="none"))
    # a Bar always gets the alcohol row (§ 102)
    assert "alcohol" in required_areas(profile("bar"))
    assert "alcohol" not in required_areas(profile("restaurant"))


# ---- the same inputs in any order give the same output -------------------------------------------------------------------
def test_order_of_stories_and_stated_uses_does_not_change_the_output() -> None:
    dumps = set()
    for stories in itertools.permutations(["second", "basement", "first"]):
        for uses in itertools.permutations(["retail", "restaurant", "bar"]):
            p = given(COCKTAIL_BAR, existing_use_stated=list(uses), **{**STATED, "stories": list(stories)})
            d = determine(p, zoning(), [], [], SITE_995, required_areas(p), today=dt.date(2026, 11, 10),
                          rules_date=dt.date(2023, 6, 1))  # fmt: skip
            dumps.add(d.model_dump_json())
    assert len(dumps) == 1


# ---- the existing-use sentences at a past rules date -----------------------------------------------------------------------
def test_the_existing_use_sentences_say_which_records_were_read() -> None:
    later = licence("700048", "48", label="Type 48 – On-Sale General - Public Premises")
    later.app.decided_at = dt.date(2025, 3, 1)  # type: ignore[misc]
    past = run(COCKTAIL_BAR, records=[later], rules_date=dt.date(2024, 6, 1))
    line = next(line for line in past.pathway.lines if line.rule_id == "zoning.existing_use")
    assert "dated before 2024-06-01" in line.text and "was used as on that date" in line.text
    today = run(COCKTAIL_BAR, records=[later])
    assert any("is on file" in line.text and "dated before" not in line.text for line in today.pathway.lines)


def test_the_t4_and_t11_phrases_are_fixed() -> None:
    for key in ("existing_hours", "existing_outdoor_area", "overnight", "haight_restaurant_quota"):
        assert key in tg.NOT_KNOWN
    assert isinstance(given(RESTAURANT), BusinessProfile)


# ---- the decision of 2026-11-12: a prohibited use carries Planning Code § 175(a) to the later rows --------------
IRVING = zoning("NCD-IRVING", section="Planning Code § 732")
NOT_AS_DESCRIBED = (
    "Zoning does not permit the concept as described at this address (what bars it: {}), and no City department "
    "may issue a permit or licence that would authorize a use the Planning Code does not permit: not permitted."
)


def test_a_formula_retail_prohibition_bars_every_later_approval() -> None:
    """Backtest case N09: a chain boba store (a Limited Restaurant) where the last use was a Limited Restaurant, on
    Irving Street, where formula retail is not permitted for a Limited Restaurant. Before the decision the health
    row read "Allowed" beside a zoning row that read "Not permitted"."""
    chain = given(
        profile("cafe"),
        formula_retail=True,
        existing_use_stated=["limited_restaurant"],
        outdoor_seating=True,
    )
    on = dt.date(2024, 7, 30)
    d = run(chain, z=IRVING, overlays=[], rules_date=on, today=on)
    assert trigger(d, "T5").control == "not_permitted"
    assert "not_permitted" not in (trigger(d, "T1").control, trigger(d, "T2").control)  # not the use itself
    assert row(d, "zoning_use").status == "not_permitted"
    later = [r for r in d.rows if r.area != "zoning_use"]
    assert {r.area for r in later} >= {"health", "building_change_of_use", "outdoor"}
    for r in later:
        assert (r.status, r.referral_steps, r.missing_inputs) == ("not_permitted", [], []), r.area
        last = r.basis[-1]
        assert last.rule_id == f"{r.area.split('_')[0]}.status"
        if r.area == "alcohol":  # ABC is a state agency: its own rule (B&P § 23790), naming the same trigger
            assert "(formula retail)" in last.text
            continue
        assert last.text == NOT_AS_DESCRIBED.format("formula retail"), r.area
        assert last.code_section == "Planning Code § 175(a)"
        assert last.citations == ["zoning:NCD-IRVING"]
    # no row zoning bars asks for an input, and the path says there is none
    assert not any(r.missing_inputs for r in d.rows)
    assert d.entitlement_path.startswith("No approval path")


def test_the_later_rows_name_what_bars_the_concept_in_trigger_order() -> None:
    """Given two findings that bar the concept (use size T7 and hours T11), a row names both in the zoning row's
    order (T1 to T11, not the text order where "T11" sorts before "T7"), whatever order the findings come in.
    The engine passes the building and entertainment rows only the prohibited uses (T1, T2, T5); the alcohol
    row's A1z, for a new business, is given every finding that bars the zoning row."""
    big = run(
        given(RESTAURANT, closing_hour="23:00", **NEW, **{**STATED, "square_feet": 6000}),
        z=CASTRO,
        overlays=[],
    )
    late = run(given(RESTAURANT, closing_hour="03:00", **NEW, **STATED), z=PACIFIC, overlays=[])
    t7, t11 = trigger(big, "T7"), trigger(late, "T11")
    assert (t7.control, t11.control) == ("not_permitted", "not_permitted")
    assert rows._barred_names([t11, t7]) == rows._barred_names([t7, t11]) == "use size and hours of operation"
    c = restaurant()
    built = rows.building_row(
        changes(c),
        c,
        zoning_prohibits_use=False,
        rules_date=dt.date(2026, 11, 10),
        zoning_barred_by=[t11, t7],
    )
    assert built.status == "not_permitted"
    assert built.basis[-1].text == NOT_AS_DESCRIBED.format("use size and hours of operation")
    shown = rows.entertainment_row(
        c, [], rules_date=dt.date(2026, 11, 10), zoning_prohibits_use=False, zoning_barred_by=[t11, t7]
    )
    assert (shown.status, shown.referral_steps) == ("not_permitted", [])
    assert shown.basis == [built.basis[-1].model_copy(update={"rule_id": "entertainment.status"})]
    # the zoning row of each run names its own trigger the same way
    assert row(big, "zoning_use").basis[-1].text.endswith("What bars it: use size: not permitted.")


def test_a_zoning_row_that_is_not_barred_leaves_the_later_rows_alone() -> None:
    """The § 175(a) lines appear only when the zoning row is not permitted: a conditional use reads as before."""
    d = run(given(RESTAURANT, closing_hour="01:00", **NEW, **STATED), z=PACIFIC, overlays=[])
    assert row(d, "zoning_use").status == "further_review"
    assert row(d, "health").status == "allowed"
    for r in d.rows:
        assert all(line.code_section != "Planning Code § 175(a)" for line in r.basis), r.area


def _no_section_175(d: Any, areas: tuple[str, ...]) -> None:
    for area in areas:
        r = row(d, area)
        assert r.status != "not_permitted", area
        assert all(line.code_section != "Planning Code § 175(a)" for line in r.basis), area


LATER_CITY_ROWS = ("health", "building_change_of_use", "entertainment", "outdoor")


def test_hours_alone_do_not_bar_the_later_approvals_of_a_business_that_stays() -> None:
    """Review of the decision of 2026-11-12: an existing, lawful restaurant that only asks to close at 3 a.m. in
    NCD-PACIFIC. Hours (T11) make the zoning row not permitted, but hours are not a prohibited use: the health
    permit stays allowed, and no later row reads "not permitted" or carries the § 175(a) line. The licence row
    does not follow the zoning row either, because the business continues (A1z needs a new use for any trigger
    other than a prohibited use)."""
    d = run(
        given(
            RESTAURANT,
            closing_hour="03:00",
            existing_use_stated=["restaurant"],
            changes_existing_business="enlarge_and_intensify",
            **NEW,
            **STATED,
        ),
        z=PACIFIC,
        overlays=[],
    )
    assert [f.rule_id for f in d.pathway.triggers if f.control == "not_permitted"] == ["T11"]
    assert row(d, "zoning_use").status == "not_permitted"
    assert row(d, "health").status == "allowed"
    _no_section_175(d, (*LATER_CITY_ROWS, "alcohol"))
    assert all("concept as described" not in line.text for line in row(d, "alcohol").basis)
    # a new dry restaurant with the same hours: the City permits still do not follow
    new = run(given(RESTAURANT, closing_hour="03:00", alcohol_type="none", **STATED), z=PACIFIC, overlays=[])
    assert [f.rule_id for f in new.pathway.triggers if f.control == "not_permitted"] == ["T11"]
    assert row(new, "health").status == "allowed"
    _no_section_175(new, LATER_CITY_ROWS)


def test_a_licence_rule_of_a_restricted_district_bars_the_licence_only() -> None:
    """Review of the decision of 2026-11-12: a new Bar with a Type 42 licence in NCD-BAYVIEW inside the Third
    Street Alcohol Restricted Use District, on 2025-04-06. Only T4 bars it. The licence row is not permitted by
    its own rule (A1r); the health, building, entertainment and outdoor rows do not follow (T4 is a rule on the
    liquor licence, not a prohibited use)."""
    on = dt.date(2025, 4, 6)
    d = run(
        given(COCKTAIL_BAR, licence_type="42", existing_use_stated=["retail"], **STATED, **NEW),
        z=zoning("NCD-BAYVIEW", section="Planning Code § 737"),
        overlays=[THIRD_ST_RUD],
        rules_date=on,
        today=on,
    )
    assert [f.rule_id for f in d.pathway.triggers if f.control == "not_permitted"] == ["T4"]
    assert (row(d, "zoning_use").status, row(d, "alcohol").status) == ("not_permitted", "not_permitted")
    assert row(d, "alcohol").basis[-1].code_section == "California Business and Professions Code § 23790"
    assert row(d, "health").status == "allowed"
    _no_section_175(d, LATER_CITY_ROWS)


def test_formula_retail_bars_the_licence_of_a_business_that_stays() -> None:
    """The decision of 2026-11-12 reaches a business that continues: a chain cafe that stays and is enlarged,
    where formula retail is not permitted, has every later row not permitted, the licence included (A1z)."""
    on = dt.date(2024, 7, 30)
    d = run(
        given(
            profile("cafe"),
            formula_retail=True,
            existing_use_stated=["limited_restaurant"],
            changes_existing_business="enlarge",
            outdoor_seating=True,
            **NEW,
        ),
        z=IRVING,
        overlays=[],
        rules_date=on,
        today=on,
    )
    assert [f.rule_id for f in d.pathway.triggers if f.control == "not_permitted"] == ["T5"]
    assert {r.area: r.status for r in d.rows if r.status != "not_permitted"} == {}
    assert (
        row(d, "alcohol")
        .basis[-1]
        .text.startswith("Zoning does not permit the concept as described at this address (formula retail)")
    )
    for area in LATER_CITY_ROWS:
        assert row(d, area).basis[-1].text == NOT_AS_DESCRIBED.format("formula retail"), area


def test_the_prohibited_uses_are_the_use_itself_and_formula_retail() -> None:
    """The set the decision of 2026-11-12 names, written down once: T1 and T2 (the use itself) and T5."""
    from app.memo.pathway import PROHIBITED_USE_TRIGGERS

    assert sorted(PROHIBITED_USE_TRIGGERS) == ["T1", "T2", "T5"]
