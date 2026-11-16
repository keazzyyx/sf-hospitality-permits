"""Record kinds and the site history: which records count toward the comparables and the base rate, and which
are listed as on file at the report's own address or parcel."""

from __future__ import annotations

import datetime as dt
import io
import json
from pathlib import Path
from typing import Any

import pypdf
import pytest
from precedent.models import Application
from precedent.store.base import Nearby
from precedent.store.local import LocalStore

from app.agents.memo_runner import SITE_READ_RADIUS_M, MemoRunInput, MemoRunner
from app.agents.runner import RunnerEvent
from app.catalog.loader import get_catalog
from app.core.config import settings
from app.memo import analytics
from app.memo.analytics import is_labelled, premises, record_kind
from app.memo.report import (
    SITE_HISTORY_EMPTY_NOTE,
    SITE_HISTORY_NOTE,
    SITE_PROXIMITY_M,
    base_rate_line,
    build_site_history,
    filed_under,
    normalize_parcel,
    normalize_street_address,
    parse_street_address,
    report_text,
    same_street_address,
    site_history_count_line,
    site_match,
    site_of,
    site_records,
)
from app.models.memo import (
    PATHWAY_RECORD_KINDS,
    RECORD_KIND_LABELS,
    SITE_HISTORY_LIMIT,
    Memo,
    SiteHistory,
)
from app.models.profile import BusinessProfile
from app.services.memo_pdf import render_memo_pdf
from tests.fakes import FakeAnthropic
from tests.memo_fakes import VALENCIA, FakeGeocoder, MemoScript, seed_store

TODAY = dt.date(2026, 10, 21)
NOW = dt.datetime(2026, 10, 21, tzinfo=dt.UTC)
# What the scripted intake model's profile (tests.fakes.BASE_PROFILE) claims, all stated, so the stated-facts check
# (app.memo.stated) keeps every fact the memo's rules read.
DESC = (
    "40-seat wine bar of 1,400 square feet, small kitchen, open until 1am, occasional live music, amplified"
)
WINE_BAR = BusinessProfile(
    business_type="bar", seats=40, serves_alcohol=True, alcohol_type="beer_wine", live_entertainment=True
).normalized()
M_PER_DEG_LAT = 111_195.0  # metres per degree of latitude on the store's sphere


def _label(kind: str, *, is_premises: bool = True) -> dict[str, Any]:
    """The three labels the record classifier writes into `extra`."""
    return {
        "premises": is_premises,
        "use_class": "bar" if is_premises else "none",
        "record_kind": kind,
    }


def _record(app_id: str, *, metres: float = 100.0, **kw: Any) -> Nearby[Application]:
    """A Planning row `metres` north of the report's point."""
    base: dict[str, Any] = {
        "id": f"datasf_planning:{app_id}",
        "source": "datasf_planning",
        "source_id": app_id,
        "source_url": f"https://example.org/{app_id}",
        "fetched_at": NOW,
        "kind": "planning_other",
        "permit_type": "Planning record",
        "lat": VALENCIA.lat + metres / M_PER_DEG_LAT,
        "lng": VALENCIA.lng,
        "zoning_district": "NCT-2",
    }
    return Nearby(Application.model_validate({**base, **kw}), metres)


def _decided(app_id: str, outcome: str = "approved", *, years: float = 1.0, **kw: Any) -> Nearby[Application]:
    """A dated Planning decision about a bar: filed 150 days before it was decided `years` ago."""
    decided = TODAY - dt.timedelta(days=int(365 * years))
    fields: dict[str, Any] = {
        "kind": "cua",
        "use_types": ["bar"],
        "filed_at": decided - dt.timedelta(days=150),
        "decided_at": decided,
        "outcome": outcome,
        **kw,
    }
    return _record(app_id, **fields)


# ---- the record kind of a row --------------------------------------------------------------------
def test_record_kind_of_a_row() -> None:
    plain = _record("plain").item
    assert record_kind(plain) == "not_labelled" and not is_labelled(plain) and not premises(plain)
    for kind in ("use_decision", "agency_referral", "building_work", "other"):
        row = _record(kind, extra=_label(kind)).item
        assert record_kind(row) == kind and is_labelled(row) and premises(row)
    # ABC rows are licences and Entertainment Commission rows are permits, whatever `extra` says
    licence = _record("l", id="abc:1", source="abc", kind="abc_license", extra=_label("other")).item
    assert record_kind(licence) == "licence"
    assert record_kind(_record("l2", id="abc:2", source="abc", kind="planning_other").item) == "licence"
    for kind in ("entertainment_poe", "entertainment_llp", "entertainment_sound", "entertainment_other"):
        permit = _record(kind, id=f"datasf_entertainment:{kind}", source="datasf_entertainment", kind=kind)
        assert record_kind(permit.item) == "entertainment_permit"
    assert record_kind(_record("e", kind="entertainment_poe").item) == "entertainment_permit"
    # a label outside the four known values is not a kind; the row still counts as labelled
    odd = _record("odd", extra={"record_kind": "something_else", "premises": True}).item
    assert record_kind(odd) == "not_labelled" and is_labelled(odd)
    # premises must be the boolean True
    assert not premises(_record("p", extra={"record_kind": "use_decision", "premises": "true"}).item)
    assert not premises(_record("p2", extra={"record_kind": "use_decision"}).item)
    assert set(RECORD_KIND_LABELS) == {
        "use_decision",
        "agency_referral",
        "building_work",
        "other",
        "licence",
        "entertainment_permit",
        "not_labelled",
    }


