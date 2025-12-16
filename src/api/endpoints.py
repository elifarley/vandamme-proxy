import json
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from src.api.utils.yaml_formatter import format_health_yaml
from src.conversion.request_converter import convert_claude_to_openai
from src.conversion.response_converter import (
    convert_openai_streaming_to_claude_with_cancellation,
    convert_openai_to_claude_response,
)
from src.core.config import config
from src.core.logging import (
    LOG_REQUEST_METRICS,
    ConversationLogger,
    conversation_logger,
    logger,
    request_tracker,
)
from src.core.model_manager import model_manager
from src.middleware import RequestContext, ResponseContext
from src.models.claude import (
    ClaudeMessagesRequest,
    ClaudeTokenCountRequest,
)

router = APIRouter()

# Custom headers are now handled per provider


def count_tool_calls(request: ClaudeMessagesRequest) -> tuple[int, int]:
    """Count tool_use and tool_result blocks in a Claude request"""
    tool_use_count = 0
    tool_result_count = 0

    for message in request.messages:
        if isinstance(message.content, list):
            for block in message.content:
                if hasattr(block, "type"):
                    if block.type == "tool_use":
                        tool_use_count += 1
                    elif block.type == "tool_result":
                        tool_result_count += 1

    return tool_use_count, tool_result_count


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


