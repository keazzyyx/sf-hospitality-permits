"""Keep a private person's name and contact details out of the published text of a condition of approval.

A Community Liaison condition sometimes names the liaison (the owner or a manager) with a phone number, an e-mail
address or a business address. Those are a private person's details, not part of the rule, so the published data
shows "[contact in the motion]" in their place (owner's decision of 2026-11-16); the condition's link to the adopted
motion stays, so the details are one click away in the public record. Only conditions that mention a liaison are
touched. City numbers and addresses stay: the standard "For information about compliance, contact ..." lines name
public departments.

Used by build_conditions_index.py (every condition it writes) and build_public_conditions_site.py (every condition
it publishes). Idempotent: running it on its own output changes nothing (tests: apps/api/tests/test_private_contacts.py).
"""

from __future__ import annotations

import re

PLACEHOLDER = "[contact in the motion]"

LIAISON = re.compile(r"liaison", re.IGNORECASE)

# Public department numbers that appear in conditions (digits only). Any other number in a liaison condition is
# replaced.
CITY_PHONES = {
    "4155586378",  # Planning, Case Planner
    "4155756863",  # Planning, Code Enforcement
    "4155545810",  # Public Works
    "4156952017",  # Public Works, Bureau of Street Use and Mapping
    "6282712000",  # Public Works
    "4152523800",  # Public Health, Environmental Health
    "4155546678",  # Entertainment Commission
    "4155586570",  # Building Inspection
    "4155530123",  # Police Department
    "4155812335",  # First Source Hiring
    "4155545184",  # Board of Supervisors
}
CITY_PHONE_PREFIXES = ("628652",)  # Planning's 628 numbers
CITY_EMAIL_DOMAINS = re.compile(
    r"@(?:sfgov\.org|sf\.gov|sfmta\.com|sfplanning\.org|sfdph\.org|sfpolice\.org|sfdbi\.org|sfwater\.org|sfdpw\.org)$",
    re.IGNORECASE,
)

PHONE = re.compile(r"\(?\b\d{3}\)?\s*[-‐–.]?\s*\d{3}\s*[-‐–.]\s*\d{4}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# "the Community Liaison Officer will be the current owner, <Name>, who ..." / "The Community Liaison is <Name>, at"
NAME = re.compile(
    r"(liaison(?: officer)?\s+(?:will be|is|shall be)\s+(?:the current (?:owner|manager|operator|general manager),\s+)?)"
    r"(?!\[)([A-Z][^,;:]{1,60}?)(?=,)",
    re.IGNORECASE,
)
ADDRESS = re.compile(
    r"((?:business |mailing |home )?address of\s+)(?!\[)(\d[^,]*,[^,]*,\s*CA\s*\d{5}(?:-\d{4})?)", re.IGNORECASE
)


def _phone(m: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    if digits in CITY_PHONES or digits.startswith(CITY_PHONE_PREFIXES):
        return m.group(0)
    return PLACEHOLDER


def _email(m: re.Match[str]) -> str:
    return m.group(0) if CITY_EMAIL_DOMAINS.search(m.group(0)) else PLACEHOLDER


def _name(m: re.Match[str]) -> str:
    name = m.group(2)
    # the name must start with a capital letter; "the Project Sponsor" and the like are left alone
    if not name[0].isupper() or name.lower().startswith(("the ", "a ", "an ")):
        return m.group(0)
    return m.group(1) + PLACEHOLDER


def withhold_private_contacts(text: str | None) -> str | None:
    """The text with a liaison's name, phone, e-mail and street address replaced; other text unchanged."""
    if not text or not LIAISON.search(text):
        return text
    text = NAME.sub(_name, text)
    text = EMAIL.sub(_email, text)
    text = PHONE.sub(_phone, text)
    text = ADDRESS.sub(lambda m: m.group(1) + PLACEHOLDER, text)
    return text


def private_contact_strings(text: str | None) -> list[str]:
    """The strings withhold_private_contacts would take out of `text`: each liaison name, private phone number,
    private e-mail address and street address, as written. Empty when it would change nothing. (Used by the public
    site's build to prove none of them is in its output.)"""
    if not text or not LIAISON.search(text):
        return []
    found: list[str] = []
    for m in NAME.finditer(text):
        name = m.group(2)
        if name[0].isupper() and not name.lower().startswith(("the ", "a ", "an ")):
            found.append(name)
    found += [m.group(0) for m in EMAIL.finditer(text) if not CITY_EMAIL_DOMAINS.search(m.group(0))]
    for m in PHONE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if digits not in CITY_PHONES and not digits.startswith(CITY_PHONE_PREFIXES):
            found.append(m.group(0))
    found += [m.group(2) for m in ADDRESS.finditer(text)]
    return found
