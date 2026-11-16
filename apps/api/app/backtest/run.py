"""Run the backtest: for each case, four result sets (docs/validation/backtest-plan.md §8).

  full report, end to end      the product as a user meets it: address + neutral concept text + the intake
                               answers the case file states; the intake model reads the text (the only model
                               call: the report is the rules and the evidence)
  full report, conditional     the decision record's facts and the correct pathway supplied (the zoning row set
                               from the trigger inventory): the report built from them, no model call
  rules only, end to end       no model: the hand-entered input facts (+ intake answers), the rules, the records
  rules only, conditional      no model: the record facts, the correct pathway supplied

Every case is run as of its rules date (the day before filing): the records through `AsOfStore`, the licences as
they stood that day, the tract counts recounted, the dated controls of that day, and the runner's "today" set to
that day, so no prompt says a later date. Model calls go through the Message Batches API (`BatchQueue`).

Leak guard, at run time: every request sent to the model is searched for the case's own record number, its
project number and its motion number; a request holding any of them is not sent and the case fails.

Output: backtest/results/<case>/ (memo JSON and PDF per full run, the rules-only determinations, the profile
each run read, the stage results); backtest/results/run-<label>.json (usage by case, run and stage, batches).

    cd apps/api && .venv/bin/python -m app.backtest.run --cases D01,N09 --cap 6 --label pilot
    cd apps/api && .venv/bin/python -m app.backtest.run --rules-only            # all 40, no model, no cost

Another case file (the holdout): --case-file ../../backtest/holdout/cases.yaml. Its inputs and motion numbers are
read from its own folder, and its results go to <its folder>/results unless --results-dir says otherwise, never
over the 40's results.
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import datetime as dt
import json
import logging
import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from app.backtest import asof as asof_mod
from app.backtest.asof import AsOfStore, tract_licence_data
from app.backtest.batch import CASE, RUN, STAGE, BatchQueue
from app.backtest.cases import BACKTEST, DEFAULT_CASE_FILE, Case, load_cases

log = logging.getLogger("backtest")
RESULTS = BACKTEST / "results"
JOURNAL = Path(os.environ.get("LOCAL_DATA_DIR", "~/sfhp-local")).expanduser() / "backtest/journal.jsonl"
STORE: contextvars.ContextVar[Any] = contextvars.ContextVar("backtest_store", default=None)
AS_OF: contextvars.ContextVar[dt.date | None] = contextvars.ContextVar("backtest_as_of", default=None)
DRY: contextvars.ContextVar[bool] = contextvars.ContextVar("backtest_dry", default=False)


class LeakError(RuntimeError):
    pass


# Model generations that reject a sampling temperature and a forced tool_choice (400 on every API version). With
# --intake-model naming one, the runner sends no temperature (as the product does after its first 400) and steers
# with tool_choice "auto" (settings.ANTHROPIC_FORCE_TOOL_CHOICE false, as apps/api/.env says for Opus 5.5): a
# batch request rejected for either would fail the case, where a live call is sent again.
NO_SAMPLING_MODELS = (
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-mythos-5",
    "claude-haiku-5",
)


def takes_no_sampling(model: str) -> bool:
    return model.startswith(NO_SAMPLING_MODELS)


# Dates later than the cut-off seen in what was sent to the model, by (case, run, stage). Not refused (a model
# can write a date from its own memory, and the catalogue is labelled as today's); written to leakage.json and
# reported. The dry run with a scripted model shows what the data itself sends.
LATER_DATES: dict[tuple[str, str, str], set[str]] = {}
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december")  # fmt: skip
_ISO = re.compile(r"(?<!\d)(20\d\d)-(\d\d)-(\d\d)(?!\d)")
_LONG = re.compile(r"(?i)\b(?:(\d{1,2}) (" + "|".join(MONTHS) + r") (20\d\d)|(" + "|".join(MONTHS)
                   + r") (\d{1,2}),? (20\d\d))\b")  # fmt: skip


_MONTH_YEAR = re.compile(r"(?i)\b(" + "|".join(MONTHS) + r") (20\d\d)\b")


def catalogue_as_of(text: str, as_of: dt.date) -> str:
    """The permit catalogue without the sentences that name a day or month after `as_of` ("Since August 2025
    small businesses no longer need a permit ..."): a rule change the report could not have known. Figures of a
    later fee year stay (the block is labelled as November 2026 figures)."""

    def later(sentence: str) -> bool:
        if later_dates(sentence, as_of):
            return True
        for month, year in _MONTH_YEAR.findall(sentence):
            if dt.date(int(year), MONTHS.index(month.lower()) + 1, 1) > as_of:
                return True
        return False

    out = []
    for line in text.split("\n"):
        parts = re.split(r"(?<=[.;])\s+(?=[A-Z])", line)
        out.append(" ".join(x for x in parts if not later(x)))
    return "\n".join(out)


def later_dates(text: str, as_of: dt.date) -> set[str]:
    """Every full date (2024-05-27, 27 May 2024, May 27, 2024) in `text` later than `as_of`."""
    found: set[str] = set()
    for y, m, d in _ISO.findall(text):
        try:
            if dt.date(int(y), int(m), int(d)) > as_of:
                found.add(f"{y}-{m}-{d}")
        except ValueError:
            continue
    for d1, m1, y1, m2, d2, y2 in _LONG.findall(text):
        day_, month, year = (d1, m1, y1) if d1 else (d2, m2, y2)
        try:
            when = dt.date(int(year), MONTHS.index(month.lower()) + 1, int(day_))
        except ValueError:
            continue
        if when > as_of:
            found.add(when.isoformat())
    return found


def install_store_context() -> None:
    """The data tools read `get_store()`; in the backtest that is the current case's AsOfStore."""
    from app.tools import precedent_tools

    original = getattr(precedent_tools, "get_store")  # noqa: B009 (not re-exported: set by name)

    def current() -> Any:
        s = STORE.get()
        return s if s is not None else original()

    setattr(precedent_tools, "get_store", current)  # noqa: B010


def make_runner_class() -> type:
    from app.agents.memo_runner import MemoRunner

    class BacktestRunner(MemoRunner):
        def __init__(self, *a: Any, queue: BatchQueue | None, forbidden: tuple[str, ...], **kw: Any) -> None:
            super().__init__(*a, **kw)
            if takes_no_sampling(self.model_main):
                self._temperature_accepted = False
            self.queue = queue
            self.forbidden = tuple(f for f in forbidden if f)

        @staticmethod
        def _data_as_of(bundle: Any) -> dt.date:
            """The records are as of the cut-off day (the report is made as if on it), not the day they were read.
            Read from a context variable, so it works when called through the class."""
            day = AS_OF.get()
            assert day is not None, "no cut-off day set for this case"
            return day

        def _system(
            self, stage_instructions: str, state: str | None, city_slug: str | None
        ) -> list[dict[str, Any]]:
            """The intake stage's copy of the catalogue, with its sentences naming a later day or month taken out."""
            blocks = super()._system(stage_instructions, state, city_slug)
            blocks[0] = {**blocks[0], "text": catalogue_as_of(blocks[0]["text"], self.today)}
            return blocks

        async def _execute_tools(
            self, stage: str, tool_uses: Any, by_name: Any, emit: Any
        ) -> list[dict[str, Any]]:
            """Tool results (the catalogue lookup among them) with sentences naming a later day or month taken out."""
            results = await super()._execute_tools(stage, tool_uses, by_name, emit)
            for r in results:
                if isinstance(r.get("content"), str):
                    r["content"] = catalogue_as_of(r["content"], self.today)
            return results

        async def _stream(self, params: dict[str, Any], stream: bool, emit: Any) -> Any:
            text = json.dumps(
                params, default=lambda o: o.model_dump(mode="json") if hasattr(o, "model_dump") else str(o)
            )
            hit = [f for f in self.forbidden if re.search(rf"(?<![0-9A-Za-z]){re.escape(f)}(?![0-9])", text)]
            later = later_dates(text, self.today)
            if later:
                LATER_DATES.setdefault((CASE.get(), RUN.get(), STAGE.get()), set()).update(later)
            if hit:
                raise LeakError(f"a request would carry the case's own {hit}; not sent")
            if self.queue is None:
                if DRY.get():  # the dry run: a scripted stand-in model answers (tests.memo_fakes.MemoScript)
                    return await super()._stream(params, stream, emit)
                raise RuntimeError("no model in a rules-only run")
            return await self.queue.submit(params)

        async def _run_stage(self, **kw: Any) -> Any:
            token = STAGE.set(str(kw.get("stage", "unknown")))
            try:
                return await super()._run_stage(**kw)
            finally:
                STAGE.reset(token)

        async def collect_records(self, geo: Any, profile: Any, emit: Any, *, rules_date: Any = None) -> Any:
            bundle = await super().collect_records(geo, profile, emit, rules_date=rules_date)
            ls = getattr(self.store, "licences", None)
            if ls is not None:
                line = asof_mod.unknown_status_line(ls, geo.lat, geo.lng, bundle.tract,
                                                    normalized_address=geo.normalized_address, parcel=geo.parcel)  # fmt: skip
                rows = [
                    r.model_copy(update={"basis": [*r.basis, line]}) if r.area == "alcohol" else r
                    for r in bundle.determinations.rows
                ]
                bundle.determinations = bundle.determinations.model_copy(update={"rows": rows})
            return bundle

    return BacktestRunner


# ---- the correct pathway, supplied ---------------------------------------------------------------------------


def supply_pathway(det: Any, case: Case) -> Any:
    """The rules' determinations with the zoning row set from the decision record (the conditional run).

    The rules' headline findings (app.memo.pathway rule 9) are left out: they come from the triggers the supplied
    zoning row replaces, so they could contradict it (a Conditional Use the rules found where the supplied pathway
    needs none). With none, rule 8 gives the overall status as the most severe row status and the overall line
    from the rows alone, as computed here."""
    from app.memo.pathway import ZONING_APPROVALS, entitlement_path, overall_line
    from app.models.memo import STATUS_SEVERITY, RuleLine

    want = case.expected_zoning
    status = "insufficient_information" if want == "unclear" else want
    approval = {"further_review": ZONING_APPROVALS["conditional"], "not_permitted": ZONING_APPROVALS["not_permitted"],
                "allowed": ZONING_APPROVALS["principal"], "insufficient_information": ZONING_APPROVALS["not_decided"]}[status]  # fmt: skip
    from app.memo.facts import MISSING_PHRASES

    items = case.cov["inventory"]["items"]
    families = ", ".join(i.get("label") or i["family"] for i in items)
    words = {"further_review": "a Conditional Use Authorization is required", "not_permitted": "the use is not "
             "permitted at this address", "allowed": "no Conditional Use Authorization is required",
             "insufficient_information": "whether a Conditional Use Authorization is required turns on a fact "
             "not given"}[status]  # fmt: skip
    # only the status and the triggers: never the outcome, the decision or a later date (case.expected_note
    # stays in the packet and the scoring)
    line = RuleLine(
        rule_id="backtest.supplied_pathway",
        text=f"Supplied for this run (the correct pathway under the rules in force on the rules date): {words}. "
        f"What requires it: {families or 'nothing'}.",
        code_section="Planning Code § 303" if status == "further_review" else None,
    )
    wanted = {i["trigger"] for i in items if i.get("trigger")}
    rows = []
    for r in det.rows:
        if r.area == "zoning_use":
            kept = [b for b in r.basis if b.rule_id.split(".")[0] in wanted]
            missing = [MISSING_PHRASES["formula_retail"]] if status == "insufficient_information" else []
            r = r.model_copy(update={"status": status, "approval": approval, "basis": [*kept, line],
                                     "status_note": None, "missing_inputs": missing})  # fmt: skip
        rows.append(r)
    worst = min((r.status for r in rows), key=STATUS_SEVERITY.index)
    pathway = det.pathway
    return det.model_copy(update={"pathway": pathway, "rows": rows, "overall_status": worst,
                                  "overall_line": overall_line(rows), "entitlement_path": entitlement_path(rows),
                                  "headline_findings": []})  # fmt: skip


# ---- one case ---------------------------------------------------------------------------------------------------


def _dump(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses

        return dataclasses.asdict(obj)
    return str(obj)


def write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, default=_dump, ensure_ascii=False) + "\n")


