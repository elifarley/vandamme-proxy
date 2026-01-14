"""Error handling services for API endpoints.

This module provides utilities for handling errors and finalizing metrics
in streaming and non-streaming contexts.
"""

import logging
import traceback
from typing import Any

from fastapi.responses import JSONResponse

from src.core.error_types import ErrorType

logger = logging.getLogger(__name__)


async def finalize_metrics_on_streaming_error(
    *,
    metrics: Any | None,
    error: str,
    tracker: Any,
    request_id: str,
) -> None:
    """Finalize metrics when a streaming error occurs.

    Args:
        metrics: The metrics object to update (may be None if disabled).
        error: The error message to record.
        tracker: The request tracker for ending the request.
        request_id: The unique request identifier.
    """
    if metrics:
        metrics.error = error
        metrics.error_type = ErrorType.API_ERROR
        metrics.end_time = __import__("time").time()
        await tracker.end_request(request_id)


def _log_traceback(log: Any = logger) -> None:
    """Log full traceback for debugging.

    This utility centralizes the traceback logging pattern.

    Args:
        log: The logger to use (defaults to module logger).
    """
    log.error(traceback.format_exc())


def build_streaming_error_response(
    *,
    exception: Exception,
    openai_client: Any,
    metrics: Any | None,
    tracker: Any,
    request_id: str,
) -> JSONResponse:
    """Build standardized error response for streaming failures.

    This function handles HTTPException errors that occur during streaming,
    finalizes metrics, and returns a properly formatted error response.

    Args:
        exception: The HTTPException that occurred.
        openai_client: The OpenAI client for error classification.
        metrics: The metrics object to update (may be None if disabled).
        tracker: The request tracker for ending the request.
        request_id: The unique request identifier.

    Returns:
        A JSONResponse with the error details.
    """
    # Finalize metrics
    if metrics:
        metrics.error = exception.detail if hasattr(exception, "detail") else str(exception)
        metrics.error_type = ErrorType.API_ERROR
        metrics.end_time = __import__("time").time()
        # Note: We can't await here because this is a sync function

    logger.error(
        f"Streaming error: {exception.detail if hasattr(exception, 'detail') else exception}"
    )
    _log_traceback()

    error_message = openai_client.classify_openai_error(
        exception.detail if hasattr(exception, "detail") else str(exception)
    )
    error_response = {
        "type": "error",
        "error": {"type": "api_error", "message": error_message},
    }
    status_code = exception.status_code if hasattr(exception, "status_code") else 500
    return JSONResponse(status_code=status_code, content=error_response)