# ---- the address normaliser ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("995 Valencia St, San Francisco, CA 94110", "995 VALENCIA ST"),
        ("995 VALENCIA STREET", "995 VALENCIA ST"),
        ("995 valencia st.", "995 VALENCIA ST"),
        ("995 Valencia St SAN FRANCISCO CA 94110", "995 VALENCIA ST"),
        ("995 Valencia St 94110", "995 VALENCIA ST"),
        ("0995 Valencia St", "995 VALENCIA ST"),
        # unit and suite text is dropped
        ("995 Valencia St #2", "995 VALENCIA ST"),
        ("995 Valencia Street, Suite 200", "995 VALENCIA ST"),
        ("995 Valencia St Apt B", "995 VALENCIA ST"),
        ("995 Valencia St Unit 3", "995 VALENCIA ST"),
        ("995 Valencia St 2nd Floor", "995 VALENCIA ST"),
        # the key of a range is its first number (both ends are kept for matching; see the range tests); a
        # letter or a fraction on the number is dropped
        ("995-999 Valencia St", "995 VALENCIA ST"),
        ("993 - 995 VALENCIA ST, SAN FRANCISCO, CA 94110", "993 VALENCIA ST"),
        ("997/999 Valencia St", "997 VALENCIA ST"),
        ("997, 999 Valencia St", "997 VALENCIA ST"),
        ("995A Valencia St", "995 VALENCIA ST"),
        ("995 1/2 Valencia St", "995 VALENCIA ST"),
        # suffixes, compass words and numbered streets are written one way
        ("300 South Van Ness Avenue", "300 S VAN NESS AVE"),
        ("300 S VAN NESS AVE", "300 S VAN NESS AVE"),
        ("1 Geary Boulevard", "1 GEARY BLVD"),
        ("2001 03RD ST", "2001 3RD ST"),
        ("2001 Third Street", "2001 3RD ST"),
        # the first word of a street is never a suffix; a name is left alone
        ("200 Avenue of the Palms", "200 AVENUE OF THE PALMS"),
        ("100 St Francis Blvd", "100 ST FRANCIS BLVD"),
        ("1 Dr Carlton B Goodlett Pl", "1 DR CARLTON B GOODLETT PL"),
        ("1 Ferry Building", "1 FERRY BUILDING"),
        ("1 Ferry Building #33", "1 FERRY BUILDING"),
        # the Planning case list writes floor and unit text after the suffix: the street ends at its suffix
        ("995 VALENCIA ST STREET LEV, SAN FRANCISCO, CA 94110", "995 VALENCIA ST"),
        ("995 VALENCIA ST ST., SAN FRANCISCO, CA", "995 VALENCIA ST"),
        ("995 VALENCIA ST 1ST FLR", "995 VALENCIA ST"),
        ("995 VALENCIA ST BSMT.", "995 VALENCIA ST"),
        ("995 VALENCIA ST GROUND", "995 VALENCIA ST"),
        ("70 OCEAN AV 0001", "70 OCEAN AVE"),
        ("2100 VAN NESS AV 1ST", "2100 VAN NESS AVE"),
        ("200 DORADO TR 0200, SAN FRANCISCO, CA", "200 DORADO TER"),
        # and its own short forms of the suffix
        ("5320 GEARY BL", "5320 GEARY BLVD"),
        ("5320 Geary Boulevard", "5320 GEARY BLVD"),
        ("5320 GEARY BL GROUND", "5320 GEARY BLVD"),
        ("100 TARAVAL WY", "100 TARAVAL WAY"),
        ("1 UNITED NATIONS PZ", "1 UNITED NATIONS PLZ"),
        ("1984 GREAT HY, SAN FRANCISCO, CA", "1984 GREAT HWY"),
        # a compass word straight after the suffix is part of the street
        ("100 Buena Vista Avenue East", "100 BUENA VISTA AVE E"),
        ("100 BUENA VISTA AVE WEST", "100 BUENA VISTA AVE W"),
        # a street without its suffix is a different string: 3RD ST and 3RD AVE both exist
        ("995 Valencia", "995 VALENCIA"),
    ],
)
def test_normalize_street_address(text: str, expected: str) -> None:
    assert normalize_street_address(text) == expected


@pytest.mark.parametrize(
    "text",
    [None, "", "   ", "Valencia St", "Pier 39", "3RD ST", "995", "San Francisco", "Valencia St & 21st St"],
)
def test_addresses_without_a_number_and_a_street_are_not_usable(text: str | None) -> None:
    assert normalize_street_address(text) is None


def test_streets_that_differ_stay_different() -> None:
    assert normalize_street_address("100 3rd St") != normalize_street_address("100 3rd Ave")
    assert normalize_street_address("300 Van Ness Ave") != normalize_street_address("300 South Van Ness Ave")
    assert normalize_street_address("995 Valencia St") != normalize_street_address("997 Valencia St")
    assert normalize_street_address("100 Buena Vista Ave East") != normalize_street_address(
        "100 Buena Vista Ave West"
    )


def _same(a: str, b: str, **kw: Any) -> bool:
    first, second = parse_street_address(a), parse_street_address(b)
    assert first is not None and second is not None
    assert same_street_address(first, second, **kw) == same_street_address(second, first, **kw)
    return same_street_address(first, second, **kw)


@pytest.mark.parametrize(
    "record",
    [
        "993-995 Valencia St",
        "993 - 995 VALENCIA ST, SAN FRANCISCO, CA 94110",
        "991 - 999 VALENCIA ST",
        "995 - 999 VALENCIA ST",
        "985/995 Valencia St",
        "993, 995 Valencia St",
        "990-999 Valencia St",  # the ends differ in parity: every number between them
    ],
)
def test_a_number_range_holds_every_number_in_it_on_the_same_side(record: str) -> None:
    assert _same(record, "995 Valencia St")
    parsed = parse_street_address(record)
    assert parsed is not None and parsed.low < parsed.high


def test_licence_addresses_with_a_dashed_letter_or_three_numbers_are_read() -> None:
    """ABC writes '425-A HAYES ST' and '501-503-505 JONES ST'; the parser read neither, so rule 4 could never tie
    those licences to their address (2026-11-15: 4 of the 3,925 SF licences)."""
    dashed = parse_street_address("425-A HAYES ST, SAN FRANCISCO, CA 94102")
    assert dashed is not None and (dashed.low, dashed.high, dashed.name, dashed.suffix) == (
        425,
        425,
        "HAYES",
        "ST",
    )
    assert _same("425-A HAYES ST", "425 Hayes St") and _same("425A Hayes St", "425 Hayes St")
    three = parse_street_address("501-503-505 JONES ST")
    assert three is not None and (three.low, three.high) == (501, 505)
    assert _same("501-503-505 JONES ST", "503 Jones St") and not _same("501-503-505 JONES ST", "507 Jones St")
    # a letter after a space is the street (A Street), never the number's letter
    a_street = parse_street_address("100 A ST")
    assert a_street is not None and (a_street.low, a_street.name, a_street.suffix) == (100, "A", "ST")


def test_a_number_range_matches_only_inside_the_range() -> None:
    assert parse_street_address("995-999 Valencia St") == parse_street_address("995 - 999 VALENCIA STREET")
    for number in (995, 997, 999):
        assert _same("995-999 Valencia St", f"{number} Valencia St"), number
    # outside the range, across the street (the other parity), or another street
    for other in (
        "993 Valencia St",
        "1001 Valencia St",
        "996 Valencia St",
        "998 Valencia St",
        "997 Mission St",
    ):
        assert not _same("995-999 Valencia St", other), other
    # two ranges that share a number are the same place; two that do not are not
    assert _same("993-995 Valencia St", "995-999 Valencia St")
    assert not _same("991-993 Valencia St", "995-999 Valencia St")
    # a range written backwards, or wider than a block, is read as its first number only
    backwards = parse_street_address("999-995 Valencia St")
    wide = parse_street_address("1 - 2000 Market St")
    assert backwards is not None and (backwards.low, backwards.high) == (999, 999)
    assert wide is not None and (wide.low, wide.high) == (1, 1)
    # a street written without its suffix is the same street only when the caller allows it
    assert not _same("2243-2247 Mission", "2245 Mission St")
    assert _same("2243-2247 Mission", "2245 Mission St", allow_missing_suffix=True)
    assert not _same("100 3rd St", "100 3rd Ave", allow_missing_suffix=True)


def test_normalize_parcel() -> None:
    assert normalize_parcel("3616/065") == normalize_parcel(" 3616 / 065 ") == normalize_parcel("3616065")
    assert normalize_parcel("3616/065a") == "3616065A"
    assert normalize_parcel(None) is None and normalize_parcel(" ") is None


