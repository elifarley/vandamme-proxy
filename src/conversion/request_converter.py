import json
import logging
from typing import Any, cast

from src.conversion.conversion_metrics import collect_request_metrics, log_request_metrics
from src.conversion.tool_schema import build_tool_name_maps_if_enabled, collect_all_tool_names
from src.core.config import config
from src.core.constants import Constants
from src.core.logging import ConversationLogger
from src.models.claude import (
    ClaudeContentBlockImage,
    ClaudeContentBlockText,
    ClaudeContentBlockToolResult,
    ClaudeContentBlockToolUse,
    ClaudeMessage,
    ClaudeMessagesRequest,
)

LOG_REQUEST_METRICS = config.log_request_metrics
conversation_logger = ConversationLogger.get_logger()


# Retained as a module-level logger for parity with existing debug logging.
logger = logging.getLogger(__name__)


def convert_claude_to_openai(
    claude_request: ClaudeMessagesRequest, model_manager: Any
) -> dict[str, Any]:
    """Convert Claude API request format to OpenAI format."""

    # Resolve provider and model
    provider_name, openai_model = model_manager.resolve_model(claude_request.model)

    if LOG_REQUEST_METRICS:
        metrics = collect_request_metrics(claude_request, provider_name=provider_name)
        log_request_metrics(conversation_logger, metrics)

    # Delegate conversion to the existing implementation below.
    # Keeping a single conversion path avoids divergent behaviors.
    return _convert_claude_to_openai_impl(claude_request, model_manager)


def _convert_claude_to_openai_impl(
    claude_request: ClaudeMessagesRequest, model_manager: Any
) -> dict[str, Any]:
    """Convert Claude API request format to OpenAI format.

    This is the historical implementation that handles tool name sanitization,
    tool result sequencing, and provider metadata fields.
    """

    provider_name, openai_model = model_manager.resolve_model(claude_request.model)

    if LOG_REQUEST_METRICS:
        # Keep a single implementation of request metrics to avoid drift.
        metrics = collect_request_metrics(claude_request, provider_name=provider_name)
        log_request_metrics(conversation_logger, metrics)

    provider_config = config.provider_manager.get_provider_config(provider_name)

    tool_name_map, tool_name_map_inverse = build_tool_name_maps_if_enabled(
        enabled=bool(provider_config and provider_config.tool_name_sanitization),
        tool_names=collect_all_tool_names(claude_request),
    )

    openai_messages = []

    if claude_request.system:
        system_text = ""
        if isinstance(claude_request.system, str):
            system_text = claude_request.system
        elif isinstance(claude_request.system, list):
            text_parts = []
            for block in claude_request.system:
                if hasattr(block, "type") and block.type == Constants.CONTENT_TEXT:
                    text_parts.append(block.text)
                elif isinstance(block, dict) and block.get("type") == Constants.CONTENT_TEXT:
                    text_parts.append(block.get("text", ""))
            system_text = "\n\n".join(text_parts)

        if system_text.strip():
            openai_messages.append({"role": Constants.ROLE_SYSTEM, "content": system_text.strip()})

    i = 0
    while i < len(claude_request.messages):
        msg = claude_request.messages[i]

        if msg.role == Constants.ROLE_USER:
            openai_messages.append(convert_claude_user_message(msg))
        elif msg.role == Constants.ROLE_ASSISTANT:
            openai_messages.append(convert_claude_assistant_message(msg, tool_name_map))

            if i + 1 < len(claude_request.messages):
                next_msg = claude_request.messages[i + 1]
                if (
                    next_msg.role == Constants.ROLE_USER
                    and isinstance(next_msg.content, list)
                    and any(
                        block.type == Constants.CONTENT_TOOL_RESULT
                        for block in next_msg.content
                        if hasattr(block, "type")
                    )
                ):
                    i += 1
                    openai_messages.extend(convert_claude_tool_results(next_msg))

        i += 1

    openai_request = {
        "model": openai_model,
        "messages": openai_messages,
        "max_tokens": min(
            max(claude_request.max_tokens, config.min_tokens_limit),
            config.max_tokens_limit,
        ),
        "temperature": claude_request.temperature,
        "stream": claude_request.stream,
    }

    # Provider metadata for upstream selection.
    openai_request["_provider"] = provider_name
    if tool_name_map_inverse:
        openai_request["_tool_name_map_inverse"] = tool_name_map_inverse

    if claude_request.stop_sequences:
        openai_request["stop"] = claude_request.stop_sequences
    if claude_request.top_p is not None:
        openai_request["top_p"] = claude_request.top_p

    if claude_request.tools:
        openai_tools = []
        for tool in claude_request.tools:
            if tool.name and tool.name.strip():
                openai_tools.append(
                    {
                        "type": Constants.TOOL_FUNCTION,
                        Constants.TOOL_FUNCTION: {
                            "name": tool_name_map.get(tool.name, tool.name),
                            "description": tool.description or "",
                            "parameters": tool.input_schema,
                        },
                    }
                )
        if openai_tools:
            openai_request["tools"] = openai_tools

    if claude_request.tool_choice:
        choice_type = claude_request.tool_choice.get("type")
        if choice_type in ("auto", "any"):
            openai_request["tool_choice"] = "auto"
        elif choice_type == "tool" and "name" in claude_request.tool_choice:
            openai_request["tool_choice"] = {
                "type": Constants.TOOL_FUNCTION,
                Constants.TOOL_FUNCTION: {
                    "name": tool_name_map.get(
                        claude_request.tool_choice["name"], claude_request.tool_choice["name"]
                    )
                },
            }
        else:
            openai_request["tool_choice"] = "auto"

    return openai_request


