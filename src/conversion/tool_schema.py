from __future__ import annotations

from collections.abc import Iterable

from src.conversion.tool_name_sanitizer import build_tool_name_maps
from src.core.constants import Constants
from src.models.claude import ClaudeContentBlockToolUse, ClaudeMessagesRequest


def collect_all_tool_names(request: ClaudeMessagesRequest) -> list[str]:
    """Collect all tool names that may appear in a Claude request.

    This includes:
    - tools schema entries
    - tool_choice name
    - assistant tool_use blocks in messages

    Keeping this logic centralized prevents request conversion from duplicating
    tool traversal and makes it easier to add new tool-related sources.
    """

    names: list[str] = []

    if request.tools:
        names.extend([t.name for t in request.tools if t.name])

    if request.tool_choice and request.tool_choice.get("type") == "tool":
        choice_name = request.tool_choice.get("name")
        if isinstance(choice_name, str) and choice_name:
            names.append(choice_name)

    for msg in request.messages:
        if msg.role != Constants.ROLE_ASSISTANT or not isinstance(msg.content, list):
            continue
        for content_block in msg.content:
            if content_block.type == Constants.CONTENT_TOOL_USE:
                tool_block = content_block
                if isinstance(tool_block, ClaudeContentBlockToolUse) and tool_block.name:
                    names.append(tool_block.name)

    return names


def build_tool_name_maps_if_enabled(
    *, enabled: bool, tool_names: Iterable[str]
) -> tuple[dict[str, str], dict[str, str]]:
    if not enabled:
        return {}, {}

    names = [n for n in tool_names if n]
    if not names:
        return {}, {}

    return build_tool_name_maps(names)
