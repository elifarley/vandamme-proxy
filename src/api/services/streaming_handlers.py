"""Streaming handler services using strategy pattern.

This module provides format-specific streaming handlers that encapsulate
the logic for handling streaming requests with different API formats.
This eliminates deep nesting in the endpoint by using a strategy pattern.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from fastapi import HTTPException, Request
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
from src.conversion.response_converter import convert_openai_streaming_to_claude_with_cancellation
from src.middleware import RequestContext

logger = logging.getLogger(__name__)


class StreamingHandler(ABC):
    """Abstract base for format-specific streaming handlers.

    Each handler encapsulates the logic for processing streaming requests
    in a specific API format (Anthropic or OpenAI).
    """

    @abstractmethod
    async def handle_streaming_request(
        self,
        *,
        request: Any,
        openai_request: dict[str, Any],
        provider_name: str,
        client_api_key: str | None,
        provider_api_key: str | None,
        tool_name_map_inverse: dict[str, str] | None,
        openai_client: Any,
        http_request: Request,
        request_id: str,
        metrics: Any | None,
        tracker: Any,
        config: Any,
    ) -> StreamingResponse | JSONResponse:
        """Handle a streaming request and return the response.

        Args:
            request: The Claude request object.
            openai_request: The converted OpenAI request (for OpenAI format).
            provider_name: The provider name.
            client_api_key: The client API key for passthrough.
            provider_api_key: The provider API key.
            tool_name_map_inverse: Inverse tool name mapping.
            openai_client: The OpenAI client instance.
            http_request: The FastAPI request object.
            request_id: Unique request identifier.
            metrics: Request metrics object (may be None).
            tracker: Request tracker instance.
            config: Application config object.

        Returns:
            A StreamingResponse with the appropriate stream.
        """
        pass


class AnthropicStreamingHandler(StreamingHandler):
    """Handler for Anthropic-format streaming requests.

    This handler processes streaming requests for providers that use
    Anthropic-compatible API format (direct passthrough without conversion).
    """

    async def handle_streaming_request(
        self,
        *,
        request: Any,
        openai_request: dict[str, Any],
        provider_name: str,
        client_api_key: str | None,
        provider_api_key: str | None,
        tool_name_map_inverse: dict[str, str] | None,
        openai_client: Any,
        http_request: Request,
        request_id: str,
        metrics: Any | None,
        tracker: Any,
        config: Any,
    ) -> StreamingResponse | JSONResponse:
        """Handle Anthropic-format streaming with direct passthrough."""
        provider_config = config.provider_manager.get_provider_config(provider_name)
        resolved_model, claude_request_dict = build_anthropic_passthrough_request(
            request=request,
            provider_name=provider_name,
        )

        try:
            api_key_params = build_api_key_params(
                provider_config=provider_config,
                provider_name=provider_name,
                client_api_key=client_api_key,
                provider_api_key=provider_api_key,
            )
            anthropic_stream = openai_client.create_chat_completion_stream(
                claude_request_dict,
                request_id,
                **api_key_params,
            )

            return streaming_response(
                stream=with_streaming_error_handling(
                    original_stream=anthropic_stream,
                    http_request=http_request,
                    request_id=request_id,
                    provider_name=provider_name,
                    metrics_enabled=config.log_request_metrics,
                ),
                headers=sse_headers(),
            )
        except HTTPException as e:
            await finalize_metrics_on_streaming_error(
                metrics=metrics,
                error=e.detail,
                tracker=tracker,
                request_id=request_id,
            )
            return build_streaming_error_response(
                exception=e,
                openai_client=openai_client,
                metrics=metrics,
                tracker=tracker,
                request_id=request_id,
            )


class OpenAIStreamingHandler(StreamingHandler):
    """Handler for OpenAI-format streaming requests.

    This handler processes streaming requests for providers that use
    OpenAI-compatible API format (with format conversion).
    """

    async def handle_streaming_request(
        self,
        *,
        request: Any,
        openai_request: dict[str, Any],
        provider_name: str,
        client_api_key: str | None,
        provider_api_key: str | None,
        tool_name_map_inverse: dict[str, str] | None,
        openai_client: Any,
        http_request: Request,
        request_id: str,
        metrics: Any | None,
        tracker: Any,
        config: Any,
    ) -> StreamingResponse | JSONResponse:
        """Handle OpenAI-format streaming with conversion to Claude format."""
        provider_config = config.provider_manager.get_provider_config(provider_name)

        try:
            api_key_params = build_api_key_params(
                provider_config=provider_config,
                provider_name=provider_name,
                client_api_key=client_api_key,
                provider_api_key=provider_api_key,
            )
            openai_stream = openai_client.create_chat_completion_stream(
                openai_request,
                request_id,
                **api_key_params,
            )

            # Convert OpenAI SSE to Claude format
            converted_stream = convert_openai_streaming_to_claude_with_cancellation(
                openai_stream,
                request,
                logger,
                http_request,
                openai_client,
                request_id,
                tool_name_map_inverse=tool_name_map_inverse,
            )

            stream_with_error_handling = with_streaming_error_handling(
                original_stream=converted_stream,
                http_request=http_request,
                request_id=request_id,
                provider_name=provider_name,
                metrics_enabled=config.log_request_metrics,
            )

            # Apply middleware to streaming deltas if configured
            if hasattr(config.provider_manager, "middleware_chain"):
                from src.api.middleware_integration import (
                    MiddlewareAwareRequestProcessor,
                    MiddlewareStreamingWrapper,
                )

                processor = MiddlewareAwareRequestProcessor()
                processor.middleware_chain = config.provider_manager.middleware_chain

                wrapped_stream = MiddlewareStreamingWrapper(
                    original_stream=stream_with_error_handling,
                    request_context=RequestContext(
                        messages=openai_request.get("messages", []),
                        provider=provider_name,
                        model=request.model,
                        request_id=request_id,
                        conversation_id=None,
                        client_api_key=client_api_key,
                    ),
                    processor=processor,
                )

                return streaming_response(stream=wrapped_stream, headers=sse_headers())

            return streaming_response(stream=stream_with_error_handling, headers=sse_headers())
        except HTTPException as e:
            await finalize_metrics_on_streaming_error(
                metrics=metrics,
                error=e.detail,
                tracker=tracker,
                request_id=request_id,
            )
            return build_streaming_error_response(
                exception=e,
                openai_client=openai_client,
                metrics=metrics,
                tracker=tracker,
                request_id=request_id,
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
