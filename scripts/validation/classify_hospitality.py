"""Classify every Planning record's description into a hospitality class with Claude Haiku.

Replaces the keyword tag (which called a library, an office amenity and a gym "hospitality"). Writes only to
the LOCAL validation database (``LOCAL_DATABASE_URL``, default the cluster in $LOCAL_DATA_DIR), table
``hospitality_labels``; production is never touched. Resumable: rows already labelled are skipped.

    apps/api/.venv/bin/python scripts/validation/classify_hospitality.py [--limit N] [--concurrency 8]

Classes (by the use the application asks to establish, expand or operate, not by words it mentions):
  restaurant_or_cafe, bar, nighttime_entertainment, other_food_drink, not_hospitality
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import anthropic
import psycopg

MODEL = "claude-haiku-5-5"
BATCH = 25
LABELS = ["restaurant_or_cafe", "bar", "nighttime_entertainment", "other_food_drink", "not_hospitality"]
PRICE_IN, PRICE_OUT = 0.10 / 1e6, 0.50 / 1e6  # Claude Haiku 5.5, per token, prompts under 100K

SYSTEM = """You label San Francisco Planning Department records by the land use the application asks to \
establish, expand, legalize or operate. Read each record's type and description and pick exactly one label:

- restaurant_or_cafe: food is the main service. Restaurants, limited restaurants, cafes, coffee shops, \
bakeries or delis that serve customers, take-out food, food halls. Beer and wine served with meals is still \
restaurant_or_cafe.
- bar: serving alcohol for drinking on site is the main service. Bars, taverns, wine bars, cocktail lounges, \
brewery or distillery tasting rooms, brewpubs where drinking is primary.
- nighttime_entertainment: nightclubs, live music or performance venues, DJ or dancing, Place of \
Entertainment, Limited Live Performance, amplified sound or extended (after 2 a.m.) hours permits.
- other_food_drink: a food or drink business that is not one of the above: liquor stores and other off-sale \
alcohol, grocery or convenience stores applying for alcohol, catering, commissary or production kitchens, \
wholesale food or beverage production, food trucks, hotel food and beverage service.
- not_hospitality: everything else. This includes records that only mention a restaurant or bar in passing: \
housing next to a restaurant, converting a former restaurant to another use, an office with an employee \
cafeteria or amenity lounge, gyms, libraries, schools, massage, cannabis retail, signs, and records with too \
little text to tell.

Return every input id exactly once. Use confidence "low" when the description is ambiguous or too short."""

SCHEMA = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "label": {"type": "string", "enum": LABELS},
                    "confidence": {"type": "string", "enum": ["high", "low"]},
                },
                "required": ["i", "label", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["labels"],
    "additionalProperties": False,
}

DDL = """
create table if not exists hospitality_labels (
  id text primary key,
  label text not null,
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


async def classify(client: anthropic.AsyncAnthropic, rows: list[tuple[str, str, str, str]]) -> tuple[list[dict], int, int]:
    resp = await client.messages.create(
        model=MODEL,
        max_tokens=4000,
        thinking={"type": "disabled"},
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": render(rows)}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"refusal: {getattr(resp, 'stop_details', None)}")
    text = next(b.text for b in resp.content if b.type == "text")
    labels = json.loads(text)["labels"]
    return labels, resp.usage.input_tokens, resp.usage.output_tokens


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int)
    p.add_argument("--concurrency", type=int, default=8)
    args = p.parse_args()
    url = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres@localhost:55433/sfhp_local")
    assert "localhost" in url or "127.0.0.1" in url, "labels are written to the local validation database only"

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(DDL)
        todo = conn.execute(
            """select a.id, coalesce(a.extra->>'record_type',''), coalesce(a.extra->>'project_name',''), a.description
               from applications a left join hospitality_labels h on h.id = a.id
               where a.source = 'datasf_planning' and h.id is null order by a.id"""
        ).fetchall()
    if args.limit:
        todo = todo[: args.limit]
    batches = [todo[i : i + BATCH] for i in range(0, len(todo), BATCH)]
    print(f"{len(todo)} records to label in {len(batches)} requests", flush=True)

    client = anthropic.AsyncAnthropic(api_key=api_key())
    sem = asyncio.Semaphore(args.concurrency)
    tokens = {"in": 0, "out": 0}
    failed = 0
    done = 0
    started = time.monotonic()

    async def run(batch: list[tuple[str, str, str, str]]) -> None:
        nonlocal failed, done
        async with sem:
            try:
                labels, tin, tout = await classify(client, batch)
            except Exception as exc:  # noqa: BLE001 — logged; the batch stays unlabelled for a re-run
                failed += 1
                print(f"batch failed: {type(exc).__name__}: {str(exc)[:160]}", flush=True)
                return
        tokens["in"] += tin
        tokens["out"] += tout
        by_i = {d["i"]: d for d in labels if 0 <= d["i"] < len(batch)}
        recs = [(batch[i][0], by_i[i]["label"], by_i[i]["confidence"], MODEL) for i in range(len(batch)) if i in by_i]
        with psycopg.connect(url, autocommit=True) as conn:
            conn.cursor().executemany(
                "insert into hospitality_labels (id, label, confidence, model) values (%s,%s,%s,%s) "
                "on conflict (id) do update set label=excluded.label, confidence=excluded.confidence, model=excluded.model, classified_at=now()",
                recs,
            )
        done += 1
        if done % 50 == 0:
            cost = tokens["in"] * PRICE_IN + tokens["out"] * PRICE_OUT
            print(f"{done}/{len(batches)} requests, ${cost:.2f} so far, {time.monotonic() - started:.0f}s", flush=True)

    await asyncio.gather(*(run(b) for b in batches))
    cost = tokens["in"] * PRICE_IN + tokens["out"] * PRICE_OUT
    print(
        f"done: {done} requests ok, {failed} failed; {tokens['in']:,} input + {tokens['out']:,} output tokens = ${cost:.2f}",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