# ---- comparables: labelled and unlabelled rows -----------------------------------------------------
def test_labelled_rows_are_candidates_only_as_premises_use_decisions_or_referrals() -> None:
    rows = [
        _decided("use", extra=_label("use_decision")),
        _decided("referral", extra=_label("agency_referral")),
        _decided("building", extra=_label("building_work")),
        _decided("other", extra=_label("other")),
        _decided("not-premises", extra=_label("use_decision", is_premises=False)),
        _decided("odd-label", extra={"record_kind": "something_else", "premises": True}),
        _decided("plain"),
        _decided(
            "permit",
            id="datasf_entertainment:permit",
            source="datasf_entertainment",
            kind="entertainment_poe",
        ),
        _decided("licence", id="abc:licence", source="abc", kind="abc_license"),
    ]
    ranked = {s.app.source_id for s in analytics.rank_candidates(rows, WINE_BAR, TODAY)}
    assert ranked == {"use", "referral", "plain", "permit"}
    # the same rows without their labels: every Planning row is a candidate again, as before
    stripped = [Nearby(n.item.model_copy(update={"extra": {}}), n.distance_m) for n in rows]
    before = {s.app.source_id for s in analytics.rank_candidates(stripped, WINE_BAR, TODAY)}
    assert before == {
        "use",
        "referral",
        "building",
        "other",
        "not-premises",
        "odd-label",
        "plain",
        "permit",
    }
    # a labelled row keeps the score it had without labels: the labels only decide whether it is ranked
    scores = {s.app.source_id: s.score for s in analytics.rank_candidates(rows, WINE_BAR, TODAY)}
    scores_before = {s.app.source_id: s.score for s in analytics.rank_candidates(stripped, WINE_BAR, TODAY)}
    assert all(scores[k] == scores_before[k] for k in scores)


# ---- base rate: labelled and unlabelled rows -------------------------------------------------------
def test_labelled_referrals_and_building_work_are_left_out_of_the_base_rate_and_counted() -> None:
    nine = [_decided(f"a{i}") for i in range(9)]
    referral = _decided("referral", extra=_label("agency_referral"))
    building = _decided("building", extra=_label("building_work"))
    labelled = analytics.base_rate([*nine, referral, building], WINE_BAR, TODAY, zoning_district=None)
    assert labelled.total == 9 and labelled.rate_shown is False and labelled.approval_rate_pct is None
    assert labelled.excluded_not_use_decision == 2
    assert (labelled.excluded_grant_only, labelled.excluded_undated) == (0, 0)
    assert labelled.scope == (
        "N = 9 dated decisions within 1,000 ft, last 5 years; too few for a rate; "
        "left out: 2 records that are not use decisions for this kind of business"
    )
    pool = {a.source_id for a in analytics.base_rate_pool([*nine, referral, building], WINE_BAR, TODAY, 5)}
    assert pool == {f"a{i}" for i in range(9)}
    # the same two rows without labels count as before: N is 11 and the rate is shown
    plain = [Nearby(n.item.model_copy(update={"extra": {}}), n.distance_m) for n in (referral, building)]
    before = analytics.base_rate([*nine, *plain], WINE_BAR, TODAY, zoning_district=None)
    assert before.total == 11 and before.rate_shown is True and before.approval_rate_pct == 100.0
    assert before.excluded_not_use_decision == 0
    assert before.scope == "N = 11 dated decisions within 1,000 ft, last 5 years"
    assert analytics.rate_payload(labelled)["excluded_not_use_decision"] == 2
    assert analytics.rate_payload(before)["excluded_not_use_decision"] == 0


def test_only_a_labelled_use_decision_about_a_premises_enters_the_base_rate() -> None:
    nine = [_decided(f"a{i}") for i in range(9)]
    use = _decided("use", "denied", extra=_label("use_decision"))
    counted = analytics.base_rate([*nine, use], WINE_BAR, TODAY, zoning_district=None)
    assert counted.total == 10 and counted.denied == 1 and counted.excluded_not_use_decision == 0
    assert counted.rate_shown is True and counted.approval_rate_pct == 90.0
    assert "left out" not in counted.scope
    # a use decision about something that is not a food, drink or entertainment premises is left out
    elsewhere = _decided("elsewhere", "denied", extra=_label("use_decision", is_premises=False))
    other = _decided("other", extra=_label("other"))
    left_out = analytics.base_rate([*nine, elsewhere, other], WINE_BAR, TODAY, zoning_district=None)
    assert left_out.total == 9 and left_out.denied == 0 and left_out.excluded_not_use_decision == 2


def test_each_left_out_row_is_counted_under_one_heading() -> None:
    """Checked in order: grant-only, not a use decision, undated."""
    rows = [
        *[_decided(f"a{i}") for i in range(10)],
        # labelled building work with no dates: not a use decision, and not also "undated"
        _record("hood", kind="cua", use_types=["bar"], outcome="approved", extra=_label("building_work")),
        # a labelled referral for another use, still pending: counted, the count needs only kind and source
        _record("pending-referral", use_types=["hotel"], outcome="pending", extra=_label("agency_referral")),
        # a labelled use decision with no dates: undated
        _record("undated-use", kind="cua", use_types=["bar"], outcome="denied", extra=_label("use_decision")),
        # an unlabelled decided row with no dates: undated, as before
        _record("undated-plain", kind="cua", use_types=["bar"], outcome="withdrawn"),
        # an Entertainment Commission permit that somehow carries a label: grant-only, and only that
        _record(
            "permit",
            id="datasf_entertainment:permit",
            source="datasf_entertainment",
            kind="entertainment_poe",
            use_types=["bar"],
            outcome="approved",
            extra=_label("building_work"),
        ),
        _record("licence", id="abc:9", source="abc", kind="abc_license", use_types=["bar"]),
    ]
    rate = analytics.base_rate(rows, WINE_BAR, TODAY, zoning_district=None)
    assert rate.total == 10
    assert (rate.excluded_grant_only, rate.excluded_not_use_decision, rate.excluded_undated) == (2, 2, 2)
    assert rate.scope == (
        "N = 10 dated decisions within 1,000 ft, last 5 years; "
        "left out: 2 permits and licences, 2 records that are not use decisions for this kind of business, "
        "2 undated"
    )
    assert analytics.left_out_clause(14, 31, 3) == (
        "left out: 14 permits and licences, 31 records that are not use decisions for this kind of business, "
        "3 undated"
    )
    assert analytics.left_out_clause(0, 1, 0) == (
        "left out: 1 record that is not a use decision for this kind of business"
    )
    assert analytics.left_out_clause(1, 0, 1) == "left out: 1 permit or licence, 1 undated"
    assert "grant-only" not in rate.scope and "—" not in rate.scope
    # order-independent
    assert analytics.base_rate(list(reversed(rows)), WINE_BAR, TODAY, zoning_district=None) == rate


# ---- site history: matching ------------------------------------------------------------------------
SITE = site_of(VALENCIA.address, VALENCIA.normalized_address, VALENCIA.parcel)


