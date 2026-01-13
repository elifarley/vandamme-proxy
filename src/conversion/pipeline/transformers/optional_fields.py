"""Optional fields transformer.

Adds optional request fields like stop_sequences and top_p.
"""

import dataclasses

from src.conversion.pipeline.base import ConversionContext, RequestTransformer


class OptionalFieldsTransformer(RequestTransformer):
    """Adds optional fields to the OpenAI request if present.

    Handles fields that are not required but may be present in the Claude request:
    - stop_sequences: Mapped to OpenAI's "stop" parameter
    - top_p: Sampling parameter passed through directly
    - temperature: Sampling parameter passed through directly
    - stream: Whether to stream the response
    """

    def transform(self, context: ConversionContext) -> ConversionContext:
        """Add optional fields from Claude request to OpenAI request.

        Args:
            context: The input conversion context.

        Returns:
            A new context with optional fields added to the OpenAI request.
        """
        new_request = context.openai_request.copy()
        request = context.claude_request

        if request.stop_sequences:
            new_request["stop"] = request.stop_sequences
        if request.top_p is not None:
            new_request["top_p"] = request.top_p
        if request.temperature is not None:
            new_request["temperature"] = request.temperature
        if request.stream is not None:
            new_request["stream"] = request.stream

        return dataclasses.replace(context, openai_request=new_request)
