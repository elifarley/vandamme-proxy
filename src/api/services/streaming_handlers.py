"""Streaming handler services using strategy pattern.

This module provides format-specific streaming handlers that encapsulate
the logic for handling streaming requests with different API formats.
This eliminates deep nesting in the endpoint by using a strategy pattern.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from src.api.services.error_handling import (
    build_streaming_error_response,
    finalize_metrics_on_streaming_error,
)
from src.api.services.key_rotation import build_api_key_params
from src.api.services.request_builder import build_anthropic_passthrough_request
from src.api.services.streaming import (
    sse_headers,
    streaming_response,
    with_streaming_error_handling,
)
from src.conversion.response_converter import convert_openai_streaming_to_claude
from src.middleware import RequestContext

logger = logging.getLogger(__name__)


class StreamingHandler(ABC):
    """Abstract base for format-specific streaming handlers.

    Each handler encapsulates the logic for processing streaming requests
    in a specific API format (Anthropic or OpenAI).
    """

    @abstractmethod
    async def handle_with_context(
        self,
        context: Any,  # ApiRequestContext - use Any to avoid circular import
    ) -> StreamingResponse | JSONResponse:
        """Handle a streaming request with RequestContext.

        Args:
            context: The ApiRequestContext containing all request data.

        Returns:
            A StreamingResponse with the appropriate stream.
        """
        pass


class AnthropicStreamingHandler(StreamingHandler):
    """Handler for Anthropic-format streaming requests.

    This handler processes streaming requests for providers that use
    Anthropic-compatible API format (direct passthrough without conversion).
    """

    async def handle_with_context(
        self,
        context: Any,
    ) -> StreamingResponse | JSONResponse:
        """Handle Anthropic-format streaming with direct passthrough."""
        resolved_model, claude_request_dict = build_anthropic_passthrough_request(
            request=context.request,
            provider_name=context.provider_name,
        )

        try:
            api_key_params = build_api_key_params(
                provider_config=context.provider_config,
                provider_name=context.provider_name,
                client_api_key=context.client_api_key,
                provider_api_key=context.provider_api_key,
            )
            anthropic_stream = context.openai_client.create_chat_completion_stream(
                claude_request_dict,
                context.request_id,
                **api_key_params,
            )

            return streaming_response(
                stream=with_streaming_error_handling(
                    original_stream=anthropic_stream,
                    http_request=context.http_request,
                    request_id=context.request_id,
                    provider_name=context.provider_name,
                    metrics_enabled=context.is_metrics_enabled,
                ),
                headers=sse_headers(),
            )
        except HTTPException as e:
            await finalize_metrics_on_streaming_error(
                metrics=context.metrics,
                error=e.detail,
                tracker=context.tracker,
                request_id=context.request_id,
            )
            return build_streaming_error_response(
                exception=e,
                openai_client=context.openai_client,
                metrics=context.metrics,
                tracker=context.tracker,
                request_id=context.request_id,
            )


class OpenAIStreamingHandler(StreamingHandler):
    """Handler for OpenAI-format streaming requests.

    This handler processes streaming requests for providers that use
    OpenAI-compatible API format (with format conversion).
    """

    async def handle_with_context(
        self,
        context: Any,
    ) -> StreamingResponse | JSONResponse:
        """Handle OpenAI-format streaming with conversion to Claude format."""
        try:
            api_key_params = build_api_key_params(
                provider_config=context.provider_config,
                provider_name=context.provider_name,
                client_api_key=context.client_api_key,
                provider_api_key=context.provider_api_key,
            )
            openai_stream = context.openai_client.create_chat_completion_stream(
                context.openai_request,
                context.request_id,
                **api_key_params,
            )

            # Convert OpenAI SSE to Claude format
            converted_stream = convert_openai_streaming_to_claude(
                openai_stream,
                context.request,
                logger,
                tool_name_map_inverse=context.tool_name_map_inverse,
                http_request=context.http_request,
                openai_client=context.openai_client,
                request_id=context.request_id,
                metrics=context.metrics,
                enable_usage_tracking=context.is_metrics_enabled,
            )

            stream_with_error_handling = with_streaming_error_handling(
                original_stream=converted_stream,
                http_request=context.http_request,
                request_id=context.request_id,
                provider_name=context.provider_name,
                metrics_enabled=context.is_metrics_enabled,
            )

            # Apply middleware to streaming deltas if configured
            if hasattr(context.config.provider_manager, "middleware_chain"):
                from src.api.middleware_integration import (
                    MiddlewareAwareRequestProcessor,
                    MiddlewareStreamingWrapper,
                )

                processor = MiddlewareAwareRequestProcessor()
                processor.middleware_chain = context.config.provider_manager.middleware_chain

                wrapped_stream = MiddlewareStreamingWrapper(
                    original_stream=stream_with_error_handling,
                    request_context=RequestContext(
                        messages=context.openai_request.get("messages", []),
                        provider=context.provider_name,
                        model=context.request.model,
                        request_id=context.request_id,
                        conversation_id=None,
                        client_api_key=context.client_api_key,
                    ),
                    processor=processor,
                )

                return streaming_response(stream=wrapped_stream, headers=sse_headers())

            return streaming_response(stream=stream_with_error_handling, headers=sse_headers())
        except HTTPException as e:
            await finalize_metrics_on_streaming_error(
                metrics=context.metrics,
                error=e.detail,
                tracker=context.tracker,
                request_id=context.request_id,
            )
            return build_streaming_error_response(
                exception=e,
                openai_client=context.openai_client,
                metrics=context.metrics,
                tracker=context.tracker,
                request_id=context.request_id,
            )


def get_streaming_handler(config: Any, provider_config: Any | None) -> StreamingHandler:
    """Factory function to get the appropriate streaming handler.

    Args:
        config: Application config object.
        provider_config: The provider configuration (may be None).

    Returns:
        The appropriate streaming handler for the provider's API format.
    """
    if provider_config and provider_config.is_anthropic_format:
        return AnthropicStreamingHandler()
    return OpenAIStreamingHandler()