def test_site_of_reads_the_report_address_with_city_state_and_zip() -> None:
    assert (SITE.address, SITE.address_key) == ("995 Valencia St", "995 VALENCIA ST")
    assert (SITE.parcel, SITE.parcel_key) == ("3616/065", "3616065")
    # the display address alone is enough when the geocoder gave no normalised form
    assert (
        site_of("995 Valencia Street, San Francisco, CA 94110", None, None).address_key == "995 VALENCIA ST"
    )
    nowhere = site_of("Somewhere in the Mission", "SOMEWHERE IN THE MISSION", None)
    assert nowhere.address is None and nowhere.address_key is None and nowhere.parcel_key is None


def test_a_record_is_at_the_site_by_parcel() -> None:
    # same parcel, another address on it, 80 m away
    row = _record("p", metres=80, parcel="3616/065", address="2 Hill St")
    assert site_match(row.item, row.distance_m, SITE) == "parcel"
    spaced = _record("p2", metres=80, parcel=" 3616 / 065 ")
    assert site_match(spaced.item, spaced.distance_m, SITE) == "parcel"
    other = _record("p3", metres=2, parcel="3616/066")
    assert site_match(other.item, other.distance_m, SITE) is None
    # no parcel on the report: a parcel on the record cannot match
    no_parcel = site_of(VALENCIA.address, VALENCIA.normalized_address, None)
    assert site_match(row.item, row.distance_m, no_parcel) is None


def test_a_record_is_at_the_site_by_address() -> None:
    for address in ("995 Valencia St", "995 VALENCIA STREET #B", "995 Valencia St, San Francisco, CA 94110"):
        row = _record("a", metres=60, address=address)
        assert site_match(row.item, row.distance_m, SITE) == "address", address
    # the address rule holds even when the record names a different parcel
    other_parcel = _record("a2", metres=60, address="995 Valencia St", parcel="3616/066")
    assert site_match(other_parcel.item, other_parcel.distance_m, SITE) == "address"
    for address in ("997 Valencia St", "995 Guerrero St", "995 Valencia Ave", "996 Valencia St"):
        row = _record("a3", metres=1, address=address)
        assert site_match(row.item, row.distance_m, SITE) is None, address


@pytest.mark.parametrize(
    "address",
    [
        # a range that holds the report's number, as the Planning case list and ABC write them
        "993-995 Valencia St",
        "993 - 995 VALENCIA ST, SAN FRANCISCO, CA 94110",
        "991 - 999 VALENCIA ST",
        "995 - 999 VALENCIA ST",
        "993/995 Valencia St",
        "993, 995 Valencia St",
        # text after the street suffix, as the Planning case list writes it
        "995 VALENCIA ST STREET LEV, SAN FRANCISCO, CA 94110",
        "995 VALENCIA ST ST., SAN FRANCISCO, CA",
        "995 VALENCIA ST 1ST FLR",
        "995 VALENCIA ST BSMT.",
        "995 VALENCIA ST 0001",
    ],
)
def test_planning_spellings_of_the_report_address_are_at_the_site(address: str) -> None:
    """No parcel on the record and 60 m from the point, so only the address rule can tie it to the site."""
    row = _record("spelled", metres=60, address=address)
    assert site_match(row.item, row.distance_m, SITE) == "address", address
    # the same record 3 m away with no parcel: still by address, never dropped
    near = _record("spelled-near", metres=3, address=address)
    assert site_match(near.item, near.distance_m, SITE) == "address", address


def test_a_range_that_does_not_hold_the_report_number_is_somewhere_else() -> None:
    for address in (
        "997-999 Valencia St",
        "985 - 993 VALENCIA ST",
        "994-998 Valencia St",
        "997/999 Valencia St",
    ):
        row = _record("range", metres=3, address=address)
        assert site_match(row.item, row.distance_m, SITE) is None, address
    # the report on a later number of a range, and on a short suffix the Planning list writes its own way
    geary = site_of("5320 Geary Blvd, San Francisco, CA 94121", "5320 GEARY BLVD", None)
    for address in ("5320 GEARY BL", "5316 - 5324 GEARY BL GROUND", "5320 Geary Boulevard #2"):
        row = _record("geary", metres=60, address=address)
        assert site_match(row.item, row.distance_m, geary) == "address", address
    ocean = site_of("70 Ocean Ave, San Francisco, CA 94112", "70 OCEAN AVE", None)
    row = _record("ocean", metres=60, address="70 OCEAN AV 0001")
    assert site_match(row.item, row.distance_m, ocean) == "address"


def test_a_street_without_its_suffix_matches_only_right_at_the_point() -> None:
    assert SITE_READ_RADIUS_M == 30.0
    for metres, expected in ((1, "address"), (30.0, "address"), (30.1, None), (200, None)):
        row = _record("bare", metres=metres, address="995 Valencia")
        assert site_match(row.item, row.distance_m, SITE) == expected, metres
    ranged = _record("bare-range", metres=10, address="993-997 VALENCIA")
    assert site_match(ranged.item, ranged.distance_m, SITE) == "address"
    # a different suffix is a different street, however close; so is another number
    for address in ("995 Valencia Ave", "997 Valencia"):
        row = _record("bare-other", metres=1, address=address)
        assert site_match(row.item, row.distance_m, SITE) is None, address
    # the report's own address may be the one without a suffix
    bare_site = site_of("2245 Mission", "2245 MISSION", None)
    row = _record("suffixed", metres=5, address="2243-2247 MISSION ST")
    assert site_match(row.item, row.distance_m, bare_site) == "address"


def test_a_record_with_no_parcel_and_no_address_is_at_the_site_within_12_metres() -> None:
    assert SITE_PROXIMITY_M == 12.0
    near = _record("n", metres=11.9)
    assert site_match(near.item, near.distance_m, SITE) == "proximity"
    edge = _record("edge", metres=12.0)
    assert site_match(edge.item, edge.distance_m, SITE) == "proximity"
    far = _record("f", metres=12.1)
    assert site_match(far.item, far.distance_m, SITE) is None
    # an address with no number in it names no place of its own
    unusable = _record("u", metres=5, address="Valencia St")
    assert site_match(unusable.item, unusable.distance_m, SITE) == "proximity"
    # an address that does carry a number names a place, readable or not: it is never "no address"
    for address in ("997/999 Valencia St", "997, 999 Valencia St", "Valencia St & 21st St", "Pier 39"):
        row = _record("named", metres=3, address=address)
        assert site_match(row.item, row.distance_m, SITE) is None, address
    # a record that names another parcel or another address is somewhere else, however close
    for kw in ({"parcel": "3616/066"}, {"address": "997 Valencia St"}):
        row = _record("x", metres=1, **kw)
        assert site_match(row.item, row.distance_m, SITE) is None, kw


