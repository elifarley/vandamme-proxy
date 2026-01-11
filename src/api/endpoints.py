import json
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from src.api.services.key_rotation import build_api_key_params
from src.api.services.metrics_helper import populate_request_metrics
from src.api.services.provider_context import resolve_provider_context
from src.api.services.request_builder import build_anthropic_passthrough_request
from src.api.services.streaming import (
    sse_headers,
    streaming_response,
    with_streaming_error_handling,
)
from src.api.services.streaming_handlers import get_streaming_handler
from src.api.utils.yaml_formatter import format_health_yaml
from src.conversion.anthropic_sse_to_openai import anthropic_sse_to_openai_chat_completions_sse
from src.conversion.anthropic_to_openai import anthropic_message_to_openai_chat_completion
from src.conversion.openai_to_anthropic import openai_chat_completions_to_anthropic_messages
from src.conversion.request_converter import convert_claude_to_openai
from src.conversion.response_converter import (
    convert_openai_to_claude_response,
)
from src.core.config import config
from src.core.logging import ConversationLogger
from src.core.metrics.runtime import get_request_tracker
from src.core.model_manager import get_model_manager
from src.middleware import RequestContext, ResponseContext
from src.models.cache import ModelsDiskCache
from src.models.claude import ClaudeMessagesRequest, ClaudeTokenCountRequest
from src.models.openai import OpenAIChatCompletionsRequest

LOG_REQUEST_METRICS = config.log_request_metrics
logger = logging.getLogger(__name__)
conversation_logger = ConversationLogger.get_logger()

router = APIRouter()


def _is_timeout_error(exc: Exception) -> bool:
    """Check if an exception is a timeout-related error.

    Args:
        exc: The exception to check.

    Returns:
        True if the exception is a timeout error, False otherwise.
    """
    # Check for httpx timeout errors
    if isinstance(exc, httpx.TimeoutException):
        return True
    # Check for httpx ReadTimeout specifically
    if isinstance(exc, httpx.ReadTimeout):
        return True
    # Check OpenAI SDK timeout errors
    error_str = str(exc).lower()
    timeout_keywords = ("timeout", "timed out", "read timeout", "connect timeout")
    return any(keyword in error_str for keyword in timeout_keywords)


def _map_timeout_to_504() -> HTTPException:
    """Map a timeout error to HTTP 504 Gateway Timeout.

    Returns:
        An HTTPException with status code 504.
    """
    return HTTPException(
        status_code=504,
        detail="Upstream request timed out. Consider increasing REQUEST_TIMEOUT.",
    )


def _log_traceback(log: Any = logger) -> None:
    """Log full traceback for debugging.

    This utility centralizes the traceback logging pattern that was
    duplicated across multiple exception handlers.

    Args:
        log: The logger to use (defaults to module logger).
    """
    import traceback

    log.error(traceback.format_exc())


# Initialize models cache if enabled
models_cache = None
if config.models_cache_enabled and not os.environ.get("PYTEST_CURRENT_TEST"):
    models_cache = ModelsDiskCache(
        cache_dir=Path(config.cache_dir),
        ttl_hours=config.models_cache_ttl_hours,
    )

# Custom headers are now handled per provider
# count_tool_calls has been moved to src.api.services.metrics_helper


async def validate_api_key(
    x_api_key: str | None = Header(None), authorization: str | None = Header(None)
) -> str | None:
    """
    Validate and return the client's API key from either x-api-key header or
    Authorization header. Returns the key if present, None otherwise.
    """
    client_api_key = None

    # Extract API key from headers
    if x_api_key:
        client_api_key = x_api_key
    elif authorization and authorization.startswith("Bearer "):
        client_api_key = authorization.replace("Bearer ", "")

    # Skip validation if PROXY_API_KEY is not set in the environment
    if not config.proxy_api_key:
        return client_api_key  # Return the key even if validation is disabled

    # Validate the client API key
    if not client_api_key or not config.validate_client_api_key(client_api_key):
        logger.warning("Invalid API key provided by client")
        raise HTTPException(
            status_code=401, detail="Invalid API key. Please provide a valid Anthropic API key."
        )

    return client_api_key