def profile_of(facts: dict[str, Any], answers: dict[str, Any] | None) -> Any:
    from app.memo.facts import profile_from_facts
    from app.memo.intake import apply_intake_answers, intake_answers

    p = profile_from_facts(facts)
    if answers:
        p = apply_intake_answers(p, intake_answers(answers))
    return p.normalized().model_copy(
        update={"city_slug": "san_francisco", "state": "CA", "city_name": "San Francisco"}
    )


def bundle_summary(bundle: Any) -> dict[str, Any]:
    """What the rules-only sheet prints beside the statuses: the site history and the counts."""
    return {
        "zoning": bundle.zoning.district if bundle.zoning else None,
        "overlays": [o.name for o in bundle.overlays],
        "tract": bundle.tract,
        "site_history": bundle.site_history,
        "density": bundle.density,
        "base_rate": bundle.base_rate,
        "applications_within_1000ft": len(bundle.applications),
        "licences_within_500ft": len(bundle.licenses_500),
        "licences_within_1000ft": len(bundle.licenses_1000),
        "businesses_within_500ft": len(bundle.businesses),
    }


async def run_case(case: Case, ctx: dict[str, Any], *, full: bool, conditional: bool) -> dict[str, Any]:
    """All the runs of one case. Returns a status line per run; files go to backtest/results/<case>/."""
    from app.agents.memo_runner import MemoRunInput
    from app.memo import tracts

    out_dir = RESULTS / case.id
    as_of = case.rules_date
    own = await ctx["base_store"].application(f"datasf_planning:{case.record}")
    motion = (own.extra.get("motion_number") if own else None) or case.motion_number
    forbidden = (case.record, asof_mod.project_of(case.record) or "", str(motion or ""))
    files = asof_mod.licence_files(str(ctx["licences_file"])) if ctx.get("licences_file") else None
    store = AsOfStore(
        ctx["base_store"], as_of, excluded_records=[case.record], licences=asof_mod.licence_set(as_of, files)
    )
    CASE.set(case.id)
    STORE.set(store)
    AS_OF.set(as_of)
    from app.memo import controls

    controls.KNOWN_ON.set(as_of)  # the dated controls as they could be known on the cut-off day
    from app.tools import precedent_tools

    precedent_tools.REPORT_DAY.set(as_of)
    asof_mod.TRACT_DATA.set(tract_licence_data(store.licences, tracts._licence_data()))
    runner_cls = ctx["runner_class"]
    status: dict[str, Any] = {"case": case.id, "as_of": as_of.isoformat()}

    def runner(queue: BatchQueue | None) -> Any:
        return runner_cls(ctx["client"], ctx["catalog"], ctx["settings"], store, ctx["geocoder"], today=as_of,
                      queue=queue, forbidden=forbidden)  # fmt: skip

    async def emit(ev: Any) -> None:
        return None

    rules = runner(None)
    geo = await rules._geocode(MemoRunInput(address=case.address, description=case.concept_input))
    write(out_dir / "leakage.json", {
        "as_of": as_of.isoformat(),
        "excluded_project": asof_mod.project_of(case.record),
        "licences_held_citywide": len(store.licences.held),
        "licences_status_unknown_citywide": len(store.licences.unknown),
        "licences_unknown_within_1000ft": sum(
            1 for f in store.licences.unknown
            if f.lat is not None and f.lng is not None and asof_mod._haversine_m(geo.lat, geo.lng, f.lat, f.lng) <= 304.8
        ),
        "licences_unknown_at_the_address": [
            f.file_number for f in asof_mod.unknown_at_address(store.licences, geo.normalized_address, geo.parcel)
        ],
        "forbidden_in_model_text": [x for x in forbidden if x],
    })  # fmt: skip

    # rules only (no model), both ways
    RUN.set("rules_only_e2e")
    p_in = profile_of(case.input_facts, case.intake_answers)
    b = await rules.collect_records(geo, p_in, emit, rules_date=as_of)
    write(
        out_dir / "rules_only_e2e.json",
        {"profile": p_in, "determinations": b.determinations, "records": bundle_summary(b)},
    )
    RUN.set("rules_only_conditional")
    p_rec = profile_of(case.record_facts, None)
    b_rec = await rules.collect_records(geo, p_rec, emit, rules_date=as_of)
    det_rec = supply_pathway(b_rec.determinations, case)
    write(out_dir / "rules_only_conditional.json",
          {"profile": p_rec, "determinations": det_rec, "rules_determinations": b_rec.determinations,
           "records": bundle_summary(b_rec)})  # fmt: skip
    # the sensitivity check (no model): the licences whose status on the day is unknown counted as active, to
    # show whether leaving them out changed an answer
    alt_store = AsOfStore(ctx["base_store"], as_of, excluded_records=[case.record],
                          licences=asof_mod.with_unknown_as_active(store.licences))  # fmt: skip
    token = STORE.set(alt_store)
    tract_token = asof_mod.TRACT_DATA.set(tract_licence_data(alt_store.licences, tracts._licence_data()))
    try:
        alt = runner_cls(ctx["client"], ctx["catalog"], ctx["settings"], alt_store, ctx["geocoder"], today=as_of,
                         queue=None, forbidden=forbidden)  # fmt: skip
        alt_e2e = await alt.collect_records(geo, p_in, emit, rules_date=as_of)
        alt_rec = await alt.collect_records(geo, p_rec, emit, rules_date=as_of)
    finally:
        STORE.reset(token)
        asof_mod.TRACT_DATA.reset(tract_token)
    write(out_dir / "sensitivity_unknown_as_active.json", {
        "assumption": "every licence whose status on the cut-off day is not in ABC's archive counted as active",
        "e2e": alt_e2e.determinations,
        "conditional": supply_pathway(alt_rec.determinations, case),
        "rules_conditional_unsupplied": alt_rec.determinations,
    })  # fmt: skip
    status["rules_only"] = "done"
    if not full:
        return status

    # full report, end to end (skipped with --conditional-only)
    RUN.set("e2e")
    if not ctx.get("conditional_only"):
        await run_e2e(case, runner(ctx["queue"]), out_dir, as_of, status, emit)
    if not conditional:
        return status
    await run_conditional(case, runner(None), out_dir, geo, p_rec, as_of, status, emit)
    return status