# ---- site history: order, truncation, counts -------------------------------------------------------
def test_site_history_is_newest_first_with_undated_last_and_counts_everything() -> None:
    d = dt.date
    rows = [
        _record("filed-2019", parcel="3616/065", filed_at=d(2019, 5, 1)),
        _record("undated-b", parcel="3616/065"),
        _record("decided-2024", parcel="3616/065", filed_at=d(2020, 1, 1), decided_at=d(2024, 3, 1)),
        _record("undated-a", parcel="3616/065"),
        _record("decided-2021", parcel="3616/065", decided_at=d(2021, 7, 1)),
        _record("elsewhere", parcel="3616/066", decided_at=d(2025, 1, 1)),
        _record("decided-2024", parcel="3616/065", decided_at=d(2030, 1, 1)),  # the same id again: skipped
    ]
    found = site_records(rows, SITE)
    # by decision date, or else filing date; undated last; ties broken by id
    assert [r.app.source_id for r in found] == [
        "decided-2024",
        "decided-2021",
        "filed-2019",
        "undated-a",
        "undated-b",
    ]
    assert found[0].app.decided_at == d(2024, 3, 1)
    assert site_records(list(reversed(rows[:-1])), SITE) == found  # order-independent
    history = build_site_history(found, SITE)
    assert history.total == 5 and len(history.entries) == 5 and history.by_kind == {"not_labelled": 5}
    assert history.note == SITE_HISTORY_NOTE
    assert history.matched_by == "Parcel 3616/065 or the address 995 Valencia St"
    assert site_history_count_line(history) is None
    first = history.entries[0]
    assert (first.application_id, first.citation_id) == (
        "datasf_planning:decided-2024",
        "app:datasf_planning:decided-2024",
    )
    assert (first.filed_at, first.decided_at) == ("2020-01-01", "2024-03-01")
    assert (first.record_kind, first.record_kind_label) == ("not_labelled", "Not labelled")
    assert (first.source, first.source_label) == ("datasf_planning", "Planning case list (DataSF)")


def test_site_history_lists_at_most_twenty_and_counts_every_kind() -> None:
    assert SITE_HISTORY_LIMIT == 20
    start = dt.date(2020, 1, 1)
    kinds = ["building_work"] * 15 + ["use_decision"] * 6 + ["agency_referral"] * 3 + ["other"] * 2
    rows: list[Nearby[Application]] = [
        _record(f"r{i:02d}", parcel="3616/065", extra=_label(kind), decided_at=start + dt.timedelta(days=i))
        for i, kind in enumerate(kinds)
    ]
    rows += [
        _record("plain", address="995 Valencia St"),
        _record("licence", id="abc:77", source="abc", kind="abc_license", address="995 VALENCIA ST"),
        _record(
            "permit",
            id="datasf_entertainment:88",
            source="datasf_entertainment",
            kind="entertainment_poe",
            metres=3,
        ),
    ]
    history = build_site_history(site_records(rows, SITE), SITE)
    assert history.total == 29 and len(history.entries) == SITE_HISTORY_LIMIT
    assert site_history_count_line(history) == "Showing 20 of 29"
    # counts cover all 29, in the order of RECORD_KIND_LABELS
    assert history.by_kind == {
        "use_decision": 6,
        "agency_referral": 3,
        "building_work": 15,
        "other": 2,
        "licence": 1,
        "entertainment_permit": 1,
        "not_labelled": 1,
    }
    assert list(history.by_kind) == [k for k in RECORD_KIND_LABELS if k in history.by_kind]
    # the 20 listed are the newest: the dated rows from the latest back; the three undated rows are cut
    assert [e.application_id for e in history.entries] == [
        f"datasf_planning:r{i:02d}" for i in range(25, 5, -1)
    ]
    # a record matched only by the 12 m rule is named in the matching rule
    assert history.matched_by == (
        "Parcel 3616/065 or the address 995 Valencia St, or a record with no parcel or street number within "
        "12 m of the address point"
    )


def test_site_history_description_is_one_line_of_at_most_300_characters() -> None:
    long = (
        "Install Type I kitchen hood\n\n  and   exhaust duct to roof. " + "Replace storefront glazing. " * 20
    )
    rows = [
        _record("long", parcel="3616/065", description=long, decided_at=dt.date(2024, 1, 1)),
        _record("short", parcel="3616/065", description="  Change of use\tto restaurant \n"),
    ]
    entries = build_site_history(site_records(rows, SITE), SITE).entries
    assert len(entries[0].description) == 300 and entries[0].description.endswith("…")
    assert entries[0].description.startswith("Install Type I kitchen hood and exhaust duct to roof. Replace")
    assert "\n" not in entries[0].description and "  " not in entries[0].description
    assert entries[1].description == "Change of use to restaurant"


def test_an_empty_site_history_says_what_that_does_and_does_not_mean() -> None:
    history = build_site_history(site_records([_record("far", parcel="3616/066")], SITE), SITE)
    assert history.total == 0 and history.entries == [] and history.by_kind == {}
    assert (
        history.note
        == SITE_HISTORY_EMPTY_NOTE
        == (
            "No records at this address or parcel in the data. That does not mean nothing was ever filed here."
        )
    )
    assert SITE_HISTORY_NOTE == (
        "Records on file at this address or parcel, newest first. Building work is listed here and is not "
        "counted in the outcome counts."
    )
    assert build_site_history([], site_of("995 Valencia St", None, None)).matched_by == (
        "The address 995 Valencia St"
    )
    assert build_site_history([], site_of("the corner", None, "3616/065")).matched_by == "Parcel 3616/065"
    assert build_site_history([], site_of("the corner", None, None)).matched_by == (
        "A record with no parcel or street number within 12 m of the address point"
    )
    for text in (SITE_HISTORY_NOTE, SITE_HISTORY_EMPTY_NOTE):
        assert "—" not in text


# ---- the whole chain ---------------------------------------------------------------------------------
HOOD = "datasf_planning:31"
REFERRAL = "datasf_planning:32"
LICENCE = "abc:33"
UNDATED = "datasf_planning:34"
NEXT_DOOR = "datasf_planning:35"
PERMIT = "datasf_entertainment:36"
HOOD_TEXT = "Install Type I kitchen hood and exhaust duct to roof for the ground floor restaurant space."


def _site_rows(*, labelled: bool) -> list[Application]:
    """Six records at or beside 995 Valencia St (parcel 3616/065)."""

    def extra(kind: str) -> dict[str, Any]:
        return _label(kind) if labelled else {}

    d = dt.date
    return [
        # building work on the report's parcel, under another address, 22 m from the point
        _record(
            "31",
            metres=22,
            permit_type="Building Permit Referral",
            use_types=["bar"],
            description=HOOD_TEXT,
            address="993 Valencia St",
            parcel="3616/065",
            status="Closed",
            outcome="approved",
            filed_at=d(2023, 1, 10),
            decided_at=d(2023, 4, 10),
            extra=extra("building_work"),
        ).item,
        # Planning's answer to an ABC referral at the report's address, no parcel on the record
        _record(
            "32",
            metres=6,
            kind="cua",
            permit_type="ABC Referral",
            use_types=["bar"],
            description="Referral from ABC for a Type 42 licence.",
            address="995 Valencia Street #A",
            status="Closed",
            outcome="approved",
            filed_at=d(2025, 6, 1),
            decided_at=d(2025, 9, 1),
            extra=extra("agency_referral"),
        ).item,
        # an ABC licence with no parcel and no address, mapped on the point
        _record(
            "33",
            metres=0,
            id=LICENCE,
            source="abc",
            kind="abc_license",
            permit_type="Type 41",
            license_type="41",
            use_types=["restaurant"],
            description="On-sale beer and wine, eating place.",
            status="Active",
            outcome="approved",
            filed_at=d(2021, 5, 5),
        ).item,
        # a Planning record at the address with no dates and no labels
        _record(
            "34",
            metres=3,
            permit_type="Project Review Meeting",
            description="Pre-application meeting.",
            address="995 Valencia St",
            status="Closed",
        ).item,
        # building work next door: its own parcel and address, 4 m away. Near, but not this site
        _record(
            "35",
            metres=4,
            permit_type="Building Permit Referral",
            use_types=["bar"],
            description="Tenant improvement next door.",
            address="997 Valencia St",
            parcel="3616/066",
            status="Closed",
            outcome="approved",
            filed_at=d(2024, 2, 1),
            decided_at=d(2024, 5, 1),
            extra=extra("building_work"),
        ).item,
        # an Entertainment Commission permit on the report's parcel
        _record(
            "36",
            metres=9,
            id=PERMIT,
            source="datasf_entertainment",
            kind="entertainment_poe",
            permit_type="Place of Entertainment",
            use_types=["live_entertainment"],
            description="Place of Entertainment permit.",
            parcel="3616/065",
            status="Active",
            outcome="approved",
            decided_at=d(2025, 3, 1),
        ).item,
    ]


