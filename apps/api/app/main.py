"""Permit Memo API entry point.

IMPORTANT: `neatlogs.init()` must run before anything imports `anthropic` (directly or through
app.agents / app.tools / app.routes / app.deps) so the Anthropic client is instrumented.
`tests/test_import_order.py` enforces this.
"""

import neatlogs

from app.core.config import settings
from app.core.observability import mask_pii

neatlogs.init(
    api_key=settings.NEATLOGS_API_KEY,
    endpoint=settings.NEATLOGS_ENDPOINT,
    workflow_name="permit_memo",
    instrumentations=["anthropic"],
    tags=[f"env:{settings.ENV}", f"version:{settings.GIT_SHA}"],
    mask=mask_pii,
    disable_export=not settings.NEATLOGS_API_KEY,
)

# ruff: noqa: E402  (imports below intentionally follow neatlogs.init)
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.catalog.loader import get_catalog
from app.core.errors import install_error_handlers
from app.routes import billing, memos, misc, plans, preview, public_memo

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("permit_memo")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    catalog = get_catalog()
    log.info(
        "permit_memo api starting env=%s version=%s catalog=%d permits neatlogs=%s",
        settings.ENV,
        settings.GIT_SHA,
        len(catalog.permits),
        "on" if settings.NEATLOGS_API_KEY else "off (no key)",
    )
    if not settings.ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY is not set: plan generation will fail until it is configured")
    try:
        yield
    finally:
        # Server mode: one init at startup, one flush + shutdown here. Never per request.
        neatlogs.flush(timeout_millis=10_000)
        neatlogs.shutdown(timeout_millis=10_000)
        log.info("permit_memo api stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.APP_NAME} API",
        version=settings.GIT_SHA,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Stripe-Signature"],
    )
    install_error_handlers(app)
    app.include_router(misc.router)
    app.include_router(preview.router)
    app.include_router(plans.router)
    app.include_router(billing.router)
    app.include_router(memos.router)
    app.include_router(public_memo.router)
    return app


app = create_app()
