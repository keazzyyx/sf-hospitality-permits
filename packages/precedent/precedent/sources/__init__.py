"""Ingestion sources. Each module exposes a `SOURCE: SourceSpec` and is registered in `REGISTRY`.

Contract (see `base.py`):
  * `fetch(client, raw_dir, since)`  → downloads raw pages to `raw_dir/<source>/<timestamp>-<n>.json`
    (never mutates existing raw files; returns the paths written). Must honour the source's rate limit.
  * `parse(raw_path)`                → pure function from one raw file to a `SourceBatch`. Unit-tested
    against `tests/fixtures/<source>/`.
Ingestion is idempotent: parse output is upserted by primary key.
"""

from __future__ import annotations

from importlib import import_module

from precedent.sources.base import SourceSpec

_MODULES = [
    "precedent.sources.datasf_planning",
    "precedent.sources.datasf_entertainment",
    "precedent.sources.datasf_business",
    "precedent.sources.datasf_zoning",
    "precedent.sources.datasf_sud",
    "precedent.sources.abc",
    "precedent.sources.sf_planning_hearings",
    "precedent.sources.static_rules",
]


def registry() -> dict[str, SourceSpec]:
    specs: dict[str, SourceSpec] = {}
    for mod in _MODULES:
        try:
            spec: SourceSpec = import_module(mod).SOURCE
        except ModuleNotFoundError as exc:  # a source not yet implemented
            if exc.name != mod:
                raise
            continue
        specs[spec.name] = spec
    return specs
