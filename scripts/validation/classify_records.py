"""Label every Planning record three ways with Claude Haiku, through the Message Batches API (half price).

Supersedes classify_hospitality.py (one label). Each record gets:

- ``premises``    is the record about a space that is, or is meant to be, a restaurant, cafe, bar, venue or
                  other food-and-drink business? A kitchen hood at an operating restaurant: yes. A whole-building
                  project that happens to include a ground-floor restaurant: no.
- ``use_class``   restaurant_or_cafe | bar | nighttime_entertainment | other_food_drink | none
- ``record_kind`` use_decision | agency_referral | building_work | other

Pathway counts and the backtest use only premises records whose kind is use_decision or agency_referral;
building_work feeds the site-history part of a report.

Writes only to the LOCAL validation database (table ``record_labels``).

    apps/api/.venv/bin/python scripts/validation/classify_records.py submit      # create the batch
    apps/api/.venv/bin/python scripts/validation/classify_records.py wait        # poll, then store results
    apps/api/.venv/bin/python scripts/validation/classify_records.py collect     # store results if it has ended
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import anthropic
import psycopg
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

MODEL = "claude-haiku-5-5"
PER_REQUEST = 25
USE_CLASSES = ["restaurant_or_cafe", "bar", "nighttime_entertainment", "other_food_drink", "none"]
RECORD_KINDS = ["use_decision", "agency_referral", "building_work", "other"]
# Claude Haiku 5.5, $ per token, prompts under 100K, Message Batches (50% of $0.10 in / $0.50 out)
P_IN, P_OUT = 0.05 / 1e6, 0.25 / 1e6
P_CACHE_WRITE, P_CACHE_READ = P_IN * 1.25, P_IN * 0.1

LOCAL = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres@localhost:55433/sfhp_local")
STATE = Path(os.environ.get("LOCAL_DATA_DIR", "~/sfhp-local")).expanduser() / "classify_records_batch.json"

SYSTEM = """You label San Francisco Planning Department records. For each record decide three things from its \
record type and description.

1. premises (true/false). True when the record is about one commercial space that is, or is meant to be, a \
restaurant, cafe, bar, entertainment venue or other food-and-drink business: opening it, changing it, licensing \
it, or doing building work in it. A kitchen hood, walk-in cooler, awning or fire repair at an operating \
restaurant is true. False when the record is about something else and food or drink is incidental: a \
whole-building or mixed-use development that includes a ground-floor restaurant, housing, offices with an \
employee cafeteria or amenity lounge, converting a former restaurant INTO a non-food use, a home "wet bar" or \
kitchen remodel, window "spacer bars", gyms, libraries, schools, massage, cannabis retail.

2. use_class. The food-and-drink use of that space, or "none" when premises is false.
- restaurant_or_cafe: food is the main service. Restaurants, limited restaurants, cafes, coffee shops, bakeries \
and delis serving customers, take-out food. A restaurant with a beer-and-wine or full liquor licence (ABC \
Type 41 or 47) is still restaurant_or_cafe.
- bar: drinking on site is the main service. Bars, taverns, wine bars, cocktail lounges, tasting rooms, ABC \
Type 42 or 48 licences.
- nighttime_entertainment: nightclubs, live music or performance venues, DJ or dancing, Place of Entertainment, \
Limited Live Performance, amplified sound or extended-hours permits.
- other_food_drink: liquor stores and other off-sale alcohol (ABC Type 20 or 21), grocery or convenience stores \
with alcohol, catering, commissary or production kitchens, breweries and wineries without a tasting room, food \
trucks, and hotels: a hotel's food-and-beverage licences are other_food_drink even when they include a \
restaurant or bar licence type.

3. record_kind.
- use_decision: decides whether a use may be established, changed, expanded, intensified, legalized or \
continued. Conditional Use, change of use (including a building permit whose description is a change of use), \
variances and discretionary review about a use, and Zoning Administrator letters of determination about a use \
(for example whether an abandoned bar may reopen).
- agency_referral: Planning's sign-off on another agency's permit for a business: ABC liquor licence, Health \
(DPH) food permit, Entertainment Commission or Police permit. Typical text: "ABC referral", "DPH referral", \
"Health -", "Recommend approval", or an older note that a named business's use "is permitted per Section ...".
- building_work: building-permit review with no change of use: tenant improvements, hoods, coolers, storefronts, \
awnings, signs, repairs, remodels.
- other: project review meetings, complaints, legacy business registry, appeals, informational records, and \
records with too little text to tell.