def _is_error_response(response: dict[str, Any]) -> bool:
    """
    Detect if a provider response is an error format.

    Checks for common error response patterns across different providers:
    - Explicit success: false flag
    - Error code with missing choices
    - Error field presence

    Args:
        response: The response dictionary from a provider

    Returns:
        True if this appears to be an error response
    """
    if not isinstance(response, dict):
        return False

    # Check explicit error indicators
    if response.get("success") is False:
        return True

    # Check for error code with missing choices
    if "code" in response and not response.get("choices"):
        return True

    # Check for error field
    return "error" in response


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: OpenAIChatCompletionsRequest,
    http_request: Request,
    client_api_key: str | None = Depends(validate_api_key),
) -> JSONResponse | StreamingResponse:
    """OpenAI-compatible chat completions endpoint.

    - If the resolved provider is OpenAI-format: passthrough request/response.
    - If the resolved provider is Anthropic-format: (future) translate OpenAI request to
      Anthropic Messages API and translate response back.

    For now, this endpoint supports OpenAI-format providers.
    """
    request_id = str(uuid.uuid4())

    # Start request tracking if metrics are enabled
    if LOG_REQUEST_METRICS:
        tracker = get_request_tracker(http_request)

        # Resolve early so active requests never show provider-prefixed aliases.
        provider_name, resolved_model = get_model_manager().resolve_model(request.model)

        metrics = await tracker.start_request(
            request_id=request_id,
            claude_model=request.model,
            is_streaming=request.stream or False,
            provider=provider_name,
            resolved_model=resolved_model,
        )
        await tracker.update_last_accessed(
            provider=provider_name,
            model=resolved_model,
            timestamp=metrics.start_time_iso,
        )

        # /v1/chat/completions doesn't carry Claude tool_use/tool_result blocks.
        # Tool call counts are derived from upstream usage where available.
    else:
        metrics = None

    with ConversationLogger.correlation_context(request_id):
        start_time = time.time()

        provider_ctx = await resolve_provider_context(
            model=request.model,
            client_api_key=client_api_key,
        )
        provider_name = provider_ctx.provider_name
        resolved_model = provider_ctx.resolved_model
        provider_config = provider_ctx.provider_config

        if LOG_REQUEST_METRICS and metrics:
            metrics.provider = provider_name  # type: ignore[assignment]

            # Metrics must always use the resolved target model (no provider prefix).
            # Some alias targets for providers like OpenRouter are configured as
            # provider-scoped model IDs (e.g. "openai/gpt-5.2"), which are still a
            # concrete model identifier; we should never record the alias token.
            metrics.openai_model = resolved_model

            await tracker.update_last_accessed(
                provider=provider_name,
                model=resolved_model,
                timestamp=metrics.start_time_iso,
            )

            logger.debug(
                "[metrics] chat.completions model=%s resolved_provider=%s resolved_model=%s",
                request.model,
                provider_name,
                resolved_model,
            )

        # Build upstream request dict and attach resolved model.
        openai_request: dict[str, Any] = request.model_dump(exclude_none=True)
        openai_request["model"] = resolved_model

        openai_client = config.provider_manager.get_client(provider_name, client_api_key)

        provider_api_key = provider_ctx.provider_api_key

        if provider_config.is_anthropic_format:
            # Translate OpenAI Chat Completions -> Anthropic Messages request.
            anthropic_request = openai_chat_completions_to_anthropic_messages(
                openai_request=openai_request,
                resolved_model=resolved_model,
            )

            if request.stream:
                api_key_params = build_api_key_params(
                    provider_config=provider_config,
                    provider_name=provider_name,
                    client_api_key=client_api_key,
                    provider_api_key=provider_api_key,
                )
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
                        metrics_enabled=LOG_REQUEST_METRICS,
                    ),
                    headers=sse_headers(),
                )

            # Non-streaming path: ensure metrics are finalized.
            # Streaming finalization is handled by with_streaming_error_handling.
            try:
                api_key_params = build_api_key_params(
                    provider_config=provider_config,
                    provider_name=provider_name,
                    client_api_key=client_api_key,
                    provider_api_key=provider_api_key,
                )
                anthropic_response = await openai_client.create_chat_completion(
                    anthropic_request,
                    request_id,
                    **api_key_params,
                )
            except Exception as e:
                if LOG_REQUEST_METRICS and metrics:
                    metrics.error = str(e)
                    metrics.error_type = "upstream_error"
                    await tracker.end_request(request_id)
                # Map timeout errors to 504 Gateway Timeout
                if _is_timeout_error(e):
                    raise _map_timeout_to_504() from e
                raise

            openai_response = anthropic_message_to_openai_chat_completion(
                anthropic=anthropic_response
            )

            if LOG_REQUEST_METRICS and metrics:
                await tracker.end_request(request_id)
            return JSONResponse(status_code=200, content=openai_response)

        # OpenAI-format providers: passthrough request/response.

        if request.stream:
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

            async def openai_stream_as_sse_lines() -> AsyncGenerator[str, None]:
                async for chunk in openai_stream:
                    # Ensure SSE lines end with newline for broad client compatibility.
                    yield f"{chunk}\n"

            return streaming_response(
                stream=with_streaming_error_handling(
                    original_stream=openai_stream_as_sse_lines(),
                    http_request=http_request,
                    request_id=request_id,
                    provider_name=provider_name,
                    metrics_enabled=LOG_REQUEST_METRICS,
                ),
                headers=sse_headers(),
            )

        try:
            api_key_params = build_api_key_params(
                provider_config=provider_config,
                provider_name=provider_name,
                client_api_key=client_api_key,
                provider_api_key=provider_api_key,
            )
            openai_response = await openai_client.create_chat_completion(
                openai_request,
                request_id,
                **api_key_params,
            )
        except Exception as e:
            if LOG_REQUEST_METRICS and metrics:
                metrics.error = str(e)
                metrics.error_type = "upstream_error"
                await tracker.end_request(request_id)
            # Map timeout errors to 504 Gateway Timeout
            if _is_timeout_error(e):
                raise _map_timeout_to_504() from e
            raise

        # Basic timing log (metrics system is handled elsewhere for /v1/messages).
        duration_ms = (time.time() - start_time) * 1000
        logger.debug(
            "OpenAI chat/completions completed in %.0fms (provider=%s model=%s)",
            duration_ms,
            provider_name,
            resolved_model,
        )

        if LOG_REQUEST_METRICS and metrics:
            await tracker.end_request(request_id)
        return JSONResponse(status_code=200, content=openai_response)


