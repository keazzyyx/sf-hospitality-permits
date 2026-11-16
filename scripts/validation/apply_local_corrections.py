"""Apply the Step 2 corrections to the LOCAL copy of the precedent store, so a locally generated report uses them.

Never run against production: the script refuses any database that is not on localhost. It is idempotent.

    apps/api/.venv/bin/python scripts/validation/apply_local_corrections.py

What it changes in ``applications`` (Planning rows only):
1. ``extra.premises``, ``extra.use_class`` and ``extra.record_kind`` from the Haiku labels (``record_labels``).
2. ``outcome``: "approved_with_conditions" survives only where a decision document lists conditions (a hearing
   extraction or a motion from the full-conditions pass); every other approval is "approved". Approvals whose
   motion lists conditions become "approved_with_conditions".
3. ``conditions`` for cases covered by the full-conditions pass: every numbered condition from the motion,
   case-specific ones first, standard ones after and marked "(standard)". The structured list, with the
   standard flag and categories, goes to ``extra.conditions_detail``; ``extra.motion_url`` points at the motion.
"""

from __future__ import annotations

import os

import psycopg
from psycopg.types.json import Jsonb

LOCAL = os.environ.get(
    "LOCAL_DATABASE_URL", "postgresql://postgres@localhost:55433/sfhp_local"
)


def main() -> None:
    assert "localhost" in LOCAL or "127.0.0.1" in LOCAL, (
        "refusing: this script only edits the local validation copy"
    )
    with psycopg.connect(LOCAL, autocommit=True) as conn:
        n1 = conn.execute(
            """update applications a
               set extra = a.extra || jsonb_build_object('premises', r.premises, 'use_class', r.use_class,
                                                         'record_kind', r.record_kind)
               from record_labels r where r.id = a.id and a.source = 'datasf_planning'"""
        ).rowcount
        n2 = conn.execute(
            """update applications a set outcome = 'approved'
               where a.source = 'datasf_planning' and a.outcome = 'approved_with_conditions'
                 and not (a.extra ? 'motion_url' and cardinality(a.conditions) > 0)
                 and not exists (select 1 from case_motions m where m.id = a.id and m.found and m.n_conditions > 0)"""
        ).rowcount
        cases = conn.execute(
            "select id, motion_url, doc_outcome from case_motions where found and n_conditions > 0"
        ).fetchall()
        n3 = 0
        for app_id, motion_url, doc_outcome in cases:
            conds = conn.execute(
                """select number, title, text, categories, standard from case_conditions where id = %s
                   order by standard, (regexp_replace(number, '[^0-9]', '', 'g'))::int, number""",
                (app_id,),
            ).fetchall()
            texts = [
                f"{text} (standard)" if standard else text
                for _n, _t, text, _c, standard in conds
            ]
            detail = [
                {
                    "number": n,
                    "title": t,
                    "text": text,
                    "categories": list(c),
                    "standard": bool(std),
                }
                for n, t, text, c, std in conds
            ]
            outcome_sql = (
                "case when a.outcome in ('approved','approved_with_conditions') then 'approved_with_conditions' "
                "else a.outcome end"
            )
            n3 += conn.execute(
                f"""update applications a
                    set conditions = %s, outcome = {outcome_sql},
                        extra = a.extra || %s
                    where a.id = %s""",
                (
                    texts,
                    Jsonb(
                        {
                            "conditions_detail": detail,
                            "conditions_source": "motion (full-conditions pass)",
                            "motion_url": motion_url,
                            "source_kind": "motion",
                            "motion_outcome": doc_outcome,
                        }
                    ),
                    app_id,
                ),
            ).rowcount
        print(
            f"labels copied to {n1} rows; {n2} inferred 'approved with conditions' reset to approved; "
            f"{n3} cases given their motion's full conditions"
        )
        for row in conn.execute(
            "select outcome, count(*) from applications where source='datasf_planning' group by 1 order by 2 desc"
        ):
            print("  ", row)


if __name__ == "__main__":
    main()
