from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from src.core.metrics.runtime import get_request_tracker

AnySseStream = AsyncGenerator[str, None] | Any


def sse_headers() -> dict[str, str]:
    # Centralize the SSE header contract used throughout the proxy.
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "*",
    }


def streaming_response(
    *,
    stream: AnySseStream,
    headers: dict[str, str] | None = None,
) -> StreamingResponse:
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers=headers or sse_headers(),
    )


async def _end_metrics_if_enabled(*, http_request: Request, request_id: str, enabled: bool) -> None:
    if not enabled:
        return
    tracker = get_request_tracker(http_request)
    await tracker.end_request(request_id)


def with_streaming_metrics_finalizer(
    *,
    original_stream: AsyncGenerator[str, None],
    http_request: Request,
    request_id: str,
    enabled: bool,
) -> AsyncGenerator[str, None]:
    """Ensure request metrics are finalized when a stream ends.

    This wrapper is intentionally simple and does not alter the stream content.
    """

    async def _wrapped() -> AsyncGenerator[str, None]:
        try:
            async for chunk in original_stream:
                yield chunk
        finally:
            await _end_metrics_if_enabled(
                http_request=http_request,
                request_id=request_id,
                enabled=enabled,
            )

    return _wrapped()