@router.post("/v1/messages", response_model=None)
async def create_message(
    request: ClaudeMessagesRequest,
    http_request: Request,
    client_api_key: str | None = Depends(validate_api_key),
) -> JSONResponse | StreamingResponse:
    # Generate unique request ID for tracking
    request_id = str(uuid.uuid4())

    # Start request tracking if metrics are enabled
    if LOG_REQUEST_METRICS:
        tracker = get_request_tracker(http_request)

        # Resolve early so active requests never show provider-prefixed aliases.
        provider_name, resolved_model = get_model_manager().resolve_model(request.model)

        metrics = await tracker.start_request(
            request_id=request_id,
            claude_model=request.model,
            is_streaming=request.stream or False,
            provider=provider_name,
            resolved_model=resolved_model,
        )
        await tracker.update_last_accessed(
            provider=provider_name,
            model=resolved_model,
            timestamp=metrics.start_time_iso,
        )

        # Populate metrics with request details (message count, size, tool counts)
        message_count, request_size, tool_use_count = populate_request_metrics(
            metrics=metrics,
            request=request,
        )
        tool_result_count = metrics.tool_result_count
    else:
        metrics = None
        # Populate metrics even when disabled to get counts for logging
        message_count, request_size, tool_use_count = populate_request_metrics(
            metrics=None,
            request=request,
        )
        tool_result_count = 0  # Not needed for logging when metrics disabled

    # Use correlation context for all logs within this request
    with ConversationLogger.correlation_context(request_id):
        # Log request start
        if LOG_REQUEST_METRICS:
            conversation_logger.info(
                f"🚀 START | Model: {request.model} | "
                f"Stream: {request.stream} | "
                f"Messages: {message_count} | "
                f"Max Tokens: {request.max_tokens} | "
                f"Size: {request_size:,} bytes | "
                f"Tools: {len(request.tools) if request.tools else 0} | "
                f"Tool Uses: {tool_use_count} | "
                f"Tool Results: {tool_result_count}"
            )
        else:
            logger.debug(
                f"Processing Claude request: model={request.model}, stream={request.stream}"
            )

        start_time = time.time()

        # Initialize client variable to avoid UnboundLocalError
        openai_client = None

        try:
            # Convert Claude request to OpenAI format
            openai_request = convert_claude_to_openai(request, get_model_manager())

            # Extract provider from request
            provider_name = openai_request.pop("_provider", "openai")
            tool_name_map_inverse = openai_request.pop("_tool_name_map_inverse", None)

            # Get provider config to check if passthrough is needed
            provider_config = config.provider_manager.get_provider_config(provider_name)

            if provider_config and provider_config.uses_passthrough:
                if not client_api_key:
                    raise HTTPException(
                        status_code=401,
                        detail=f"Provider '{provider_name}' requires API key passthrough, "
                        f"but no client API key was provided",
                    )
                logger.debug(f"Using client API key for provider '{provider_name}'")

            # Get the appropriate client for this provider
            openai_client = config.provider_manager.get_client(provider_name, client_api_key)

            # For non-passthrough providers, select a provider API key (supports multi-key rotation)
            provider_api_key: str | None = None
            if provider_config and not provider_config.uses_passthrough:
                provider_api_key = await config.provider_manager.get_next_provider_api_key(
                    provider_name
                )

            # Apply middleware to request (e.g., inject thought signatures)
            if hasattr(config.provider_manager, "middleware_chain"):
                request_context = RequestContext(
                    messages=openai_request.get("messages", []),
                    provider=provider_name,
                    model=request.model,
                    request_id=request_id,
                    conversation_id=None,  # Could be extracted from request if needed
                    client_api_key=client_api_key,  # Pass client API key to middleware
                )
                processed_context = await config.provider_manager.middleware_chain.process_request(
                    request_context
                )
                if processed_context.messages != request_context.messages:
                    openai_request["messages"] = processed_context.messages
                    logger.debug(f"Request modified by middleware, provider={provider_name}")

            # Metrics should always be recorded against the *resolved target model*
            # (never the alias the user typed).
            if LOG_REQUEST_METRICS and metrics:
                resolved_model = str(openai_request.get("model", "unknown"))
                metrics.provider = provider_name  # type: ignore[assignment]
                metrics.openai_model = resolved_model

                # Update last_accessed timestamp
                await tracker.update_last_accessed(
                    provider=provider_name,
                    model=resolved_model,
                    timestamp=metrics.start_time_iso,
                )

                logger.debug(
                    "[metrics] messages model=%s resolved_provider=%s resolved_model=%s",
                    request.model,
                    provider_name,
                    resolved_model,
                )

            # Check if client disconnected before processing
            if await http_request.is_disconnected():
                if LOG_REQUEST_METRICS and metrics:
                    metrics.error = "Client disconnected before processing"
                    metrics.error_type = "client_disconnect"
                    await tracker.end_request(request_id)
                raise HTTPException(status_code=499, detail="Client disconnected")

            if request.stream:
                # Streaming response - use strategy pattern to handle different formats
                provider_config = config.provider_manager.get_provider_config(provider_name)
                handler = get_streaming_handler(config, provider_config)

                return await handler.handle_streaming_request(
                    request=request,
                    openai_request=openai_request,
                    provider_name=provider_name,
                    client_api_key=client_api_key,
                    provider_api_key=provider_api_key,
                    tool_name_map_inverse=tool_name_map_inverse,
                    openai_client=openai_client,
                    http_request=http_request,
                    request_id=request_id,
                    metrics=metrics,
                    tracker=tracker,
                    config=config,
                )
            else:
                # Non-streaming response
                # Check if provider uses Anthropic format
                provider_config = config.provider_manager.get_provider_config(provider_name)

                if provider_config and provider_config.is_anthropic_format:
                    # Passthrough mode for Anthropic-compatible APIs
                    # Convert request to dict directly (no format conversion)
                    resolved_model, claude_request_dict = build_anthropic_passthrough_request(
                        request=request,
                        provider_name=provider_name,
                    )

                    # Make API call
                    api_key_params = build_api_key_params(
                        provider_config=provider_config,
                        provider_name=provider_name,
                        client_api_key=client_api_key,
                        provider_api_key=provider_api_key,
                    )
                    anthropic_response = await openai_client.create_chat_completion(
                        claude_request_dict,
                        request_id,
                        **api_key_params,
                    )

                    # Apply middleware to response (e.g., extract thought signatures)
                    if hasattr(config.provider_manager, "middleware_chain"):
                        response_context = ResponseContext(
                            response=anthropic_response,
                            request_context=RequestContext(
                                messages=claude_request_dict.get("messages", []),
                                provider=provider_name,
                                model=request.model,
                                request_id=request_id,
                            ),
                            is_streaming=False,
                        )
                        processed_response = (
                            await config.provider_manager.middleware_chain.process_response(
                                response_context
                            )
                        )
                        anthropic_response = processed_response.response

                    # Update metrics
                    if LOG_REQUEST_METRICS and metrics:
                        response_json = json.dumps(anthropic_response)
                        metrics.response_size = len(response_json)

                        # Extract usage from response (if available)
                        usage = anthropic_response.get("usage", {})
                        metrics.input_tokens = usage.get("input_tokens", 0)
                        metrics.output_tokens = usage.get("output_tokens", 0)
                        metrics.cache_read_tokens = usage.get("cache_read_tokens", 0)
                        metrics.cache_creation_tokens = usage.get("cache_creation_tokens", 0)

                    # Direct passthrough - no conversion needed
                    if LOG_REQUEST_METRICS and metrics:
                        await tracker.end_request(request_id)
                    return JSONResponse(status_code=200, content=anthropic_response)
                else:
                    # OpenAI format path (existing logic)
                    api_key_params = build_api_key_params(
                        provider_config=provider_config,
                        provider_name=provider_name,
                        client_api_key=client_api_key,
                        provider_api_key=provider_api_key,
                    )
                    openai_response = await openai_client.create_chat_completion(
                        openai_request,
                        request_id,
                        **api_key_params,
                    )

                    # Apply middleware to response (e.g., extract thought signatures)
                    if hasattr(config.provider_manager, "middleware_chain"):
                        response_context = ResponseContext(
                            response=openai_response,
                            request_context=RequestContext(
                                messages=openai_request.get("messages", []),
                                provider=provider_name,
                                model=request.model,
                                request_id=request_id,
                                client_api_key=client_api_key,
                            ),
                            is_streaming=False,
                        )
                        processed_response = (
                            await config.provider_manager.middleware_chain.process_response(
                                response_context
                            )
                        )
                        openai_response = processed_response.response

                    # Add error detection before processing
                    if _is_error_response(openai_response):
                        error_msg = openai_response.get("msg", "Provider returned error response")
                        error_code = openai_response.get("code", 500)
                        logger.error(
                            f"[{request_id}] Provider {provider_name} returned error: {error_msg}"
                        )
                        response_keys = list(openai_response.keys())
                        logger.error(f"[{request_id}] Error response structure: {response_keys}")
                        if LOG_REQUEST_METRICS:
                            logger.error(f"[{request_id}] Full error response: {openai_response}")
                        raise HTTPException(
                            status_code=error_code if isinstance(error_code, int) else 500,
                            detail=f"Provider error: {error_msg}",
                        )

                    # Add defensive check
                    if openai_response is None:
                        logger.error(f"Received None response from provider {provider_name}")
                        logger.error(f"Request was: {openai_request}")
                        raise HTTPException(
                            status_code=500,
                            detail=f"Provider {provider_name} returned None response",
                        )

                    # Calculate response size
                    response_json = json.dumps(openai_response)
                    response_size = len(response_json)

                    # Extract token usage
                    usage = openai_response.get("usage")
                    if usage is None:
                        # Handle missing usage field
                        input_tokens = 0
                        output_tokens = 0
                        if LOG_REQUEST_METRICS:
                            conversation_logger.warning("No usage information in response")
                    else:
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)

                    # Count tool calls in response (OpenAI function calls)
                    choices = openai_response.get("choices") or []
                    response_message = choices[0].get("message", {}) if choices else {}
                    tool_calls = response_message.get("tool_calls", []) or []
                    tool_call_count = len(tool_calls)

                    # Update metrics
                    if LOG_REQUEST_METRICS and metrics:
                        metrics.response_size = response_size
                        metrics.input_tokens = input_tokens
                        metrics.output_tokens = output_tokens
                        metrics.cache_creation_tokens = (
                            usage.get("cache_creation_tokens", 0) if usage else 0
                        )
                        metrics.tool_call_count = tool_call_count

                    # Debug: Log the response structure
                    if LOG_REQUEST_METRICS:
                        conversation_logger.debug(
                            f"📡 RESPONSE STRUCTURE: {list(openai_response.keys())}"
                        )
                        conversation_logger.debug(f"📡 FULL RESPONSE: {openai_response}")

                    claude_response = convert_openai_to_claude_response(
                        openai_response,
                        request,
                        tool_name_map_inverse=tool_name_map_inverse,
                    )

                # Log successful completion
                duration_ms = (time.time() - start_time) * 1000
                if LOG_REQUEST_METRICS:
                    # Get tool call count if available
                    tool_call_display = ""
                    if metrics and metrics.tool_call_count > 0:
                        tool_call_display = f" | Tool Calls: {metrics.tool_call_count}"
                    elif tool_use_count > 0 or tool_result_count > 0:
                        tool_call_display = (
                            f" | Tool Uses: {tool_use_count} | Tool Results: {tool_result_count}"
                        )

                    conversation_logger.info(
                        f"✅ SUCCESS | Duration: {duration_ms:.0f}ms | "
                        f"Tokens: {input_tokens:,}→{output_tokens:,} | "
                        f"Size: {request_size:,}→{response_size:,} bytes"
                        f"{tool_call_display}"
                    )

                # End request tracking
                if LOG_REQUEST_METRICS:
                    await tracker.end_request(request_id)

                return JSONResponse(status_code=200, content=claude_response)

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            if LOG_REQUEST_METRICS and metrics:
                metrics.error = "HTTP exception"
                metrics.error_type = "http_error"
                metrics.end_time = time.time()
                await tracker.end_request(request_id)
            raise
        except Exception as e:
            # Check if this is a timeout error and map to 504
            if _is_timeout_error(e):
                if LOG_REQUEST_METRICS and metrics:
                    metrics.error = "Upstream timeout"
                    metrics.error_type = "timeout"
                    metrics.end_time = time.time()
                    await tracker.end_request(request_id)
                raise _map_timeout_to_504() from e

            duration_ms = (time.time() - start_time) * 1000

            # Debug: Check if we have an openai_response when error occurs
            if "openai_response" in locals() and openai_response is not None:
                logger.error(f"Error occurred with response: {openai_response}")

            # Use openai_client if available, otherwise use a generic error message
            if openai_client is not None:
                error_message = openai_client.classify_openai_error(str(e))
            else:
                error_message = str(e)

            # Update metrics with error
            if LOG_REQUEST_METRICS and metrics:
                metrics.error = error_message
                metrics.error_type = "unexpected_error"
                metrics.end_time = time.time()

            if LOG_REQUEST_METRICS:
                conversation_logger.error(
                    f"❌ ERROR | Duration: {duration_ms:.0f}ms | Error: {error_message}"
                )
                _log_traceback(conversation_logger)
            else:
                logger.error(f"Unexpected error processing request: {e}")
                _log_traceback()

            # End request tracking
            if LOG_REQUEST_METRICS:
                await tracker.end_request(request_id)

            raise HTTPException(status_code=500, detail=error_message) from e