Examples (type :: description -> premises, use_class, record_kind):
- CUA :: "Conditional Use to establish a bar (dba Casements) with outdoor activity area" -> true, bar, use_decision
- PRL :: "Change of use from retail to limited restaurant. Install hood." -> true, restaurant_or_cafe, use_decision
- PRL :: "Install hood and gas line at ground floor of existing restaurant. No change of use." -> true, \
restaurant_or_cafe, building_work
- PRL :: "Renovate one-story fire damaged restaurant, add roof deck" -> true, restaurant_or_cafe, building_work
- PRL :: "Interior changes only to replace restaurant with office space." -> false, none, use_decision
- MIS :: "ABC referral - Type 41 - Recommend approval, restaurant is a bona fide eating place" -> true, \
restaurant_or_cafe, agency_referral
- MIS :: "On-Sale Beer & Wine - ABC License Type 41 is permitted with an existing restaurant use" -> true, \
restaurant_or_cafe, agency_referral
- MIS :: "The Marker Hotel - ABC referral - Type 47, 58, 66, 68 permitted with continued hotel and restaurant \
use" -> true, other_food_drink, agency_referral
- MIS :: "HOMRAN LIQUOR STORE existing liquor store permitted. Change of ownership only." -> true, \
other_food_drink, agency_referral
- MIS :: "Entertainment Commission - Limited Live Performance permitted with restaurant use" -> true, \
nighttime_entertainment, agency_referral
- ZAD :: "Letter of Determination - prior restaurant/bar space abandoned and new facility not permitted without \
new conditional use" -> true, bar, use_decision
- CUA :: "New nine-story building with 120 dwelling units and ground floor restaurant (3,700 sq ft)" -> false, \
none, use_decision
- CUA :: "Conditional Use to add massage services to existing foot massage establishment" -> false, none, \
use_decision
- PRV :: "Project Review Meeting to discuss a proposed restaurant/beer hall with outdoor seating" -> true, bar, \
other
- PRL :: "Replace windows with simulated divided lights with dark spacer bar" -> false, none, building_work
- PRL :: "Interior remodel of existing restaurant for new non-formula retail operator. No change of use." -> \
true, restaurant_or_cafe, building_work ("non-formula retail" only means the operator is not a chain)
- CUA :: "Conditional Use to include message services in existing foot message establishment" -> false, none, \
use_decision ("message" is a misspelling of massage)

