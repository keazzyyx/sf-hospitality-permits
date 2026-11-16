"""Socrata (DataSF) paging helper shared by the datasf_* sources."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any

import httpx

from precedent.sources.base import RateLimiter, raw_path, write_raw

DATASF = "https://data.sf.gov"
PAGE_SIZE = 5000


def dataset_url(dataset_id: str) -> str:
    return f"{DATASF}/resource/{dataset_id}.json"


def dataset_home(dataset_id: str) -> str:
    return f"{DATASF}/d/{dataset_id}"


async def fetch_all(
    client: httpx.AsyncClient,
    *,
    source: str,
    dataset_id: str,
    raw_dir: Path,
    where: str | None = None,
    select: str | None = None,
    order: str = ":id",
    page_size: int = PAGE_SIZE,
    limiter: RateLimiter | None = None,
    max_pages: int | None = None,
) -> list[Path]:
    """Page through a dataset with $limit/$offset and save each page as a raw file."""
    limiter = limiter or RateLimiter(2.0)
    paths: list[Path] = []
    offset = 0
    page = 0
    headers = {}
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    while True:
        params: dict[str, Any] = {"$limit": page_size, "$offset": offset, "$order": order}
        if where:
            params["$where"] = where
        if select:
            params["$select"] = select
        await limiter.wait()
        resp = await client.get(dataset_url(dataset_id), params=params, headers=headers)
        resp.raise_for_status()
        rows = resp.json()
        path = raw_path(raw_dir, source, f"{dataset_id}-p{page:04d}")
        write_raw(
            path, rows, {"url": str(resp.url), "dataset_id": dataset_id, "offset": offset, "count": len(rows)}
        )
        paths.append(path)
        page += 1
        if len(rows) < page_size or (max_pages is not None and page >= max_pages):
            break
        offset += page_size
    return paths


def parse_date(value: Any) -> dt.date | None:
    if not value:
        return None
    text = str(value)[:10]
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def parse_point(row: dict[str, Any], *keys: str) -> tuple[float | None, float | None]:
    """Extract (lat, lng) from a Socrata point column or lat/lng columns."""
    for key in keys:
        val = row.get(key)
        if isinstance(val, dict):
            coords = val.get("coordinates")
            if isinstance(coords, list) and len(coords) >= 2:
                return float(coords[1]), float(coords[0])
    lat = row.get("latitude") or row.get("lat")
    lng = row.get("longitude") or row.get("lon") or row.get("lng")
    try:
        if lat is not None and lng is not None:
            return float(lat), float(lng)
    except (TypeError, ValueError):
        pass
    return None, None