@router.post("/v1/messages/count_tokens")
async def count_tokens(
    request: ClaudeTokenCountRequest, _: None = Depends(validate_api_key)
) -> JSONResponse:
    try:
        # Get provider and model
        provider_name, actual_model = get_model_manager().resolve_model(request.model)
        provider_config = config.provider_manager.get_provider_config(provider_name)

        if provider_config and provider_config.is_anthropic_format:
            # For Anthropic-compatible APIs, use their token counting if available
            # Create request for token counting
            messages_list: list[dict[str, Any]] = []
            count_request = {
                "model": actual_model,
                "messages": messages_list,
            }

            # Add system message
            if request.system:
                messages_list.append(
                    {
                        "role": "user",  # type: ignore[assignment]
                        "content": request.system if isinstance(request.system, str) else "",
                    }
                )

            # Add messages (excluding content for counting)
            for msg in request.messages:
                msg_dict: dict[str, Any] = {"role": msg.role}
                if isinstance(msg.content, str):
                    msg_dict["content"] = msg.content
                elif isinstance(msg.content, list):
                    # For counting, we can combine text blocks
                    text_parts = []
                    for block in msg.content:
                        if hasattr(block, "text") and block.text is not None:
                            text_parts.append(block.text)
                    msg_dict["content"] = "".join(text_parts)

                messages_list.append(msg_dict)

            # Try to get token count from provider
            try:
                client = config.provider_manager.get_client(provider_name)
                count_response = await client.create_chat_completion(
                    {**count_request, "max_tokens": 1},
                    "count_tokens",  # We just want token count
                )

                # Extract usage if available
                usage = count_response.get("usage", {})
                input_tokens = usage.get("input_tokens", max(1, len(str(count_request)) // 4))

                return JSONResponse(status_code=200, content={"input_tokens": input_tokens})

            except Exception:
                # Fallback to estimation if provider doesn't support counting
                pass

        # Fallback to character-based estimation
        total_chars = 0

        # Count system message characters
        if request.system:
            if isinstance(request.system, str):
                total_chars += len(request.system)
            elif isinstance(request.system, list):
                for block in request.system:  # type: ignore[assignment]
                    if hasattr(block, "text"):
                        total_chars += len(block.text)

        # Count message characters
        for msg in request.messages:
            if msg.content is None:
                continue
            elif isinstance(msg.content, str):
                total_chars += len(msg.content)
            elif isinstance(msg.content, list):
                for block in msg.content:  # type: ignore[arg-type, assignment]
                    if hasattr(block, "text") and block.text is not None:
                        total_chars += len(block.text)

        # Rough estimation: 4 characters per token
        estimated_tokens = max(1, total_chars // 4)

        return JSONResponse(status_code=200, content={"input_tokens": estimated_tokens})

    except Exception as e:
        logger.error(f"Error counting tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/health")
async def health_check() -> PlainTextResponse:
    """Health check endpoint with provider status"""
    try:
        # Gather provider information
        providers = {}
        try:
            for provider_name in config.provider_manager.list_providers():
                provider_config = config.provider_manager.get_provider_config(provider_name)
                providers[provider_name] = {
                    "api_format": provider_config.api_format if provider_config else "unknown",
                    "base_url": provider_config.base_url if provider_config else None,
                    "api_key_hash": (
                        f"sha256:{config.provider_manager.get_api_key_hash(provider_config.api_key)}"
                        if provider_config and provider_config.api_key
                        else "<not set>"
                    ),
                }
        except Exception as e:
            # If provider manager fails, include error in response
            logger.error(f"Error gathering provider info: {e}")

        health_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "api_key_valid": config.validate_api_key(),
            "client_api_key_validation": bool(config.proxy_api_key),
            "default_provider": getattr(config.provider_manager, "default_provider", "unknown"),
            "providers": providers,
        }

        # Format as YAML
        yaml_output = format_health_yaml(health_data)

        return PlainTextResponse(
            content=yaml_output,
            media_type="text/yaml; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "Content-Disposition": (
                    f"inline; filename=health-{datetime.now().strftime('%Y%m%d-%H%M%S')}.yaml"
                ),
            },
        )
    except Exception as e:
        # Return degraded health status if configuration is missing
        logger.error(f"Health check error: {e}")
        degraded_data = {
            "status": "degraded",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "message": "Server is running but configuration is incomplete",
            "suggestions": [
                "Set OPENAI_API_KEY environment variable for OpenAI provider",
                "Set VDM_DEFAULT_PROVIDER to specify your preferred provider",
                "Check .env file for required configuration",
            ],
        }

        # Format as YAML
        yaml_output = format_health_yaml(degraded_data)

        return PlainTextResponse(
            content=yaml_output,
            media_type="text/yaml; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "Content-Disposition": (
                    f"inline; filename=health-{datetime.now().strftime('%Y%m%d-%H%M%S')}.yaml"
                ),
            },
        )


