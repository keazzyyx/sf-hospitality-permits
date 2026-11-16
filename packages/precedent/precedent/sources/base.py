from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from precedent.models import Source, SourceBatch

USER_AGENT = "SF public-records research client/1.0 (independent research)"
ABC_USER_AGENT = "CA ABC public-report archiver/1.0"


def abc_user_agent(contact: str | None = None) -> str:
    """User-Agent for every request to abc.ca.gov. The contact comes from ``ABC_ARCHIVE_CONTACT`` (set in
    ~/.config/sfhp/abc-archive.env on the workstation that runs the archive), never from code."""
    contact = (contact if contact is not None else os.environ.get("ABC_ARCHIVE_CONTACT", "")).strip()
    return (
        f"{ABC_USER_AGENT} (independent research; contact: {contact})"
        if contact
        else f"{ABC_USER_AGENT} (independent research)"
    )


FetchFn = Callable[[httpx.AsyncClient, Path, dt.date | None], Awaitable[list[Path]]]
ParseFn = Callable[[Path], SourceBatch]


@dataclass(frozen=True)
class SourceSpec:
    name: Source
    description: str
    fetch: FetchFn
    parse: ParseFn
    rate_limit_per_second: float
    source_home: str  # human landing page for the dataset / agency


class RateLimiter:
    """Simple token spacing: at most `per_second` requests per second, shared per source."""

    def __init__(self, per_second: float) -> None:
        self._interval = 1.0 / per_second if per_second > 0 else 0.0
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        if self._interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            delay = self._last + self._interval - now
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


def raw_path(raw_dir: Path, source: str, label: str, suffix: str = ".json") -> Path:
    """Timestamped, never-overwritten raw file path: raw_dir/<source>/<utc stamp>-<label><suffix>."""
    folder = raw_dir / source
    folder.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return folder / f"{stamp}-{label}{suffix}"


def write_raw(path: Path, payload: Any, meta: dict[str, Any]) -> Path:
    """Save a raw page with an envelope: {meta: {url, fetched_at, ...}, data: ...}."""
    envelope = {"meta": {"fetched_at": dt.datetime.now(dt.UTC).isoformat(), **meta}, "data": payload}
    path.write_text(json.dumps(envelope, ensure_ascii=False))
    return path


def read_raw(path: Path) -> tuple[dict[str, Any], Any]:
    env = json.loads(path.read_text())
    return env["meta"], env["data"]


def fetched_at_from(meta: dict[str, Any]) -> dt.datetime:
    return dt.datetime.fromisoformat(meta["fetched_at"])


def make_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
