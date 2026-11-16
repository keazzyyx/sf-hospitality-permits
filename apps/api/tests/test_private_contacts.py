"""The published conditions name no private liaison: scripts/validation/private_contacts.py puts "[contact in the
motion]" in place of a liaison's name, phone, e-mail and street address, keeps public department numbers, and the
shipped data passes through it unchanged."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "tools" / "conditions-search" / "data" / "conditions.json"


def load() -> ModuleType:
    path = REPO / "scripts" / "validation" / "private_contacts.py"
    spec = importlib.util.spec_from_file_location("private_contacts", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("private_contacts", module)
    spec.loader.exec_module(module)
    return module


P = load()


def test_a_named_liaison_is_replaced() -> None:
    text = (
        "Community Liaison: The Project Sponsor shall appoint a community liaison officer. The community liaison "
        "officer will be Alex Example, who can be contacted at (415) 555-0100, or via email at alex@example.com."
    )
    out = P.withhold_private_contacts(text)
    assert "Alex Example" not in out and "555-0100" not in out and "alex@example.com" not in out
    assert (
        "will be [contact in the motion], who can be contacted at [contact in the motion], or via email at [contact in the motion]"
        in out
    )
    assert P.withhold_private_contacts(out) == out


def test_the_owner_or_manager_form_and_a_business_address() -> None:
    owner = "The Community Liaison Officer will be the current owner, Sam Sample, who can be contacted at 415-555-0199."
    assert P.withhold_private_contacts(owner) == (
        "The Community Liaison Officer will be the current owner, [contact in the motion], who can be contacted at "
        "[contact in the motion]."
    )
    address = (
        "The Community Liaison is Pat Q. Placeholder, at a business address of 1 Example Avenue, San Francisco, "
        "CA 94100, and phone number 415-555-0142."
    )
    assert P.withhold_private_contacts(address) == (
        "The Community Liaison is [contact in the motion], at a business address of [contact in the motion], and phone number "
        "[contact in the motion]."
    )


def test_public_numbers_and_unnamed_liaisons_are_kept() -> None:
    standard = (
        "Community Liaison: Prior to issuance of a building permit, the Project Sponsor shall appoint a community "
        "liaison officer to deal with the issues of concern to owners and occupants of nearby properties. The "
        "Project Sponsor shall provide the Zoning Administrator with written notice of the name, business address, "
        "and telephone number of the community liaison. For information about compliance, contact Code "
        "Enforcement, Planning Department at 415-575-6863, www.sf-planning.org"
    )
    assert P.withhold_private_contacts(standard) == standard
    bikes = "contact the SFMTA Bike Parking Program at bikeparking@sfmta.com"
    assert P.withhold_private_contacts(bikes) == bikes  # no liaison: never touched
    assert P.withhold_private_contacts(None) is None


def test_the_shipped_conditions_name_no_private_liaison() -> None:
    data = json.loads(DATA.read_text())
    for c in data["conditions"]:
        for field in ("text", "raw_text"):
            assert P.withhold_private_contacts(c.get(field)) == c.get(field), (
                c["record"],
                c["number"],
                field,
            )
    replaced = sorted(
        (c["record"], c["number"])
        for c in data["conditions"]
        if "[contact in the motion]" in (c.get("text") or "")
    )
    assert replaced == [
        ("2010.0255C", "8"),
        ("2010.0970C", "8"),
        ("2011.1216C", "9"),
        ("2017-015669CUA", "10"),
    ]
    for c in data["conditions"]:
        if (c["record"], c["number"]) in replaced:
            assert c.get("pdf") and c.get("page"), c["record"]  # the link to the motion stays


# An independent check of the shipped data that does not reuse the scrubber's own patterns (review of 2026-11-16):
# every phone-shaped number in any condition, liaison or not, written with any separators, must be a public
# department line, and every e-mail address must be at a city domain.
PHONE_SHAPED = re.compile(r"(?<![\dA-Za-z])\(?\d{3}\)?[\s\-‐‑–—−.]*\d{3}[\s\-‐‑–—−.]+\d{4}(?![\dA-Za-z])")
ANY_EMAIL = re.compile(r"[\w.+~-]+\s*@\s*[\w-]+(?:\s*\.\s*[\w-]+)+")


def test_no_private_phone_or_email_in_any_condition() -> None:
    data = json.loads(DATA.read_text())
    private: list[tuple[str, str, str]] = []
    for c in data["conditions"]:
        for field in ("text", "raw_text", "title"):
            text = c.get(field) or ""
            for m in PHONE_SHAPED.finditer(text):
                digits = re.sub(r"\D", "", m.group(0))
                if digits not in P.CITY_PHONES and not digits.startswith(P.CITY_PHONE_PREFIXES):
                    private.append((c["record"], c["number"], field))
            for m in ANY_EMAIL.finditer(text):
                if not P.CITY_EMAIL_DOMAINS.search(re.sub(r"\s", "", m.group(0))):
                    private.append((c["record"], c["number"], field))
    assert private == []


def test_the_independent_check_catches_forms_the_scrubber_misses() -> None:
    for text in (
        "contact the owner, Alex Example, at 415 555 0100",
        "call (415)555–0100 after hours",
        "write to alex @ example.com",
    ):
        assert PHONE_SHAPED.search(text) or ANY_EMAIL.search(text), text
    assert not PHONE_SHAPED.search("Case No. 2015- 000491CUA")
    assert not PHONE_SHAPED.search("the residential tenants of 4022 - 4024 24th Street")
