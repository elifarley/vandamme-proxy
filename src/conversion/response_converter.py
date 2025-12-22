import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import HTTPException, Request

from src.conversion.errors import ConversionError, SSEParseError
from src.conversion.tool_call_delta import (
    ToolCallArgsAssembler,
    ToolCallIdAllocator,
    ToolCallIndexState,
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

    # Send initial SSE events
    yield f"event: {Constants.EVENT_MESSAGE_START}\ndata: {json.dumps({'type': Constants.EVENT_MESSAGE_START, 'message': {'id': message_id, 'type': 'message', 'role': Constants.ROLE_ASSISTANT, 'model': original_request.model, 'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 0, 'output_tokens': 0}}}, ensure_ascii=False)}\n\n"  # noqa: E501

    yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': 0, 'content_block': {'type': Constants.CONTENT_TEXT, 'text': ''}}, ensure_ascii=False)}\n\n"  # noqa: E501

    yield f"event: {Constants.EVENT_PING}\ndata: {json.dumps({'type': Constants.EVENT_PING}, ensure_ascii=False)}\n\n"  # noqa: E501

    tool_name_map_inverse = tool_name_map_inverse or {}

    # Process streaming chunks
    text_block_index = 0
    tool_block_counter = 0
    tool_id_allocator = ToolCallIdAllocator(id_prefix=f"toolu_{message_id}")
    args_assembler = ToolCallArgsAssembler()
    current_tool_calls: dict[int, ToolCallIndexState] = {}
    final_stop_reason = Constants.STOP_END_TURN

    try:
        async for line in openai_stream:
            if line.strip() and line.startswith("data: "):
                chunk_data = line[6:]
                if chunk_data.strip() == "[DONE]":
                    break

                try:
                    chunk = json.loads(chunk_data)
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                except json.JSONDecodeError as e:
                    raise SSEParseError(
                        "Failed to parse OpenAI streaming chunk as JSON",
                        context={"chunk_data": chunk_data, "json_error": str(e)},
                    ) from e

                choice = choices[0]
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason")

                # Handle text delta
                if delta and "content" in delta and delta["content"] is not None:
                    yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': text_block_index, 'delta': {'type': Constants.DELTA_TEXT, 'text': delta['content']}}, ensure_ascii=False)}\n\n"  # noqa: E501

                # Handle tool call deltas with improved incremental processing
                if "tool_calls" in delta:
                    for tc_delta in delta["tool_calls"]:
                        tc_index = tc_delta.get("index", 0)

                        # Initialize tool call tracking by index if not exists
                        if tc_index not in current_tool_calls:
                            current_tool_calls[tc_index] = ToolCallIndexState()

                        tool_call = current_tool_calls[tc_index]

                        # Update tool call ID if provided
                        provided_id = tc_delta.get("id")
                        if isinstance(provided_id, str) and provided_id:
                            tool_call.tool_id = tool_id_allocator.get(
                                tc_index, provided_id=provided_id
                            )

                        function_data = tc_delta.get(Constants.TOOL_FUNCTION, {})
                        if isinstance(function_data, dict):
                            name = function_data.get("name")
                            if name:
                                tool_call.tool_name = str(name)

                        # Start content block when we have complete initial data
                        if tool_call.tool_id and tool_call.tool_name and not tool_call.started:
                            tool_block_counter += 1
                            claude_index = text_block_index + tool_block_counter
                            tool_call.output_index = str(claude_index)
                            tool_call.started = True

                            tool_name = tool_call.tool_name
                            original_name = tool_name_map_inverse.get(tool_name, tool_name)
                            tool_call.tool_name = original_name

                            yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': claude_index, 'content_block': {'type': Constants.CONTENT_TOOL_USE, 'id': tool_call.tool_id, 'name': original_name, 'input': {}}}, ensure_ascii=False)}\n\n"  # noqa: E501

                        # Handle function arguments
                        if (
                            isinstance(function_data, dict)
                            and function_data.get("arguments") is not None
                            and tool_call.started
                        ):
                            args_delta = str(function_data["arguments"])
                            tool_call.args_buffer = args_assembler.append(tc_index, args_delta)

                            # Try to parse complete JSON and send delta when we have valid JSON
                            if (
                                tool_call.output_index is not None
                                and not tool_call.json_sent
                                and ToolCallArgsAssembler.is_complete_json(tool_call.args_buffer)
                            ):
                                yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': tool_call.output_index, 'delta': {'type': Constants.DELTA_INPUT_JSON, 'partial_json': tool_call.args_buffer}}, ensure_ascii=False)}\n\n"  # noqa: E501
                                tool_call.json_sent = True

                        # JSON incomplete: keep buffering

                # Handle finish reason
                if finish_reason:
                    if finish_reason == "length":
                        final_stop_reason = Constants.STOP_MAX_TOKENS
                    elif finish_reason in ["tool_calls", "function_call"]:
                        final_stop_reason = Constants.STOP_TOOL_USE
                    elif finish_reason == "stop":
                        final_stop_reason = Constants.STOP_END_TURN
                    else:
                        final_stop_reason = Constants.STOP_END_TURN
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

    # Send final SSE events
    yield f"event: {Constants.EVENT_CONTENT_BLOCK_STOP}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_STOP, 'index': text_block_index}, ensure_ascii=False)}\n\n"  # noqa: E501

    for tool_data in current_tool_calls.values():
        if tool_data.started and tool_data.output_index is not None:
            yield f"event: {Constants.EVENT_CONTENT_BLOCK_STOP}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_STOP, 'index': tool_data.output_index}, ensure_ascii=False)}\n\n"  # noqa: E501

    usage_data = {"input_tokens": 0, "output_tokens": 0}
    yield f"event: {Constants.EVENT_MESSAGE_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_MESSAGE_DELTA, 'delta': {'stop_reason': final_stop_reason, 'stop_sequence': None}, 'usage': usage_data}, ensure_ascii=False)}\n\n"  # noqa: E501
    yield f"event: {Constants.EVENT_MESSAGE_STOP}\ndata: {json.dumps({'type': Constants.EVENT_MESSAGE_STOP}, ensure_ascii=False)}\n\n"  # noqa: E501


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

    # Send initial SSE events
    yield f"event: {Constants.EVENT_MESSAGE_START}\ndata: {json.dumps({'type': Constants.EVENT_MESSAGE_START, 'message': {'id': message_id, 'type': 'message', 'role': Constants.ROLE_ASSISTANT, 'model': original_request.model, 'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 0, 'output_tokens': 0}}}, ensure_ascii=False)}\n\n"  # noqa: E501

    yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': 0, 'content_block': {'type': Constants.CONTENT_TEXT, 'text': ''}}, ensure_ascii=False)}\n\n"  # noqa: E501

    yield f"event: {Constants.EVENT_PING}\ndata: {json.dumps({'type': Constants.EVENT_PING}, ensure_ascii=False)}\n\n"  # noqa: E501

    tool_name_map_inverse = tool_name_map_inverse or {}

    # Process streaming chunks
    text_block_index = 0
    tool_block_counter = 0
    tool_id_allocator = ToolCallIdAllocator(id_prefix=f"toolu_{message_id}")
    args_assembler = ToolCallArgsAssembler()
    current_tool_calls: dict[int, ToolCallIndexState] = {}
    final_stop_reason = Constants.STOP_END_TURN
    usage_data = {"input_tokens": 0, "output_tokens": 0}

    try:
        async for line in openai_stream:
            # Check if client disconnected
            if await http_request.is_disconnected():
                logger.info(f"Client disconnected, cancelling request {request_id}")
                openai_client.cancel_request(request_id)
                break

            if line.strip() and line.startswith("data: "):
                chunk_data = line[6:]
                if chunk_data.strip() == "[DONE]":
                    break

                try:
                    chunk = json.loads(chunk_data)
                    chunk_count += 1

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
                except json.JSONDecodeError as e:
                    raise SSEParseError(
                        "Failed to parse OpenAI streaming chunk as JSON",
                        context={"chunk_data": chunk_data, "json_error": str(e)},
                    ) from e

                choice = choices[0]
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason")

                # Handle text delta
                if delta and "content" in delta and delta["content"] is not None:
                    yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': text_block_index, 'delta': {'type': Constants.DELTA_TEXT, 'text': delta['content']}}, ensure_ascii=False)}\n\n"  # noqa: E501

                # Handle tool call deltas with improved incremental processing
                if "tool_calls" in delta and delta["tool_calls"]:
                    for tc_delta in delta["tool_calls"]:
                        tc_index = tc_delta.get("index", 0)

                        # Initialize tool call tracking by index if not exists
                        if tc_index not in current_tool_calls:
                            current_tool_calls[tc_index] = ToolCallIndexState()

                        tool_call = current_tool_calls[tc_index]

                        # Update tool call ID if provided
                        provided_id = tc_delta.get("id")
                        if isinstance(provided_id, str) and provided_id:
                            tool_call.tool_id = tool_id_allocator.get(
                                tc_index, provided_id=provided_id
                            )

                        function_data = tc_delta.get(Constants.TOOL_FUNCTION, {})
                        if isinstance(function_data, dict):
                            name = function_data.get("name")
                            if name:
                                tool_call.tool_name = str(name)

                        # Start content block when we have complete initial data
                        if tool_call.tool_id and tool_call.tool_name and not tool_call.started:
                            tool_block_counter += 1
                            claude_index = text_block_index + tool_block_counter
                            tool_call.output_index = str(claude_index)
                            tool_call.started = True

                            tool_name = tool_call.tool_name
                            original_name = tool_name_map_inverse.get(tool_name, tool_name)
                            tool_call.tool_name = original_name

                            yield f"event: {Constants.EVENT_CONTENT_BLOCK_START}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_START, 'index': claude_index, 'content_block': {'type': Constants.CONTENT_TOOL_USE, 'id': tool_call.tool_id, 'name': original_name, 'input': {}}}, ensure_ascii=False)}\n\n"  # noqa: E501

                        # Handle function arguments
                        if (
                            isinstance(function_data, dict)
                            and function_data.get("arguments") is not None
                            and tool_call.started
                        ):
                            args_delta = str(function_data["arguments"])
                            tool_call.args_buffer = args_assembler.append(tc_index, args_delta)

                            # Try to parse complete JSON and send delta when we have valid JSON
                            if (
                                tool_call.output_index is not None
                                and not tool_call.json_sent
                                and ToolCallArgsAssembler.is_complete_json(tool_call.args_buffer)
                            ):
                                yield f"event: {Constants.EVENT_CONTENT_BLOCK_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_DELTA, 'index': tool_call.output_index, 'delta': {'type': Constants.DELTA_INPUT_JSON, 'partial_json': tool_call.args_buffer}}, ensure_ascii=False)}\n\n"  # noqa: E501
                                tool_call.json_sent = True

                        # JSON incomplete: keep buffering

                # Handle finish reason
                if finish_reason:
                    if finish_reason == "length":
                        final_stop_reason = Constants.STOP_MAX_TOKENS
                    elif finish_reason in ["tool_calls", "function_call"]:
                        final_stop_reason = Constants.STOP_TOOL_USE
                    elif finish_reason == "stop":
                        final_stop_reason = Constants.STOP_END_TURN
                    else:
                        final_stop_reason = Constants.STOP_END_TURN

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

    # Send final SSE events
    yield f"event: {Constants.EVENT_CONTENT_BLOCK_STOP}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_STOP, 'index': text_block_index}, ensure_ascii=False)}\n\n"  # noqa: E501

    for tool_data in current_tool_calls.values():
        if tool_data.started and tool_data.output_index is not None:
            yield f"event: {Constants.EVENT_CONTENT_BLOCK_STOP}\ndata: {json.dumps({'type': Constants.EVENT_CONTENT_BLOCK_STOP, 'index': tool_data.output_index}, ensure_ascii=False)}\n\n"  # noqa: E501

    # Log streaming completion
    if LOG_REQUEST_METRICS and metrics:
        duration_ms = metrics.duration_ms
        conversation_logger.info(
            f"✅ STREAM COMPLETE | Duration: {duration_ms:.0f}ms | "
            f"Chunks: {chunk_count} | "
            f"Tokens: {input_tokens:,}→{output_tokens:,} | "
            f"Cache: {cache_read_tokens:,}"
        )

    yield f"event: {Constants.EVENT_MESSAGE_DELTA}\ndata: {json.dumps({'type': Constants.EVENT_MESSAGE_DELTA, 'delta': {'stop_reason': final_stop_reason, 'stop_sequence': None}, 'usage': usage_data}, ensure_ascii=False)}\n\n"  # noqa: E501
    yield f"event: {Constants.EVENT_MESSAGE_STOP}\ndata: {json.dumps({'type': Constants.EVENT_MESSAGE_STOP}, ensure_ascii=False)}\n\n"  # noqa: E501
