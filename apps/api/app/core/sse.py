"""Server-Sent Events helpers with keepalive comments so proxies do not drop long LLM pauses."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi.responses import StreamingResponse

KEEPALIVE_SECONDS = 15.0


def format_event(event: str, data: Any) -> str:
    payload = json.dumps(data, default=str, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


async def with_keepalive(
    source: AsyncIterator[str], interval: float = KEEPALIVE_SECONDS
) -> AsyncIterator[str]:
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def pump() -> None:
        try:
            async for chunk in source:
                await queue.put(chunk)
        finally:
            await queue.put(None)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=interval)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if item is None:
                break
            yield item
    finally:
        if not task.done():
            task.cancel()


def sse_response(source: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        with_keepalive(source),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
