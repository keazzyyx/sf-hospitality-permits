"""Label-coverage counts for docs/validation/label-coverage.md.

Read-only: the connection is opened with ``read_only = True`` and every query is a SELECT, so this is safe
to point at production. Prints Markdown tables to stdout and writes the raw numbers next to the report.

    PRECEDENT_DATABASE_URL=postgresql://… apps/api/.venv/bin/python scripts/validation/label_coverage.py \
        > docs/validation/label-coverage.tables.md

``--local`` reads the local validation database instead (LOCAL_DATABASE_URL, default $LOCAL_DATA_DIR) and
applies the Step 2 corrections: Planning rows count as hospitality only when the Haiku classifier says so
(``hospitality_labels``), and "approved with conditions" means a decision document lists conditions (the hearing
extraction or the full-conditions pass), never the word "condition" in a description. Output goes to
``label_coverage_local.json`` and stdout.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg

HOSP = "array['bar','restaurant','cafe','nightclub','live_entertainment','outdoor_seating','retail_alcohol']"
DECIDED = "('approved','approved_with_conditions','denied','withdrawn')"
ABC_RX = r"(\mabc\M|liquor|alcohol|type[- ]?(20|21|40|41|42|47|48)\M|beer and wine|on-sale|off-sale|pcn|public convenience)"
ENT_RX = r"(entertainment|\mpoe\M|place of entertainment|limited live|\mllp\M|amplified|extended hours)"
DPH_RX = r"(dph|health|food permit)"

# One row per application with the derived labels used throughout the report.
HOSP_EXPR = f"(a.use_types && {HOSP})"
OUTCOME_APPROVED_EXPR = "a.outcome"

BASE_TEMPLATE = """
select a.*,
  {hosp} as hosp,
  (a.extra ? 'motion_url') as hearing,
  case
{planning_pathway}
    when a.source='abc' and exists (
      select 1 from jsonb_array_elements_text(coalesce(a.extra->'transfers','[]'::jsonb)) x where x ilike 'From License%%'
    ) then 'abc_transfer'
    when a.source='abc' then 'abc_new'
    when a.source='datasf_entertainment' then 'entertainment'
  end as pathway,
  case
    when a.outcome='withdrawn' and a.status ilike '%%cancel%%' then 'cancelled'
    when a.outcome='denied' then 'disapproved'
    else {approved} end as outcome2
