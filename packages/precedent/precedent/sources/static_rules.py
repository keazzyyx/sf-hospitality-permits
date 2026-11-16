"""Hand-maintained Planning Code rule rows (no geometry). Loaded from static/sf_overlay_rules.json."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx

from precedent.models import Overlay, SourceBatch
from precedent.sources.base import SourceSpec, raw_path, write_raw

STATIC = Path(__file__).resolve().parent.parent / "static" / "sf_overlay_rules.json"


async def fetch(client: httpx.AsyncClient, raw_dir: Path, since: dt.date | None) -> list[Path]:
    doc = json.loads(STATIC.read_text())
    path = raw_path(raw_dir, "static", "sf_overlay_rules")
    write_raw(path, doc, {"url": f"file://{STATIC}", "count": len(doc["overlays"])})
    return [path]


def parse(path: Path) -> SourceBatch:
    from precedent.sources.base import read_raw

    _, data = read_raw(path)
    return SourceBatch(overlays=[Overlay.model_validate(o) for o in data["overlays"]])


SOURCE = SourceSpec(
    name="static",
    description="Planning Code rule rows for SF special use districts and NC bar controls (hand-maintained, cited)",
    fetch=fetch,
    parse=parse,
    rate_limit_per_second=0,
    source_home="https://codelibrary.amlegal.com/codes/san_francisco/latest/sf_planning/0-0-0-21046",
)
