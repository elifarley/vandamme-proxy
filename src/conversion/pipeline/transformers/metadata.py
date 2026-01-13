"""Metadata injector transformer.

Adds provider metadata for upstream routing and response conversion.
"""

import dataclasses

from src.conversion.pipeline.base import ConversionContext, RequestTransformer


class MetadataInjector(RequestTransformer):
    """Injects provider metadata into the request.

    These fields are used internally by the proxy for:
    - Provider selection and routing
    - Response conversion (tool name un-mapping)
    - Metrics and logging

    The metadata fields are removed before sending the request to upstream
    providers.
    """

    def transform(self, context: ConversionContext) -> ConversionContext:
        """Add provider metadata to the OpenAI request.

        Args:
            context: The input conversion context.

        Returns:
            A new context with metadata added to the OpenAI request.
        """
        new_request = context.openai_request.copy()

        # Provider metadata for upstream selection
        new_request["_provider"] = context.provider_name

        # Tool name inverse mapping for response conversion
        if context.tool_name_map_inverse:
            new_request["_tool_name_map_inverse"] = context.tool_name_map_inverse

        return dataclasses.replace(context, openai_request=new_request)
