"""System message transformer.

Converts Claude's system parameter to OpenAI's system message format.
"""

import dataclasses

from src.conversion.pipeline.base import ConversionContext, RequestTransformer
from src.core.constants import Constants
from src.models.claude import ClaudeSystemContent


class SystemMessageTransformer(RequestTransformer):
    """Converts Claude system parameter to OpenAI system message.

    Claude accepts system as:
    - str: Direct text content
    - list[ClaudeSystemContent]: Structured blocks with type="text"

    OpenAI requires a single system message at the start of messages array.
    """

    def transform(self, context: ConversionContext) -> ConversionContext:
        """Extract system text and prepend to messages array.

        Args:
            context: The input conversion context.

        Returns:
            A new context with system message added to the OpenAI request.
        """
        system_text = self._extract_system_text(context.claude_request.system)

        if not system_text or not system_text.strip():
            return context

        # Prepend system message to messages array
        existing_messages = context.openai_request.get("messages", [])
        new_messages = [
            {"role": Constants.ROLE_SYSTEM, "content": system_text.strip()},
            *existing_messages,
        ]

        new_request = {**context.openai_request, "messages": new_messages}
        return dataclasses.replace(context, openai_request=new_request)

    def _extract_system_text(self, system: str | list[ClaudeSystemContent] | None) -> str:
        """Extract text content from Claude system parameter.

        Args:
            system: The system parameter from Claude request (str, list, or None).

        Returns:
            Extracted text content as a string.
        """
        if not system:
            return ""

        if isinstance(system, str):
            return system

        # Handle list of system blocks
        text_parts = []
        for block in system:
            if hasattr(block, "type") and block.type == Constants.CONTENT_TEXT:
                text_parts.append(block.text)

        return "\n\n".join(text_parts)