@router.get("/test-connection")
async def test_connection() -> JSONResponse:
    """Test API connectivity to the default provider"""
    try:
        # Get the default provider client
        default_client = config.provider_manager.get_client(
            config.provider_manager.default_provider
        )

        # Simple test request to verify API connectivity
        test_response = await default_client.create_chat_completion(
            {
                "model": "gpt-4o-mini",  # Use a common model that most providers support
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 20,  # Minimum value that most providers accept
            }
        )

        # Add defensive check
        if test_response is None:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "failed",
                    "message": (
                        f"Provider {config.provider_manager.default_provider} "
                        f"returned None response"
                    ),
                    "provider": config.provider_manager.default_provider,
                    "error": "None response from provider",
                },
            )

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": (
                    f"Successfully connected to {config.provider_manager.default_provider} API"
                ),
                "provider": config.provider_manager.default_provider,
                "model_used": "gpt-4o-mini",
                "timestamp": datetime.now().isoformat(),
                "response_id": test_response.get("id", "unknown"),
            },
        )

    except Exception as e:
        logger.error(f"API connectivity test failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "failed",
                "error_type": "API Error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
                "suggestions": [
                    "Check your OPENAI_API_KEY is valid",
                    "Verify your API key has the necessary permissions",
                    "Check if you have reached rate limits",
                ],
            },
        )


