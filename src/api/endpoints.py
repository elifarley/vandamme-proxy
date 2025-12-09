import json
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional, Union

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.conversion.request_converter import convert_claude_to_openai
from src.conversion.response_converter import (
    convert_openai_streaming_to_claude_with_cancellation,
    convert_openai_to_claude_response,
)
from src.core.client import OpenAIClient
from src.core.config import config
from src.core.logging import (
    LOG_REQUEST_METRICS,
    ConversationLogger,
    conversation_logger,
    logger,
    request_tracker,
)
from src.core.model_manager import model_manager
from src.models.claude import ClaudeMessagesRequest, ClaudeTokenCountRequest

router = APIRouter()

# Custom headers are now handled per provider


async def validate_api_key(
    x_api_key: Optional[str] = Header(None), authorization: Optional[str] = Header(None)
) -> None:
    """Validate the client's API key from either x-api-key header or Authorization header."""
    client_api_key = None

    # Extract API key from headers
    if x_api_key:
        client_api_key = x_api_key
    elif authorization and authorization.startswith("Bearer "):
        client_api_key = authorization.replace("Bearer ", "")

    # Skip validation if ANTHROPIC_API_KEY is not set in the environment
    if not config.anthropic_api_key:
        return

    # Validate the client API key
    if not client_api_key or not config.validate_client_api_key(client_api_key):
        logger.warning(f"Invalid API key provided by client")
        raise HTTPException(
            status_code=401, detail="Invalid API key. Please provide a valid Anthropic API key."
        )


@router.post("/v1/messages")
async def create_message(  # type: ignore[no-untyped-def]
    request: ClaudeMessagesRequest, http_request: Request, _: None = Depends(validate_api_key)
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
    else:
        metrics = None
        request_size = 0
        message_count = len(request.messages) + (1 if request.system else 0)

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
                f"Tools: {len(request.tools) if request.tools else 0}"
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

            # Get the appropriate client for this provider
            openai_client = config.provider_manager.get_client(provider_name)

            # Update metrics with OpenAI model and provider
            if LOG_REQUEST_METRICS and metrics:
                openai_model = openai_request.get("model", "unknown")
                metrics.openai_model = openai_model
                metrics.provider = provider_name

            # Check if client disconnected before processing
            if await http_request.is_disconnected():
                if LOG_REQUEST_METRICS and metrics:
                    metrics.error = "Client disconnected before processing"
                    metrics.error_type = "client_disconnect"
                    request_tracker.end_request(request_id)
                raise HTTPException(status_code=499, detail="Client disconnected")

            if request.stream:
                # Streaming response
                try:
                    openai_stream = openai_client.create_chat_completion_stream(
                        openai_request, request_id
                    )

                    # Wrap streaming to capture metrics
                    async def streaming_with_metrics() -> AsyncGenerator[str, None]:
                        try:
                            async for chunk in convert_openai_streaming_to_claude_with_cancellation(
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
                openai_response = await openai_client.create_chat_completion(
                    openai_request, request_id
                )

                # Calculate response size
                response_json = json.dumps(openai_response)
                response_size = len(response_json)

                # Extract token usage
                usage = openai_response.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)

                # Update metrics
                if LOG_REQUEST_METRICS and metrics:
                    metrics.response_size = response_size
                    metrics.input_tokens = input_tokens
                    metrics.output_tokens = output_tokens

                claude_response = convert_openai_to_claude_response(openai_response, request)

                # Log successful completion
                duration_ms = (time.time() - start_time) * 1000
                if LOG_REQUEST_METRICS:
                    conversation_logger.info(
                        f"✅ SUCCESS | Duration: {duration_ms:.0f}ms | "
                        f"Tokens: {input_tokens:,}→{output_tokens:,} | "
                        f"Size: {request_size:,}→{response_size:,} bytes"
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
                    f"❌ ERROR | Duration: {duration_ms:.0f}ms | " f"Error: {error_message}"
                )
                conversation_logger.error(traceback.format_exc())
            else:
                logger.error(f"Unexpected error processing request: {e}")
                logger.error(traceback.format_exc())

            # End request tracking
            if LOG_REQUEST_METRICS:
                request_tracker.end_request(request_id)

            raise HTTPException(status_code=500, detail=error_message)


@router.post("/v1/messages/count_tokens")
async def count_tokens(
    request: ClaudeTokenCountRequest, _: None = Depends(validate_api_key)
) -> JSONResponse:
    try:
        # For token counting, we'll use a simple estimation
        # In a real implementation, you might want to use tiktoken or similar

        total_chars = 0

        # Count system message characters
        if request.system:
            if isinstance(request.system, str):
                total_chars += len(request.system)
            elif isinstance(request.system, list):
                for block in request.system:
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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "openai_api_configured": bool(config.openai_api_key),
        "api_key_valid": config.validate_api_key(),
        "client_api_key_validation": bool(config.anthropic_api_key),
    }


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
                "model": config.small_model,
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 5,
            }
        )

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": f"Successfully connected to {config.provider_manager.default_provider} API",
                "provider": config.provider_manager.default_provider,
                "model_used": config.small_model,
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


@router.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint"""
    return {
        "message": "VanDamme Proxy v1.0.0",
        "status": "running",
        "config": {
            "base_url": config.base_url,
            "max_tokens_limit": config.max_tokens_limit,
            "api_key_configured": bool(config.openai_api_key),
            "client_api_key_validation": bool(config.anthropic_api_key),
            "big_model": config.big_model,
            "small_model": config.small_model,
        },
        "endpoints": {
            "messages": "/v1/messages",
            "count_tokens": "/v1/messages/count_tokens",
            "health": "/health",
            "test_connection": "/test-connection",
        },
    }
