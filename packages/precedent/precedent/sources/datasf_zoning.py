"""SF Zoning Map – Zoning Districts polygons (DataSF 3i4a-hu95) → one `zoning_district` Overlay per code.

The dataset has ~10.6k polygons (`zoning`, `districtna` = district name, `gen`, `codesectio`, `url`,
`the_geom` MultiPolygon). Fetch pages one zoning code at a time so a raw file always holds every polygon of
its code, and parse() dissolves them into a single MultiPolygon per code.

Bar / restaurant permissions and the controlling Planning Code section come from the verified
`zoning_controls` table in static/sf_overlay_rules.json; the dataset's own `codesectio` values predate
the 2015+ renumbering of Articles 7 and 8 (e.g. it lists 726.1 for NCT-VALENCIA, which is now § 762), so
they are only used, flagged as unverified, for codes the table does not cover.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, cast

import httpx
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from precedent.models import Overlay, SourceBatch
from precedent.sources import socrata
from precedent.sources.base import RateLimiter, SourceSpec, fetched_at_from, read_raw

SOURCE_NAME: Final = "datasf_zoning"
DATASET_ID = "3i4a-hu95"
RATE = 2.0
RULES_FILE = Path(__file__).resolve().parent.parent / "static" / "sf_overlay_rules.json"
_PERMS = {"principal", "conditional", "prohibited", "unknown"}
_WORD = {
    "principal": "principally permitted",
    "conditional": "requires Conditional Use Authorization",
    "prohibited": "not permitted",
    "unknown": "not determined",
}


@lru_cache(maxsize=1)
def rules_doc() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(RULES_FILE.read_text()))


def zoning_controls() -> dict[str, dict[str, Any]]:
    return cast(dict[str, dict[str, Any]], rules_doc().get("zoning_controls", {}))


# ---- geometry ----------------------------------------------------------------------------------------------
def _polygons(geom: BaseGeometry) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom] if not geom.is_empty else []
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if not g.is_empty]
    out: list[Polygon] = []
    for g in getattr(geom, "geoms", []):  # GeometryCollection from make_valid / union
        out.extend(_polygons(g))
    return out


def dissolve(geoms: list[Any]) -> dict[str, Any] | None:
    """Union GeoJSON (Multi)Polygons into one GeoJSON MultiPolygon (lists, not tuples)."""
    shapes = []
    for g in geoms:
        if not g:
            continue
        s = shape(g)
        if not s.is_valid:
            s = make_valid(s)
        shapes.extend(_polygons(s))
    if not shapes:
        return None
    merged = unary_union(shapes)
    polys = _polygons(merged)
    if not polys:
        return None
    return cast(dict[str, Any], json.loads(json.dumps(mapping(MultiPolygon(polys)))))


# ---- fetch -------------------------------------------------------------------------------------------------
def _headers() -> dict[str, str]:
    token = os.environ.get("SOCRATA_APP_TOKEN")
    return {"X-App-Token": token} if token else {}


async def list_codes(
    client: httpx.AsyncClient, dataset_id: str, column: str, limiter: RateLimiter
) -> list[str]:
    await limiter.wait()
    resp = await client.get(
        socrata.dataset_url(dataset_id),
        headers=_headers(),
        params={"$select": column, "$group": column, "$order": column, "$limit": 50000},
    )
    resp.raise_for_status()
    return [r[column] for r in resp.json() if r.get(column)]


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


async def fetch(client: httpx.AsyncClient, raw_dir: Path, since: dt.date | None) -> list[Path]:
    # Polygons carry no edit dates in this dataset: always a full snapshot; `since` is not applicable.
    limiter = RateLimiter(RATE)
    codes = await list_codes(client, DATASET_ID, "zoning", limiter)
    cap = int(os.environ["DATASF_MAX_CODES"]) if os.environ.get("DATASF_MAX_CODES") else None
    paths: list[Path] = []
    for code in codes[:cap]:
        paths += await socrata.fetch_all(
            client,
            source=SOURCE_NAME,
            dataset_id=DATASET_ID,
            raw_dir=raw_dir,
            where=f"zoning = {_quote(code)}",
            select="zoning,zoning_sim,districtna,gen,codesectio,url,the_geom",
            order=":id",
            limiter=limiter,
            page_size=50000,  # Socrata maximum: keeps every polygon of a code in one raw file
        )
    return paths


# ---- parse -------------------------------------------------------------------------------------------------
def _most_common(values: list[str | None]) -> str | None:
    vals = [v for v in values if v]
    return Counter(vals).most_common(1)[0][0] if vals else None


def overlay_for(code: str, rows: list[dict[str, Any]], fetched_at: dt.datetime) -> Overlay | None:
    geom = dissolve([r.get("the_geom") for r in rows if isinstance(r.get("the_geom"), dict)])
    district = (_most_common([r.get("districtna") for r in rows]) or code).strip()
    gen = _most_common([r.get("gen") for r in rows])
    ds_section = _most_common([r.get("codesectio") for r in rows])
    ds_url = _most_common([r.get("url") for r in rows])
    ctl = zoning_controls().get(code)
    if ctl:
        bar, rest = ctl["bar_permission"], ctl["restaurant_permission"]
        if bar not in _PERMS or rest not in _PERMS:
            raise ValueError(f"bad permission in zoning_controls[{code!r}]")
        code_section = f"Planning Code § {ctl['section']} (zoning control table for {code})"
        rules = (
            f"{ctl.get('name') or district.title()} ({code}). Bar {_WORD[bar]}; Restaurant {_WORD[rest]} on the First Story. "
            f"{ctl.get('note') or ''}"
        ).strip()
        late = f"Hours of operation: {ctl['hours'].rstrip('.')}." if ctl.get("hours") else None
        source_url = ctl.get("source_url") or ds_url or socrata.dataset_home(DATASET_ID)
    else:
        bar = rest = "unknown"
        listed = (
            f"; DataSF lists § {ds_section}, not verified"
            if ds_section and ds_section.upper() not in {"TBD", "NONE"}
            else ""
        )
        code_section = f"Planning Code Article 7/8 zoning control table for {code}{listed}"
        rules = f"{district.title()} ({code}){f', {gen}' if gen else ''}. Bar/restaurant controls not resolved for this district; check its control table."
        late = None
        source_url = ds_url or socrata.dataset_home(DATASET_ID)
    return Overlay(
        id=f"{SOURCE_NAME}:{code}",
        kind="zoning_district",
        name=code,
        rules=rules,
        code_section=code_section,
        geom=geom,
        district_codes=[code],
        bar_permission=bar,
        restaurant_permission=rest,
        late_night_rule=late,
        source=SOURCE_NAME,
        source_url=source_url,
        fetched_at=fetched_at,
    )


def parse(path: Path) -> SourceBatch:
    meta, rows = read_raw(path)
    fetched_at = fetched_at_from(meta)
    by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        code = (r.get("zoning") or "").strip()
        if code:
            by_code[code].append(r)
    overlays = [
        o for code, rs in sorted(by_code.items()) if (o := overlay_for(code, rs, fetched_at)) is not None
    ]
    return SourceBatch(overlays=overlays)


SOURCE = SourceSpec(
    name=SOURCE_NAME,
    description=f"SF Zoning Districts (DataSF {DATASET_ID}) dissolved per code, with verified bar/restaurant controls",
    fetch=fetch,
    parse=parse,
    rate_limit_per_second=RATE,
    source_home=socrata.dataset_home(DATASET_ID),
)
