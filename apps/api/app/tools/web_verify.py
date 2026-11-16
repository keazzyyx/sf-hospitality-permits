"""web_verify: confirm a permit's application_url is live. Results cached in-process for 24h."""

from __future__ import annotations

import datetime as dt
import time
from typing import Literal

import httpx
import neatlogs
from pydantic import BaseModel, Field

from app.catalog.loader import get_catalog
from app.core.config import settings
from app.tools.base import ToolExecutionError, ToolSpec

UrlStatus = Literal["live", "dead", "unchecked"]
_CACHE: dict[str, tuple[float, VerifyOutput]] = {}
_TTL = 24 * 3600
_UA = "Mozilla/5.0 (compatible; permit-link-check/1.0)"


class VerifyInput(BaseModel):
    permit_id: str = Field(description="Catalog permit id whose application_url should be checked.")


class VerifyOutput(BaseModel):
    permit_id: str
    url: str
    status: UrlStatus
    http_status: int | None
    final_url: str | None
    checked_at: str
    detail: str


async def verify_url(permit_id: str, url: str, *, client: httpx.AsyncClient | None = None) -> VerifyOutput:
    now = time.monotonic()
    cached = _CACHE.get(permit_id)
    if cached and now - cached[0] < _TTL:
        return cached[1]
    checked_at = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    if not settings.WEB_VERIFY_ENABLED:
        return VerifyOutput(
            permit_id=permit_id,
            url=url,
            status="unchecked",
            http_status=None,
            final_url=None,
            checked_at=checked_at,
            detail="link checking disabled",
        )
    own = client is None
    client = client or httpx.AsyncClient(
        timeout=settings.WEB_VERIFY_TIMEOUT_SECONDS, follow_redirects=True, headers={"User-Agent": _UA}
    )
    try:
        try:
            resp = await client.head(url)
            if resp.status_code in (405, 403, 404, 501) or resp.status_code >= 500:
                resp = await client.get(url)
        except httpx.HTTPError:
            resp = await client.get(url)
        live = resp.status_code < 400
        out = VerifyOutput(
            permit_id=permit_id,
            url=url,
            status="live" if live else "dead",
            http_status=resp.status_code,
            final_url=str(resp.url),
            checked_at=checked_at,
            detail="ok" if live else f"HTTP {resp.status_code}",
        )
    except httpx.HTTPError as exc:
        out = VerifyOutput(
            permit_id=permit_id,
            url=url,
            status="dead",
            http_status=None,
            final_url=None,
            checked_at=checked_at,
            detail=f"{type(exc).__name__}",
        )
    finally:
        if own:
            await client.aclose()
    _CACHE[permit_id] = (now, out)
    return out


def clear_cache() -> None:
    _CACHE.clear()


@neatlogs.span(kind="TOOL", name="tool.web_verify")
async def _verify_tool(inp: BaseModel) -> BaseModel:
    assert isinstance(inp, VerifyInput)
    permit = get_catalog().get(inp.permit_id)
    if permit is None:
        raise ToolExecutionError("unknown_permit_id", f"Not in catalog: {inp.permit_id}")
    return await verify_url(permit.id, permit.application_url)


WEB_VERIFY = ToolSpec(
    name="web_verify",
    description="Fetch a permit's application_url and report whether it is live (HTTP < 400). Flags dead links.",
    input_model=VerifyInput,
    handler=_verify_tool,
)
