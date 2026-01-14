from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse

from src.core.error_types import ErrorType
from src.core.logging import ConversationLogger
from src.core.metrics.runtime import get_request_tracker

AnySseStream = AsyncGenerator[str, None] | Any

conversation_logger = ConversationLogger.get_logger()


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


def _format_sse_error_event(
    *,
    message: str,
    error_type: ErrorType = ErrorType.UPSTREAM_TIMEOUT,
    code: str = "read_timeout",
    suggestion: str | None = None,
) -> str:
    """Format an error event as OpenAI-style SSE.

    Args:
        message: Human-readable error message.
        error_type: Error type/category (e.g., "upstream_timeout").
        code: Error code (e.g., "read_timeout").
        suggestion: Optional actionable suggestion for the user.

    Returns:
        A string containing the SSE-formatted error event.
    """
    error_payload: dict[str, Any] = {
        "error": {
            "message": message,
            "type": error_type.value,
            "code": code,
        }
    }
    if suggestion:
        error_payload["error"]["suggestion"] = suggestion

    return f"data: {__import__('json').dumps(error_payload, ensure_ascii=False)}\n\n"


def with_sse_error_handler(
    *,
    original_stream: AsyncGenerator[str, None],
    request_id: str,
    provider_name: str | None = None,
) -> AsyncGenerator[str, None]:
    """Wrap a streaming generator to gracefully handle errors mid-stream.

    This prevents FastAPI from logging "response already started" errors by:
    - Catching exceptions raised after SSE streaming has begun
    - Emitting a warning log with request details
    - Yielding an OpenAI-style error event to the client
    - Yielding [DONE] and terminating cleanly

    Args:
        original_stream: The original streaming generator to wrap.
        request_id: Unique request ID for logging/tracking.
        provider_name: Optional upstream provider name for logging.

    Yields:
        SSE-formatted strings (chunks from original stream, or error event + [DONE]).
    """

    async def _wrapped() -> AsyncGenerator[str, None]:
        try:
            async for chunk in original_stream:
                yield chunk
        except httpx.ReadTimeout as e:
            provider_info = f" (provider={provider_name})" if provider_name else ""
            conversation_logger.warning(
                f"[{request_id}] Upstream read timeout{provider_info}: {e}. "
                f"Consider increasing REQUEST_TIMEOUT and/or "
                f"STREAMING_READ_TIMEOUT_SECONDS"
            )
            yield _format_sse_error_event(
                message=f"Upstream read timeout: {str(e)}",
                error_type=ErrorType.UPSTREAM_TIMEOUT,
                code="read_timeout",
                suggestion=(
                    "Consider increasing REQUEST_TIMEOUT and/or STREAMING_READ_TIMEOUT_SECONDS"
                ),
            )
            yield "data: [DONE]\n\n"
        except httpx.TimeoutException as e:
            provider_info = f" (provider={provider_name})" if provider_name else ""
            conversation_logger.warning(
                f"[{request_id}] Upstream timeout{provider_info}: {e}. "
                f"Consider increasing REQUEST_TIMEOUT and/or "
                f"STREAMING_READ_TIMEOUT_SECONDS"
            )
            yield _format_sse_error_event(
                message=f"Upstream timeout: {str(e)}",
                error_type=ErrorType.UPSTREAM_TIMEOUT,
                code="timeout",
                suggestion=(
                    "Consider increasing REQUEST_TIMEOUT and/or STREAMING_READ_TIMEOUT_SECONDS"
                ),
            )
            yield "data: [DONE]\n\n"
        except httpx.HTTPStatusError as e:
            provider_info = f" (provider={provider_name})" if provider_name else ""
            try:
                error_detail = e.response.json() if e.response.content else str(e)
            except Exception:
                error_detail = str(e)
            conversation_logger.warning(
                f"[{request_id}] Upstream HTTP error{provider_info}: "
                f"status={e.response.status_code} detail={error_detail}"
            )
            yield _format_sse_error_event(
                message=f"Upstream HTTP error: status {e.response.status_code}",
                error_type=ErrorType.UPSTREAM_HTTP_ERROR,
                code=f"http_{e.response.status_code}",
                suggestion=None,
            )
            yield "data: [DONE]\n\n"
        except Exception as e:
            provider_info = f" (provider={provider_name})" if provider_name else ""
            conversation_logger.warning(
                f"[{request_id}] Streaming error{provider_info}: {type(e).__name__}: {e}"
            )
            yield _format_sse_error_event(
                message=f"Streaming error: {type(e).__name__}: {str(e)}",
                error_type=ErrorType.STREAMING_ERROR,
                code="stream_error",
                suggestion=None,
            )
            yield "data: [DONE]\n\n"

    return _wrapped()


def with_streaming_error_handling(
    *,
    original_stream: AsyncGenerator[str, None],
    http_request: Request,
    request_id: str,
    provider_name: str | None = None,
    metrics_enabled: bool,
) -> AsyncGenerator[str, None]:
    """Combine error handling and metrics finalization for streaming responses.

    This composes:
    1. SSE error handling (with_sse_error_handler)
    2. Metrics finalization (with_streaming_metrics_finalizer)

    The metrics finalizer runs in a finally block, so it executes regardless of
    whether the stream completes normally or encounters an error.

    Args:
        original_stream: The original streaming generator.
        http_request: FastAPI Request object for metrics tracking.
        request_id: Unique request ID.
        provider_name: Optional upstream provider name for logging.
        metrics_enabled: Whether metrics collection is enabled.

    Yields:
        SSE-formatted strings with error handling and metrics finalization.
    """

    async def _wrapped() -> AsyncGenerator[str, None]:
        # Apply error handling first (inner layer)
        error_handled_stream = with_sse_error_handler(
            original_stream=original_stream,
            request_id=request_id,
            provider_name=provider_name,
        )
        # Then apply metrics finalization (outer layer, in finally)
        metrics_finalized_stream = with_streaming_metrics_finalizer(
            original_stream=error_handled_stream,
            http_request=http_request,
            request_id=request_id,
            enabled=metrics_enabled,
        )
        async for chunk in metrics_finalized_stream:
            yield chunk

    return _wrapped()
