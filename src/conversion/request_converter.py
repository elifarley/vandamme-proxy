import json
import logging
from typing import TYPE_CHECKING, Any, cast

from src.conversion.conversion_metrics import (
    collect_request_metrics,
)
from src.conversion.conversion_metrics import (
    log_request_metrics as log_request_metrics_impl,
)
from src.conversion.tool_schema import build_tool_name_maps_if_enabled, collect_all_tool_names
from src.core.config import Config
from src.core.config.accessors import log_request_metrics
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

if TYPE_CHECKING:
    from src.conversion.pipeline.base import ConversionContext

conversation_logger = ConversationLogger.get_logger()


# Retained as a module-level logger for parity with existing debug logging.
logger = logging.getLogger(__name__)


def _is_tool_result_message(msg: ClaudeMessage) -> bool:
    """Check if a message contains tool result content blocks.

    A tool result message is a user message containing one or more
    CONTENT_TOOL_RESULT blocks, which contain the results of tool
    executions that should be paired with preceding tool_use blocks.

    Args:
        msg: The Claude message to check.

    Returns:
        True if the message is a user message containing tool results,
        False otherwise.
    """
    if msg.role != Constants.ROLE_USER:
        return False
    if not isinstance(msg.content, list):
        return False
    return any(
        hasattr(block, "type") and block.type == Constants.CONTENT_TOOL_RESULT
        for block in msg.content
    )


def _should_consume_tool_results(messages: list[ClaudeMessage], index: int) -> bool:
    """Check if we should consume tool results following an assistant message.

    In Claude's API, tool results are sent as a separate user message that
    immediately follows an assistant message containing tool_use blocks.
    This function checks if the next message is such a tool result message.

    Args:
        messages: The list of Claude messages.
        index: The current index in the message list (typically an assistant
            message position).

    Returns:
        True if the next message exists and contains tool results that
        should be consumed, False otherwise.
    """
    if index + 1 >= len(messages):
        return False
    return _is_tool_result_message(messages[index + 1])


def convert_claude_to_openai(
    claude_request: ClaudeMessagesRequest, model_manager: Any
) -> dict[str, Any]:
    """Convert Claude API request format to OpenAI format.

    This function now uses a composable pipeline of transformers, making the
    conversion process more maintainable and testable. Each transformer handles
    a single responsibility.
    """
    # Resolve provider and model
    provider_name, openai_model = model_manager.resolve_model(claude_request.model)

    if log_request_metrics():
        metrics = collect_request_metrics(claude_request, provider_name=provider_name)
        log_request_metrics_impl(conversation_logger, metrics)

    # Build the initial conversion context
    context = _build_initial_context(claude_request, provider_name, openai_model)

    # Execute the conversion pipeline
    from src.conversion.pipeline import RequestPipelineFactory

    pipeline = RequestPipelineFactory.create_default()
    return pipeline.execute(context)


def _build_initial_context(
    claude_request: ClaudeMessagesRequest,
    provider_name: str,
    openai_model: str,
) -> "ConversionContext":
    """Build the initial conversion context for the pipeline.

    Args:
        claude_request: The Claude API request.
        provider_name: The resolved provider name.
        openai_model: The resolved OpenAI model name.

    Returns:
        A ConversionContext with all initial state populated.
    """
    from src.conversion.pipeline.base import ConversionContext

    # Get provider config to check if tool name sanitization is enabled
    cfg = Config()
    provider_config = cfg.provider_manager.get_provider_config(provider_name)

    # Build tool name maps if sanitization is enabled
    tool_name_map, tool_name_map_inverse = build_tool_name_maps_if_enabled(
        enabled=bool(provider_config and provider_config.tool_name_sanitization),
        tool_names=collect_all_tool_names(claude_request),
    )

    # Initialize the OpenAI request with the base fields
    openai_request = {
        "model": openai_model,
        "messages": [],
    }

    return ConversionContext(
        claude_request=claude_request,
        provider_name=provider_name,
        openai_model=openai_model,
        tool_name_map=tool_name_map,
        tool_name_map_inverse=tool_name_map_inverse,
        openai_request=openai_request,
    )


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
