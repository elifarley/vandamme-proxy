"""Token limit transformer.

Validates and clamps max_tokens to configured limits.
"""

import dataclasses

from src.conversion.pipeline.base import ConversionContext, RequestTransformer
from src.core.config.accessors import max_tokens_limit, min_tokens_limit


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
        requested = context.claude_request.max_tokens
        clamped = min(max(requested, min_tokens_limit()), max_tokens_limit())

        new_request = {**context.openai_request, "max_tokens": clamped}
        return dataclasses.replace(context, openai_request=new_request)
