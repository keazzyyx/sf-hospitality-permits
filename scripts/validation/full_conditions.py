"""Find the Planning Commission motion for every hospitality conditional-use case decided since 2010 and extract
ALL of its numbered conditions, then mark each condition standard or case-specific.

Writes only to the LOCAL validation database (tables ``case_motions`` and ``case_conditions``); raw lookups and
PDFs are cached under $LOCAL_DATA_DIR/raw. Requests go through the hearing source's own fetcher, one every
2 seconds. Resumable: cases already looked up are skipped.

    apps/api/.venv/bin/python scripts/validation/full_conditions.py run
    apps/api/.venv/bin/python scripts/validation/full_conditions.py standard   # recompute standard flags only

A condition is "standard" when its wording is boilerplate: the same normalised text (letters only, so PDF spacing
and hyphenation glitches do not matter) opens the same-titled condition on at least WORDING_MIN motions, or its
title appears on at least half of the approved motions for that use (not the generic title "Condition" of untitled
2009-2010 conditions, GENERIC_TITLE). Otherwise it is case-specific. (The first
version used titles only; a 20-motion hand check found 40 boilerplate conditions flagged case-specific.)

    apps/api/.venv/bin/python scripts/validation/full_conditions.py reparse    # re-extract from cached PDFs

"Hospitality" means the Haiku labels in ``record_labels`` say the record is about a food-and-drink premises and is a
use decision. A condition is
"standard" when its normalised title appears on at least half of the approved motions for that use (restaurant
or cafe, bar, nighttime entertainment, other food and drink); groups with fewer than 8 motions are pooled.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
import sys
from pathlib import Path

import httpx
import psycopg

os.environ.setdefault("PLANNING_HEARINGS_MAX_DOCS", "2000")
os.environ.setdefault("PLANNING_HEARINGS_MAX_REQUESTS", "6000")

from precedent.pdftext import (
    find_sections,
    read_pdf,
    read_pdf_poppler,
    strip_running_headers,
)
from precedent.sources import sf_planning_hearings as H
from precedent.sources.base import USER_AGENT, read_raw

LOCAL = os.environ.get(
    "LOCAL_DATABASE_URL", "postgresql://postgres@localhost:55433/sfhp_local"
)
RAW = Path(os.environ.get("LOCAL_DATA_DIR", "~/sfhp-local")).expanduser() / "raw"
# Decided on or after this date. 2019 until 2026-11-13; the owner extended it back to 2010 that day.
SINCE = dt.date.fromisoformat(os.environ.get("CONDITIONS_SINCE", "2010-01-01"))
MIN_GROUP = 8
# Motions decided before this date (case_motions.decided_at, as the site filters) are read with
# all_conditions(older_formats=True) (2009-2018 layouts, numbers lost by OCR). Never on 2019+ motions, so the
# published 2019+ conditions do not change.
OLDER_FORMATS_BEFORE = dt.date(2019, 1, 1)
WORDING_MIN = 5  # motions sharing the same opening wording
# A motion dated more than this many days after the case's decision is for a later decision on the same record, not
# for this one (2015-002658CUA, decided 2015-12-11: the lookup returned Motion No. 21682 of 2025-02-13, the motion of
# 2015-002658CUA-02). Such a motion is refused: no conditions, and reparse marks the case not found with LATER_NOTE.
# Checked for motions read the older way only (case decided before OLDER_FORMATS_BEFORE), so the published 2019+
# motions stay as they are.
LATER_MOTION_DAYS = 366
LATER_NOTE = "motion found is for a later decision"
# the title of untitled conditions (2009-2010 motions number their paragraphs without titles): every such condition
# shares it, so it says nothing about boilerplate and is left out of the title rule (the wording rule still applies)
GENERIC_TITLE = "Condition"
WORDING_CHARS = 120

DDL = """
create table if not exists case_motions (
  id text primary key, record text not null, decided_at date, outcome text, label text,
  found boolean not null, motion_url text, pdf_pages int, doc_outcome text, n_conditions int,
  numbered boolean, note text, checked_at timestamptz not null default now()
);
create table if not exists case_conditions (
  id text not null, number text not null, title text not null, text text not null,
  categories text[] not null, norm_title text not null, standard boolean,
  primary key (id, number)
);
alter table case_conditions add column if not exists wording_key text;
"""


def norm_title(title: str) -> str:
    t = re.sub(r"\s*\([A-H]\)$", "", title).lower()
    return re.sub(r"[^a-z]+", "", t)


def wording_key(title: str, text: str) -> str:
    """Title plus the first WORDING_CHARS letters of the body, letters only."""
    body = text.split(": ", 1)[1] if ": " in text else text
    return (
        norm_title(title) + "|" + re.sub(r"[^a-z]+", "", body.lower())[:WORDING_CHARS]
    )


def older_formats(decided: dt.date | str | None) -> bool:
    """Whether a motion is read with all_conditions(older_formats=True): by case_motions.decided_at, the date the
    published site filters on (a 2019 decision on a 2018 motion is read the 2019+ way). None: the 2019+ way."""
    if isinstance(decided, str):
        decided = dt.date.fromisoformat(decided[:10])
    return decided is not None and decided < OLDER_FORMATS_BEFORE


def later_motion(parsed: object, meta: dict, decided: dt.date | str | None) -> bool:
    """Whether the motion is for a later decision than the case's: its date (parse_motion's decided_at, the date in
    the motion's text, else the sidecar's hearing_date) is more than LATER_MOTION_DAYS after ``decided``
    (case_motions.decided_at). Older-formats cases only (see LATER_MOTION_DAYS)."""
    if not older_formats(decided):
        return False
    if isinstance(decided, str):
        decided = dt.date.fromisoformat(decided[:10])
    assert decided is not None
    motion_day = getattr(parsed, "decided_at", None)
    if motion_day is None and meta.get("hearing_date"):
        motion_day = dt.date.fromisoformat(str(meta["hearing_date"])[:10])
    return motion_day is not None and (motion_day - decided).days > LATER_MOTION_DAYS


def conditions_section(text: str, older: bool, stop=None) -> str:  # type: ignore[no-untyped-def]
    """The conditions section of a motion's text, without the plan sheets (from the first page ``stop`` says is
    one, H.is_plan_page by default). Older motions (``older``) are first cut at an Exhibit C / mitigation monitoring
    heading after their conditions (H.cut_older_exhibits)."""
    body = H.motion_body(text, stop)
    if older:
        body = H.cut_older_exhibits(body)
    return find_sections(strip_running_headers(body)).get("conditions", "")


def extract(path: Path, decided: dt.date | str | None) -> tuple[dict, object, list, bool, bool]:
    """(meta, parsed application, conditions, numbered, has_section) for one cached motion sidecar. ``decided`` is
    the case's case_motions.decided_at (applications.decided_at), which picks the older-formats reading. A motion
    for a later decision (later_motion) gives no conditions and no section; reparse and run record it as not found."""
    meta, data = read_raw(path)
    pdf = path.parent / str((data or {}).get("pdf") or meta.get("pdf"))
    doc = read_pdf(pdf.read_bytes(), max_pages=H.MOTION_MAX_PAGES, stop=H.is_plan_page)
    parsed = H.parse_motion(doc.text, meta, pages=doc.pages, sidecar=path)
    if later_motion(parsed, meta, decided):
        return meta, parsed, [], False, False
    older = older_formats(decided)
    section = conditions_section(doc.text, older)
    if older and not section:
        # the text can end early (2011.0026C: a short last findings page, "Motion 18420" with no "No.", was taken
        # for a plan sheet, and Exhibit A on page 12 was never read): read it again with pdftotext, stopping only at
        # a page H.is_plan_page_older calls a plan sheet, its numbers joined to their titles. The motion's other
        # facts (outcome, pages) stay from the first reading.
        again = read_pdf_poppler(pdf, max_pages=H.MOTION_MAX_PAGES, stop=H.is_plan_page_older)
        section = conditions_section(H.join_number_lines(again.text), older, H.is_plan_page_older)
    conds = H.all_conditions(section, older_formats=older) if section else []
    numbered = bool(conds)
    if (
        section and not conds
    ):  # un-numbered conditions: sentence heuristics, as the source does
        conds = [
            H.Condition(
                str(i + 1), "Condition", H._clip(c, 600), H._categories(c) or ("other",)
            )
            for i, c in enumerate(H.extract_conditions(H.squash(section)))
        ]
    return meta, parsed, conds, numbered, bool(section)


def store(conn: psycopg.Connection, app_id: str, conds: list) -> None:
    conn.execute("delete from case_conditions where id = %s", (app_id,))
    conn.cursor().executemany(
        """insert into case_conditions (id, number, title, text, categories, norm_title, wording_key)
           values (%s,%s,%s,%s,%s,%s,%s) on conflict (id, number) do nothing""",
        [
            (
                app_id,
                c.number,
                c.title,
                c.text,
                list(c.categories),
                norm_title(c.title),
                wording_key(c.title, c.text),
            )
            for c in conds
        ],
    )


def reparse() -> int:
    """Re-extract every found motion from its cached PDF (no network) after an extractor change."""
    sidecars = {}
    for p in (RAW / H.NAME).glob("*-motion*.json"):
        meta, _ = read_raw(p)
        sidecars[H.normalize_record(str(meta.get("record_number", "")))] = p
    with psycopg.connect(LOCAL, autocommit=True) as conn:
        conn.execute(DDL)
        rows = conn.execute(
            "select id, record, decided_at from case_motions where found"
        ).fetchall()
        done = 0
        for app_id, record, decided in rows:
            path = sidecars.get(H.normalize_record(record))
            if path is None:
                print("no cached sidecar for", record)
                continue
            meta, parsed, conds, numbered, has_section = extract(path, decided)
            if later_motion(parsed, meta, decided):
                print(f"{record}: {LATER_NOTE} ({parsed.decided_at}, case decided {decided})")
                store(conn, app_id, [])
                conn.execute(
                    "update case_motions set found=false, doc_outcome=null, n_conditions=0, numbered=false, note=%s "
                    "where id=%s",
                    (LATER_NOTE, app_id),
                )
                continue
            store(conn, app_id, conds)
            conn.execute(
                "update case_motions set doc_outcome=%s, n_conditions=%s, numbered=%s, note=%s where id=%s",
                (
                    parsed.outcome,
                    len(conds),
                    numbered,
                    None if has_section else "motion has no conditions section",
                    app_id,
                ),
            )
            done += 1
        print(f"re-extracted {done} motions")
    standard()
    return 0


def cases(conn: psycopg.Connection) -> list[tuple[str, str, dt.date, str, str]]:
    return conn.execute(
        """select a.id, a.source_id, a.decided_at, a.outcome, r.use_class
           from applications a join record_labels r using (id)
           left join case_motions m using (id)
           where a.source = 'datasf_planning' and a.kind = 'cua' and r.premises and r.record_kind = 'use_decision'
             and a.decided_at >= %s and a.outcome in ('approved','approved_with_conditions','denied')
             and m.id is null
           order by a.decided_at desc""",
        (SINCE,),
    ).fetchall()


async def run() -> int:
    assert "localhost" in LOCAL, "local validation database only"
    with psycopg.connect(LOCAL, autocommit=True) as conn:
        conn.execute(DDL)
        todo = cases(conn)
    print(
        f"{len(todo)} hospitality conditional-use cases decided since {SINCE} still to look up",
        flush=True,
    )
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=90
    ) as client:
        fetcher = H.Fetcher(client, RAW, SINCE)
        for n, (app_id, record, decided, outcome, label) in enumerate(todo, 1):
            note = None
            try:
                path = await fetcher.fetch_motion(H.normalize_record(record), decided)
            except Exception as exc:  # noqa: BLE001 — one case failing must not stop the rest
                path, note = (
                    None,
                    f"lookup error: {type(exc).__name__}: {str(exc)[:120]}",
                )
            with psycopg.connect(LOCAL, autocommit=True) as conn:
                if path is None:
                    conn.execute(
                        "insert into case_motions (id, record, decided_at, outcome, label, found, note) values (%s,%s,%s,%s,%s,false,%s)",
                        (
                            app_id,
                            record,
                            decided,
                            outcome,
                            label,
                            note or "no motion PDF in the Planning document index",
                        ),
                    )
                    continue
                meta, parsed, conds, numbered, has_section = extract(path, decided)
                if later_motion(parsed, meta, decided):
                    conn.execute(
                        "insert into case_motions (id, record, decided_at, outcome, label, found, motion_url, note) "
                        "values (%s,%s,%s,%s,%s,false,%s,%s)",
                        (app_id, record, decided, outcome, label, meta.get("url"), LATER_NOTE),
                    )
                    continue
                conn.execute(
                    """insert into case_motions (id, record, decided_at, outcome, label, found, motion_url, pdf_pages,
                         doc_outcome, n_conditions, numbered, note) values (%s,%s,%s,%s,%s,true,%s,%s,%s,%s,%s,%s)""",
                    (
                        app_id,
                        record,
                        decided,
                        outcome,
                        label,
                        meta.get("url"),
                        parsed.extra.get("pdf_pages"),
                        parsed.outcome,
                        len(conds),
                        numbered,
                        None if has_section else "motion has no conditions section",
                    ),
                )
                store(conn, app_id, conds)
            if n % 10 == 0:
                print(
                    f"{n}/{len(todo)} cases, fetcher stats {fetcher.stats}", flush=True
                )
    standard()
    return 0


def standard() -> None:
    approved = "found and doc_outcome in ('approved','approved_with_conditions')"
    with psycopg.connect(LOCAL, autocommit=True) as conn:
        conn.execute("update case_conditions set standard = false")
        # 1. boilerplate wording: the same opening text under the same title on WORDING_MIN or more motions
        conn.execute(
            """update case_conditions c set standard = true
               where c.wording_key in (select wording_key from case_conditions where wording_key is not null
                                       group by 1 having count(distinct id) >= %s)""",
            (WORDING_MIN,),
        )
        # 2. a title carried by at least half of the approved motions for that use (small groups pooled); not the
        #    generic title of untitled conditions
        groups = dict(
            conn.execute(
                f"select label, count(*) from case_motions where {approved} group by 1"
            ).fetchall()
        )
        for label, size in groups.items():
            scope = "m.label = %(label)s" if size >= MIN_GROUP else "true"
            conn.execute(
                f"""with approved as (select id from case_motions m where {approved} and {scope}),
                    share as (
                      select c.norm_title, count(distinct c.id)::float / (select count(*) from approved) s
                      from case_conditions c join approved a using (id) group by 1)
                    update case_conditions c set standard = true
                    from share sh, case_motions m
                    where c.norm_title = sh.norm_title and sh.s >= 0.5 and m.id = c.id and m.label = %(label)s
                      and not c.categories && array['hours'] and c.norm_title <> %(generic)s""",
                {"label": label, "generic": norm_title(GENERIC_TITLE)},
            )
        print(
            "standard flags:",
            conn.execute(
                "select standard, count(*) from case_conditions group by 1"
            ).fetchall(),
        )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "standard":
        standard()
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "reparse":
        sys.exit(reparse())
    sys.exit(asyncio.run(run()))
