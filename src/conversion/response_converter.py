import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import HTTPException, Request

from src.conversion.errors import ConversionError
from src.conversion.openai_stream_to_claude_state_machine import (
    OpenAIToClaudeStreamState,
    final_events,
    ingest_openai_chunk,
    initial_events,
    parse_openai_sse_line,
)
from src.core.config import config
from src.core.constants import Constants
from src.core.error_types import ErrorType
from src.core.logging import ConversationLogger
from src.core.metrics.runtime import get_request_tracker
from src.models.claude import ClaudeMessagesRequest

LOG_REQUEST_METRICS = config.log_request_metrics
conversation_logger = ConversationLogger.get_logger()
logger = logging.getLogger(__name__)

# Progress logging configuration
PROGRESS_LOG_INTERVAL_CHUNKS = 50


# =============================================================================
# Optional Feature Helpers (extracted for testability)
# =============================================================================


class _UsageTracker:
    """Tracks token usage during streaming.

    Orthogonal to conversion - can be enabled/disabled independently.
    """

    def __init__(self) -> None:
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cache_read_tokens: int = 0
        self.chunk_count: int = 0
        self._duration_ms: float | None = None

    def set_duration_ms(self, duration_ms: float) -> None:
        """Set the stream duration for completion logging."""
        self._duration_ms = duration_ms

    def update(self, chunk: dict[str, Any]) -> dict[str, int]:
        """Extract and return usage data from chunk."""
        self.chunk_count += 1
        usage = chunk.get("usage")
        if not usage:
            return {"input_tokens": 0, "output_tokens": 0}

        prompt_details = usage.get("prompt_tokens_details", {})
        cached_tokens = prompt_details.get("cached_tokens", 0) if prompt_details else 0

        self.input_tokens = usage.get("prompt_tokens", 0)
        self.output_tokens = usage.get("completion_tokens", 0)
        self.cache_read_tokens = cached_tokens

        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": cached_tokens,
        }

    def log_progress(self) -> None:
        """Log streaming progress periodically."""
        if self.chunk_count % PROGRESS_LOG_INTERVAL_CHUNKS == 0:
            conversation_logger.debug(
                f"🌊 STREAMING | Chunks: {self.chunk_count} | "
                f"Tokens so far: {self.input_tokens:,}→{self.output_tokens:,}"
            )

    def log_completion(self) -> None:
        """Log stream completion with final stats."""
        if self._duration_ms is not None:
            conversation_logger.info(
                f"✅ STREAM COMPLETE | Duration: {self._duration_ms:.0f}ms | "
                f"Chunks: {self.chunk_count} | "
                f"Tokens: {self.input_tokens:,}→{self.output_tokens:,} | "
                f"Cache: {self.cache_read_tokens:,}"
            )


class _CancellationChecker:
    """Handles client disconnection detection and cancellation.

    Orthogonal to conversion - only needed when http_request is available.
    """

    def __init__(self, http_request: Request, openai_client: Any, request_id: str, log: Any):
        self._http_request = http_request
        self._openai_client = openai_client
        self._request_id = request_id
        self._log = log

    async def check(self) -> bool:
        """Check if client disconnected. Returns True if cancellation occurred."""
        if await self._http_request.is_disconnected():
            self._log.info(f"Client disconnected, cancelling request {self._request_id}")
            self._openai_client.cancel_request(self._request_id)
            return True
        return False


def _build_sse_error(error_type: str, message: str) -> str:
    """Build a Server-Sent Event error payload.

    Centralized error formatting ensures consistent client experience.
    """
    error_event = {
        "type": "error",
        "error": {"type": error_type, "message": message},
    }
    return f"event: error\ndata: {json.dumps(error_event, ensure_ascii=False)}\n\n"


# =============================================================================
# Non-streaming converter (unchanged - no duplication here)
# =============================================================================