async def fetch_models_unauthenticated(
    base_url: str, custom_headers: dict[str, str]
) -> dict[str, Any]:
    """Fetch models from endpoint using raw HTTP client without authentication"""
    # Prepare headers without authentication
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "claude-proxy/1.0.0",
        **custom_headers,  # Note: exclude any auth-related custom headers
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{base_url}/models", headers=headers)
        response.raise_for_status()
        # Type: ignore because we're trusting the API to return the expected format
        return response.json()  # type: ignore[no-any-return]


@router.get("/v1/models")
async def list_models(
    _: None = Depends(validate_api_key),
    provider: str | None = Query(
        None,
        description="Provider name to fetch models from (defaults to configured default provider)",
    ),
    format: str | None = Query(
        None,
        description=(
            "Response format selector (takes precedence over headers): "
            "anthropic, openai, or raw. If omitted, inferred from headers."
        ),
    ),
    refresh: bool = Query(
        False,
        description="Force refresh model list from upstream (bypass models cache)",
    ),
    provider_header: str | None = Header(
        None,
        alias="provider",
        description="Provider override (header takes precedence over query/default)",
    ),
    anthropic_version: str | None = Header(
        None,
        alias="anthropic-version",
        description=(
            "If present and no explicit format=... was provided, the response format may be "
            "inferred as Anthropic for /v1/models compatibility"
        ),
    ),
) -> JSONResponse:
    """List available models from the specified provider or default provider"""
    try:
        # Determine provider using header > query param > default
        provider_candidate = provider_header or provider
        provider_name = (
            provider_candidate.lower()
            if provider_candidate
            else config.provider_manager.default_provider
        )

        # Check if provider exists
        all_providers = config.provider_manager.list_providers()
        if provider_name not in all_providers:
            available_providers = ", ".join(sorted(all_providers.keys()))
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Provider '{provider_name}' not found. "
                    f"Available providers: {available_providers}"
                ),
            )

        # If client didn't explicitly choose a format, allow header-based inference.
        # Precedence rule: query param takes precedence over headers.
        # Default should be OpenAI (OpenAI clients won't send `anthropic-version`).
        if format is None:
            format = "anthropic" if anthropic_version else "openai"

        if format not in {"anthropic", "openai", "raw"}:
            raise HTTPException(
                status_code=400,
                detail="Invalid format. Use format=anthropic|openai|raw",
            )

        # Get the provider client and config
        default_client = config.provider_manager.get_client(provider_name)
        provider_config = config.provider_manager.get_provider_config(provider_name)

        base_url = default_client.base_url
        custom_headers = provider_config.custom_headers if provider_config else {}

        # 1) Try fresh cache (unless refresh requested)
        raw: dict[str, Any] | None = None
        if models_cache and not refresh:
            raw = models_cache.read_response_if_fresh(
                provider=provider_name,
                base_url=base_url,
                custom_headers=custom_headers,
            )
            if raw is not None:
                logger.debug(f"Using cached models response for {provider_name}")

        # 2) Fetch if cache miss
        if raw is None:
            try:
                raw = await fetch_models_unauthenticated(base_url, custom_headers)
                if models_cache and raw is not None:
                    models_cache.write_response(
                        provider=provider_name,
                        base_url=base_url,
                        custom_headers=custom_headers,
                        response=raw,
                    )
                    logger.debug(f"Cached models response for {provider_name}")
            except Exception as e:
                logger.warning(f"Failed to fetch models from {provider_name}: {e}")

                # 3) On upstream failure, return cached if any (stale allowed)
                if models_cache:
                    raw = models_cache.read_response_if_any(
                        provider=provider_name,
                        base_url=base_url,
                        custom_headers=custom_headers,
                    )
                    if raw is not None:
                        logger.debug(
                            "Using stale cached models response for %s after fetch failure",
                            provider_name,
                        )

        if raw is None:
            raise RuntimeError("Models response was not constructed")

        if format == "raw":
            return JSONResponse(status_code=200, content=raw)

        from src.conversion.models_converter import raw_to_anthropic_models, raw_to_openai_models

        if format == "openai":
            return JSONResponse(status_code=200, content=raw_to_openai_models(raw))

        # Default: anthropic
        return JSONResponse(status_code=200, content=raw_to_anthropic_models(raw))

    except Exception as e:
        logger.error(f"Error listing models: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": f"Failed to list models: {str(e)}",
                },
            },
        )


