"""scripts/validation/review_hospitality_batch.py, the Haiku + Opus review of the 2010-2018 motions, against a fake
Batches API: no network, no API key, no database."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import re
import shutil
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "validation" / "review_hospitality_batch.py"
REVIEWED = REPO / "tools" / "conditions-search" / "reviewed-labels.json"

LEDGER = """# Claude API spend ledger

## Caps for the current cycle

| Bucket | Cap | Spent | Left |
|---|---|---|---|
| Validation work | $130.00 | about $105.32 | about $24.68 |

## Ledger

| Date | What ran | Model | API | Input tokens | Output tokens | Cost | Running total |
|---|---|---|---|---|---|---|---|
| 2026-11-12 | Holdout run | claude-sonnet-4-5-20250929 | Message Batches | see journal | | $0.3883 | about $105.32 |

Notes:
- a note that must stay after the table.
"""


# what extractor_check returns once `full_conditions.py reparse` has run: every stored motion matches
FRESH = {"checked": 4, "same": 4, "stale": [], "no_pdf": []}


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validation_review_hospitality_batch", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def rv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = load_module()
    monkeypatch.setattr(module, "REVIEW_DIR", tmp_path / "review")
    spend = tmp_path / "spend.md"
    spend.write_text(LEDGER)
    monkeypatch.setattr(module, "SPEND", spend)
    reviewed = tmp_path / "reviewed-labels.json"
    shutil.copy(REVIEWED, reviewed)
    monkeypatch.setattr(module, "REVIEWED", reviewed)

    def no_client() -> Any:
        raise AssertionError("tests must not build a real client or read an API key")

    monkeypatch.setattr(module, "make_client", no_client)

    def no_database(*a: Any, **kw: Any) -> Any:
        raise AssertionError("tests must not read the database")

    monkeypatch.setattr(module, "query", no_database)
    monkeypatch.setattr(module, "extractor_check", lambda: dict(FRESH))
    return module


def motion(record: str, decided: str, use_class: str | None, text: str, titles: list[str]) -> dict:
    return {"id": f"datasf_planning:{record}", "record": record, "decided_at": decided, "doc_outcome": "approved",
            "address": "100 MAIN ST 94110", "description": "Conditional Use for a new business.",
            "premises": True, "use_class": use_class, "titles": titles, "_text": text}  # fmt: skip


MOTIONS = [
    motion("2012.0638C", "2013-03-14", "restaurant_or_cafe",
           "The project would establish a Full-Service Restaurant with beer and wine.", ["Validity", "Hours"]),
    motion("2014.0123C", "2014-06-05", "other_food_drink",
           "The project would establish a General Grocery use (Mission Market) with off-sale beer and wine.",
           ["Validity", "Condition", "Condition"]),
    motion("2016-001111CUA", "2016-09-01", "none",
           "The project would establish a Bar use (dba The Tap) with an outdoor activity area.", ["Validity"]),
    motion("2017-002222CUA", "2017-02-02", "restaurant_or_cafe",
           "The project would establish a Place of Entertainment within an existing restaurant.", ["Noise"]),
]  # fmt: skip


def inputs(rv: ModuleType) -> list[dict]:
    texts = {m["record"]: m["_text"] for m in MOTIONS}
    return [rv.motion_input(m, read=lambda r: (texts[r], "PDF text layer")) for m in MOTIONS]


def args(**kw: Any) -> SimpleNamespace:
    base = {"cap": 5.0, "disagree_rate": 0.25, "allow_partial": False, "all": False, "partial": False,
            "dry_run": False}  # fmt: skip
    return SimpleNamespace(**{**base, **kw})


def answer(decision: str, business: str = "none", quote: str = "", agrees_with: str | None = None) -> str:
    a = {"what": "a business", "decision": decision, "business": business, "reason": "Because of the rules.",
         "quote": quote, "confidence": "high"}  # fmt: skip
    if agrees_with:
        a["agrees_with"] = agrees_with
    return json.dumps(a)


def message(text: str | None, stop: str = "end_turn") -> SimpleNamespace:
    content = [SimpleNamespace(type="thinking", thinking="")]
    if text is not None:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        stop_reason=stop,
        content=content,
        usage=SimpleNamespace(
            input_tokens=1000,
            output_tokens=200,
            cache_creation_input_tokens=100,
            cache_read_input_tokens=2000,
        ),
    )


class LostResponseError(Exception):
    """A create call whose response never arrived (a timeout or a dropped connection)."""


class FakeBatches:
    """The Batches API: `replies` maps a custom_id to a message (or None for an errored request). `fail` makes the
    next create raise: "after" once the batch exists on the server (the response is lost), "before" without
    creating it."""

    def __init__(self) -> None:
        self.created: list[list[dict]] = []
        self.batches: list[Any] = []  # every batch on the account, oldest first
        self.replies: dict[str, Any] = {}
        self.status = "ended"
        self.fail: str | None = None
        self.calls = 0

    def create(self, *, requests: list[dict]) -> Any:
        self.calls += 1
        fail, self.fail = self.fail, None
        if fail == "before":
            raise LostResponseError("connection reset before the request was sent")
        self.created.append(requests)
        batch = SimpleNamespace(id=f"msgbatch_test{len(self.created)}", processing_status="in_progress",
                                created_at=dt.datetime.now(dt.UTC),
                                request_counts=SimpleNamespace(processing=len(requests), succeeded=0, errored=0,
                                                               canceled=0, expired=0))  # fmt: skip
        self.batches.append(batch)
        if fail == "after":
            raise LostResponseError("read timed out")
        return batch

    def list(self, *, limit: int = 20) -> Any:
        return iter(reversed(self.batches))  # newest first

    def retrieve(self, batch_id: str) -> Any:
        return SimpleNamespace(id=batch_id, processing_status=self.status, request_counts={"processing": 0})

    def results(self, batch_id: str) -> Any:
        reqs = self.created[int(batch_id.removeprefix("msgbatch_test")) - 1]
        for r in reqs:
            reply = self.replies.get(r["custom_id"])
            if reply is None:
                yield SimpleNamespace(custom_id=r["custom_id"], result=SimpleNamespace(type="errored"))
            else:
                yield SimpleNamespace(
                    custom_id=r["custom_id"], result=SimpleNamespace(type="succeeded", message=reply)
                )


def fake_client() -> Any:
    return SimpleNamespace(messages=SimpleNamespace(batches=FakeBatches()))


class RetryingClient:
    """A client with with_options(), recording the max_retries the create call was made with."""

    def __init__(self) -> None:
        self.messages = SimpleNamespace(batches=FakeBatches())
        self.options: list[dict] = []

    def with_options(self, **kw: Any) -> Any:
        self.options.append(kw)
        return self


PROGRESS_DONE = {"cases": 307, "looked_up": 307, "found": 280}


# ---- requests --------------------------------------------------------------------------------------------------


def test_stage1_requests_two_haiku_passes_with_cached_rules_and_schema(rv: ModuleType) -> None:
    reqs = rv.stage1_requests(inputs(rv))
    assert [r["custom_id"] for r in reqs[:4]] == ["r0", "c0", "r1", "c1"]
    assert all(re.match(r"^[a-zA-Z0-9_-]{1,64}$", r["custom_id"]) for r in reqs)
    for r in reqs:
        p = r["params"]
        assert p["model"] == "claude-haiku-5-5"
        assert p["output_config"]["format"]["type"] == "json_schema"
        assert p["output_config"]["format"]["schema"]["properties"]["business"]["enum"] == [
            "Restaurant or cafe",
            "Bar",
            "Nighttime entertainment",
            "Other food and drink",
            "none",
        ]
        rules, _role = p["system"]
        assert rules["text"] == rv.RULES and rules["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
        # thinking off (Haiku 5.5 accepts it at effort low to high), a small answer, no sampling parameters
        assert p["thinking"] == {"type": "disabled"} and p["output_config"]["effort"] == "low"
        assert p["max_tokens"] == 1000 and "temperature" not in p
    reader, checker = reqs[0]["params"], reqs[1]["params"]
    assert reader["system"][1]["text"] == rv.READER and checker["system"][1]["text"] == rv.CHECKER
    assert reader["messages"] == checker["messages"]  # the same motion, worded differently only in the role
    user = reader["messages"][0]["content"]
    for part in (
        "2012.0638C",
        "2013-03-14",
        "kept, as Restaurant or cafe",
        "Full-Service Restaurant",
        "Validity",
    ):
        assert part in user
    # untitled conditions ("Condition") are counted, not listed
    assert "plus 2 conditions without a title" in rv.render_motion(inputs(rv)[1])


def test_estimate_makes_no_call_and_prints_costs(rv: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        rv.cmd_estimate(args(), inputs=inputs(rv), progress={"cases": 307, "looked_up": 100, "found": 90})
        == 0
    )
    out = capsys.readouterr().out
    assert "stage 1, reader + checker (claude-haiku-5-5, Message Batches): 8 requests" in out
    assert "claude-opus-5-5" in out and "No API call made" in out and "projected for all 307 cases" in out
    assert "worst case $" in out and "expected $" in out
    e = rv.estimate(rv.stage1_requests(inputs(rv)))
    assert 0 < e["expected"] < e["worst"] < 0.05


def test_cost_from_usage_at_batch_prices(rv: ModuleType) -> None:
    u = {"input": 1_000_000, "output": 1_000_000, "cache_write": 1_000_000, "cache_read": 1_000_000}
    assert rv.usage_cost("claude-haiku-5-5", u) == pytest.approx(0.5 * (0.10 + 0.50 + 0.20 + 0.01))
    assert rv.usage_cost("claude-opus-5-5", u) == pytest.approx(0.5 * (4.00 + 20.00 + 8.00 + 0.20))


# ---- submit, cap, ledger -----------------------------------------------------------------------------------------


def test_submit_refuses_over_cap_without_calling(rv: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    client = fake_client()
    assert rv.cmd_submit(args(cap=0.0001), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 2
    assert client.messages.batches.created == []
    assert "over the cap" in capsys.readouterr().out
    assert not rv.state_path().exists()


def test_submit_refuses_while_lookup_runs(rv: ModuleType) -> None:
    client = fake_client()
    progress = {"cases": 307, "looked_up": 120, "found": 110}
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=progress) == 2
    assert client.messages.batches.created == []
    assert rv.cmd_submit(args(allow_partial=True), client=client, inputs=inputs(rv), progress=progress) == 0
    assert len(client.messages.batches.created) == 1


def test_ledger_row_goes_after_the_last_row_with_running_total(rv: ModuleType) -> None:
    rv.ledger_row("test run", "claude-haiku-5-5", "Message Batches", "1", "2", "$0.1234", 0.1234)
    text = rv.SPEND.read_text()
    lines = text.splitlines()
    i = next(n for n, line in enumerate(lines) if "| test run |" in line)
    assert lines[i - 1].startswith("| 2026-11-12 | Holdout run")
    assert lines[i].endswith("| $0.1234 | about $105.44 |")
    assert text.rstrip().endswith("a note that must stay after the table.")


# ---- the whole flow ------------------------------------------------------------------------------------------------


def test_full_flow_agree_disagree_failed_then_opus(
    rv: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    client = fake_client()
    b = client.messages.batches
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 0
    assert len(b.created[0]) == 8
    assert "stage 1 submitted" in rv.SPEND.read_text()
    # 0: both include the restaurant; 1: both exclude the grocery; 2: reader include Bar, checker exclude;
    # 3: reader include Nighttime entertainment, checker's request failed
    b.replies = {
        "r0": message(answer("include", "Restaurant or cafe", "establish a Full-Service Restaurant")),
        "c0": message(answer("include", "Restaurant or cafe", "Full-Service Restaurant with beer and wine")),
        "r1": message(answer("exclude", "Other food and drink", "General Grocery use")),  # business ignored
        "c1": message(answer("exclude", "none", "a General Grocery use (Mission Market)")),
        "r2": message(answer("include", "Bar", "establish a Bar use")),
        "c2": message(answer("exclude", "none", "an outdoor activity area")),
        "r3": message(answer("include", "Nighttime entertainment", "a Place of Entertainment")),
        "c3": None,
    }
    assert rv.cmd_submit(args(), client=client) == 3  # stage 1 not collected yet
    assert rv.cmd_collect(args(), client=client) == 1  # one request failed
    state = json.loads(rv.state_path().read_text())
    assert state["stages"]["haiku"]["collected"] and state["stages"]["haiku"]["usage"]["input"] == 7000
    rows = {r["record"]: r for r in json.loads(rv.decisions_path().read_text())["decisions"]}
    assert rows["2012.0638C"]["status"] == "final" and rows["2012.0638C"]["change"] == "none"
    assert rows["2014.0123C"]["decision"] == "exclude" and rows["2014.0123C"]["change"] == "remove"
    assert rows["2014.0123C"]["business"] is None and rows["2014.0123C"]["quote_found"]
    assert rows["2016-001111CUA"]["status"] == "pending" and rows["2017-002222CUA"]["status"] == "pending"
    ledger = rv.SPEND.read_text()
    assert "stage 1 (reader + checker) collected: 7 answers, 1 failed" in ledger
    assert "7,000 + 700 cache write + 14,000 cache read" in ledger

    # apply refuses while the Opus check is pending
    assert rv.cmd_apply(args()) == 2

    # stage 2: Opus only on the two unresolved motions, with both answers in the prompt
    assert rv.cmd_submit(args(), client=client) == 0
    opus = b.created[1]
    assert [r["custom_id"] for r in opus] == ["o2", "o3"]
    p = opus[0]["params"]
    assert p["model"] == "claude-opus-5-5" and p["system"][1]["text"] == rv.OPUS_ROLE
    assert "agrees_with" in p["output_config"]["format"]["schema"]["required"]
    assert (
        "READER's answer: {" in p["messages"][0]["content"]
        and '"decision": "exclude"' in p["messages"][0]["content"]
    )
    assert "CHECKER's answer: (no answer" in opus[1]["params"]["messages"][0]["content"]
    b.replies = {
        "o2": message(answer("include", "Bar", "establish a Bar use (dba The Tap)", agrees_with="reader")),
        "o3": message(answer("include", "Nighttime entertainment", "a Place of Entertainment",
                             agrees_with="reader")),
    }  # fmt: skip
    assert rv.cmd_collect(args(), client=client) == 0
    rows = {r["record"]: r for r in json.loads(rv.decisions_path().read_text())["decisions"]}
    assert all(r["status"] == "final" for r in rows.values())
    assert rows["2016-001111CUA"]["change"] == "add back" and rows["2016-001111CUA"]["business"] == "Bar"
    assert "claude-opus-5-5 decided, agreeing with the reader" in rows["2016-001111CUA"]["agreement"]
    assert rows["2017-002222CUA"]["change"] == "business type"
    assert "stage 2 (Opus on the disagreements) collected: 2 answers" in rv.SPEND.read_text()
    assert rv.cmd_submit(args(), client=client) == 0  # complete: nothing more to submit
    assert len(b.created) == 2

    # apply: only the changes, in the file's exact format, then validated by the build's own loader
    before = json.loads(rv.REVIEWED.read_text())
    assert rv.cmd_apply(args(dry_run=True)) == 0
    assert json.loads(rv.REVIEWED.read_text()) == before
    assert rv.cmd_apply(args()) == 0
    text = rv.REVIEWED.read_text()
    after = json.loads(text)
    assert text == json.dumps(after, indent=1, ensure_ascii=False) + "\n"
    added = after["decisions"][len(before["decisions"]) :]
    assert [d["record"] for d in added] == ["2014.0123C", "2016-001111CUA", "2017-002222CUA"]
    assert list(added[0]) == ["record", "address", "decision", "business", "what", "reason", "review"]
    assert added[0]["decision"] == "exclude" and added[0]["business"] is None
    assert added[0]["review"] == "reader and checker agreed"
    assert (
        added[0]["reason"] == 'Because of the rules. (Motion: "General Grocery use")'
    )  # the reader's words when both agree
    assert added[1]["business"] == "Bar" and "disagreed" in added[1]["review"]
    assert after["_doc"] == before["_doc"] and after["reviewed_on"] == before["reviewed_on"]
    # a second apply adds nothing (every record is already listed)
    assert rv.cmd_apply(args(all=True)) == 0
    assert (
        len(json.loads(rv.REVIEWED.read_text())["decisions"]) == len(after["decisions"]) + 1
    )  # only 2012.0638C


def test_apply_skips_motions_outside_2010_2018(rv: ModuleType) -> None:
    rv.write_json(rv.decisions_path(), {"decisions": [
        {"record": "2019-000001CUA", "address": "1 A St", "decided_at": "2019-02-01", "status": "final",
         "decision": "exclude", "business": None, "what": "x", "reason": "y", "quote": "", "quote_found": True,
         "change": "remove", "agreement": "reader and checker agreed"},
        {"record": "2009.0001C", "address": "1 A St", "decided_at": "2009-12-31", "status": "final",
         "decision": "exclude", "business": None, "what": "x", "reason": "y", "quote": "", "quote_found": True,
         "change": "remove", "agreement": "reader and checker agreed"},
    ]})  # fmt: skip
    before = rv.REVIEWED.read_text()
    assert rv.cmd_apply(args()) == 0
    assert rv.REVIEWED.read_text() == before


# ---- answers ---------------------------------------------------------------------------------------------------


def test_parse_answer_rejects_refusals_cutoffs_and_bad_json(rv: ModuleType) -> None:
    assert rv.parse_answer(message(answer("include", "Bar"), stop="refusal")) is None
    assert rv.parse_answer(message(answer("include", "Bar"), stop="max_tokens")) is None
    assert rv.parse_answer(message("not json")) is None
    assert rv.parse_answer(message(None)) is None
    assert rv.parse_answer(message(json.dumps({"decision": "include"}))) is None
    assert rv.parse_answer(message(answer("include", "Cafe"))) is None  # not one of the page's types
    assert (
        rv.parse_answer(message(answer("include", "Bar")), opus=True) is None
    )  # Opus must say whom it agrees with
    assert rv.parse_answer(message(answer("exclude", "Bar")))["business"] == "none"


def test_disagreement_on_business_type_goes_to_opus(rv: ModuleType) -> None:
    inc = {"decision": "include", "business": "Bar"}
    assert rv.same(inc, {"decision": "include", "business": "Bar"})
    assert not rv.same(inc, {"decision": "include", "business": "Restaurant or cafe"})
    assert rv.same({"decision": "exclude", "business": "none"}, {"decision": "exclude", "business": "Bar"})
    assert not rv.same(inc, None)


# ---- the hard cap: worst case, cumulative, metered ------------------------------------------------------------


def test_opus_requests_low_effort_room_for_thinking_thinking_not_disabled(rv: ModuleType) -> None:
    r = rv.request("o0", rv.OPUS, rv.OPUS_ROLE, "motion", rv.OPUS_SCHEMA)["params"]
    # Opus 5.5 rejects thinking disabled at every effort: omitted (adaptive) at low effort; its thinking counts
    # toward max_tokens, so the limit leaves room for thinking as well as the ~300-token answer
    assert "thinking" not in r and r["output_config"]["effort"] == "low" and r["max_tokens"] == 8000


def test_worst_case_prices_max_tokens_bytes_and_cache_write_on_every_request(rv: ModuleType) -> None:
    reqs = rv.stage1_requests(inputs(rv))
    r = reqs[0]
    p = r["params"]
    system = "".join(b["text"] for b in p["system"]).encode()
    schema = json.dumps(p["output_config"]["format"]["schema"]).encode()
    user = p["messages"][0]["content"].encode()
    sys_t = len(system) + len(schema) + rv.FORMAT_OVERHEAD_TOKENS
    want = 0.5 * (sys_t * 0.20 + len(user) * 0.10 + 1000 * 0.50) / 1e6  # Haiku: cache write 2x, output at max
    assert rv.worst_request(r)["cost"] == pytest.approx(want)
    # every request pays the cache write in the worst case: the total is the plain sum, no cache-read discount
    e = rv.estimate(reqs)
    assert e["worst"] == pytest.approx(sum(rv.worst_request(q)["cost"] for q in reqs))
    assert e["worst_output"] == 1000 * len(reqs)
    # the worst case follows max_tokens, not a guess
    rv.HAIKU_MAX_TOKENS = 2000
    assert rv.estimate(rv.stage1_requests(inputs(rv)))["worst"] == pytest.approx(
        e["worst"] + len(reqs) * 0.5 * 1000 * 0.50 / 1e6
    )
    # an Opus request at its prices
    o = rv.request("o0", rv.OPUS, rv.OPUS_ROLE, "é" * 10, rv.OPUS_SCHEMA)
    w = rv.worst_request(o)
    assert w["input"] == 20  # bytes, not characters
    assert w["output"] == 8000  # priced at the full max_tokens, thinking included
    assert w["cost"] == pytest.approx(0.5 * (w["system"] * 8.00 + 20 * 4.00 + 8000 * 20.00) / 1e6)


def test_submit_refuses_when_worst_case_is_over_the_cap_even_if_expected_fits(
    rv: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    e = rv.estimate(rv.stage1_requests(inputs(rv)))
    cap = (e["expected"] + e["worst"]) / 2
    client = fake_client()
    assert rv.cmd_submit(args(cap=cap), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 2
    assert client.messages.batches.created == [] and "worst case" in capsys.readouterr().out
    assert rv.cmd_submit(args(cap=e["worst"] * 1.0001), client=client, inputs=inputs(rv),
                         progress=PROGRESS_DONE) == 0  # fmt: skip
    state = json.loads(rv.state_path().read_text())
    assert state["stages"]["haiku"]["worst"] == pytest.approx(e["worst"], abs=1e-4)


def stage1_collected(rv: ModuleType, client: Any) -> None:
    b = client.messages.batches
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 0
    b.replies = {
        "r0": message(answer("include", "Restaurant or cafe")), "c0": message(answer("include", "Restaurant or cafe")),
        "r1": message(answer("exclude")), "c1": message(answer("exclude")),
        "r2": message(answer("include", "Bar")), "c2": message(answer("exclude")),
        "r3": message(answer("include", "Bar")), "c3": message(answer("exclude")),
    }  # fmt: skip
    assert rv.cmd_collect(args(), client=client) == 0


def test_collect_records_metered_spend_and_stage2_cap_is_cumulative(
    rv: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    client = fake_client()
    stage1_collected(rv, client)
    state = json.loads(rv.state_path().read_text())
    haiku = state["stages"]["haiku"]
    u = {
        "input": 8000,
        "output": 1600,
        "cache_write": 800,
        "cache_read": 16000,
    }  # 8 messages of the fake usage
    assert haiku["usage"] == u and haiku["cost"] == pytest.approx(rv.usage_cost(rv.HAIKU, u), abs=1e-4)
    assert state["spent"] == haiku["cost"] and rv.committed(state) == haiku["cost"]
    # stage 2: what stage 1 cost plus Opus's worst case must fit
    inp = json.loads(rv.inputs_path().read_text())
    answers = json.loads(rv.answers_path().read_text())
    e2 = rv.estimate(rv.stage2_requests(inp, answers, ["2016-001111CUA", "2017-002222CUA"]))
    assert rv.cmd_submit(args(cap=e2["worst"]), client=client) == 2  # fits alone, not with stage 1's spend
    assert len(client.messages.batches.created) == 1 and "over the cap" in capsys.readouterr().out
    assert rv.cmd_submit(args(cap=haiku["cost"] + e2["worst"] + 1e-6), client=client) == 0
    state = json.loads(rv.state_path().read_text())
    assert state["stages"]["opus"]["worst"] == pytest.approx(e2["worst"], abs=1e-4)
    # while stage 2 is out, the job counts it at its worst case
    assert rv.committed(state) == pytest.approx(haiku["cost"] + state["stages"]["opus"]["worst"])


def test_max_tokens_cut_offs_are_counted(rv: ModuleType) -> None:
    client = fake_client()
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 0
    client.messages.batches.replies = {"r0": message(answer("include", "Bar"), stop="max_tokens")}
    rv.cmd_collect(args(), client=client)
    assert json.loads(rv.state_path().read_text())["stages"]["haiku"]["cut_off"] == 1


# ---- include needs a business type ----------------------------------------------------------------------------


def test_include_with_business_none_is_no_answer_and_goes_to_opus(rv: ModuleType) -> None:
    assert rv.parse_answer(message(answer("include", "none"))) is None
    assert rv.parse_answer(message(answer("include", "none", agrees_with="reader")), opus=True) is None
    assert (
        rv.parse_answer(message(answer("include", "Bar", agrees_with="reader")), opus=True)["business"]
        == "Bar"
    )
    assert not rv.same(
        {"decision": "include", "business": "none"}, {"decision": "include", "business": "none"}
    )
    client = fake_client()
    b = client.messages.batches
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 0
    b.replies = {cid: message(answer("include", "none")) for cid in ("r0", "c0")}
    b.replies.update({cid: message(answer("exclude")) for cid in ("r1", "c1", "r2", "c2", "r3", "c3")})
    rv.cmd_collect(args(), client=client)
    rows = {r["record"]: r for r in json.loads(rv.decisions_path().read_text())["decisions"]}
    assert rows["2012.0638C"]["status"] == "pending"  # two include+none answers are not an agreement
    assert rv.cmd_submit(args(), client=client) == 0
    assert [r["custom_id"] for r in b.created[1]] == ["o0"]
    b.replies = {"o0": message(answer("include", "none", agrees_with="neither"))}
    rv.cmd_collect(args(), client=client)
    rows = {r["record"]: r for r in json.loads(rv.decisions_path().read_text())["decisions"]}
    assert rows["2012.0638C"]["status"] == "unresolved"  # Opus must name a type to include


# ---- the prompt follows REVIEWED.md -----------------------------------------------------------------------------


def test_museum_exception_matches_reviewed_md(rv: ModuleType) -> None:
    rules = re.sub(r"\s+", " ", rv.RULES)
    assert "early evening" not in rules
    assert "serves no food or drink and its hours end at 9:30 pm at the latest" in rules
    reviewed_md = re.sub(r"\s+", " ", (REPO / "tools" / "conditions-search" / "REVIEWED.md").read_text())
    assert "serves no food or drink, its hours end at 9:30 pm at the latest" in reviewed_md


# ---- cached motion text is keyed on the reading code ------------------------------------------------------------


def test_cached_text_is_keyed_on_the_extractor(
    rv: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from precedent import pdftext
    from precedent.sources import sf_planning_hearings as hearings

    pdf = tmp_path / "2012.0638C.pdf"
    pdf.write_bytes(b"%PDF fake")
    monkeypatch.setattr(rv.bci, "pdf_for", lambda record: pdf)
    calls: list[int] = []
    body = "Full-Service Restaurant with beer and wine. " * 60  # enough letters: no OCR

    def fake_read(data: bytes, **kw: Any) -> Any:
        calls.append(1)
        return SimpleNamespace(text=body, pages=3)

    monkeypatch.setattr(pdftext, "read_pdf", fake_read)
    monkeypatch.setattr(pdftext, "strip_running_headers", lambda t: t)
    monkeypatch.setattr(hearings, "motion_body", lambda t: t)
    st = pdf.stat()
    old = rv.REVIEW_DIR / "text" / f"2012.0638C-{st.st_size}-{int(st.st_mtime)}.json"  # the old key
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps({"text": "STALE TEXT FROM THE OLD EXTRACTOR", "source": "PDF text layer"}))

    text, _ = rv.motion_text("2012.0638C")
    assert "STALE" not in text and text.startswith("Full-Service") and len(calls) == 1
    assert rv.motion_text("2012.0638C")[0] == text and len(calls) == 1  # cached under the new key
    # a change to an extractor source file is a new key: read again
    src = tmp_path / "pdftext.py"
    src.write_text("# changed extractor\n")
    monkeypatch.setattr(rv, "EXTRACTOR_SOURCES", (src,))
    rv.motion_text("2012.0638C")
    assert len(calls) == 2
    # so is a bump of TEXT_VERSION
    key = rv.text_key()
    monkeypatch.setattr(rv, "TEXT_VERSION", rv.TEXT_VERSION + 1)
    assert rv.text_key() != key
    rv.motion_text("2012.0638C")
    assert len(calls) == 3


# ---- a batch is created at most once -----------------------------------------------------------------------------


def test_create_is_made_without_retries(rv: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[dict] = []
    client = RetryingClient()

    def make(**kw: Any) -> Any:
        built.append(kw)
        return client

    monkeypatch.setattr(rv, "make_client", make)
    assert rv.cmd_submit(args(), inputs=inputs(rv), progress=PROGRESS_DONE) == 0
    assert built == [{"max_retries": 0}]  # the client submit builds
    assert client.options == [{"max_retries": 0}]  # and the create call itself, also on a client passed in
    assert len(client.messages.batches.created) == 1


def test_lost_response_is_found_by_list_and_not_submitted_twice(
    rv: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    client = fake_client()
    b = client.messages.batches
    b.fail = "after"  # the batch is created on the server, the response is lost
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 4
    assert len(b.created) == 1 and "run submit again" in capsys.readouterr().out
    state = json.loads(rv.state_path().read_text())
    attempt = state["stages"]["haiku"]["attempt"]
    assert "batch_id" not in state["stages"]["haiku"] and attempt["requests"] == 8
    assert "stage 1 submitted" not in rv.SPEND.read_text()  # no ledger row for a batch not yet known
    # while the batch id is unknown, poll and collect say so, and the stage counts at its worst case
    assert rv.cmd_poll(args(), client=client) == 3 and rv.cmd_collect(args(), client=client) == 3
    assert rv.committed(state) == pytest.approx(state["stages"]["haiku"]["worst"])
    # the next submit finds the batch (ended by now: its custom_ids are checked too) and records it
    b.batches[0].processing_status = "ended"
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 0
    assert len(b.created) == 1 and b.calls == 1
    assert "found batch msgbatch_test1" in capsys.readouterr().out
    state = json.loads(rv.state_path().read_text())
    assert state["stages"]["haiku"]["batch_id"] == "msgbatch_test1" and state["stages"]["haiku"]["recovered"]
    assert "stage 1 submitted" in rv.SPEND.read_text() and "batch msgbatch_test1" in rv.SPEND.read_text()
    # and from there the flow goes on as usual
    assert rv.cmd_submit(args(), client=client) == 3  # not collected yet
    assert len(b.created) == 1


def test_create_that_never_reached_the_server_is_submitted_again_after_a_wait(
    rv: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    client = fake_client()
    b = client.messages.batches
    b.fail = "before"
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 4
    assert b.created == []
    # at once: refused, so a batch still being created is not missed
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 3
    assert b.created == [] and "run submit again in 2 minutes" in capsys.readouterr().out
    state = json.loads(rv.state_path().read_text())
    started = dt.datetime.fromisoformat(state["stages"]["haiku"]["attempt"]["started_at"])
    state["stages"]["haiku"]["attempt"]["started_at"] = (started - dt.timedelta(minutes=5)).isoformat()
    rv.write_json(rv.state_path(), state)
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 0
    assert len(b.created) == 1 and "no batch of it exists" in capsys.readouterr().out
    assert json.loads(rv.state_path().read_text())["stages"]["haiku"]["batch_id"] == "msgbatch_test1"


def test_list_matches_only_this_jobs_batch(rv: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    client = fake_client()
    b = client.messages.batches
    now = dt.datetime.now(dt.UTC)

    def other(bid: str, n: int, created: dt.datetime, status: str = "in_progress") -> Any:
        return SimpleNamespace(id=bid, processing_status=status, created_at=created,
                               request_counts={"processing": 0, "succeeded": n, "errored": 0, "canceled": 0,
                                               "expired": 0})  # fmt: skip

    b.batches = [other("msgbatch_old", 8, now - dt.timedelta(days=1))]  # before the attempt: not ours
    b.fail = "after"
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 4
    b.batches.append(other("msgbatch_size", 3, now))  # another job's batch, another size
    b.batches.append(other("msgbatch_ended", 8, now, "ended"))  # same size, ended, other custom_ids
    b.created.append([{"custom_id": f"x{i}"} for i in range(8)])  # its results (index 2 in the fake)
    b.batches[-1].id = "msgbatch_test2"
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 0
    assert json.loads(rv.state_path().read_text())["stages"]["haiku"]["batch_id"] == "msgbatch_test1"
    assert b.calls == 1


def test_several_matching_batches_need_adopt(rv: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    client = fake_client()
    b = client.messages.batches
    b.fail = "after"
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 4
    twin = SimpleNamespace(
        **{**vars(b.batches[0]), "id": "msgbatch_twin"}
    )  # e.g. a submit from a copy of the job
    b.batches.append(twin)
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 2
    assert "--adopt" in capsys.readouterr().out and b.calls == 1
    assert rv.cmd_submit(args(adopt="msgbatch_nope"), client=client) == 2
    assert "is not one of them" in capsys.readouterr().out
    assert rv.cmd_submit(args(adopt="msgbatch_test1"), client=client) == 0
    assert json.loads(rv.state_path().read_text())["stages"]["haiku"]["batch_id"] == "msgbatch_test1"
    assert b.calls == 1


def test_lost_opus_response_is_recovered_too(rv: ModuleType) -> None:
    client = fake_client()
    stage1_collected(rv, client)
    b = client.messages.batches
    b.fail = "after"
    assert rv.cmd_submit(args(cap=100.0), client=client) == 4
    assert rv.cmd_submit(args(cap=100.0), client=client) == 0
    assert len(b.created) == 2 and b.calls == 2  # stage 1 and one Opus batch
    assert json.loads(rv.state_path().read_text())["stages"]["opus"]["batch_id"] == "msgbatch_test2"


# ---- stage 1 needs the current extractor's conditions --------------------------------------------------------------


def test_stage1_refuses_while_conditions_are_from_an_older_extractor(
    rv: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = fake_client()
    stale = {"checked": 4, "same": 3, "stale": ["2014.0123C"], "no_pdf": []}
    monkeypatch.setattr(rv, "extractor_check", lambda: stale)
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 2
    out = capsys.readouterr().out
    assert "refused" in out and "2014.0123C" in out and "full_conditions.py reparse" in out
    assert client.messages.batches.calls == 0 and not rv.state_path().exists()
    # a motion that cannot be checked (no cached PDF) also stops it
    monkeypatch.setattr(
        rv, "extractor_check", lambda: {**FRESH, "checked": 3, "same": 3, "no_pdf": ["2016-001111CUA"]}
    )
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 2
    assert client.messages.batches.calls == 0
    # check-extractor reports the same, read-only
    assert rv.cmd_check_extractor(args(), check=stale) == 2 and "not ready" in capsys.readouterr().out
    assert rv.cmd_check_extractor(args(), check=FRESH) == 0 and "ready:" in capsys.readouterr().out
    # once reparse has run, stage 1 goes
    monkeypatch.setattr(rv, "extractor_check", lambda: dict(FRESH))
    assert rv.cmd_submit(args(), client=client, inputs=inputs(rv), progress=PROGRESS_DONE) == 0


def test_extractor_check_compares_every_condition_with_the_stored_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rv = load_module()  # the real extractor_check, against a fake database and extractor

    def cond(number: str, title: str, text: str, cats: tuple = ("hours",)) -> Any:
        return SimpleNamespace(number=number, title=title, text=text, categories=cats)

    motions = [{"id": "a", "record": "2012.0638C", "decided_at": "2013-03-14"},
               {"id": "b", "record": "2014.0123C", "decided_at": "2014-06-05"},
               {"id": "c", "record": "2016-001111CUA", "decided_at": "2016-09-01"},
               {"id": "d", "record": "2017-002222CUA", "decided_at": "2017-02-02"}]  # fmt: skip
    stored = [
        {"id": "a", "number": "1", "title": "Validity", "text": "Valid.", "categories": ["hours"]},
        {"id": "a", "number": "2", "title": "Hours", "text": "Close at 2 am.", "categories": ["hours"]},
        {"id": "b", "number": "1", "title": "Condition", "text": "Old reading.", "categories": ["hours"]},
    ]
    seen_sql: list[str] = []

    def fake_query(sql: str, params: tuple = ()) -> list[dict]:
        seen_sql.append(sql)
        assert params == ("2010-01-01", "2019-01-01")
        return motions if "from case_motions" in sql.split("join")[0] else stored

    fresh = {
        # a: the same, with a repeated number the database kept the first of
        "2012.0638C": [cond("1", "Validity", "Valid."), cond("2", "Hours", "Close at 2 am."),
                       cond("2", "Hours", "a repeat the insert skipped")],
        "2014.0123C": [cond("1", "Validity", "New reading.")],  # b: the fixed extractor reads it differently
        "2016-001111CUA": [],  # c: no conditions either way
    }  # fmt: skip
    seen_dates: list[str] = []

    def fake_extract(path: Path, decided: str) -> tuple:
        seen_dates.append(decided)
        return {}, None, fresh[path.name], True, True

    monkeypatch.setattr(rv, "query", fake_query)
    sidecars = {r: Path(r) for r in fresh}  # d has no cached PDF
    check = rv.extractor_check(extract=fake_extract, sidecars=sidecars)
    assert check == {"checked": 3, "same": 2, "stale": ["2014.0123C"], "no_pdf": ["2017-002222CUA"]}
    assert seen_dates == ["2013-03-14", "2014-06-05", "2016-09-01"]  # each read with its own decision date
    assert all(not re.search(r"\b(insert|update|delete)\b", s, re.I) for s in seen_sql)
    why = rv.extractor_verdict(check)
    assert why and "1 of 3" in why and "reparse" in why and "no cached PDF" in why
    assert rv.extractor_verdict({"checked": 3, "same": 3, "stale": [], "no_pdf": []}) is None


def test_number_key_sorts_like_the_search_page(rv: ModuleType) -> None:
    """Dotted numbers of older motions that restart their numbering ("2.3": list 2, condition 3) follow the whole
    first list, as build_conditions_index orders them; before, "2.3" sorted between "1" and "8"."""
    numbers = ["2.3", "10", "9", "2.1A", "1", "8A", "8", "2.10"]
    assert sorted(numbers, key=rv.number_key) == ["1", "8", "8A", "9", "10", "2.1A", "2.3", "2.10"]
    assert all(rv.number_key(n) == rv.bci.number_order(n) for n in numbers)