Return every input index exactly once. Use confidence "low" when the description is ambiguous or too short."""

SCHEMA = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "premises": {"type": "boolean"},
                    "use_class": {"type": "string", "enum": USE_CLASSES},
                    "record_kind": {"type": "string", "enum": RECORD_KINDS},
                    "confidence": {"type": "string", "enum": ["high", "low"]},
                },
                "required": ["i", "premises", "use_class", "record_kind", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["labels"],
    "additionalProperties": False,
}

DDL = """
create table if not exists record_labels (
  id text primary key,
  premises boolean not null,
  use_class text not null,
  record_kind text not null,
  confidence text not null,
  model text not null,
  classified_at timestamptz not null default now()
);
"""


def api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    env = Path(__file__).resolve().parents[2] / "apps" / "api" / ".env"
    for line in env.read_text().splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].split("#", 1)[0].strip()
    raise SystemExit("ANTHROPIC_API_KEY not found")


def render(rows: list[tuple[str, str, str, str]]) -> str:
    out = []
    for i, (_id, rtype, project, desc) in enumerate(rows):
        text = " ".join(t for t in (project, desc) if t).strip()[:700]
        out.append(f"[{i}] type={rtype or '?'} :: {text or '(no description)'}")
    return "Label these records:\n" + "\n".join(out)


def todo_rows() -> list[tuple[str, str, str, str]]:
    assert "localhost" in LOCAL, "labels are written to the local validation database only"
    with psycopg.connect(LOCAL, autocommit=True) as conn:
        conn.execute(DDL)
        return conn.execute(
            """select a.id, coalesce(a.extra->>'record_type',''), coalesce(a.extra->>'project_name',''), a.description
               from applications a left join record_labels r on r.id = a.id
               where a.source = 'datasf_planning' and r.id is null order by a.id"""
        ).fetchall()


def submit() -> int:
    rows = todo_rows()
    if not rows:
        print("nothing to label")
        return 0
    chunks = [rows[i : i + PER_REQUEST] for i in range(0, len(rows), PER_REQUEST)]
    system = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
    requests = [
        Request(
            custom_id=f"c{n}",
            params=MessageCreateParamsNonStreaming(
                model=MODEL,
                max_tokens=4000,
                thinking={"type": "disabled"},
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                system=system,
                messages=[{"role": "user", "content": render(chunk)}],
            ),
        )
        for n, chunk in enumerate(chunks)
    ]
    client = anthropic.Anthropic(api_key=api_key())
    batch = client.messages.batches.create(requests=requests)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"batch_id": batch.id, "chunks": [[r[0] for r in c] for c in chunks]}))
    print(f"submitted batch {batch.id}: {len(rows)} records in {len(requests)} requests")
    return 0


def collect(wait: bool) -> int:
    state = json.loads(STATE.read_text())
    client = anthropic.Anthropic(api_key=api_key())
    while True:
        batch = client.messages.batches.retrieve(state["batch_id"])
        if batch.processing_status == "ended":
            break
        print(f"status {batch.processing_status}: {batch.request_counts}", flush=True)
        if not wait:
            return 3
        time.sleep(60)
    chunks: list[list[str]] = state["chunks"]
    usage = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
    ok = bad = 0
    recs: list[tuple[str, bool, str, str, str, str]] = []
    for result in client.messages.batches.results(state["batch_id"]):
        n = int(result.custom_id[1:])
        if result.result.type != "succeeded":
            bad += 1
            continue
        msg = result.result.message
        usage["input"] += msg.usage.input_tokens
        usage["output"] += msg.usage.output_tokens
        usage["cache_write"] += msg.usage.cache_creation_input_tokens or 0
        usage["cache_read"] += msg.usage.cache_read_input_tokens or 0
        if msg.stop_reason == "refusal":
            bad += 1
            continue
        try:
            labels = json.loads(next(b.text for b in msg.content if b.type == "text"))["labels"]
        except (StopIteration, json.JSONDecodeError, KeyError):
            bad += 1
            continue
        ok += 1
        ids = chunks[n]
        seen: set[int] = set()
        for d in labels:
            i = d.get("i")
            if not isinstance(i, int) or not 0 <= i < len(ids) or i in seen:
                continue
            seen.add(i)
            use_class = d["use_class"] if d["premises"] else "none"
            recs.append((ids[i], bool(d["premises"]), use_class, d["record_kind"], d["confidence"], MODEL))
    with psycopg.connect(LOCAL, autocommit=True) as conn:
        conn.cursor().executemany(
            """insert into record_labels (id, premises, use_class, record_kind, confidence, model)
               values (%s,%s,%s,%s,%s,%s)
               on conflict (id) do update set premises=excluded.premises, use_class=excluded.use_class,
                 record_kind=excluded.record_kind, confidence=excluded.confidence, model=excluded.model,
                 classified_at=now()""",
            recs,
        )
    cost = (
        usage["input"] * P_IN
        + usage["output"] * P_OUT
        + usage["cache_write"] * P_CACHE_WRITE
        + usage["cache_read"] * P_CACHE_READ
    )
    print(f"requests ok {ok}, failed {bad}; records labelled {len(recs)}")
    print(f"usage {usage} -> ${cost:.4f} (batch prices)")
    return 1 if bad else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "submit":
        sys.exit(submit())
    if cmd in ("collect", "wait"):
        sys.exit(collect(wait=cmd == "wait"))
    print(__doc__)
    sys.exit(2)
