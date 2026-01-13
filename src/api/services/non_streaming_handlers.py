"""Non-streaming handler services using strategy pattern.

This module provides format-specific non-streaming handlers that encapsulate
the logic for handling non-streaming requests with different API formats.
This eliminates deep nesting in the endpoint by using a strategy pattern.
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from src.api.services.key_rotation import build_api_key_params
from src.api.services.request_builder import build_anthropic_passthrough_request
from src.conversion.response_converter import convert_openai_to_claude_response
from src.core.logging import ConversationLogger
from src.middleware import RequestContext, ResponseContext

logger = logging.getLogger(__name__)
conversation_logger = ConversationLogger.get_logger()


class NonStreamingHandler(ABC):
    """Abstract base for format-specific non-streaming handlers.

    Each handler encapsulates the logic for processing non-streaming requests
    in a specific API format (Anthropic or OpenAI).
    """

    @abstractmethod
    async def handle_with_context(
        self,
        context: Any,  # ApiRequestContext - use Any to avoid circular import
    ) -> JSONResponse:
        """Handle a non-streaming request with RequestContext.

        Args:
            context: The ApiRequestContext containing all request data.

        Returns:
            A JSONResponse with the Claude API format response.
        """
        pass


class AnthropicNonStreamingHandler(NonStreamingHandler):
    """Handler for Anthropic-format non-streaming requests.

    This handler processes non-streaming requests for providers that use
    Anthropic-compatible API format (direct passthrough without conversion).
    """

    async def handle_with_context(
        self,
        context: Any,
    ) -> JSONResponse:
        """Handle Anthropic-format non-streaming with direct passthrough."""
        resolved_model, claude_request_dict = build_anthropic_passthrough_request(
            request=context.request,
            provider_name=context.provider_name,
        )

        # Make API call
        api_key_params = build_api_key_params(
            provider_config=context.provider_config,
            provider_name=context.provider_name,
            client_api_key=context.client_api_key,
            provider_api_key=context.provider_api_key,
        )
        anthropic_response = await context.openai_client.create_chat_completion(
            claude_request_dict,
            context.request_id,
            **api_key_params,
        )

        # Apply middleware to response if configured
        if hasattr(context.config.provider_manager, "middleware_chain"):
            response_context = ResponseContext(
                response=anthropic_response,
                request_context=RequestContext(
                    messages=claude_request_dict.get("messages", []),
                    provider=context.provider_name,
                    model=context.request.model,
                    request_id=context.request_id,
                ),
                is_streaming=False,
            )
            processed_response = (
                await context.config.provider_manager.middleware_chain.process_response(
                    response_context
                )
            )
            anthropic_response = processed_response.response

        # Update metrics
        if context.config.log_request_metrics and context.metrics:
            response_json = json.dumps(anthropic_response)
            context.metrics.response_size = len(response_json)

            usage = anthropic_response.get("usage", {})
            context.metrics.input_tokens = usage.get("input_tokens", 0)
            context.metrics.output_tokens = usage.get("output_tokens", 0)
            context.metrics.cache_read_tokens = usage.get("cache_read_tokens", 0)
            context.metrics.cache_creation_tokens = usage.get("cache_creation_tokens", 0)

            await context.tracker.end_request(context.request_id)

        return JSONResponse(status_code=200, content=anthropic_response)


class OpenAINonStreamingHandler(NonStreamingHandler):
    """Handler for OpenAI-format non-streaming requests.

    This handler processes non-streaming requests for providers that use
    OpenAI-compatible API format (with format conversion).
    """

    async def handle_with_context(
        self,
        context: Any,
    ) -> JSONResponse:
        """Handle OpenAI-format non-streaming with conversion to Claude format."""
        api_key_params = build_api_key_params(
            provider_config=context.provider_config,
            provider_name=context.provider_name,
            client_api_key=context.client_api_key,
            provider_api_key=context.provider_api_key,
        )
        openai_response = await context.openai_client.create_chat_completion(
            context.openai_request,
            context.request_id,
            **api_key_params,
        )

        # Apply middleware to response if configured
        if hasattr(context.config.provider_manager, "middleware_chain"):
            response_context = ResponseContext(
                response=openai_response,
                request_context=RequestContext(
                    messages=context.openai_request.get("messages", []),
                    provider=context.provider_name,
                    model=context.request.model,
                    request_id=context.request_id,
                    client_api_key=context.client_api_key,
                ),
                is_streaming=False,
            )
            processed_response = (
                await context.config.provider_manager.middleware_chain.process_response(
                    response_context
                )
            )
            openai_response = processed_response.response

        # Error detection
        if self._is_error_response(openai_response):
            error_msg = openai_response.get("msg", "Provider returned error response")
            error_code = openai_response.get("code", 500)
            logger.error(
                f"[{context.request_id}] Provider {context.provider_name} "
                f"returned error: {error_msg}"
            )
            response_keys = list(openai_response.keys())
            logger.error(f"[{context.request_id}] Error response structure: {response_keys}")
            if context.config.log_request_metrics:
                logger.error(f"[{context.request_id}] Full error response: {openai_response}")
            raise HTTPException(
                status_code=error_code if isinstance(error_code, int) else 500,
                detail=f"Provider error: {error_msg}",
            )

        # Defensive check
        if openai_response is None:
            logger.error(f"Received None response from provider {context.provider_name}")
            logger.error(f"Request was: {context.openai_request}")
            raise HTTPException(
                status_code=500,
                detail=f"Provider {context.provider_name} returned None response",
            )

        # Calculate response size and extract token usage
        response_json = json.dumps(openai_response)
        response_size = len(response_json)

        usage = openai_response.get("usage")
        if usage is None:
            input_tokens = 0
            output_tokens = 0
            if context.config.log_request_metrics:
                conversation_logger.warning("No usage information in response")
        else:
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)

        # Count tool calls in response
        choices = openai_response.get("choices") or []
        response_message = choices[0].get("message", {}) if choices else {}
        tool_calls = response_message.get("tool_calls", []) or []
        tool_call_count = len(tool_calls)

        # Update metrics
        if context.config.log_request_metrics and context.metrics:
            context.metrics.response_size = response_size
            context.metrics.input_tokens = input_tokens
            context.metrics.output_tokens = output_tokens
            context.metrics.cache_creation_tokens = (
                usage.get("cache_creation_tokens", 0) if usage else 0
            )
            context.metrics.tool_call_count = tool_call_count

            # Debug logging
            conversation_logger.debug(f"📡 RESPONSE STRUCTURE: {list(openai_response.keys())}")
            conversation_logger.debug(f"📡 FULL RESPONSE: {openai_response}")

        # Convert to Claude format
        claude_response = convert_openai_to_claude_response(
            openai_response,
            context.request,
            tool_name_map_inverse=context.tool_name_map_inverse,
        )

        # Log successful completion
        duration_ms = (time.time() - context.start_time) * 1000
        if context.config.log_request_metrics:
            tool_call_display = ""
            if context.metrics and context.metrics.tool_call_count > 0:
                tool_call_display = f" | Tool Calls: {context.metrics.tool_call_count}"
            elif context.tool_use_count > 0 or context.tool_result_count > 0:
                tool_call_display = (
                    f" | Tool Uses: {context.tool_use_count} | "
                    f"Tool Results: {context.tool_result_count}"
                )

            conversation_logger.info(
                f"✅ SUCCESS | Duration: {duration_ms:.0f}ms | "
                f"Tokens: {input_tokens:,}→{output_tokens:,} | "
                f"Size: {context.request_size:,}→{response_size:,} bytes"
                f"{tool_call_display}"
            )
            await context.tracker.end_request(context.request_id)

        return JSONResponse(status_code=200, content=claude_response)

    def _is_error_response(self, response: dict) -> bool:
        """Check if the response is an error response."""
        return response.get("msg") is not None or response.get("error") is not None


def get_non_streaming_handler(config: Any, provider_config: Any | None) -> NonStreamingHandler:
    """Factory function to get the appropriate non-streaming handler.

    Args:
        config: Application config object.
        provider_config: The provider configuration (may be None).

    Returns:
        The appropriate non-streaming handler for the provider's API format.
    """
    if provider_config and provider_config.is_anthropic_format:
        return AnthropicNonStreamingHandler()
    return OpenAINonStreamingHandler()
