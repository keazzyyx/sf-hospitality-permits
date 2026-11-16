"""FastAPI dependencies (overridable in tests)."""

from __future__ import annotations

import logging
from functools import lru_cache

from anthropic import AsyncAnthropic
from precedent.geocode import Geocoder
from precedent.store import Store

from app.agents.memo_runner import MemoRunner
from app.agents.runner import AgentRunner
from app.catalog.loader import get_catalog
from app.core.config import Settings, get_settings
from app.memo.context import get_geocoder as _context_geocoder
from app.memo.context import get_store as _context_store
from app.services.db import Database, MemoryDatabase, SupabaseDatabase
from app.services.memos import MemoService
from app.services.plans import PlanService

log = logging.getLogger(__name__)


@lru_cache
def _db_singleton() -> Database:
    settings = get_settings()
    if settings.supabase_configured:
        return SupabaseDatabase(settings)
    if settings.is_production:
        raise RuntimeError("Supabase must be configured in production")
    log.warning("SUPABASE not configured: using in-memory database (development only)")
    return MemoryDatabase()


def get_db() -> Database:
    return _db_singleton()


def get_plan_service() -> PlanService:
    return PlanService(get_db(), get_settings())


def get_memo_service() -> MemoService:
    return MemoService(get_db(), get_settings())


@lru_cache
def _anthropic_client() -> AsyncAnthropic:
    settings: Settings = get_settings()
    # Reads ANTHROPIC_API_KEY from env when api_key is None. The Neatlogs instrumentation wraps
    # this client because `neatlogs.init()` ran before `anthropic` was imported (see app/main.py).
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=2, timeout=120.0)


def get_runner() -> AgentRunner:
    return AgentRunner(_anthropic_client(), get_catalog(), get_settings())


def get_store() -> Store:
    return _context_store()


def get_geocoder() -> Geocoder:
    return _context_geocoder()


def get_memo_runner() -> MemoRunner:
    return MemoRunner(_anthropic_client(), get_catalog(), get_settings(), get_store(), get_geocoder())