from applications a
"""

PLANNING_PATHWAY = """    when a.source='datasf_planning' and a.kind='cua' then 'planning_cua'
    when a.source='datasf_planning' and a.extra->>'record_type'='MIS' and a.description ~* '{DPH_RX}' then 'referral_dph'
    when a.source='datasf_planning' and a.extra->>'record_type'='MIS' and a.description ~* '{ABC_RX}' then 'referral_abc'
    when a.source='datasf_planning' and a.extra->>'record_type'='MIS' and a.description ~* '{ENT_RX}' then 'referral_entertainment'
    when a.source='datasf_planning' then 'planning_other'"""

# Local corrections (Steps 2 and 2b). A Planning record counts toward a pathway only when the Haiku labels in
# ``record_labels`` say it is about a food-and-drink premises AND it is a use decision or an agency referral.
# Building work at such premises is site history, not a pathway.
LOCAL_HOSP_EXPR = f"""(case when a.source = 'datasf_planning'
  then exists (select 1 from record_labels r where r.id = a.id and r.premises
               and r.record_kind in ('use_decision','agency_referral'))
  else a.use_types && {HOSP} end)"""
LOCAL_PLANNING_PATHWAY = """    when a.source='datasf_planning' and a.kind='cua'
         and (select r.record_kind from record_labels r where r.id = a.id) = 'use_decision' then 'planning_cua'
    when a.source='datasf_planning' and (select r.record_kind from record_labels r where r.id = a.id) = 'agency_referral'
         and a.description ~* '{DPH_RX}' then 'referral_dph'
    when a.source='datasf_planning' and (select r.record_kind from record_labels r where r.id = a.id) = 'agency_referral'
         and a.description ~* '{ABC_RX}' then 'referral_abc'
    when a.source='datasf_planning' and (select r.record_kind from record_labels r where r.id = a.id) = 'agency_referral'
         and a.description ~* '{ENT_RX}' then 'referral_entertainment'
    when a.source='datasf_planning' and (select r.record_kind from record_labels r where r.id = a.id) = 'agency_referral'
         then 'referral_agency_not_stated'
    when a.source='datasf_planning' and (select r.record_kind from record_labels r where r.id = a.id) = 'use_decision'
         then 'planning_other_use_decision'"""
LOCAL_OUTCOME_APPROVED_EXPR = """(case
  when a.outcome in ('approved','approved_with_conditions') and (
        exists (select 1 from case_motions m where m.id = a.id and m.found and m.n_conditions > 0)
        or (a.extra ? 'motion_url' and cardinality(a.conditions) > 0))
    then 'approved_with_conditions'
  when a.outcome = 'approved_with_conditions' then 'approved'
  else a.outcome end)"""


def base(local: bool) -> str:
    hosp = LOCAL_HOSP_EXPR if local else HOSP_EXPR
    approved = LOCAL_OUTCOME_APPROVED_EXPR if local else OUTCOME_APPROVED_EXPR
    pathway = LOCAL_PLANNING_PATHWAY if local else PLANNING_PATHWAY
    out = (
        BASE_TEMPLATE.replace("{planning_pathway}", pathway)
        .replace("{hosp}", hosp)
        .replace("{approved}", approved)
    )
    for k, v in {"{DPH_RX}": DPH_RX, "{ABC_RX}": ABC_RX, "{ENT_RX}": ENT_RX}.items():
        out = out.replace(k, v)
    return out


BASE = base(False)

METRICS = """
count(*) total,
count(*) filter (where hosp) hosp_use,
count(*) filter (where filed_at is not null) filed_date,
count(*) filter (where decided_at is not null) decision_date,
count(*) filter (where outcome2='approved') approved,
count(*) filter (where outcome2='approved_with_conditions') approved_w_cond,
count(*) filter (where outcome2='disapproved') disapproved,
count(*) filter (where outcome2='withdrawn') withdrawn,
count(*) filter (where outcome2='cancelled') cancelled,
count(*) filter (where outcome2='pending') pending,
count(*) filter (where outcome2='unknown') unknown,
count(*) filter (where cardinality(conditions)>0) has_condition,
count(*) filter (where parcel is not null) parcel,
count(*) filter (where geom is not null) geocoded
"""

COMPLETE = f"hosp and geom is not null and pathway is not null and outcome in {DECIDED} and filed_at is not null"


def queries(BASE: str) -> dict[str, str]:
    return {
        "per_source": f"""
      select s as source, {METRICS} from (
        select case when hearing then 'hearing PDFs (subset of Planning)' else source end s, * from ({BASE}) t
        union all select 'Planning, all rows', * from ({BASE}) t where source='datasf_planning'
      ) q group by s order by s""",
        "per_source_hosp": f"""
      select s as source, {METRICS} from (
        select case when hearing then 'hearing PDFs (subset of Planning)' else source end s, * from ({BASE}) t where hosp
        union all select 'Planning, all rows', * from ({BASE}) t where source='datasf_planning' and hosp
      ) q group by s order by s""",
        "per_pathway_hosp": f"select pathway, {METRICS} from ({BASE}) t where hosp group by 1 order by 1",
        "businesses": """
      select count(*) total, count(*) filter (where is_food_or_drink) food_or_drink, count(*) filter (where is_bar) bar,
             count(*) filter (where start_date is not null) start_date, count(*) filter (where end_date is not null) end_date,
             count(*) filter (where geom is not null) geocoded
      from businesses""",
        "complete_by_year": f"""
      select pathway, extract(year from filed_at)::int as year, count(*) n,
             count(*) filter (where outcome in ('denied','withdrawn')) failures,
             count(*) filter (where decided_at is not null) with_decision_date
      from ({BASE}) t where {COMPLETE} and filed_at between '2019-01-01' and '2026-12-31'
      group by 1,2 order by 1,2""",
        "apps_per_year": f"""
      select pathway, extract(year from filed_at)::int as year, count(*) n from ({BASE}) t
      where hosp and filed_at between '2019-01-01' and '2026-12-31' group by 1,2 order by 1,2""",
        "days_by_pathway": f"""
      select pathway, count(*) n,
             percentile_cont(0.5) within group (order by decided_at-filed_at) median_days,
             percentile_cont(0.9) within group (order by decided_at-filed_at) p90_days
      from ({BASE}) t
      where {COMPLETE} and filed_at between '2019-01-01' and '2026-12-31'
        and decided_at is not null and decided_at >= filed_at
      group by 1 order by 1""",
        "days_cua_by_outcome": f"""
      select outcome2 as outcome, count(*) n,
             percentile_cont(0.5) within group (order by decided_at-filed_at) median_days,
             percentile_cont(0.9) within group (order by decided_at-filed_at) p90_days
      from ({BASE}) t
      where pathway='planning_cua' and {COMPLETE} and filed_at between '2019-01-01' and '2026-12-31'
        and decided_at is not null and decided_at >= filed_at
      group by 1 order by 1""",
        "cua_by_year": f"""
      select extract(year from filed_at)::int as year, count(*) n,
             count(*) filter (where outcome2 in ('approved','approved_with_conditions')) approved,
             count(*) filter (where outcome2='disapproved') disapproved,
             count(*) filter (where outcome2='withdrawn') withdrawn,
             count(*) filter (where outcome2='cancelled') cancelled,
             count(*) filter (where outcome2 in ('pending','unknown')) open_or_unknown,
             count(*) filter (where hearing) with_hearing_pdf
      from ({BASE}) t where pathway='planning_cua' and hosp and filed_at between '2015-01-01' and '2026-12-31'
      group by 1 order by 1""",
        "reconciliation": f"""
      select pathway,
             count(*) complete,
             count(*) filter (where outcome in ('denied','withdrawn')) failures,
             count(*) filter (where decided_at is not null and decided_at >= filed_at) with_decision_date,
             count(*) filter (where decided_at is not null and decided_at >= filed_at and outcome in ('denied','withdrawn')) failures_with_date,
             count(*) filter (where decided_at is null or decided_at < filed_at) no_decision_date,
             count(*) filter (where (decided_at is null or decided_at < filed_at) and outcome in ('denied','withdrawn')) failures_no_date
      from ({BASE}) t where {COMPLETE} and filed_at between '2019-01-01' and '2026-12-31'
      group by 1 order by 1""",
        "site_history": """
      select r.record_kind, count(*) records, count(distinct a.address) addresses,
             count(*) filter (where a.filed_at >= '2019-01-01') filed_2019_on
      from applications a join record_labels r using (id)
      where a.source = 'datasf_planning' and r.premises group by 1 order by 2 desc""",
        "abc_flags": """
      select count(*) total,
             count(*) filter (where extra->>'record_kind'='APP') app_records,
             count(*) filter (where extra->>'protest_indicator'='true') protest_flag,
             count(*) filter (where extra->>'hearing_indicator'='true') hearing_flag,
             count(*) filter (where cardinality(conditions)>0) with_conditions,
             count(*) filter (where decided_at = (extra->'license_types'->0->>'orig_iss_date')::date) decided_is_orig_issue
      from applications where source='abc'""",
        "hearing_extractions": f"""
      select count(*) n, count(*) filter (where hosp) hospitality, count(*) filter (where cardinality(conditions)>0) with_conditions,
             sum(cardinality(conditions)) conditions_total, count(*) filter (where opposition_noted) opposition,
             count(*) filter (where extra->>'source_kind'='minutes') from_minutes
      from ({BASE}) t where hearing""",
    }


def fmt(v: Any, col: str = "") -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.0f}"
    if isinstance(v, int) and col != "year":
        return f"{v:,}"
    return str(v)


def table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "_no rows_\n"
    cols = list(rows[0])
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join(fmt(r[c], c) for c in cols) + " |" for r in rows]
    return "\n".join(out) + "\n"


def pivot(
    rows: list[dict[str, Any]], row_key: str, col_key: str, val: str
) -> list[dict[str, Any]]:
    cols = sorted({r[col_key] for r in rows})
    keys = sorted({r[row_key] for r in rows})
    out = []
    for k in keys:
        rec: dict[str, Any] = {row_key: k}
        for c in cols:
            rec[str(c)] = next(
                (r[val] for r in rows if r[row_key] == k and r[col_key] == c), 0
            )
        rec["total"] = sum(v for kk, v in rec.items() if kk != row_key)
        out.append(rec)
    return out


def main() -> int:
    local = "--local" in sys.argv[1:]
    url = (
        os.environ.get(
            "LOCAL_DATABASE_URL",
            "postgresql://postgres@localhost:55433/sfhp_local",
        )
        if local
        else os.environ.get("PRECEDENT_DATABASE_URL")
    )
    if not url:
        print("set PRECEDENT_DATABASE_URL", file=sys.stderr)
        return 2
    QUERIES = queries(base(local))
    if not local:
        QUERIES.pop("site_history")
    data: dict[str, Any] = {}
    with psycopg.connect(url) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("show transaction_read_only")
            row = cur.fetchone()
            assert row and row[0] == "on", (
                "refusing to run outside a read-only transaction"
            )
            for name, sql in QUERIES.items():
                cur.execute(sql)
                cols = [d.name for d in cur.description or []]
                data[name] = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    Path(__file__).with_name(
        "label_coverage_local.json" if local else "label_coverage.json"
    ).write_text(json.dumps(data, indent=1, default=str))

    sections = [
        ("All rows per source", table(data["per_source"])),
        ("Hospitality rows per source", table(data["per_source_hosp"])),
        ("Hospitality rows per pathway", table(data["per_pathway_hosp"])),
        ("Registered businesses", table(data["businesses"])),
        (
            "Complete records by pathway and filing year",
            table(pivot(data["complete_by_year"], "pathway", "year", "n")),
        ),
        (
            "…of which failures (disapproved, withdrawn, cancelled)",
            table(pivot(data["complete_by_year"], "pathway", "year", "failures")),
        ),
        (
            "Hospitality applications per filing year",
            table(pivot(data["apps_per_year"], "pathway", "year", "n")),
        ),
        (
            "Complete records with and without a decision date (timing uses only those with one)",
            table(data["reconciliation"]),
        ),
        (
            "Days from filing to decision, complete records filed 2019+",
            table(data["days_by_pathway"]),
        ),
        (
            "Conditional use, days by outcome, complete records filed 2019+",
            table(data["days_cua_by_outcome"]),
        ),
        ("Conditional use (hospitality) by filing year", table(data["cua_by_year"])),
        *(
            [
                (
                    "Premises records by kind (building work is site history, not a pathway)",
                    table(data["site_history"]),
                )
            ]
            if local
            else []
        ),
        ("ABC flags", table(data["abc_flags"])),
        ("Hearing extractions", table(data["hearing_extractions"])),
    ]
    for title, body in sections:
        print(f"### {title}\n\n{body}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
