"""Tool choice transformer.

Maps Claude's tool_choice to OpenAI's format.
"""

import dataclasses
from typing import Any

from src.conversion.pipeline.base import ConversionContext, RequestTransformer
from src.core.constants import Constants


class ToolChoiceTransformer(RequestTransformer):
    """Converts Claude tool_choice to OpenAI format.

    Claude types:
    - "auto": Model decides whether to call tools
    - "any": Must call at least one tool
    - "tool": Specific tool to call (with name parameter)

    OpenAI types:
    - "auto": Model decides whether to call functions
    - {"type": "function", "function": {"name": "..."}}: Specific function

    This transformer maps Claude's format to OpenAI's equivalent.
    """

    def transform(self, context: ConversionContext) -> ConversionContext:
        """Convert tool_choice from Claude to OpenAI format.

        Args:
            context: The input conversion context.

        Returns:
            A new context with tool_choice added to the OpenAI request, or
            unchanged if no tool_choice is specified.
        """
        tool_choice = context.claude_request.tool_choice
        if not tool_choice:
            return context

        choice_type = tool_choice.get("type")

        if choice_type in ("auto", "any"):
            openai_choice: str | dict[str, Any] = "auto"
        elif choice_type == "tool" and "name" in tool_choice:
            mapped_name = context.tool_name_map.get(tool_choice["name"], tool_choice["name"])
            openai_choice = {
                "type": Constants.TOOL_FUNCTION,
                Constants.TOOL_FUNCTION: {"name": mapped_name},
            }
        else:
            openai_choice = "auto"

        new_request = {**context.openai_request, "tool_choice": openai_choice}
        return dataclasses.replace(context, openai_request=new_request)