def convert_openai_to_claude_response(
    openai_response: dict,
    original_request: ClaudeMessagesRequest,
    tool_name_map_inverse: dict[str, str] | None = None,
) -> dict:
    """Convert OpenAI response to Claude format."""

    # Extract response data
    choices = openai_response.get("choices", [])
    if not choices:
        raise HTTPException(status_code=500, detail="No choices in OpenAI response")

    choice = choices[0]
    message = choice.get("message", {})

    # Extract reasoning_details for thought signatures if present
    reasoning_details = message.get("reasoning_details", [])

    # Build Claude content blocks
    content_blocks = []

    # Add text content
    text_content = message.get("content")
    if text_content is not None:
        content_blocks.append({"type": Constants.CONTENT_TEXT, "text": text_content})

    tool_name_map_inverse = tool_name_map_inverse or {}

    # Add tool calls
    tool_calls = message.get("tool_calls", []) or []
    for tool_call in tool_calls:
        if tool_call.get("type") == Constants.TOOL_FUNCTION:
            function_data = tool_call.get(Constants.TOOL_FUNCTION, {})
            try:
                arguments = json.loads(function_data.get("arguments", "{}"))
            except json.JSONDecodeError:
                arguments = {"raw_arguments": function_data.get("arguments", "")}

            sanitized_name = function_data.get("name", "")
            original_name = tool_name_map_inverse.get(sanitized_name, sanitized_name)

            content_blocks.append(
                {
                    "type": Constants.CONTENT_TOOL_USE,
                    "id": tool_call.get("id", f"tool_{uuid.uuid4()}"),
                    "name": original_name,
                    "input": arguments,
                }
            )

    # Ensure at least one content block
    if not content_blocks:
        content_blocks.append({"type": Constants.CONTENT_TEXT, "text": ""})

    # Map finish reason
    finish_reason = choice.get("finish_reason", "stop")
    stop_reason = {
        "stop": Constants.STOP_END_TURN,
        "length": Constants.STOP_MAX_TOKENS,
        "tool_calls": Constants.STOP_TOOL_USE,
        "function_call": Constants.STOP_TOOL_USE,
    }.get(finish_reason, Constants.STOP_END_TURN)

    # Build Claude response
    claude_response = {
        "id": openai_response.get("id", f"msg_{uuid.uuid4()}"),
        "type": "message",
        "role": Constants.ROLE_ASSISTANT,
        "model": original_request.model,
        "content": content_blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": openai_response.get("usage", {}).get("prompt_tokens", 0),
            "output_tokens": openai_response.get("usage", {}).get("completion_tokens", 0),
        },
    }

    # Pass through reasoning_details for middleware to process
    if reasoning_details:
        claude_response["reasoning_details"] = reasoning_details

    return claude_response


# =============================================================================
# Unified streaming converter (single function with optional features)
# =============================================================================


