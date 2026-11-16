"""Settings must load from .env.example exactly as shipped, and from plain comma-separated env values."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import API_DIR, Settings

EXAMPLE = API_DIR / ".env.example"


def test_env_example_loads_as_is(monkeypatch: pytest.MonkeyPatch) -> None:
    # isolate from the developer's real environment so only the example file is read
    for key in list(Settings.model_fields):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=EXAMPLE)  # type: ignore[call-arg]
    assert s.CORS_ORIGINS == ["http://localhost:3000"]
    assert s.ENV == "development" and s.FREE_PLAN_LIMIT == 3 and s.WEB_VERIFY_ENABLED is True
    assert s.ANTHROPIC_MODEL_MAIN == "claude-sonnet-4-5" and s.ANTHROPIC_MODEL_TRIAGE == "claude-haiku-4-5"
    assert s.NEATLOGS_API_KEY in (None, "")  # blank in the example → export disabled


def test_env_example_has_every_setting_documented() -> None:
    text = EXAMPLE.read_text()
    missing = [k for k in Settings.model_fields if k not in text and k != "CATALOG_DIR"]
    assert not missing, f".env.example is missing: {missing}"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://localhost:3000", ["http://localhost:3000"]),
        (
            "http://localhost:3000, https://app.example.org/",
            ["http://localhost:3000", "https://app.example.org"],
        ),
        ('["https://a.example","https://b.example"]', ["https://a.example", "https://b.example"]),
        ("", []),
    ],
)
def test_cors_origins_accepts_plain_strings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw: str, expected: list[str]
) -> None:
    for key in list(Settings.model_fields):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CORS_ORIGINS", raw)
    s = Settings(_env_file=tmp_path / "missing.env")  # type: ignore[call-arg]
    assert expected == s.CORS_ORIGINS


def test_default_without_any_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in list(Settings.model_fields):
        monkeypatch.delenv(key, raising=False)
    assert Settings(_env_file=tmp_path / "missing.env").CORS_ORIGINS == ["http://localhost:3000"]  # type: ignore[call-arg]
