"""Idempotent ingestion CLI.

    python -m precedent.ingest --source datasf_planning            # fetch + parse + upsert one source
    python -m precedent.ingest --all                               # every registered source (nightly job),
                                                                   # then the post-ingest enrichment steps
    python -m precedent.ingest --parse-only raw/datasf_planning/x.json

Store selection: PRECEDENT_DATABASE_URL (PostGIS) when set, else the local JSONL store under
PRECEDENT_DATA_DIR (default ./data). Raw responses always land in PRECEDENT_RAW_DIR (default ./data/raw).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import os
import sys
from pathlib import Path
from typing import Any

import neatlogs

from precedent.enrich import enrich_businesses
from precedent.models import IngestionRun, SourceBatch
from precedent.sources import registry
from precedent.sources.base import SourceSpec, make_client
from precedent.store import Store, open_store

log = logging.getLogger("precedent.ingest")

ENRICH_AFTER = {"datasf_business", "abc"}


async def upsert_batch(store: Store, batch: SourceBatch) -> int:
    n = 0
    n += await store.upsert_applications(batch.applications)
    n += await store.upsert_overlays(batch.overlays)
    n += await store.upsert_businesses(batch.businesses)
    return n


@neatlogs.span(kind="CHAIN", name="ingest.source", capture_output=False)
async def run_source(spec: SourceSpec, store: Store, raw_dir: Path, since: dt.date | None) -> IngestionRun:
    run = IngestionRun(source=spec.name, started_at=dt.datetime.now(dt.UTC))
    try:
        async with make_client() as client:
            paths = await spec.fetch(client, raw_dir, since)
        fetched = 0
        upserted = 0
        for path in paths:
            batch = spec.parse(path)
            fetched += len(batch)
            upserted += await upsert_batch(store, batch)
        run = run.model_copy(
            update={
                "status": "ok",
                "rows_fetched": fetched,
                "rows_upserted": upserted,
                "finished_at": dt.datetime.now(dt.UTC),
                "notes": f"{len(paths)} raw files",
            }
        )
    except Exception as exc:  # recorded, never crashes the nightly loop
        log.exception("ingestion failed for %s", spec.name)
        run = run.model_copy(
            update={
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}"[:500],
                "finished_at": dt.datetime.now(dt.UTC),
            }
        )
    await store.record_run(run)
    log.info("%s: %s fetched=%d upserted=%d", spec.name, run.status, run.rows_fetched, run.rows_upserted)
    return run


async def run_all(
    sources: list[str], store: Store, raw_dir: Path, since: dt.date | None
) -> list[IngestionRun]:
    specs = registry()
    unknown = [s for s in sources if s not in specs]
    if unknown:
        raise SystemExit(f"unknown source(s): {unknown}; available: {sorted(specs)}")
    runs = []
    for name in sources:
        runs.append(await run_source(specs[name], store, raw_dir, since))
    return runs


def select_sources(names: list[str], skip: list[str], available: set[str]) -> list[str]:
    """The sources to run: `names` minus `skip`. Unknown names on either side are a usage error."""
    unknown = [s for s in [*names, *skip] if s not in available]
    if unknown:
        raise SystemExit(f"unknown source(s): {unknown}; available: {sorted(available)}")
    return [s for s in names if s not in set(skip)]


def skip_notice(name: str, last_ok: IngestionRun | None, latest: dict[str, Any] | None) -> str:
    """One line saying a source was skipped, when its rows were last refreshed successfully, and whether a
    more recent attempt failed."""
    if last_ok is None:
        line = f"{name}: SKIPPED by request; this store has never been refreshed from it"
    else:
        when = (last_ok.finished_at or last_ok.started_at).isoformat(timespec="minutes")
        line = f"{name}: SKIPPED by request; last successful refresh {when} ({last_ok.rows_upserted} rows)"
    if latest and latest.get("status") != "ok":
        attempt = latest.get("finished_at") or latest.get("started_at") or "unknown time"
        line += f"; latest attempt {attempt} {latest.get('status', 'unknown')}"
    return line


def parse_only(path: Path) -> int:
    specs = registry()
    source = path.parent.name
    if source not in specs:
        raise SystemExit(f"cannot infer source from {path}; parent dir must be a source name")
    batch = specs[source].parse(path)
    print(batch.model_dump_json(indent=1)[:5000])
    print(f"... {len(batch)} rows")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="precedent-ingest")
    parser.add_argument("--source", action="append", help="source name (repeatable)")
    parser.add_argument("--all", action="store_true", help="run every registered source")
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="NAME",
        help="leave this source out (repeatable); its staleness is logged as a warning",
    )
    parser.add_argument("--since", type=dt.date.fromisoformat, help="incremental window start (YYYY-MM-DD)")
    parser.add_argument("--parse-only", type=Path, help="parse one raw file and print the batch")
    parser.add_argument("--raw-dir", type=Path, default=Path(os.environ.get("PRECEDENT_RAW_DIR", "data/raw")))
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("PRECEDENT_DATA_DIR", "data")))
    parser.add_argument("--database-url", default=os.environ.get("PRECEDENT_DATABASE_URL"))
    parser.add_argument("--list", action="store_true", help="list registered sources")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    if args.list:
        for name, spec in sorted(registry().items()):
            print(f"{name:26} {spec.rate_limit_per_second:>4}/s  {spec.description}")
        return 0
    if args.parse_only:
        return parse_only(args.parse_only)
    requested = sorted(registry()) if args.all else (args.source or [])
    if not requested:
        parser.error("pass --source NAME, --all, --parse-only PATH or --list")
    sources = select_sources(requested, args.skip, set(registry()))

    if os.environ.get("NEATLOGS_API_KEY"):
        neatlogs.init(
            api_key=os.environ["NEATLOGS_API_KEY"],
            workflow_name="permit-memo-ingest",
            tags=[
                f"env:{os.environ.get('ENV', 'development')}",
                f"version:{os.environ.get('GIT_SHA', 'dev')}",
            ],
        )

    async def go() -> int:
        store = open_store(args.database_url, str(args.data_dir))
        if hasattr(store, "ensure_schema"):
            await store.ensure_schema()
        try:
            if args.skip:
                last_runs = (await store.status()).get("last_runs", {})
                for name in args.skip:
                    notice = skip_notice(name, await store.last_successful_run(name), last_runs.get(name))
                    log.warning(notice)
                    if os.environ.get("GITHUB_ACTIONS"):
                        print(f"::warning title=Source skipped::{notice}", flush=True)
            runs = await run_all(sources, store, args.raw_dir, args.since)
            # bar flags need businesses and ABC licenses in the store together; a business re-parse resets
            # them, so re-run whenever either side was refreshed
            enrich_ok = True
            if args.all or ENRICH_AFTER & set(sources):
                try:
                    await enrich_businesses(store)
                except Exception:  # logged like a failed source; the other sources' rows stay upserted
                    log.exception("business bar enrichment failed")
                    enrich_ok = False
        finally:
            await store.close()
        failed = [r for r in runs if r.status != "ok"]
        return 1 if failed or not enrich_ok else 0

    code = asyncio.run(go())
    if os.environ.get("NEATLOGS_API_KEY"):
        neatlogs.flush()
        neatlogs.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