async def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, labelled: bool = True, **script_kw: Any):  # type: ignore[no-untyped-def]
    """Seed the usual store plus the site rows, point the tools at it, and run one memo."""
    import app.memo.context as ctx
    import app.tools.precedent_tools as pt

    await LocalStore(tmp_path / "data").upsert_applications(_site_rows(labelled=labelled))
    store = seed_store(tmp_path / "data")
    for mod in (ctx, pt):
        monkeypatch.setattr(mod, "get_store", lambda: store)
        monkeypatch.setattr(mod, "get_geocoder", lambda: FakeGeocoder())
    script = MemoScript(**script_kw)
    runner = MemoRunner(FakeAnthropic(script), get_catalog(), settings, store, FakeGeocoder(), today=TODAY)  # type: ignore[arg-type]

    async def emit(ev: RunnerEvent) -> None:
        return None

    terminal = [
        ev async for ev in runner.run_memo(MemoRunInput(address="995 Valencia St", description=DESC), emit)
    ]
    assert [e.type for e in terminal] == ["memo"], terminal
    memo: Memo = terminal[0].data["memo"]
    return runner, script, memo


def _call(script: MemoScript, submit: str) -> str:
    call = next(c for c in script.calls if any(t["name"] == submit for t in c["tools"]))
    content: str = call["messages"][0]["content"]
    return content


def _between(text: str, start: str, end: str) -> Any:
    return json.loads(text.split(start, 1)[1].split(end, 1)[0])


def _pdf_text(memo: Memo) -> str:
    reader = pypdf.PdfReader(io.BytesIO(render_memo_pdf(memo)))
    return " ".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)


@pytest.mark.anyio
async def test_site_history_in_the_finished_memo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _runner, _script, memo = await _run(tmp_path, monkeypatch)
    Memo.model_validate(memo.model_dump())
    history = memo.site_history
    # five records at the site, newest first, the undated one last; the row next door is not one of them
    assert [e.application_id for e in history.entries] == [REFERRAL, PERMIT, HOOD, LICENCE, UNDATED]
    assert history.total == 5 and history.note == SITE_HISTORY_NOTE
    assert history.by_kind == {
        "agency_referral": 1,
        "building_work": 1,
        "licence": 1,
        "entertainment_permit": 1,
        "not_labelled": 1,
    }
    assert history.matched_by == (
        "Parcel 3616/065 or the address 995 Valencia St, or a record with no parcel or street number within "
        "12 m of the address point"
    )
    hood = next(e for e in history.entries if e.application_id == HOOD)
    assert (hood.record_kind, hood.record_kind_label) == ("building_work", "Building work")
    assert (hood.description, hood.address, hood.status, hood.outcome) == (
        HOOD_TEXT,
        "993 Valencia St",
        "Closed",
        "approved",
    )
    assert (hood.filed_at, hood.decided_at) == ("2023-01-10", "2023-04-10")
    licence = next(e for e in history.entries if e.application_id == LICENCE)
    assert (licence.record_kind_label, licence.source_label) == ("ABC licence", "ABC licence export")
    # every listed record is a citation of the memo, as app:<id>, whatever its kind
    cited = {c.id: c for c in memo.citations}
    for e in history.entries:
        assert e.citation_id == f"app:{e.application_id}" and e.citation_id in cited
    assert cited[f"app:{LICENCE}"].kind == "application"
    assert cited[f"app:{HOOD}"].label == "Building Permit Referral · 993 Valencia St · approved (2023)"

    # building work is in the site history and nowhere else: not a comparable, not in the base rate
    comparable_ids = {c.application_id for c in memo.comparable_cases}
    assert HOOD not in comparable_ids and NEXT_DOOR not in comparable_ids
    allowed = PATHWAY_RECORD_KINDS | {"not_labelled", "entertainment_permit"}
    assert all(c.record_kind in allowed for c in memo.comparable_cases)
    assert all(c.record_kind_label == RECORD_KIND_LABELS[c.record_kind] for c in memo.comparable_cases)
    by_id = {c.application_id: c for c in memo.comparable_cases}
    assert (by_id[REFERRAL].record_kind, by_id[REFERRAL].record_kind_label) == (
        "agency_referral",
        "Agency referral",
    )
    assert by_id["datasf_planning:1"].record_kind == "not_labelled"
    # base rate: still the four seeded bar decisions. The hood, the referral and the row next door are counted
    # as not use decisions; the licence and the permit join the grant-only count
    rate = memo.base_rate
    assert (rate.total, rate.approved_with_conditions, rate.denied, rate.withdrawn) == (4, 2, 1, 1)
    assert (rate.excluded_grant_only, rate.excluded_not_use_decision, rate.excluded_undated) == (8, 3, 0)
    assert rate.scope == (
        "N = 4 dated decisions within 1,000 ft, last 10 years (fewer than 5 in the last 5); too few for a rate; "
        "left out: 8 permits and licences, 3 records that are not use decisions for this kind of business"
    )
    # the scope gives the counts; the line then says in plain words what each one is
    assert base_rate_line(memo) == (
        f"2 approved / 1 denied / 1 withdrawn or cancelled. {rate.scope}. Entertainment Commission permits and ABC "
        "licences are lists of grants only, so they are not counted. Agency referrals, building work, other "
        "records and decisions about other kinds of business are not counted."
    )
    undated = memo.model_copy(
        update={
            "base_rate": rate.model_copy(
                update={"excluded_undated": 2, "excluded_grant_only": 0, "scope": rate.scope + ", 2 undated"}
            )
        }
    )
    assert base_rate_line(undated).endswith(
        "2 undated. Agency referrals, building work, other records and decisions about other kinds of "
        "business are not counted. Decided Planning records without both dates are not counted."
    )
    assert "grant-only" not in base_rate_line(memo) and "grant-only" not in rate.scope
    assert cited["stat:base_rate"].excerpt == (
        "Not counted: 8 Entertainment Commission permits and ABC licences (lists of grants only), 3 Planning "
        "records that are not use decisions for this kind of business (agency referrals, building work, other "
        "records, decisions about other kinds of business) and 0 decided Planning rows without both dates."
    )

    # each listed record carries what it says about its use, hours and conditions
    assert (hood.use_types, hood.hours_close, hood.conditions) == (["bar"], None, [])
    # the rows read the records at the report's own street address: the hood is filed under another number
    building = next(r for r in memo.approvals if r.area == "building_change_of_use")
    assert all(f"app:{HOOD}" not in f.citations for f in building.facts)

    # the PDF and the plain-text report carry the section
    text = _pdf_text(memo)
    section = text.split("Site history", 1)[1].split("At a glance", 1)[0]
    assert SITE_HISTORY_NOTE in section and "Date Kind What Outcome" in section
    assert f"Matched by: {history.matched_by}." in section
    assert "2023-04-10 Building work Building Permit Referral" in section and HOOD_TEXT in section
    # the hood is filed under another street number on the parcel, and the row says so; no other row does
    assert f"{HOOD_TEXT} Filed under 993 Valencia St" in section and section.count("Filed under") == 1
    assert "filed 2021-05-05 ABC licence Type 41" in section and "undated Not labelled" in section
    assert "Showing" not in section
    assert text.index("What the records could not establish") < text.index("Site history")
    assert text.index("Site history") < text.index("Comparable cases")
    table = text.split("Comparable cases", 1)[1].split("What each source leaves out", 1)[0]
    assert "Planning case list (DataSF) Agency referral" in table
    plain = report_text(memo)
    assert f"SITE HISTORY: 5 on file. Matched by: {history.matched_by}." in plain
    assert (
        f"  - 2023-04-10 · Building work · Building Permit Referral: {HOOD_TEXT} (Filed under 993 Valencia St) "
        f"· approved [app:{HOOD}]" in (plain)
    )
    assert plain.count("Filed under") == 1
    assert plain.index("COULD NOT ESTABLISH") < plain.index("SITE HISTORY") < plain.index("DATED DECISIONS")


