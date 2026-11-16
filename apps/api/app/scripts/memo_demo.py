"""Generate one Location Risk Memo from the command line (real model, real store), print the report
(overall status, the pathway and every row's status with the rule ids that set them, one row per approval
with labelled findings, what could not be established, the citation-check counts), and write the JSON and
the PDF. `--profile-json` writes the concept profile the intake stage produced, which is what the rules read.
`--rules-date YYYY-MM-DD` applies the rules in force on that date instead of today's (rule table v2); the
records, the comparables and the counts stay today's. The run ends with one line per row: its status with its
status note, and the inputs the rules name as not given.

python -m app.scripts.memo_demo "995 Valencia St" "40-seat wine bar, small kitchen, open until 1am, live music" --pdf /tmp/memo.pdf
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any

import neatlogs

from app.core.config import settings
from app.core.observability import mask_pii

neatlogs.init(
    api_key=settings.NEATLOGS_API_KEY,
    endpoint=settings.NEATLOGS_ENDPOINT,
    workflow_name="permit_memo",
    instrumentations=["anthropic"],
    tags=[f"env:{settings.ENV}", f"version:{settings.GIT_SHA}", "entry:memo_demo"],
    mask=mask_pii,
    disable_export=not settings.NEATLOGS_API_KEY,
)

from app.agents.memo_runner import MemoRunInput  # noqa: E402
from app.agents.runner import RunnerEvent  # noqa: E402
from app.deps import get_memo_runner  # noqa: E402
from app.memo.intake import IntakeAnswers  # noqa: E402
from app.memo.report import (  # noqa: E402
    pathway_headline,
    report_text,
    status_summary_lines,
    statuses_line,
)
from app.services.memo_pdf import render_memo_pdf  # noqa: E402


@neatlogs.span(kind="WORKFLOW", name="memo.generate", capture_output=False)
async def generate(
    address: str,
    description: str,
    *,
    pdf: Path | None,
    out_json: Path | None,
    quiet: bool,
    profile_json: Path | None = None,
    rules_date: dt.date | None = None,
    intake_answers: IntakeAnswers | None = None,
) -> int:
    """One report. `rules_date` is the date whose rules apply; None means today. `intake_answers` are the
    applicant's answers to the optional intake questions (app.memo.intake), applied as a create request applies
    them; None answers none."""
    runner = get_memo_runner()
    started = time.monotonic()

    async def emit(ev: RunnerEvent) -> None:
        if quiet:
            return
        if ev.type == "stage":
            print(
                f"[{time.monotonic() - started:6.1f}s] {ev.data['stage']:10} {ev.data['status']:9} {ev.data['message']}",
                file=sys.stderr,
            )
        elif ev.type == "tool":
            rows = f" rows={ev.data['rows']}" if ev.data.get("rows") is not None else ""
            print(
                f"            tool {ev.data['tool']:22} {ev.data['status']:9} {ev.data['message']}{rows}",
                file=sys.stderr,
            )

    terminal = [
        ev
        async for ev in runner.run_memo(
            MemoRunInput(
                address=address,
                description=description,
                allow_clarification=False,
                rules_date=rules_date,
                intake_answers=intake_answers or IntakeAnswers(),
            ),
            emit,
        )
    ]
    print(file=sys.stderr)
    final = terminal[-1]
    if final.type != "memo":
        print(json.dumps(final.data, indent=2))
        return 2
    memo = final.data["memo"]
    if profile_json:
        write_profile(final.data["profile"], profile_json)
    if not quiet:
        print(report_text(memo), file=sys.stderr)
    write_outputs(memo, pdf=pdf, out_json=out_json)
    # the pathway and every row's status with its rule ids: the lines to compare between runs
    print(f"PATHWAY: {pathway_headline(memo.pathway)}", file=sys.stderr)
    print(statuses_line(memo), file=sys.stderr)
    # each row's status with its status note and the inputs the rules name as not given, under the rules date
    print("\n".join(status_summary_lines(memo)), file=sys.stderr)
    print(
        f"overall_status={memo.overall.status} approvals={len(memo.approvals)} "
        f"comparables={len(memo.comparable_cases)} site_history={memo.site_history.total} "
        f"citations={len(memo.citations)} facts={len(memo.facts)} elapsed={time.monotonic() - started:.1f}s",
        file=sys.stderr,
    )
    return 0


def write_profile(profile: Any, path: Path) -> None:
    """The intake profile the rules read. Two runs with the same profile, zoning, overlays and site records
    give the same pathway and statuses."""
    path.write_text(json.dumps(profile.model_dump(), indent=2, default=str) + "\n")
    print(f"intake profile → {path}", file=sys.stderr)


def write_outputs(memo: Any, *, pdf: Path | None, out_json: Path | None) -> None:
    text = json.dumps(memo.model_dump(), indent=2, default=str)
    if out_json:
        out_json.write_text(text)
        print(f"memo JSON → {out_json}", file=sys.stderr)
    else:
        print(text)
    if pdf:
        # A PDF that fails to render must not lose a finished run: the JSON is already written, and the
        # caller still prints the statuses and, in the validation script, what the run cost.
        try:
            pdf.write_bytes(render_memo_pdf(memo))
        except Exception as exc:
            print(f"memo PDF not written: {type(exc).__name__}: {exc}", file=sys.stderr)
        else:
            print(f"memo PDF  → {pdf} ({pdf.stat().st_size:,} bytes)", file=sys.stderr)


def rules_date_arg(text: str) -> dt.date:
    """`--rules-date`: a calendar date written YYYY-MM-DD."""
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a date written YYYY-MM-DD: {text!r}") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("address")
    parser.add_argument("description")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--json", dest="out_json", type=Path)
    parser.add_argument("--profile-json", type=Path, help="write the intake profile the rules read")
    parser.add_argument(
        "--rules-date",
        type=rules_date_arg,
        metavar="YYYY-MM-DD",
        help="apply the rules in force on this date (default: today)",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code: int = asyncio.run(
        generate(
            args.address,
            args.description,
            pdf=args.pdf,
            out_json=args.out_json,
            quiet=args.quiet,
            profile_json=args.profile_json,
            rules_date=args.rules_date,
        )
    )
    neatlogs.flush()
    neatlogs.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
