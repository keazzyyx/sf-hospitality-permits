"""Generate one report against the LOCAL validation database, with the production models, and print its real cost.

Refuses any database that is not on localhost, so it cannot read or write production. Tracing export is off:
nothing about the run leaves this machine except the Claude API calls themselves and the public geocoder lookup.
The API key is read by the app from apps/api/.env and is never printed.

The run prints the pathway and every row's status with the rule ids that set them (the PATHWAY and STATUSES
lines), so several runs can be compared side by side, and then, under ROWS, the rules date and one line per row:
its status with its status note ("Further review: Code and Planning practice differ") and the inputs the rules
name as not given. `--json` holds the whole report, the pathway included; `--profile-json` writes the intake
profile the rules read.

`--rules-date YYYY-MM-DD` applies the rules in force on that date instead of today's (rule table v2). Only the
rules read it: the records, the comparables and the counts are today's.

`--intake JSON` gives the answers to the optional intake questions, as a file or as inline JSON, with the keys a
create request takes (app.memo.intake.IntakeAnswers: part_of_chain, other_locations, floor_area_sqft,
liquor_licence, stories, alcohol_served, closing_time, last_use, fewer_than_50_people, outdoor_area and the rest;
docs/api-contract-memo.md lists every key and its allowed answers). Any key
may be left out (a skipped question). They are applied the same way: by code, after the intake model's profile
and before the rules. `other_locations` may also be "11_or_more", as backtest/inputs.json writes it.
`liquor_licence` is one of "new", "transfer_from_another_owner", "transfer_from_another_location",
"already_held" (a licence already held at this address) or "none" (no alcohol, whatever the description says).

The report is the rules and the evidence; the intake is the only model call, and the cost table counts it.

    cd apps/api && .venv/bin/python ../../scripts/validation/run_report_local.py \
        "995 Valencia St, San Francisco, CA 94110" \
        "40-seat wine bar, small kitchen, open until 1am, occasional live music" \
        --json ../../docs/examples/memo-995-valencia.json --pdf ../../docs/examples/memo-995-valencia.pdf \
        --profile-json /tmp/profile-995-valencia.json
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import datetime as dt
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

LOCAL = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres@localhost:55433/sfhp_local")
assert "@localhost:" in LOCAL or "@127.0.0.1:" in LOCAL, "refusing: the validation run only uses the local database"
os.environ["PRECEDENT_DATABASE_URL"] = LOCAL
os.environ["NEATLOGS_API_KEY"] = ""  # no trace export

# $ per million tokens: input, output. Cache writes cost 1.25x input (5-minute) or 2x (1-hour); cache reads 0.1x.
PRICES = {
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-5-5": (0.10, 0.50),
}

USAGE: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
# The same counts by stage (the intake is the memo's only model call), for pricing a batched backtest stage by
# stage. The stage is read from AgentRunner._run_stage, which every model call goes through.
USAGE_BY_STAGE: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
_STAGE: contextvars.ContextVar[str] = contextvars.ContextVar("stage", default="unknown")


def price_for(model: str) -> tuple[float, float]:
    for name, p in PRICES.items():
        if model.startswith(name):
            return p
    raise SystemExit(f"no price on file for model {model!r}; add it to PRICES before trusting the cost")


def install_usage_meter() -> None:
    """Count the tokens of every model call."""
    from anthropic.lib.streaming import AsyncMessageStream

    original = AsyncMessageStream.get_final_message

    async def metered(self):  # type: ignore[no-untyped-def]
        msg = await original(self)
        u = msg.usage
        creation = getattr(u, "cache_creation", None)
        w5 = getattr(creation, "ephemeral_5m_input_tokens", None) if creation else None
        w1h = getattr(creation, "ephemeral_1h_input_tokens", None) if creation else None
        if w5 is None and w1h is None:
            w5 = getattr(u, "cache_creation_input_tokens", 0) or 0
        for row in (USAGE[msg.model], USAGE_BY_STAGE[f"{_STAGE.get()}|{msg.model}"]):
            row["calls"] += 1
            row["input"] += u.input_tokens or 0
            row["output"] += u.output_tokens or 0
            row["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
            row["cache_write_5m"] += w5 or 0
            row["cache_write_1h"] += w1h or 0
        return msg

    AsyncMessageStream.get_final_message = metered  # type: ignore[method-assign]

    from app.agents.runner import AgentRunner

    run_stage = AgentRunner._run_stage

    async def tagged(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        token = _STAGE.set(str(kwargs.get("stage", "unknown")))
        try:
            return await run_stage(self, *args, **kwargs)
        finally:
            _STAGE.reset(token)

    AgentRunner._run_stage = tagged  # type: ignore[method-assign]


def cost_table() -> tuple[str, float]:
    lines = ["| Model | Calls | Input | Cache write | Cache read | Output | Cost |", "|---|---|---|---|---|---|---|"]
    total = 0.0
    for model, r in sorted(USAGE.items()):
        pin, pout = price_for(model)
        cost = (
            r["input"] * pin
            + r["cache_write_5m"] * pin * 1.25
            + r["cache_write_1h"] * pin * 2.0
            + r["cache_read"] * pin * 0.1
            + r["output"] * pout
        ) / 1e6
        total += cost
        lines.append(
            f"| {model} | {r['calls']} | {r['input']:,} | {r['cache_write_5m'] + r['cache_write_1h']:,} | "
            f"{r['cache_read']:,} | {r['output']:,} | ${cost:.4f} |"
        )
    lines.append(f"| **Total** | | | | | | **${total:.4f}** |")
    return "\n".join(lines), total


def rules_date_arg(text: str) -> dt.date:
    """`--rules-date`: a calendar date written YYYY-MM-DD."""
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a date written YYYY-MM-DD: {text!r}") from None


def intake_arg(text: str) -> Any:
    """`--intake`: a JSON file, or the JSON itself, holding the intake answers (app.memo.intake.IntakeAnswers)."""
    from app.memo.intake import intake_answers
    from pydantic import ValidationError

    inline = text.lstrip().startswith("{")
    try:
        data = json.loads(text if inline else Path(text).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise argparse.ArgumentTypeError(f"not a JSON object or a file holding one: {text!r}") from None
    if not isinstance(data, dict):
        raise argparse.ArgumentTypeError(f"the intake answers are a JSON object, got {text!r}")
    try:
        return intake_answers(data)
    except ValidationError as exc:
        errors = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'intake'}: {e['msg']}" for e in exc.errors())
        raise argparse.ArgumentTypeError(f"not valid intake answers: {errors}") from None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("address")
    p.add_argument("description")
    p.add_argument("--json", type=Path)
    p.add_argument("--pdf", type=Path)
    p.add_argument("--usage-json", type=Path)
    p.add_argument("--profile-json", type=Path, help="write the intake profile used (what the rules read)")
    p.add_argument(
        "--rules-date",
        type=rules_date_arg,
        metavar="YYYY-MM-DD",
        help="apply the rules in force on this date instead of today's; the records stay today's",
    )
    p.add_argument(
        "--intake",
        type=intake_arg,
        metavar="JSON",
        help="the answers to the optional intake questions, as a JSON file or inline JSON, e.g. "
        '{"part_of_chain": false, "floor_area_sqft": 1800, "liquor_licence": "new"}; liquor_licence is new, '
        "transfer_from_another_owner, transfer_from_another_location, already_held or none (no alcohol)",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()

    from app.core.config import settings

    url = settings.PRECEDENT_DATABASE_URL or ""
    assert "@localhost:" in url or "@127.0.0.1:" in url, "refusing: the app resolved a non-local precedent database"
    print(f"precedent store: local ({url.rsplit('@', 1)[-1]})", file=sys.stderr)
    print(f"model: main={settings.ANTHROPIC_MODEL_MAIN} (the intake)", file=sys.stderr)
    install_usage_meter()
    from app.scripts.memo_demo import generate

    code = asyncio.run(
        generate(args.address, args.description, pdf=args.pdf, out_json=args.json, quiet=False,
                 profile_json=args.profile_json, rules_date=args.rules_date, intake_answers=args.intake)
    )  # fmt: skip
    table, total = cost_table()
    print("\n" + table)
    if args.usage_json:
        by_stage = {}
        for key, r in sorted(USAGE_BY_STAGE.items()):
            stage, model = key.split("|", 1)
            pin, pout = price_for(model)
            cost = (r["input"] * pin + r["cache_write_5m"] * pin * 1.25 + r["cache_write_1h"] * pin * 2.0 + r["cache_read"] * pin * 0.1 + r["output"] * pout) / 1e6
            by_stage[key] = {**dict(r), "stage": stage, "model": model, "cost_usd": round(cost, 4)}
        args.usage_json.write_text(json.dumps({"models": {m: dict(r) for m, r in USAGE.items()}, "by_stage": by_stage, "cost_usd": round(total, 4)}, indent=1) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