@pytest.mark.anyio
async def test_the_same_rows_without_labels_behave_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _runner, _script, memo = await _run(tmp_path, monkeypatch, labelled=False)
    # the base rate counts the hood, the referral and the row next door again, and names no new exclusion
    rate = memo.base_rate
    assert rate.total == 7 and rate.excluded_not_use_decision == 0 and rate.excluded_grant_only == 8
    assert rate.scope == (
        "N = 7 dated decisions in zoning district NCT-2 (within 1,000 ft), last 5 years; too few for a rate"
    )
    assert "not use decisions" not in base_rate_line(memo)
    # every Planning row may be a comparable again, with no kind of its own
    assert all(c.record_kind in ("not_labelled", "entertainment_permit") for c in memo.comparable_cases)
    # the site history does not depend on labels: the same five records, the Planning ones not labelled
    history = memo.site_history
    assert [e.application_id for e in history.entries] == [REFERRAL, PERMIT, HOOD, LICENCE, UNDATED]
    assert history.by_kind == {"licence": 1, "entertainment_permit": 1, "not_labelled": 3}


@pytest.mark.anyio
async def test_the_tools_report_record_kinds_and_the_same_base_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.tools.precedent_tools import (
        BASE_RATE,
        BaseRateInput,
        NearbyInput,
        ReadDecisionInput,
        _base_rate,
        _nearby_apps,
        _read_decision,
    )

    _runner, _script, memo = await _run(tmp_path, monkeypatch)
    out = (
        await _base_rate(
            BaseRateInput(lat=VALENCIA.lat, lng=VALENCIA.lng, profile=WINE_BAR, zoning_district="NCT-2")
        )
    ).model_dump()
    assert (out["excluded_grant_only"], out["excluded_not_use_decision"], out["excluded_undated"]) == (
        8,
        3,
        0,
    )
    assert out["total"] == memo.base_rate.total == 4
    assert out["scope"].endswith(
        "left out: 8 permits and licences, 3 records that are not use decisions for this kind of business"
    )
    assert "agency referrals and building work are left out" in BASE_RATE.description
    nearby = (await _nearby_apps(NearbyInput(lat=VALENCIA.lat, lng=VALENCIA.lng))).model_dump()
    kinds = {r["id"]: r["record_kind"] for r in nearby["rows"]}
    assert (kinds[HOOD], kinds[REFERRAL], kinds[PERMIT], kinds[UNDATED]) == (
        "building_work",
        "agency_referral",
        "entertainment_permit",
        "not_labelled",
    )
    one = (await _read_decision(ReadDecisionInput(application_id=LICENCE))).model_dump()
    assert one["record_kind"] == "licence"


