"""Tool schema transformer.

Converts Claude tool definitions to OpenAI function calling format.
"""

import dataclasses

from src.conversion.pipeline.base import ConversionContext, RequestTransformer
from src.core.constants import Constants


class ToolSchemaTransformer(RequestTransformer):
    """Converts Claude tools to OpenAI function format.

    Applies tool name sanitization if enabled for the provider. Tool names
    are mapped using the tool_name_map from the conversion context.
    """

    def transform(self, context: ConversionContext) -> ConversionContext:
        """Convert Claude tools to OpenAI function format.

        Args:
            context: The input conversion context.

        Returns:
            A new context with tools added to the OpenAI request, or unchanged
            if no tools are present.
        """
        tools = context.claude_request.tools
        if not tools:
            return context

        openai_tools = [
            {
                "type": Constants.TOOL_FUNCTION,
                Constants.TOOL_FUNCTION: {
                    "name": context.tool_name_map.get(tool.name, tool.name),
                    "description": tool.description or "",
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
            if tool.name and tool.name.strip()
        ]

        if openai_tools:
            new_request = {**context.openai_request, "tools": openai_tools}
            return dataclasses.replace(context, openai_request=new_request)

        return context