@router.get("/v1/aliases")
async def list_aliases(_: None = Depends(validate_api_key)) -> JSONResponse:
    """List all configured model aliases grouped by provider.

    Only shows aliases for active providers (those with API keys configured).

    Also includes a non-mutating overlay of "suggested" aliases derived from
    `/top-models`.
    """
    try:
        # Only show aliases for active providers (with API keys)
        aliases = config.alias_service.get_active_aliases()

        # Return aliases grouped by provider
        total_aliases = sum(len(provider_aliases) for provider_aliases in aliases.values())

        suggested: dict[str, dict[str, str]] = {}
        try:
            from src.top_models.service import TopModelsService

            top = await TopModelsService().get_top_models(limit=10, refresh=False, provider=None)
            if top.aliases:
                # "default" indicates these are global suggestions, not provider-scoped.
                suggested["default"] = top.aliases
        except Exception as e:
            # Suggestions should never break /v1/aliases
            logger.debug(f"Failed to compute suggested aliases overlay: {e}")

        return JSONResponse(
            status_code=200,
            content={
                "object": "list",
                "aliases": aliases,
                "suggested": suggested,
                "total": total_aliases,
            },
        )
    except Exception as e:
        logger.error(f"Error listing aliases: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": f"Failed to list aliases: {str(e)}",
                },
            },
        )


