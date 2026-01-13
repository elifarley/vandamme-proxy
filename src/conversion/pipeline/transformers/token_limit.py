"""Token limit transformer.

Validates and clamps max_tokens to configured limits.
"""

import dataclasses

from src.conversion.pipeline.base import ConversionContext, RequestTransformer


class TokenLimitTransformer(RequestTransformer):
    """Ensures max_tokens falls within configured bounds.

    The proxy has configured minimum and maximum token limits. This transformer
    ensures the requested max_tokens value is clamped to these bounds.
    """

    def transform(self, context: ConversionContext) -> ConversionContext:
        """Clamp max_tokens to configured limits.

        Args:
            context: The input conversion context.

        Returns:
            A new context with clamped max_tokens in the OpenAI request.
        """
        # Import config lazily to avoid circular imports
        from src.core.config import config

        requested = context.claude_request.max_tokens
        clamped = min(max(requested, config.min_tokens_limit), config.max_tokens_limit)

        new_request = {**context.openai_request, "max_tokens": clamped}
        return dataclasses.replace(context, openai_request=new_request)