def convert_claude_user_message(msg: ClaudeMessage) -> dict[str, Any]:
    """Convert Claude user message to OpenAI format."""
    if msg.content is None:
        return {"role": Constants.ROLE_USER, "content": ""}

    if isinstance(msg.content, str):
        return {"role": Constants.ROLE_USER, "content": msg.content}

    # Handle multimodal content
    openai_content: list[dict[str, Any]] = []
    for block in msg.content:  # type: ignore[arg-type, assignment]
        if block.type == Constants.CONTENT_TEXT:
            text_block = cast(ClaudeContentBlockText, block)
            openai_content.append({"type": "text", "text": text_block.text})
        elif block.type == Constants.CONTENT_IMAGE:
            # Convert Claude image format to OpenAI format
            image_block = cast(ClaudeContentBlockImage, block)
            if (
                isinstance(image_block.source, dict)
                and image_block.source.get("type") == "base64"
                and "media_type" in image_block.source
                and "data" in image_block.source
            ):
                openai_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": (
                                f"data:{image_block.source['media_type']};base64,"
                                f"{image_block.source['data']}"
                            )
                        },
                    }
                )

    if len(openai_content) == 1 and openai_content[0]["type"] == "text":
        return {"role": Constants.ROLE_USER, "content": openai_content[0]["text"]}
    else:
        return {"role": Constants.ROLE_USER, "content": openai_content}


def convert_claude_assistant_message(
    msg: ClaudeMessage, tool_name_map: dict[str, str] | None = None
) -> dict[str, Any]:
    """Convert Claude assistant message to OpenAI format."""
    tool_name_map = tool_name_map or {}
    text_parts = []
    tool_calls = []

    if msg.content is None:
        return {"role": Constants.ROLE_ASSISTANT, "content": None}

    if isinstance(msg.content, str):
        return {"role": Constants.ROLE_ASSISTANT, "content": msg.content}

    for block in msg.content:  # type: ignore[arg-type, assignment]
        if block.type == Constants.CONTENT_TEXT:
            text_block = cast(ClaudeContentBlockText, block)
            text_parts.append(text_block.text)
        elif block.type == Constants.CONTENT_TOOL_USE:
            tool_block = cast(ClaudeContentBlockToolUse, block)
            tool_calls.append(
                {
                    "id": tool_block.id,
                    "type": Constants.TOOL_FUNCTION,
                    Constants.TOOL_FUNCTION: {
                        "name": tool_name_map.get(tool_block.name, tool_block.name),
                        "arguments": json.dumps(tool_block.input, ensure_ascii=False),
                    },
                }
            )

    openai_message: dict[str, Any] = {"role": Constants.ROLE_ASSISTANT}

    # Set content
    if text_parts:
        openai_message["content"] = "".join(text_parts)
    else:
        openai_message["content"] = ""

    # Set tool calls
    if tool_calls:
        openai_message["tool_calls"] = tool_calls

    return openai_message


def convert_claude_tool_results(msg: ClaudeMessage) -> list[dict[str, Any]]:
    """Convert Claude tool results to OpenAI format."""
    tool_messages = []

    if isinstance(msg.content, list):
        for block in msg.content:  # type: ignore[arg-type, assignment]
            if block.type == Constants.CONTENT_TOOL_RESULT:
                tool_result_block = cast(ClaudeContentBlockToolResult, block)
                content = parse_tool_result_content(tool_result_block.content)
                tool_messages.append(
                    {
                        "role": Constants.ROLE_TOOL,
                        "tool_call_id": tool_result_block.tool_use_id,
                        "content": content,
                    }
                )

    return tool_messages


def parse_tool_result_content(content: Any) -> str:
    """Parse and normalize tool result content into a string format."""
    if content is None:
        return "No content provided"

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        result_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == Constants.CONTENT_TEXT:
                result_parts.append(item.get("text", ""))
            elif isinstance(item, str):
                result_parts.append(item)
            elif isinstance(item, dict):
                if "text" in item:
                    result_parts.append(item.get("text", ""))
                else:
                    # Best-effort stringify of arbitrary dict blocks.
                    try:
                        result_parts.append(json.dumps(item, ensure_ascii=False))
                    except (TypeError, ValueError):
                        result_parts.append(str(item))
        return "\n".join(result_parts).strip()

    if isinstance(content, dict):
        if content.get("type") == Constants.CONTENT_TEXT:
            return cast(str, content.get("text", ""))
        try:
            return json.dumps(content, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(content)

    try:
        return str(content)
    except Exception:
        return "Unparseable content"