@router.post("/v1/messages")
async def create_message(  # type: ignore[no-untyped-def]
    request: ClaudeMessagesRequest,
    http_request: Request,
    client_api_key: str | None = Depends(validate_api_key),
):
    # Generate unique request ID for tracking
    request_id = str(uuid.uuid4())

    # Start request tracking if metrics are enabled
    if LOG_REQUEST_METRICS:
        metrics = request_tracker.start_request(
            request_id=request_id, claude_model=request.model, is_streaming=request.stream or False
        )

        # Calculate request size
        request_size = len(json.dumps(request.model_dump(exclude_none=True)))
        metrics.request_size = request_size

        # Count messages including system message
        message_count = len(request.messages)
        if request.system:
            if isinstance(request.system, str):
                message_count += 1
            elif isinstance(request.system, list):
                message_count += len(request.system)
        metrics.message_count = message_count

        # Count tool uses and tool results
        tool_use_count, tool_result_count = count_tool_calls(request)
        metrics.tool_use_count = tool_use_count
        metrics.tool_result_count = tool_result_count
    else:
        metrics = None
        request_size = 0
        message_count = len(request.messages) + (1 if request.system else 0)
        tool_use_count, tool_result_count = count_tool_calls(request)

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
            openai_request = convert_claude_to_openai(request, model_manager)

            # Extract provider from request
            provider_name = openai_request.pop("_provider", "openai")

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

            # Update metrics with OpenAI model and provider
            if LOG_REQUEST_METRICS and metrics:
                openai_model = openai_request.get("model", "unknown")
                metrics.openai_model = openai_model
                metrics.provider = provider_name  # type: ignore[assignment]

                # Update last_accessed timestamp
                request_tracker.update_last_accessed(
                    provider=provider_name, model=openai_model, timestamp=metrics.start_time_iso
                )

            # Check if client disconnected before processing
            if await http_request.is_disconnected():
                if LOG_REQUEST_METRICS and metrics:
                    metrics.error = "Client disconnected before processing"
                    metrics.error_type = "client_disconnect"
                    request_tracker.end_request(request_id)
                raise HTTPException(status_code=499, detail="Client disconnected")

            if request.stream:
                # Streaming response
                # Check if provider uses Anthropic format
                provider_config = config.provider_manager.get_provider_config(provider_name)

                if provider_config and provider_config.is_anthropic_format:
                    # Passthrough streaming for Anthropic-compatible APIs
                    # Convert request to dict directly (no format conversion)
                    # Get the actual model name without provider prefix
                    provider_name_for_model, resolved_model = model_manager.resolve_model(
                        request.model
                    )
                    claude_request_dict = request.model_dump(exclude_none=True)

                    # Add provider tracking
                    claude_request_dict["_provider"] = provider_name
                    claude_request_dict["model"] = resolved_model  # Use stripped model name

                    try:
                        # Direct streaming with passthrough
                        anthropic_stream = openai_client.create_chat_completion_stream(
                            claude_request_dict,
                            request_id,
                            api_key=(
                                client_api_key
                                if provider_config and provider_config.uses_passthrough
                                else None
                            ),
                        )

                        # Wrap streaming to capture metrics
                        async def streaming_with_metrics() -> AsyncGenerator[str, None]:
                            try:
                                # Pass through SSE events directly
                                async for chunk in anthropic_stream:
                                    yield chunk
                            finally:
                                # End request tracking after streaming
                                if LOG_REQUEST_METRICS:
                                    request_tracker.end_request(request_id)

                        return StreamingResponse(
                            streaming_with_metrics(),
                            media_type="text/event-stream",
                            headers={
                                "Cache-Control": "no-cache",
                                "Connection": "keep-alive",
                                "Access-Control-Allow-Origin": "*",
                                "Access-Control-Allow-Headers": "*",
                            },
                        )
                    except HTTPException as e:
                        # Convert to proper error response for streaming
                        if LOG_REQUEST_METRICS and metrics:
                            metrics.error = e.detail
                            metrics.error_type = "api_error"
                            metrics.end_time = time.time()
                            request_tracker.end_request(request_id)

                        logger.error(f"Streaming error: {e.detail}")
                        import traceback

                        logger.error(traceback.format_exc())

                        error_message = openai_client.classify_openai_error(e.detail)
                        error_response = {
                            "type": "error",
                            "error": {"type": "api_error", "message": error_message},
                        }
                        return JSONResponse(status_code=e.status_code, content=error_response)
                else:
                    # OpenAI format streaming (existing logic)
                    try:
                        openai_stream = openai_client.create_chat_completion_stream(
                            openai_request,
                            request_id,
                            api_key=(
                                client_api_key
                                if provider_config and provider_config.uses_passthrough
                                else None
                            ),
                        )

                        # Wrap streaming to capture metrics
                        async def streaming_with_metrics() -> AsyncGenerator[str, None]:
                            try:
                                async for (
                                    chunk
                                ) in convert_openai_streaming_to_claude_with_cancellation(
                                    openai_stream,
                                    request,
                                    logger,
                                    http_request,
                                    openai_client,
                                    request_id,
                                ):
                                    yield chunk
                            finally:
                                # End request tracking after streaming
                                if LOG_REQUEST_METRICS:
                                    request_tracker.end_request(request_id)

                        return StreamingResponse(
                            streaming_with_metrics(),
                            media_type="text/event-stream",
                            headers={
                                "Cache-Control": "no-cache",
                                "Connection": "keep-alive",
                                "Access-Control-Allow-Origin": "*",
                                "Access-Control-Allow-Headers": "*",
                            },
                        )
                    except HTTPException as e:
                        # Convert to proper error response for streaming
                        if LOG_REQUEST_METRICS and metrics:
                            metrics.error = e.detail
                            metrics.error_type = "api_error"
                            metrics.end_time = time.time()
                            request_tracker.end_request(request_id)

                        logger.error(f"Streaming error: {e.detail}")
                        import traceback

                        logger.error(traceback.format_exc())

                        error_message = openai_client.classify_openai_error(e.detail)
                        error_response = {
                            "type": "error",
                            "error": {"type": "api_error", "message": error_message},
                        }
                        return JSONResponse(status_code=e.status_code, content=error_response)
            else:
                # Non-streaming response
                # Check if provider uses Anthropic format
                provider_config = config.provider_manager.get_provider_config(provider_name)

                if provider_config and provider_config.is_anthropic_format:
                    # Passthrough mode for Anthropic-compatible APIs
                    # Convert request to dict directly (no format conversion)
                    # Get the actual model name without provider prefix
                    provider_name_for_model, resolved_model = model_manager.resolve_model(
                        request.model
                    )
                    claude_request_dict = request.model_dump(exclude_none=True)

                    # Add provider tracking
                    claude_request_dict["_provider"] = provider_name
                    claude_request_dict["model"] = resolved_model  # Use stripped model name

                    # Make API call
                    anthropic_response = await openai_client.create_chat_completion(
                        claude_request_dict,
                        request_id,
                        api_key=(
                            client_api_key
                            if provider_config and provider_config.uses_passthrough
                            else None
                        ),
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
                    return JSONResponse(status_code=200, content=anthropic_response)
                else:
                    # OpenAI format path (existing logic)
                    openai_response = await openai_client.create_chat_completion(
                        openai_request,
                        request_id,
                        api_key=(
                            client_api_key
                            if provider_config and provider_config.uses_passthrough
                            else None
                        ),
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
                    response_message = openai_response.get("choices", [{}])[0].get("message", {})
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

                    claude_response = convert_openai_to_claude_response(openai_response, request)

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
                    request_tracker.end_request(request_id)

                return JSONResponse(status_code=200, content=claude_response)

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            if LOG_REQUEST_METRICS and metrics:
                metrics.error = "HTTP exception"
                metrics.error_type = "http_error"
                metrics.end_time = time.time()
                request_tracker.end_request(request_id)
            raise
        except Exception as e:
            import traceback

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
                conversation_logger.error(traceback.format_exc())
            else:
                logger.error(f"Unexpected error processing request: {e}")
                logger.error(traceback.format_exc())

            # End request tracking
            if LOG_REQUEST_METRICS:
                request_tracker.end_request(request_id)

            raise HTTPException(status_code=500, detail=error_message) from e


@router.post("/v1/messages/count_tokens")
async def count_tokens(
    request: ClaudeTokenCountRequest, _: None = Depends(validate_api_key)
) -> JSONResponse:
    try:
        # Get provider and model
        from src.core.model_manager import model_manager

        provider_name, actual_model = model_manager.resolve_model(request.model)
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
            "openai_api_configured": bool(config.openai_api_key),
            "api_key_valid": config.validate_api_key(),
            "client_api_key_validation": bool(config.proxy_api_key),
            "default-provider": getattr(config.provider_manager, "default-provider", "unknown"),
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
) -> JSONResponse:
    """List available models from the specified provider or default provider"""
    try:
        # Get the provider name from query param or use default
        provider_name = provider if provider else config.provider_manager.default_provider

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

        # Get the provider client and config
        default_client = config.provider_manager.get_client(provider_name)
        provider_config = config.provider_manager.get_provider_config(provider_name)

        if provider_config and provider_config.is_anthropic_format:
            # For Anthropic-compatible APIs, models list is typically static
            # Return common Claude models that Anthropic-compatible APIs support
            models = {
                "object": "list",
                "data": [
                    {
                        "id": "claude-3-5-sonnet-20241022",
                        "object": "model",
                        "created": 1699905200,
                        "display_name": "Claude 3.5 Sonnet (October 2024)",
                    },
                    {
                        "id": "claude-3-5-haiku-20241022",
                        "object": "model",
                        "created": 1699905200,
                        "display_name": "Claude 3.5 Haiku (October 2024)",
                    },
                    {
                        "id": "claude-3-opus-20240229",
                        "object": "model",
                        "created": 1699905200,
                        "display_name": "Claude 3 Opulus",
                    },
                    {
                        "id": "claude-3-sonnet-20240229",
                        "object": "model",
                        "created": 1699905200,
                        "display_name": "Claude 3 Sonnet",
                    },
                    {
                        "id": "claude-3-haiku-20240307",
                        "object": "model",
                        "created": 1699905200,
                        "display_name": "Claude 3 Haiku",
                    },
                ],
            }
        else:
            # OpenAI format - use unauthenticated HTTP client for all providers
            try:
                # Use unauthenticated HTTP client (no provider requires auth for /models)
                openai_models = await fetch_models_unauthenticated(
                    default_client.base_url,
                    provider_config.custom_headers if provider_config else {},
                )

                # Transform OpenAI models format to Claude format
                openai_models_response: dict[str, Any] = {"object": "list", "data": []}
                models_list: list[dict[str, Any]] = openai_models_response["data"]  # type: ignore[assignment]

                for model in openai_models.get("data", []):
                    # Create a Claude-compatible model entry
                    claude_model = {
                        "id": model.get("id", ""),
                        "object": "model",
                        "created": model.get("created", 0),
                        "display_name": model.get("id", "").replace("-", " ").title(),
                    }
                    models_list.append(claude_model)
                models = openai_models_response

            except Exception as e:
                # Log the error and fall back to common models if provider doesn't support /models
                logger.warning(f"Failed to fetch models from {provider_name}: {e}")

                # Fallback to common models
                models = {
                    "object": "list",
                    "data": [
                        {
                            "id": "gpt-4o",
                            "object": "model",
                            "created": 1699905200,
                            "display_name": "GPT-4o",
                        },
                        {
                            "id": "gpt-4o-mini",
                            "object": "model",
                            "created": 1699905200,
                            "display_name": "GPT-4o Mini",
                        },
                        {
                            "id": "gpt-4-turbo",
                            "object": "model",
                            "created": 1699905200,
                            "display_name": "GPT-4 Turbo",
                        },
                        {
                            "id": "gpt-3.5-turbo",
                            "object": "model",
                            "created": 1699905200,
                            "display_name": "GPT-3.5 Turbo",
                        },
                    ],
                }

        return JSONResponse(status_code=200, content=models)

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
    """List all configured model aliases grouped by provider"""
    try:
        aliases = config.alias_manager.get_all_aliases()

        # Return aliases grouped by provider
        total_aliases = sum(len(provider_aliases) for provider_aliases in aliases.values())

        return JSONResponse(
            status_code=200,
            content={
                "object": "list",
                "aliases": aliases,
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
            "health": "/health",
            "test_connection": "/test-connection",
        },
    }