async def run_e2e(
    case: Case, e2e: Any, out_dir: Path, as_of: dt.date, status: dict[str, Any], emit: Any
) -> None:
    from app.agents.memo_runner import MemoRunInput
    from app.memo.intake import intake_answers
    from app.services.memo_pdf import render_memo_pdf

    inp = MemoRunInput(address=case.address, description=case.concept_input, rules_date=as_of,
                       intake_answers=intake_answers(case.intake_answers), allow_clarification=False)  # fmt: skip
    started = time.monotonic()
    final = None
    try:
        async for ev in e2e.run_memo(inp, emit):
            final = ev
    except Exception as exc:
        final = None
        status["e2e"] = f"failed: {type(exc).__name__}: {exc}"[:400]
        traceback.print_exc()
    if final is not None and final.type == "memo":
        memo = final.data["memo"]
        write(out_dir / "e2e" / "memo.json", memo)
        write(out_dir / "e2e" / "profile.json", final.data["profile"])
        try:
            (out_dir / "e2e" / "memo.pdf").write_bytes(render_memo_pdf(memo))
        except Exception as exc:  # the PDF is for the reviewer; its failure is noted, not fatal
            status["e2e_pdf"] = f"failed: {exc}"[:200]
        status["e2e"] = f"done in {(time.monotonic() - started) / 60:.1f} min"
    elif "e2e" not in status:
        status["e2e"] = f"no memo: {final.data if final is not None else 'no event'}"[:400]


