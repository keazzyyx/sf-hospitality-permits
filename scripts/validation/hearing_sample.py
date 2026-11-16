"""Draw a reproducible random sample of 30 hearing extractions (read-only), download each decision PDF
with the project's declared user agent at <= 1 request / 2 s, and extract its text with pypdf.

Usage: python -I hearing_sample.py <out_dir>
"""

import json
import os
import random
import sys
import time
from pathlib import Path

import httpx
import psycopg
from psycopg.rows import dict_row
from pypdf import PdfReader

USER_AGENT = "SF public-records research client/1.0 (independent research)"
SEED = 20261109
N = 30


def main() -> None:
    out = Path(sys.argv[1])
    pdf_dir = out / "pdf"  # downloaded, untrusted
    txt_dir = out / "text"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    txt_dir.mkdir(parents=True, exist_ok=True)

    with psycopg.connect(os.environ["PRECEDENT_DATABASE_URL"], row_factory=dict_row) as conn:
        conn.read_only = True
        rows = conn.execute(
            """select id, source_url, address, kind, permit_type, use_types, status, outcome, filed_at, decided_at,
                      hours_close, conditions, opposition_noted, decision_summary, extraction_confidence, extra
               from applications where extra ? 'motion_url' order by id"""
        ).fetchall()
    print(f"population: {len(rows)} hearing extractions", file=sys.stderr)
    sample = random.Random(SEED).sample(rows, N)

    cases = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=60) as client:
        for i, r in enumerate(sample, 1):
            extra = r["extra"]
            url = extra.get("motion_url")
            case = {
                "case": i,
                "id": r["id"],
                "address": r["address"],
                "kind": r["kind"],
                "use_types": r["use_types"],
                "status": r["status"],
                "outcome": r["outcome"],
                "filed_at": str(r["filed_at"]),
                "decided_at": str(r["decided_at"]),
                "hours_close": r["hours_close"],
                "opposition_noted": r["opposition_noted"],
                "decision_summary": r["decision_summary"],
                "extracted_conditions": r["conditions"],
                "condition_categories": extra.get("condition_categories"),
                "source_kind": extra.get("source_kind"),
                "motion_number": extra.get("motion_number"),
                "vote": extra.get("vote"),
                "pdf_url": url,
                "minutes_url": extra.get("minutes_url"),
                "item": extra.get("item"),
            }
            pdf_path = pdf_dir / f"case{i:02d}.pdf"
            try:
                resp = client.get(url)
                resp.raise_for_status()
                pdf_path.write_bytes(resp.content)
                reader = PdfReader(str(pdf_path))
                pages = reader.pages[:60]
                text = "\n".join(f"\n[[page {n + 1}]]\n" + (p.extract_text() or "") for n, p in enumerate(pages))
                (txt_dir / f"case{i:02d}.txt").write_text(text)
                case["pdf_pages"] = len(reader.pages)
                case["text_file"] = str(txt_dir / f"case{i:02d}.txt")
            except Exception as exc:  # noqa: BLE001
                case["fetch_error"] = f"{type(exc).__name__}: {exc}"[:300]
            cases.append(case)
            print(f"{i:02d} {r['id']} pages={case.get('pdf_pages')} err={case.get('fetch_error')}", file=sys.stderr)
            time.sleep(2.0)
    (out / "sample.json").write_text(json.dumps(cases, indent=1, default=str))


if __name__ == "__main__":
    main()
