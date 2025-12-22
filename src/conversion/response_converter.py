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
from src.core.logging import ConversationLogger
from src.core.metrics.runtime import get_request_tracker
from src.models.claude import ClaudeMessagesRequest

LOG_REQUEST_METRICS = config.log_request_metrics
conversation_logger = ConversationLogger.get_logger()
logger = logging.getLogger(__name__)


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


async def convert_openai_streaming_to_claude(
    openai_stream: Any,
    original_request: ClaudeMessagesRequest,
    logger: Any,
    tool_name_map_inverse: dict[str, str] | None = None,
) -> AsyncGenerator[str, None]:
    """Convert OpenAI streaming response to Claude streaming format."""

    message_id = f"msg_{uuid.uuid4().hex[:24]}"
    tool_name_map_inverse = tool_name_map_inverse or {}

    for ev in initial_events(message_id=message_id, model=original_request.model):
        yield ev

    state = OpenAIToClaudeStreamState(
        message_id=message_id,
        tool_name_map_inverse=tool_name_map_inverse,
    )

    try:
        async for line in openai_stream:
            chunk = parse_openai_sse_line(line)
            if chunk is None:
                continue
            if chunk.get("_done"):
                break

            for out in ingest_openai_chunk(state, chunk):
                yield out

            # If the upstream signals a finish_reason we stop consuming further chunks.
            choices = chunk.get("choices", [])
            if choices and choices[0].get("finish_reason"):
                break

    except ConversionError as e:
        logger.error("Streaming conversion error: %s", e)
        error_event = {"type": "error", "error": {"type": e.error_type, "message": e.message}}
        yield f"event: error\ndata: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        return

    except Exception as e:
        # Unexpected streaming errors: keep client-visible shape stable.
        logger.exception("Streaming error")
        error_event = {
            "type": "error",
            "error": {"type": "api_error", "message": f"Streaming error: {str(e)}"},
        }
        yield f"event: error\ndata: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        return

    for ev in final_events(state, usage={"input_tokens": 0, "output_tokens": 0}):
        yield ev


async def convert_openai_streaming_to_claude_with_cancellation(
    openai_stream: Any,
    original_request: ClaudeMessagesRequest,
    logger: Any,
    http_request: Request,
    openai_client: Any,
    request_id: str,
    tool_name_map_inverse: dict[str, str] | None = None,
) -> AsyncGenerator[str, None]:
    """Convert OpenAI streaming response to Claude streaming format with cancellation support."""

    message_id = f"msg_{uuid.uuid4().hex[:24]}"

    # Get request metrics for updating
    metrics = None
    if LOG_REQUEST_METRICS:
        tracker = get_request_tracker(http_request)
        metrics = await tracker.get_request(request_id)

    # Initialize tracking variables
    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    chunk_count = 0

    tool_name_map_inverse = tool_name_map_inverse or {}

    for ev in initial_events(message_id=message_id, model=original_request.model):
        yield ev

    state = OpenAIToClaudeStreamState(
        message_id=message_id,
        tool_name_map_inverse=tool_name_map_inverse,
    )

    usage_data = {"input_tokens": 0, "output_tokens": 0}

    # The cancellation path historically used local counters and allocators. After refactoring,
    # the conversion state lives on `state`. Keep locals only where the cancellation path still
    # needs them (e.g., usage accounting).

    try:
        async for line in openai_stream:
            # Check if client disconnected
            if await http_request.is_disconnected():
                logger.info(f"Client disconnected, cancelling request {request_id}")
                openai_client.cancel_request(request_id)
                break

            chunk = parse_openai_sse_line(line)
            if chunk is None:
                continue
            if chunk.get("_done"):
                break

            try:
                chunk_count += 1

                # Usage accounting is orthogonal to conversion; keep it here.
                usage = chunk.get("usage", None)
                if usage:
                    cache_read_input_tokens = 0
                    prompt_tokens_details = usage.get("prompt_tokens_details", {})
                    if prompt_tokens_details:
                        cache_read_input_tokens = prompt_tokens_details.get("cached_tokens", 0)

                    input_tokens = usage.get("prompt_tokens", 0)
                    output_tokens = usage.get("completion_tokens", 0)
                    cache_read_tokens = cache_read_input_tokens

                    usage_data = {
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cache_read_input_tokens": cache_read_input_tokens,
                    }

                    # Update metrics if available
                    if LOG_REQUEST_METRICS and metrics:
                        metrics.input_tokens = input_tokens
                        metrics.output_tokens = output_tokens
                        metrics.cache_read_tokens = cache_read_tokens

                choices = chunk.get("choices", [])
                if not choices:
                    continue

                # Log streaming progress every 50 chunks
                if LOG_REQUEST_METRICS and chunk_count % 50 == 0:
                    conversation_logger.debug(
                        f"🌊 STREAMING | Chunks: {chunk_count} | "
                        f"Tokens so far: {input_tokens:,}→{output_tokens:,}"
                    )

            except ConversionError:
                raise
            except Exception:
                # We keep conversion errors typed, but don't let usage parsing kill the stream.
                # This path is for unexpected shapes in usage fields.
                logger.exception("Streaming usage accounting error")

            for out in ingest_openai_chunk(state, chunk):
                yield out

            finish_reason = choices[0].get("finish_reason") if choices else None
            if finish_reason:
                break

            # Continue streaming
            continue

    except HTTPException as e:
        # Preserve existing cancellation behavior.
        if e.status_code == 499:
            if LOG_REQUEST_METRICS and metrics:
                metrics.error = "Request cancelled by client"
                metrics.error_type = "cancelled"
            logger.info(f"Request {request_id} was cancelled")
            error_event = {
                "type": "error",
                "error": {"type": "cancelled", "message": "Request was cancelled by client"},
            }
            yield f"event: error\ndata: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            return

        if LOG_REQUEST_METRICS and metrics:
            metrics.error = f"HTTP exception: {e.detail}"
            metrics.error_type = "http_error"
        raise

    except ConversionError as e:
        if LOG_REQUEST_METRICS and metrics:
            metrics.error = e.message
            metrics.error_type = e.error_type
        logger.error("Streaming conversion error: %s", e)
        error_event = {"type": "error", "error": {"type": e.error_type, "message": e.message}}
        yield f"event: error\ndata: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        return

    except Exception as e:
        # Unexpected streaming errors: keep client-visible shape stable.
        if LOG_REQUEST_METRICS and metrics:
            metrics.error = f"Streaming error: {str(e)}"
            metrics.error_type = "streaming_error"
        logger.exception("Streaming error")
        error_event = {
            "type": "error",
            "error": {"type": "api_error", "message": f"Streaming error: {str(e)}"},
        }
        yield f"event: error\ndata: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        return

    # Send final SSE events (reuse the shared state machine implementation).
    # In the cancellation-aware path we include usage in message_delta.
    for ev in final_events(state, usage=usage_data):
        yield ev

    # Log streaming completion
    if LOG_REQUEST_METRICS and metrics:
        duration_ms = metrics.duration_ms
        conversation_logger.info(
            f"✅ STREAM COMPLETE | Duration: {duration_ms:.0f}ms | "
            f"Chunks: {chunk_count} | "
            f"Tokens: {input_tokens:,}→{output_tokens:,} | "
            f"Cache: {cache_read_tokens:,}"
        )