async def convert_openai_streaming_to_claude(
    openai_stream: Any,
    original_request: ClaudeMessagesRequest,
    logger: Any,
    tool_name_map_inverse: dict[str, str] | None = None,
    *,
    # Optional features via keyword-only parameters
    http_request: Request | None = None,
    openai_client: Any = None,
    request_id: str | None = None,
    metrics: Any = None,
    enable_usage_tracking: bool | None = None,
) -> AsyncGenerator[str, None]:
    """Convert OpenAI streaming response to Claude streaming format.

    This unified function supports both simple and cancellation-aware streaming
    through optional keyword-only parameters. The simple case (used in tests)
    requires only the first three positional arguments.

    Features enabled by optional parameters:
    - http_request + openai_client + request_id: Enables cancellation detection
    - metrics + request_id: Enables metrics tracking and logging
    - enable_usage_tracking: Explicit control (default: uses LOG_REQUEST_METRICS)

    Args:
        openai_stream: The OpenAI streaming response to convert.
        original_request: The original Claude request (for model name, etc.).
        logger: Logger instance for error reporting.
        tool_name_map_inverse: Inverse mapping for tool name sanitization.

    Keyword-only optional features:
        http_request: FastAPI Request object - enables cancellation detection.
        openai_client: OpenAI client - used to cancel requests on disconnect.
        request_id: Unique request identifier for logging and cancellation.
        metrics: Metrics object from request tracker (populated if provided).

    Yields:
        Server-Sent Event (SSE) formatted strings in Claude API format.

    Example:
        # Simple case (tests, no cancellation/metrics)
        stream = convert_openai_streaming_to_claude(openai_stream, request, logger)

        # Full-featured case (production)
        stream = convert_openai_streaming_to_claude(
            openai_stream,
            request,
            logger,
            tool_name_map_inverse=tool_map,
            http_request=http_req,
            openai_client=client,
            request_id=req_id,
            metrics=metrics,
        )
    """

    # -------------------------------------------------------------------------
    # Initialization (shared)
    # -------------------------------------------------------------------------
    message_id = f"msg_{uuid.uuid4().hex[:24]}"
    tool_name_map_inverse = tool_name_map_inverse or {}

    # Determine if usage tracking should be enabled
    # Priority: explicit param > global config
    # Note: metrics param only affects whether metrics are updated, not tracker creation
    should_track_usage = (
        enable_usage_tracking if enable_usage_tracking is not None else LOG_REQUEST_METRICS
    )

    # Initialize optional feature helpers
    usage_tracker = _UsageTracker() if should_track_usage else None
    cancellation_checker = (
        _CancellationChecker(http_request, openai_client, request_id, logger)
        if http_request and openai_client and request_id
        else None
    )

    # Get request metrics for updating (if enabled) - best-effort only
    if metrics is None and LOG_REQUEST_METRICS and http_request and request_id:
        tracker = get_request_tracker(http_request)
        try:
            metrics = await tracker.get_request(request_id)
        except Exception as e:
            logger.warning(
                f"Failed to fetch metrics for request {request_id}: {e}. "
                "Continuing without metrics."
            )

    # Send initial events
    for ev in initial_events(message_id=message_id, model=original_request.model):
        yield ev

    # Initialize conversion state machine
    state = OpenAIToClaudeStreamState(
        message_id=message_id,
        tool_name_map_inverse=tool_name_map_inverse,
    )

    usage_data = {"input_tokens": 0, "output_tokens": 0}

    # -------------------------------------------------------------------------
    # Stream processing loop (with optional features)
    # -------------------------------------------------------------------------
    try:
        async for line in openai_stream:
            # Optional: Check for client disconnection
            if cancellation_checker and await cancellation_checker.check():
                # Handle cancellation in-band: emit SSE error, update metrics, skip final events
                if metrics:
                    metrics.error = "Request cancelled by client"
                    metrics.error_type = ErrorType.CANCELLED
                logger.info(
                    f"Request {request_id or 'unknown'} was cancelled (client disconnected)"
                )
                yield _build_sse_error("cancelled", "Request was cancelled by client")
                return

            # Parse SSE line
            chunk = parse_openai_sse_line(line)
            if chunk is None:
                continue
            if chunk.get("_done"):
                break

            # Optional: Track usage and metrics
            if usage_tracker:
                try:
                    usage_data = usage_tracker.update(chunk)

                    # Update metrics if available
                    if metrics:
                        metrics.input_tokens = usage_data.get("input_tokens", 0)
                        metrics.output_tokens = usage_data.get("output_tokens", 0)
                        metrics.cache_read_tokens = usage_data.get("cache_read_input_tokens", 0)

                    # Log progress periodically
                    if LOG_REQUEST_METRICS:
                        usage_tracker.log_progress()

                except ConversionError:
                    raise
                except Exception:
                    # Don't let usage parsing kill the stream
                    logger.exception(
                        "Streaming usage accounting error at chunk %d. Usage field: %s",
                        usage_tracker.chunk_count if usage_tracker else 0,
                        chunk.get("usage") if chunk else None,
                    )

            # Convert and yield Claude-formatted events
            for out in ingest_openai_chunk(state, chunk):
                yield out

            # Check for stream completion
            choices = chunk.get("choices", [])
            if choices and choices[0].get("finish_reason"):
                break

    # -------------------------------------------------------------------------
    # Error handling (with optional metrics updates)
    # -------------------------------------------------------------------------
    except HTTPException as e:
        # Cancellation is now handled in-band (see loop above), so 499 should not reach here.
        # If it does (e.g., from deeper layers), log and propagate as non-cancellation error.
        if metrics:
            metrics.error = f"HTTP exception: {e.detail}"
            metrics.error_type = ErrorType.HTTP_ERROR
        raise

    except ConversionError as e:
        if metrics:
            metrics.error = e.message
            metrics.error_type = e.error_type
        logger.error("Streaming conversion error: %s", e)
        yield _build_sse_error(e.error_type, e.message)
        return

    except Exception as e:
        if metrics:
            metrics.error = f"Streaming error: {str(e)}"
            metrics.error_type = ErrorType.STREAMING_ERROR
        logger.exception("Streaming error")
        yield _build_sse_error("api_error", f"Streaming error: {str(e)}")
        return

    # -------------------------------------------------------------------------
    # Final events and logging (with optional metrics)
    # -------------------------------------------------------------------------
    for ev in final_events(state, usage=usage_data):
        yield ev

    # Optional: Log stream completion
    if metrics and usage_tracker:
        usage_tracker.set_duration_ms(metrics.duration_ms)
        usage_tracker.log_completion()
