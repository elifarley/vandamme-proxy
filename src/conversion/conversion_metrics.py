import json

# ConversationLogger.get_logger() returns a standard logging.Logger.
import logging
from dataclasses import dataclass

from src.core.constants import Constants
from src.models.claude import ClaudeMessagesRequest

Logger = logging.Logger


@dataclass(frozen=True)
class RequestMetrics:
    provider_name: str
    model_name: str
    model_category: str
    message_count: int
    total_chars: int
    estimated_tokens: int
    tool_count: int


def _model_category(model_name: str) -> str:
    model_lower = model_name.lower()
    if "haiku" in model_lower:
        return "small"
    if "sonnet" in model_lower:
        return "medium"
    if "opus" in model_lower:
        return "large"
    if model_name.startswith(("gpt-", "o1-")):
        return "openai-native"
    if model_name.startswith(("ep-", "doubao-", "deepseek-")):
        return "third-party"
    return "unknown"


def collect_request_metrics(
    claude_request: ClaudeMessagesRequest,
    *,
    provider_name: str,
) -> RequestMetrics:
    total_chars = 0
    message_count = len(claude_request.messages)

    if claude_request.system:
        message_count += 1
        if isinstance(claude_request.system, str):
            total_chars += len(claude_request.system)
        elif isinstance(claude_request.system, list):
            # Pydantic models: ClaudeSystemContent
            for system_block in claude_request.system:
                total_chars += len(system_block.text)

    for message in claude_request.messages:
        if message.content is None:
            continue
        if isinstance(message.content, str):
            total_chars += len(message.content)
        elif isinstance(message.content, list):
            for block in message.content:
                if getattr(block, "type", None) == Constants.CONTENT_TEXT:
                    # Pydantic model: ClaudeContentBlockText
                    total_chars += len(getattr(block, "text", ""))
                elif isinstance(block, dict) and block.get("text"):
                    total_chars += len(block["text"])
                elif isinstance(block, dict) and block.get("type") == Constants.CONTENT_TOOL_USE:
                    total_chars += len(block.get("name", ""))
                    total_chars += len(json.dumps(block.get("input", {})))
                elif isinstance(block, dict) and block.get("type") == Constants.CONTENT_TOOL_RESULT:
                    content = block.get("content", "")
                    if isinstance(content, str):
                        total_chars += len(content)
                    else:
                        total_chars += len(json.dumps(content))

    estimated_tokens = max(1, total_chars // 4)
    tool_count = len(claude_request.tools) if claude_request.tools else 0

    return RequestMetrics(
        provider_name=provider_name,
        model_name=claude_request.model,
        model_category=_model_category(claude_request.model),
        message_count=message_count,
        total_chars=total_chars,
        estimated_tokens=estimated_tokens,
        tool_count=tool_count,
    )


def log_request_metrics(logger: Logger, metrics: RequestMetrics) -> None:
    logger.debug(
        "📊 REQUEST METRICS | Provider: %s | Model: %s (%s) | Messages: %s | "
        "Chars: %s | Est Tokens: %s | Tools: %s",
        metrics.provider_name,
        metrics.model_name,
        metrics.model_category,
        metrics.message_count,
        f"{metrics.total_chars:,}",
        f"{metrics.estimated_tokens:,}",
        metrics.tool_count,
    )
