"""Message content transformer.

Converts Claude messages to OpenAI format, handling tool result lookahead.
"""

import dataclasses
from typing import Any

from src.conversion.pipeline.base import ConversionContext, RequestTransformer
from src.conversion.request_converter import (
    _is_tool_result_message,
    convert_claude_assistant_message,
    convert_claude_tool_results,
    convert_claude_user_message,
)
from src.core.constants import Constants
from src.models.claude import ClaudeMessage


class MessageContentTransformer(RequestTransformer):
    """Converts Claude messages to OpenAI format.

    Key complexities:
    - User messages: Handle multimodal content (text + images)
    - Assistant messages: Extract text and tool_calls
    - Tool results: Consumed immediately after assistant messages (lookahead pattern)
    """

    def transform(self, context: ConversionContext) -> ConversionContext:
        """Convert all Claude messages to OpenAI format.

        Args:
            context: The input conversion context.

        Returns:
            A new context with converted messages in the OpenAI request.
        """
        openai_messages: list[dict[str, Any]] = []
        messages = context.claude_request.messages

        i = 0
        while i < len(messages):
            msg = messages[i]

            if msg.role == Constants.ROLE_USER:
                openai_messages.append(convert_claude_user_message(msg))
            elif msg.role == Constants.ROLE_ASSISTANT:
                openai_messages.append(convert_claude_assistant_message(msg, context.tool_name_map))
                # Lookahead: consume tool results if present
                if self._should_consume_tool_results(messages, i):
                    i += 1
                    openai_messages.extend(convert_claude_tool_results(messages[i]))

            i += 1

        new_request = {**context.openai_request, "messages": openai_messages}
        return dataclasses.replace(context, openai_request=new_request)

    def _should_consume_tool_results(self, messages: list[ClaudeMessage], index: int) -> bool:
        """Check if we should consume tool results following an assistant message.

        In Claude's API, tool results are sent as a separate user message that
        immediately follows an assistant message containing tool_use blocks.

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
