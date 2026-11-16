"""Application settings. This module must stay free of `anthropic` imports:
`app.main` imports it *before* `neatlogs.init()` runs."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

API_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = API_DIR.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", str(API_DIR / ".env")), extra="ignore")

    ENV: str = "development"
    GIT_SHA: str = "dev"
    LOG_LEVEL: str = "INFO"
    PORT: int = 8000

    # Observability (Neatlogs). The key is never logged.
    NEATLOGS_API_KEY: str | None = None
    NEATLOGS_ENDPOINT: str | None = None

    # Model layer (Anthropic only).
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL_MAIN: str = "claude-sonnet-4-5"
    ANTHROPIC_MODEL_TRIAGE: str = "claude-haiku-4-5"
    ANTHROPIC_MAX_TOOL_TURNS: int = 8
    # Forced `tool_choice` to the submit tool is accepted by the 4.x models above. Newer
    # generations (Opus 5.5 / Sonnet 5.5 / Fable) reject forced tool_choice with a 400;
    # set this to false there and the runner steers with `auto` + instructions instead.
    ANTHROPIC_FORCE_TOOL_CHOICE: bool = True

    # Supabase (service role is used server-side only; JWT verified on every route).
    SUPABASE_URL: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    SUPABASE_JWT_SECRET: str | None = None
    SUPABASE_JWT_AUDIENCE: str = "authenticated"

    # Billing
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_PLAN: str | None = None  # $29 one-time
    STRIPE_PRICE_SUBSCRIPTION: str | None = None  # $49 / month
    FREE_PLAN_LIMIT: int = 3

    # Web
    WEB_URL: str = "http://localhost:3000"
    # Plain comma-separated string in env/.env (NoDecode stops pydantic-settings from JSON-decoding it).
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Location Risk Memo / precedent data layer
    PRECEDENT_DATABASE_URL: str | None = (
        None  # PostGIS (Supabase direct/pooler URL); None → local JSONL store
    )
    PRECEDENT_DATA_DIR: Path = REPO_ROOT / "data"
    MEMO_COVERAGE_CITIES: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["san_francisco"])
    FREE_TEASER_LIMIT: int = 2
    STRIPE_PRICE_MEMO: str | None = None  # $499 one-time Operator memo
    STRIPE_PRICE_PRO: str | None = None  # $299 / month Pro
    ADMIN_EMAILS: Annotated[list[str], NoDecode] = Field(default_factory=list)
    RESEND_API_KEY: str | None = None
    # The extracted opposition flag stays out of tools and reports until it passes a 30-row check of its readings with
    # 27+ right (validation 2026-11-09: 13 of 30). Flip only after re-validating.
    REPORT_OPPOSITION_FLAG: bool = False
    FEEDBACK_FROM_EMAIL: str | None = (
        None  # e.g. "Permit Memo <memos@your-verified-domain>"; must be on a Resend-verified domain
    )
    FEEDBACK_TOKEN_SECRET: str | None = None  # falls back to SUPABASE_JWT_SECRET
    FEEDBACK_DELAY_DAYS: int = 90
    GEOCODE_RATE_LIMIT_PER_MINUTE: int = 60

    # Misc
    CATALOG_DIR: Path = REPO_ROOT / "packages" / "catalog" / "data"
    PREVIEW_RATE_LIMIT_PER_HOUR: int = 10
    LEADS_RATE_LIMIT_PER_HOUR: int = 20
    # answer rounds on a memo (POST /v1/memos/{id}/answers), per signed-in account
    MEMO_ANSWERS_RATE_LIMIT_PER_HOUR: int = 20
    WEB_VERIFY_ENABLED: bool = True
    WEB_VERIFY_TIMEOUT_SECONDS: float = 6.0
    USER_ID_HASH_SALT: str = "change-me"
    # The product name in reports, PDFs, e-mails and the API title (a placeholder; the web app's is
    # apps/web/src/lib/brand.ts)
    APP_NAME: str = "Permit Memo"

    @field_validator("CORS_ORIGINS", "MEMO_COVERAGE_CITIES", "ADMIN_EMAILS", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            text = v.strip()
            if text.startswith("["):  # a JSON list is accepted too
                import json

                return json.loads(text)
            return [
                o.strip().rstrip("/").lower() if "@" in o else o.strip().rstrip("/")
                for o in text.split(",")
                if o.strip()
            ]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() in {"production", "prod"}

    @property
    def supabase_configured(self) -> bool:
        return bool(self.SUPABASE_URL and self.SUPABASE_SERVICE_ROLE_KEY)

    @property
    def feedback_secret(self) -> str | None:
        return self.FEEDBACK_TOKEN_SECRET or self.SUPABASE_JWT_SECRET

    @property
    def memo_billing_configured(self) -> bool:
        return bool(self.STRIPE_SECRET_KEY and self.STRIPE_PRICE_MEMO and self.STRIPE_PRICE_PRO)

    @property
    def stripe_configured(self) -> bool:
        return bool(self.STRIPE_SECRET_KEY and self.STRIPE_PRICE_PLAN and self.STRIPE_PRICE_SUBSCRIPTION)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
