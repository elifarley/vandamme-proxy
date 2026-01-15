"""Error handling services for API endpoints.

This module provides utilities for handling errors and finalizing metrics
in streaming and non-streaming contexts.
"""

import logging
import traceback
from dataclasses import dataclass
from typing import Any

from fastapi.responses import JSONResponse

from src.core.error_types import ErrorType

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ErrorResponseBuilder:
    """Centralized builder for consistent error responses across all endpoints.

    Provides type-safe methods for constructing error responses with
    consistent structure and status codes.

    Error response format:
    {
        "type": "error",
        "error": {
            "type": "<error_type>",
            "message": "<error_message>"
        }
    }
    """

    @staticmethod
    def not_found(resource: str, identifier: str) -> JSONResponse:
        """Build a 404 Not Found error response.

        Args:
            resource: The type of resource that was not found (e.g., "Provider", "Model")
            identifier: The specific identifier that was not found

        Returns:
            JSONResponse with 404 status and error details
        """
        message = f"{resource} '{identifier}' not found"
        return JSONResponse(
            status_code=404,
            content={
                "type": "error",
                "error": {
                    "type": "not_found",
                    "message": message,
                },
            },
        )

    @staticmethod
    def invalid_parameter(name: str, reason: str, value: Any | None = None) -> JSONResponse:
        """Build a 400 Bad Request error response for invalid parameters.

        Args:
            name: The parameter name that is invalid
            reason: Description of why the parameter is invalid
            value: Optional invalid value (will be converted to string)

        Returns:
            JSONResponse with 400 status and error details
        """
        message = f"Invalid parameter '{name}': {reason}"
        if value is not None:
            message += f" (got: {value!r})"
        return JSONResponse(
            status_code=400,
            content={
                "type": "error",
                "error": {
                    "type": "invalid_parameter",
                    "message": message,
                },
            },
        )

    @staticmethod
    def unauthorized(message: str = "Authentication required") -> JSONResponse:
        """Build a 401 Unauthorized error response.

        Args:
            message: Optional custom error message

        Returns:
            JSONResponse with 401 status and error details
        """
        return JSONResponse(
            status_code=401,
            content={
                "type": "error",
                "error": {
                    "type": "unauthorized",
                    "message": message,
                },
            },
        )

    @staticmethod
    def forbidden(message: str = "Access denied") -> JSONResponse:
        """Build a 403 Forbidden error response.

        Args:
            message: Optional custom error message

        Returns:
            JSONResponse with 403 status and error details
        """
        return JSONResponse(
            status_code=403,
            content={
                "type": "error",
                "error": {
                    "type": "forbidden",
                    "message": message,
                },
            },
        )

    @staticmethod
    def upstream_error(exception: Exception, context: str | None = None) -> JSONResponse:
        """Build a 502 Bad Gateway or 504 Gateway Timeout error response.

        Automatically detects timeout errors and returns appropriate status code.

        Args:
            exception: The upstream exception
            context: Optional context about what operation failed

        Returns:
            JSONResponse with appropriate status code and error details
        """
        import httpx

        # Detect timeout errors
        if isinstance(exception, httpx.TimeoutException):
            message = "Upstream request timed out"
            if context:
                message += f" while {context}"
            message += ". Consider increasing REQUEST_TIMEOUT."
            return JSONResponse(
                status_code=504,
                content={
                    "type": "error",
                    "error": {
                        "type": "upstream_timeout",
                        "message": message,
                    },
                },
            )

        # Generic upstream error
        message = "Upstream service error"
        if context:
            message += f" while {context}"
        return JSONResponse(
            status_code=502,
            content={
                "type": "error",
                "error": {
                    "type": "upstream_error",
                    "message": message,
                    "details": str(exception),
                },
            },
        )

    @staticmethod
    def internal_error(
        message: str, error_type: str = "internal_error", details: Any | None = None
    ) -> JSONResponse:
        """Build a 500 Internal Server Error response.

        Args:
            message: Human-readable error message
            error_type: Specific error type for classification
            details: Optional additional error details

        Returns:
            JSONResponse with 500 status and error details
        """
        content: dict[str, Any] = {
            "type": "error",
            "error": {
                "type": error_type,
                "message": message,
            },
        }
        if details is not None:
            content["error"]["details"] = details
        return JSONResponse(status_code=500, content=content)

    @staticmethod
    def service_unavailable(message: str = "Service temporarily unavailable") -> JSONResponse:
        """Build a 503 Service Unavailable error response.

        Args:
            message: Optional custom error message

        Returns:
            JSONResponse with 503 status and error details
        """
        return JSONResponse(
            status_code=503,
            content={
                "type": "error",
                "error": {
                    "type": "service_unavailable",
                    "message": message,
                },
            },
        )


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