async def run_conditional(case: Case, cond: Any, out_dir: Path, geo: Any, p_rec: Any, as_of: dt.date,
                          status: dict[str, Any], emit: Any) -> None:  # fmt: skip
    """The full report, conditional: the record facts and the correct pathway supplied. The report is the rules
    and the evidence for those facts: no model call."""
    from app.services.memo_pdf import render_memo_pdf

    RUN.set("conditional")
    try:
        bundle = await cond.collect_records(geo, p_rec, emit, rules_date=as_of)
        bundle.determinations = supply_pathway(bundle.determinations, case)
        memo = cond.assemble_memo(p_rec, bundle)
        write(out_dir / "conditional" / "memo.json", memo)
        write(out_dir / "conditional" / "profile.json", p_rec)
        try:
            (out_dir / "conditional" / "memo.pdf").write_bytes(render_memo_pdf(memo))
        except Exception as exc:
            status["conditional_pdf"] = f"failed: {exc}"[:200]
        status["conditional"] = "done"
    except Exception as exc:
        status["conditional"] = f"failed: {type(exc).__name__}: {exc}"[:400]
        traceback.print_exc()


async def main_async(args: argparse.Namespace) -> int:
    from anthropic import AsyncAnthropic

    from app.catalog.loader import get_catalog
    from app.core.config import get_settings
    from app.memo.context import get_geocoder, get_store

    settings = get_settings()
    url = settings.PRECEDENT_DATABASE_URL or ""
    assert "@localhost:" in url or "@127.0.0.1:" in url, "refusing: not the local database"
    install_store_context()
    cases = [c for c in load_cases(args.case_file) if not args.cases or c.id in args.cases.split(",")]
    queue = None
    client: Any = None
    if args.dry:
        # no API at all: a scripted model answers every call, so every prompt the data builds can be read and
        # searched for dates after the cut-off and for the case's own numbers
        import importlib

        fakes, memo_fakes = (
            importlib.import_module("tests.fakes"),
            importlib.import_module("tests.memo_fakes"),
        )
        client = fakes.FakeAnthropic(memo_fakes.MemoScript())
        DRY.set(True)
        assert args.results_dir, "--dry writes to --results-dir, never over the real results"
    elif not args.rules_only:
        # no SDK retry: a retried batch create could pay for the same batch twice (the queue retries its own reads)
        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=0, timeout=300.0)
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        from app.backtest.batch import journal_spend

        # the cap is a total for the whole backtest: what earlier runs paid (the journal) counts against it
        queue = BatchQueue(client, JOURNAL, cap_usd=args.cap, max_batch_usd=args.max_batch, quiet_s=args.quiet,
                           spent_before=journal_spend(JOURNAL))  # fmt: skip
        recovered = await queue.recover()
        print(f"spent before this run: ${queue.spent_before:.4f}; recovered {recovered} answers of earlier batches",
              file=sys.stderr)  # fmt: skip
    ctx = {"client": client, "catalog": get_catalog(), "settings": settings, "geocoder": get_geocoder(),
           "base_store": get_store(), "queue": queue, "runner_class": make_runner_class(),
           "conditional_only": args.conditional_only, "licences_file": args.licences_file}  # fmt: skip
    print(f"{len(cases)} cases; model main={settings.ANTHROPIC_MODEL_MAIN}; force tool_choice="
          f"{settings.ANTHROPIC_FORCE_TOOL_CHOICE}; licences {args.licences_file or asof_mod.LICENCES_FILE}; "
          f"cap ${args.cap}", file=sys.stderr)  # fmt: skip

    async def one(c: Case) -> dict[str, Any]:
        try:
            return await run_case(c, ctx, full=not args.rules_only, conditional=not args.no_conditional)
        except Exception as exc:
            traceback.print_exc()
            return {"case": c.id, "error": f"{type(exc).__name__}: {exc}"[:400]}
        finally:
            later = {f"{r}/{st}": sorted(v) for (cid, r, st), v in LATER_DATES.items() if cid == c.id}
            leak_file = RESULTS / c.id / "leakage.json"
            if leak_file.exists():
                data = json.loads(leak_file.read_text())
                data["later_dates_sent_to_the_model"] = later
                leak_file.write_text(json.dumps(data, indent=1) + "\n")

    started = time.monotonic()
    statuses = await asyncio.gather(
        *(asyncio.create_task(one(c), context=contextvars.copy_context()) for c in cases)
    )
    summary = {
        "label": args.label,
        "cases": statuses,
        "minutes": round((time.monotonic() - started) / 60, 1),
    }
    if queue is not None:
        summary |= {
            "cost_usd": round(queue.ledger.total, 4),
            "replayed_from_journal": queue.replayed,
            "stopped": queue.stopped,
            "batches": queue.ledger.batches,
            "by_case_run_stage": [
                {"case": k[0], "run": k[1], "stage": k[2], **v} for k, v in sorted(queue.ledger.by.items())
            ],
        }
    write(RESULTS / f"run-{args.label}.json", summary)
    for s in statuses:
        print(json.dumps(s), file=sys.stderr)
    if queue is not None:
        print(
            f"cost ${queue.ledger.total:.4f} in {len(queue.ledger.batches)} batches; stopped: {queue.stopped}",
            file=sys.stderr,
        )
    return 0