@pytest.mark.anyio
async def test_site_records_are_read_past_the_limits_of_the_nearby_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 1,000 ft reads keep the nearest rows only: 300 licences for the bundle, 1,000 for the base rate.
    1,001 licences sit 5 m away under another address; the one at the report's address is 20 m away, so every
    one of those reads drops it. The 30 m read still finds it."""
    assert SITE_READ_RADIUS_M > 20 and analytics.BASE_RATE_LIMIT == 1000
    crowd = [
        _record(
            f"c{i}",
            metres=5,
            id=f"abc:{5000 + i}",
            source="abc",
            kind="abc_license",
            permit_type="Type 41",
            license_type="41",
            address="1001 Valencia St",
            status="Active",
        ).item
        for i in range(1001)
    ]
    here = _record(
        "here",
        metres=20,
        id="abc:4999",
        source="abc",
        kind="abc_license",
        permit_type="Type 47",
        license_type="47",
        address="995 Valencia St",
        status="Active",
        filed_at=dt.date(2019, 1, 1),
    ).item
    await LocalStore(tmp_path / "data").upsert_applications([*crowd, here])
    _runner, _script, memo = await _run(tmp_path, monkeypatch)
    assert "abc:4999" in {e.application_id for e in memo.site_history.entries}
    assert memo.site_history.total == 6 and memo.site_history.by_kind["licence"] == 2
    assert "app:abc:4999" in {c.id for c in memo.citations}
    assert "license:abc:4999" not in {c.id for c in memo.citations}  # the 1,000 ft licence read missed it
    assert memo.base_rate.excluded_grant_only == 1000  # and so did the base-rate read


@pytest.mark.anyio
async def test_pdf_says_how_many_site_records_are_shown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _runner, _script, memo = await _run(tmp_path, monkeypatch)
    entry = memo.site_history.entries[0]
    crowded = SiteHistory(
        matched_by=memo.site_history.matched_by,
        total=37,
        by_kind={"building_work": 37},
        entries=[entry.model_copy(update={"application_id": f"x:{i}"}) for i in range(SITE_HISTORY_LIMIT)],
        note=SITE_HISTORY_NOTE,
    )
    text = _pdf_text(memo.model_copy(update={"site_history": crowded}))
    assert "Showing 20 of 37" in text.split("Site history", 1)[1].split("At a glance", 1)[0]
    assert "  Showing 20 of 37." in report_text(memo.model_copy(update={"site_history": crowded}))
    # an empty site history still prints the section, with the note that says what empty means
    empty = SiteHistory(
        matched_by="Parcel 3616/065 or the address 995 Valencia St",
        total=0,
        by_kind={},
        entries=[],
        note=SITE_HISTORY_EMPTY_NOTE,
    )
    text = _pdf_text(memo.model_copy(update={"site_history": empty}))
    section = text.split("Site history", 1)[1].split("At a glance", 1)[0]
    assert SITE_HISTORY_EMPTY_NOTE in section and "Date Kind What Outcome" not in section


# ---- the candidate window on a crowded, labelled block ---------------------------------------------------
def test_the_candidate_window_is_topped_up_with_rows_that_can_be_comparables() -> None:
    crowd = [_decided(f"hood{i:03d}", metres=10 + i * 0.4, extra=_label("building_work")) for i in range(200)]
    uses = [_decided(f"use{i:02d}", metres=150 + i, extra=_label("use_decision")) for i in range(12)]
    elsewhere = _decided("elsewhere", metres=140, extra=_label("use_decision", is_premises=False))
    licence = _record("licence", metres=120, id="abc:1", source="abc", kind="abc_license")
    permit = _record(
        "permit",
        metres=170,
        id="datasf_entertainment:1",
        source="datasf_entertainment",
        kind="entertainment_poe",
    )
    wider = [*crowd, *uses, elsewhere, licence, permit]
    # the 200 nearest rows are all building work: none of them can be a comparable
    assert analytics.rank_candidates(crowd, WINE_BAR, TODAY) == []
    filled = analytics.fill_candidate_window(crowd, list(reversed(wider)))
    assert filled[:200] == crowd  # the nearest rows are kept, in order
    # added nearest first: the use decisions and the permit; never a licence or a row about other premises
    added = [n.item.source_id for n in filled[200:]]
    assert added == [*(f"use{i:02d}" for i in range(12)), "permit"]
    ranked = {s.app.source_id for s in analytics.rank_candidates(filled, WINE_BAR, TODAY)}
    assert {f"use{i:02d}" for i in range(12)} <= ranked and "elsewhere" not in ranked
    # it stops at the limit: with room for five, the five nearest that can be comparables
    five = analytics.fill_candidate_window(crowd[:3], wider, limit=5)
    assert [n.item.source_id for n in five[3:]] == ["use00", "use01", "use02", "use03", "use04"]
    # rows already in hand are not added twice, and a full window of rows that can be comparables is left alone
    assert analytics.fill_candidate_window(uses, wider, limit=12) == uses
    # no labels: every row can be a comparable, so the 200 nearest rows are the window, as before
    plain = [Nearby(n.item.model_copy(update={"extra": {}}), n.distance_m) for n in wider]
    assert analytics.fill_candidate_window(plain[:200], plain) == plain[:200]


@pytest.mark.anyio
@pytest.mark.parametrize("labelled", [True, False])
async def test_a_crowd_of_labelled_building_work_does_not_empty_the_comparables(
    tmp_path: Path, labelled: bool
) -> None:
    """200 building-work rows within 90 m and 12 use decisions about a bar at 150 to 161 m. The 200 nearest
    rows are all building work, so the use decisions have to be read past them."""

    def extra(kind: str) -> dict[str, Any]:
        return _label(kind) if labelled else {}

    crowd = [
        _decided(f"hood{i:03d}", metres=10 + i * 0.4, extra=extra("building_work")).item for i in range(200)
    ]
    uses = [_decided(f"use{i:02d}", metres=150 + i, extra=extra("use_decision")).item for i in range(12)]
    store = LocalStore(tmp_path / "data")
    await store.upsert_applications([*crowd, *uses])
    runner = MemoRunner(
        FakeAnthropic(MemoScript()),  # type: ignore[arg-type]
        get_catalog(),
        settings,
        store,
        FakeGeocoder(),
        today=TODAY,
    )

    async def emit(ev: RunnerEvent) -> None:
        return None

    bundle = await runner.collect_records(VALENCIA, WINE_BAR, emit)
    use_ids = {a.id for a in uses}
    candidates = {s.app.id for s in bundle.candidates}
    in_hand = [n.item.id for n in bundle.applications]
    if labelled:
        # every use decision is a candidate, a citation and a record the checker can be shown
        assert candidates == use_ids
        assert bundle.base_rate.total == 12 and bundle.base_rate.excluded_not_use_decision == 200
        assert len(in_hand) == 212 and len(set(in_hand)) == 212 and use_ids <= set(in_hand)
        assert {f"app:{i}" for i in use_ids} <= set(bundle.citations)
    else:
        # no labels: the 200 nearest rows and nothing else, exactly as before the labels existed
        assert len(in_hand) == 200 and not use_ids & set(in_hand)
        assert len(candidates) == 20 and not candidates & use_ids
        assert bundle.base_rate.excluded_not_use_decision == 0


# ---- a record filed under another address ------------------------------------------------------------
def test_filed_under_names_the_record_address_only_when_it_is_not_the_report_address() -> None:
    site = parse_street_address("995 Valencia St, San Francisco, CA 94110")
    assert filed_under("993 Valencia St", site) == "993 Valencia St"
    assert filed_under("997 - 999 VALENCIA ST, SAN FRANCISCO, CA 94110", site) == "997 - 999 VALENCIA ST"
    assert filed_under("2 Hill St, San Francisco, CA", site) == "2 Hill St"
    # the report's own address in any spelling, a range that holds it, or the street without its suffix
    for same in (
        "995 Valencia Street #A",
        "995 VALENCIA ST STREET LEV, SAN FRANCISCO, CA 94110",
        "993 - 995 VALENCIA ST",
        "995 Valencia",
    ):
        assert filed_under(same, site) is None, same
    # no readable address on the record: nothing to say
    for unreadable in (None, "", "Valencia St", "Pier 39"):
        assert filed_under(unreadable, site) is None, unreadable
    # the report's address cannot be read: the record's own address is still named
    assert filed_under("993 Valencia St", None) == "993 Valencia St"


@pytest.mark.anyio
async def test_pdf_and_text_name_the_address_of_a_record_filed_under_another_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _runner, _script, memo = await _run(tmp_path, monkeypatch)
    hood = next(e for e in memo.site_history.entries if e.application_id == HOOD)
    for address, shown in (
        ("993 Valencia St", "Filed under 993 Valencia St"),
        ("997 - 999 VALENCIA ST, SAN FRANCISCO, CA 94110", "Filed under 997 - 999 VALENCIA ST"),
        ("993 - 995 VALENCIA ST, SAN FRANCISCO, CA 94110", None),  # the range holds the report's number
        ("995 VALENCIA ST 1ST FLR", None),
        (None, None),
    ):
        history = memo.site_history.model_copy(
            update={"entries": [hood.model_copy(update={"address": address})]}
        )
        changed = memo.model_copy(update={"site_history": history})
        section = _pdf_text(changed).split("Site history", 1)[1].split("At a glance", 1)[0]
        plain = report_text(changed)
        if shown:
            assert f"{HOOD_TEXT} {shown} [" in section and f"{HOOD_TEXT} ({shown}) · approved" in plain
        else:
            assert "Filed under" not in section and "Filed under" not in plain, address
