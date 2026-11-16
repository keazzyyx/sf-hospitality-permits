"""The permit catalog fails loudly when its data folder holds no catalog files (a checkout without
packages/catalog/data/ once passed until the first lookup raised a KeyError), and the validator does too."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.catalog.loader import Catalog

REPO = Path(__file__).resolve().parents[3]


def test_an_empty_catalog_folder_raises_at_load(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no permit catalog files"):
        Catalog(tmp_path)


def test_the_real_catalog_folder_loads() -> None:
    catalog = Catalog(REPO / "packages" / "catalog" / "data")
    assert catalog.permits
    assert "san_francisco" in catalog.cities


def test_the_validator_passes_on_the_committed_catalog() -> None:
    run = subprocess.run(
        [sys.executable, str(REPO / "packages" / "catalog" / "scripts" / "validate.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.startswith("OK: ")
    assert not run.stdout.startswith("OK: 0 files")