def main() -> int:
    local = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres@localhost:55433/sfhp_local")
    assert "@localhost:" in local or "@127.0.0.1:" in local, (
        "refusing: the backtest only reads the local database"
    )
    os.environ["PRECEDENT_DATABASE_URL"] = local  # before the settings are first read
    os.environ["NEATLOGS_API_KEY"] = ""
    p = argparse.ArgumentParser()
    p.add_argument("--cases", help="comma-separated case ids (default: every case of the case file)")
    p.add_argument("--case-file", type=Path, default=None,
                   help="the cases to run (default backtest/cases.yaml, the 40); e.g. backtest/holdout/cases.yaml")  # fmt: skip
    p.add_argument("--rules-only", action="store_true", help="no model: the two rules-only runs only")
    p.add_argument("--no-conditional", action="store_true", help="skip the full report's conditional run")
    p.add_argument("--conditional-only", action="store_true", help="only the full report's conditional run")
    p.add_argument("--cap", type=float, default=0.0, help="the most this run may spend, in dollars")
    p.add_argument("--max-batch", type=float, default=20.0, help="the most one batch may cost (estimate)")
    p.add_argument(
        "--quiet", type=float, default=20.0, help="seconds without a new call before a batch is sent"
    )
    p.add_argument("--label", default="run")
    p.add_argument("--dry", action="store_true", help="no API: a scripted model answers; prompts are scanned")
    p.add_argument("--results-dir", help="write results here instead of backtest/results")
    p.add_argument("--journal", help="journal file (default $LOCAL_DATA_DIR/backtest/journal.jsonl); a separate "
                   "one re-runs a failed case fresh instead of replaying its answers")  # fmt: skip
    p.add_argument("--intake-model", help="the intake model (default settings.ANTHROPIC_MODEL_MAIN); a model that "
                   "takes no temperature or forced tool_choice gets neither")  # fmt: skip
    p.add_argument("--licences-file", type=Path, default=None,
                   help="the as-of licence file to read instead of $LOCAL_DATA_DIR/backtest/licences_asof.json "
                   "(same format; e.g. a subset of it): the licences, the at-address check and the tract counts "
                   "are all built from it")  # fmt: skip
    args = p.parse_args()
    if args.intake_model:  # before the settings are first read
        os.environ["ANTHROPIC_MODEL_MAIN"] = args.intake_model
        if takes_no_sampling(args.intake_model):
            os.environ["ANTHROPIC_FORCE_TOOL_CHOICE"] = "false"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", stream=sys.stderr)
    for noisy in ("httpx", "anthropic", "app.agents", "neatlogs", "psycopg"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("app.backtest.batch").setLevel(logging.INFO)
    global RESULTS, JOURNAL
    if args.journal:
        JOURNAL = Path(args.journal).expanduser()
    if args.results_dir:
        RESULTS = Path(args.results_dir)
    elif args.case_file is not None and args.case_file.resolve() != DEFAULT_CASE_FILE:
        # another case file never writes into the 40's results
        RESULTS = args.case_file.resolve().parent / "results"
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