@router.get("/top-models")
async def top_models(
    _: None = Depends(validate_api_key),
    limit: int = Query(10, ge=1, le=50),
    refresh: bool = Query(False),
    provider: str | None = Query(None),
    include_cache_info: bool = Query(False),
) -> JSONResponse:
    """List curated top models (proxy metadata, not part of /v1 surface).

    This endpoint is intended as a dashboard-friendly discovery contract.
    """
    from src.top_models.service import TopModelsService
    from src.top_models.types import top_model_to_api_dict

    svc = TopModelsService()
    result = await svc.get_top_models(limit=limit, refresh=refresh, provider=provider)

    models = [top_model_to_api_dict(m) for m in result.models]
    providers_raw = [m.get("provider") for m in models if isinstance(m.get("provider"), str)]
    providers: list[str] = sorted({p for p in providers_raw if isinstance(p, str)})

    sub_providers_raw = [
        m.get("sub_provider") for m in models if isinstance(m.get("sub_provider"), str)
    ]
    sub_providers: list[str] = sorted({p for p in sub_providers_raw if isinstance(p, str)})

    meta: dict[str, Any] = {
        "excluded_rules": list(svc._cfg.exclude),
    }

    if include_cache_info:
        meta["rankings_file"] = str(svc._cfg.rankings_file)

    return JSONResponse(
        status_code=200,
        content={
            "object": "top_models",
            "source": result.source,
            "last_updated": result.last_updated.isoformat(),
            "providers": providers,
            "sub_providers": sub_providers,
            "models": models,
            "suggested_aliases": result.aliases,
            "meta": meta,
        },
    )


@router.get("/")
async def root() -> dict[str, Any]:
    """Root endpoint"""
    return {
        "message": "VanDamme Proxy v1.0.0",
        "status": "running",
        "config": {
            "base_url": config.base_url,
            "max_tokens_limit": config.max_tokens_limit,
            "api_key_configured": bool(config.openai_api_key),
            "client_api_key_validation": bool(config.proxy_api_key),
        },
        "endpoints": {
            "messages": "/v1/messages",
            "count_tokens": "/v1/messages/count_tokens",
            "running_totals": "/metrics/running-totals",
            "models": "/v1/models",
            "aliases": "/v1/aliases",
            "top_models": "/top-models",
            "health": "/health",
            "test_connection": "/test-connection",
        },
    }
