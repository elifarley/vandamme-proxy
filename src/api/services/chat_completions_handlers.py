"""Chat completions handlers using strategy pattern.

This module provides format-specific handlers for the /v1/chat/completions
endpoint, eliminating duplication between OpenAI and Anthropic formats.

The strategy pattern allows each handler to encapsulate the logic for processing
requests in a specific API format, making the endpoint code cleaner and more maintainable.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from fastapi.responses import JSONResponse, StreamingResponse


class ChatCompletionsHandler(ABC):
    """Abstract base for format-specific chat completions handlers.

    Each handler encapsulates the logic for processing chat completions requests
    in a specific API format (Anthropic or OpenAI).
    """

    @abstractmethod
    async def handle(
        self,
        openai_request: dict[str, Any],
        resolved_model: str,
        provider_name: str,
        provider_config: Any,
        provider_api_key: str | None,
        client_api_key: str | None,
        config: Any,
        openai_client: Any,
        request_id: str,
        http_request: Any,
        is_metrics_enabled: bool,
        metrics: Any,
        tracker: Any,
    ) -> JSONResponse | StreamingResponse:
        """Handle a chat completions request.

        Args:
            openai_request: The OpenAI-format request dict
            resolved_model: The resolved model name
            provider_name: The provider name
            provider_config: The provider configuration
            provider_api_key: The provider API key
            client_api_key: The client API key
            config: Application config
            openai_client: The OpenAI/Anthropic client
            request_id: Unique request ID
            http_request: FastAPI Request object
            is_metrics_enabled: Whether metrics are enabled
            metrics: Request metrics object
            tracker: Request tracker object

        Returns:
            A JSONResponse or StreamingResponse
        """
        pass


class AnthropicChatCompletionsHandler(ChatCompletionsHandler):
    """Handler for Anthropic-format chat completions (with conversion).

    This handler processes requests for providers that use Anthropic-compatible
    API format. It converts OpenAI Chat Completions requests to Anthropic Messages
    format and converts responses back to OpenAI format.
    """

    async def handle(
        self,
        openai_request: dict[str, Any],
        resolved_model: str,
        provider_name: str,
        provider_config: Any,
        provider_api_key: str | None,
        client_api_key: str | None,
        config: Any,
        openai_client: Any,
        request_id: str,
        http_request: Any,
        is_metrics_enabled: bool,
        metrics: Any,
        tracker: Any,
    ) -> JSONResponse | StreamingResponse:
        """Handle Anthropic-format chat completions."""
        from src.api.services.key_rotation import build_api_key_params
        from src.api.services.streaming import (
            sse_headers,
            streaming_response,
            with_streaming_error_handling,
        )
        from src.conversion.anthropic_sse_to_openai import (
            anthropic_sse_to_openai_chat_completions_sse,
        )
        from src.conversion.anthropic_to_openai import anthropic_message_to_openai_chat_completion
        from src.conversion.openai_to_anthropic import openai_chat_completions_to_anthropic_messages

        # Convert to Anthropic format
        anthropic_request = openai_chat_completions_to_anthropic_messages(
            openai_request=openai_request,
            resolved_model=resolved_model,
        )

        api_key_params = build_api_key_params(
            provider_config=provider_config,
            provider_name=provider_name,
            client_api_key=client_api_key,
            provider_api_key=provider_api_key,
            config=config,
        )

        is_streaming = openai_request.get("stream", False)

        if is_streaming:
            anthropic_stream = openai_client.create_chat_completion_stream(
                anthropic_request,
                request_id,
                **api_key_params,
            )

            async def anthropic_stream_as_openai() -> AsyncGenerator[str, None]:
                async for chunk in anthropic_sse_to_openai_chat_completions_sse(
                    anthropic_sse_lines=anthropic_stream,
                    model=resolved_model,
                    completion_id=f"chatcmpl-{request_id}",
                ):
                    yield chunk

            return streaming_response(
                stream=with_streaming_error_handling(
                    original_stream=anthropic_stream_as_openai(),
                    http_request=http_request,
                    request_id=request_id,
                    provider_name=provider_name,
                    metrics_enabled=is_metrics_enabled,
                ),
                headers=sse_headers(),
            )
        else:
            anthropic_response = await openai_client.create_chat_completion(
                anthropic_request,
                request_id,
                **api_key_params,
            )

            openai_response = anthropic_message_to_openai_chat_completion(
                anthropic=anthropic_response
            )

            if is_metrics_enabled and metrics and tracker:
                await tracker.end_request(request_id)

            return JSONResponse(status_code=200, content=openai_response)


class OpenAIChatCompletionsHandler(ChatCompletionsHandler):
    """Handler for OpenAI-format chat completions (passthrough).

    This handler processes requests for providers that use OpenAI-compatible
    API format with direct passthrough (no conversion needed).
    """

    async def handle(
        self,
        openai_request: dict[str, Any],
        resolved_model: str,
        provider_name: str,
        provider_config: Any,
        provider_api_key: str | None,
        client_api_key: str | None,
        config: Any,
        openai_client: Any,
        request_id: str,
        http_request: Any,
        is_metrics_enabled: bool,
        metrics: Any,
        tracker: Any,
    ) -> JSONResponse | StreamingResponse:
        """Handle OpenAI-format chat completions with passthrough."""
        from src.api.services.key_rotation import build_api_key_params
        from src.api.services.streaming import (
            sse_headers,
            streaming_response,
            with_streaming_error_handling,
        )

        api_key_params = build_api_key_params(
            provider_config=provider_config,
            provider_name=provider_name,
            client_api_key=client_api_key,
            provider_api_key=provider_api_key,
            config=config,
        )

        is_streaming = openai_request.get("stream", False)

        if is_streaming:
            openai_stream = openai_client.create_chat_completion_stream(
                openai_request,
                request_id,
                **api_key_params,
            )

            async def openai_stream_as_sse_lines() -> AsyncGenerator[str, None]:
                async for chunk in openai_stream:
                    yield f"{chunk}\n"

            return streaming_response(
                stream=with_streaming_error_handling(
                    original_stream=openai_stream_as_sse_lines(),
                    http_request=http_request,
                    request_id=request_id,
                    provider_name=provider_name,
                    metrics_enabled=is_metrics_enabled,
                ),
                headers=sse_headers(),
            )
        else:
            openai_response = await openai_client.create_chat_completion(
                openai_request,
                request_id,
                **api_key_params,
            )

            if is_metrics_enabled and metrics and tracker:
                await tracker.end_request(request_id)

            return JSONResponse(status_code=200, content=openai_response)


def get_chat_completions_handler(provider_config: Any | None) -> ChatCompletionsHandler:
    """Factory function to get the appropriate chat completions handler.

    Args:
        provider_config: The provider configuration (may be None)

    Returns:
        The appropriate chat completions handler for the provider's API format
    """
    if provider_config and provider_config.is_anthropic_format:
        return AnthropicChatCompletionsHandler()
    return OpenAIChatCompletionsHandler()
