"""Process-wide precedent store + geocoder singletons (kept out of app.deps to avoid import cycles)."""

from __future__ import annotations

import logging
from functools import lru_cache

from precedent.geocode import Geocoder
from precedent.store import Store, open_store

from app.core.config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def _store_singleton() -> Store:
    settings = get_settings()
    if not settings.PRECEDENT_DATABASE_URL:
        log.warning(
            "PRECEDENT_DATABASE_URL not set: memo tools use the local JSONL store at %s",
            settings.PRECEDENT_DATA_DIR,
        )
    return open_store(settings.PRECEDENT_DATABASE_URL, str(settings.PRECEDENT_DATA_DIR))


def get_store() -> Store:
    return _store_singleton()


@lru_cache
def _geocoder_singleton() -> Geocoder:
    from precedent.geocode_sf import SFGeocoder

    return SFGeocoder()


def get_geocoder() -> Geocoder:
    return _geocoder_singleton()
