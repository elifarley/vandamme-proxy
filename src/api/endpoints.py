import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from src.api.models.endpoint_requests import ModelsListRequest, TopModelsRequest
from src.api.models_cache_runtime import get_models_cache
from src.api.services.endpoint_services import (
    AliasesListService,
    HealthCheckService,
    ModelsListService,
    TestConnectionService,
    TokenCountService,
    TopModelsEndpointService,
)
from src.api.services.non_streaming_handlers import get_non_streaming_handler
from src.api.services.provider_context import resolve_provider_context
from src.api.services.streaming_handlers import get_streaming_handler
from src.core.config import Config
from src.core.config.accessors import log_request_metrics
from src.core.config.runtime import get_config
from src.core.error_types import ErrorType
from src.core.logging import ConversationLogger
from src.core.model_manager import ModelManager
from src.core.model_manager_runtime import get_model_manager
from src.models.cache import ModelsDiskCache
from src.models.claude import ClaudeMessagesRequest, ClaudeTokenCountRequest
from src.models.openai import OpenAIChatCompletionsRequest

logger = logging.getLogger(__name__)
conversation_logger = ConversationLogger.get_logger()

router = APIRouter()


def _is_timeout_error(exc: Exception) -> bool:
    """Check if an exception is a timeout-related error.

    Uses proper exception hierarchy instead of string matching.
    httpx.TimeoutException is the base class for all timeout errors.

    Args:
        exc: The exception to check.

    Returns:
        True if the exception is a timeout error, False otherwise.
    """
    return isinstance(exc, httpx.TimeoutException)


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


# Custom headers are now handled per provider
# count_tool_calls has been moved to src.api.services.metrics_helper


async def validate_api_key(
    cfg: Config = Depends(get_config),
    x_api_key: str | None = Header(None),
    authorization: str | None = Header(None),
) -> str | None:
    """
    Validate and return the client's API key from either x-api-key header or
    Authorization header. Returns the key if present, None otherwise.

    Uses dependency injection to get the Config instance.
    """
    client_api_key = None

    # Extract API key from headers
    if x_api_key:
        client_api_key = x_api_key
    elif authorization and authorization.startswith("Bearer "):
        client_api_key = authorization.replace("Bearer ", "")

    # Skip validation if PROXY_API_KEY is not set in the environment
    if not cfg.proxy_api_key:
        return client_api_key  # Return the key even if validation is disabled

    # Validate the client API key
    if not client_api_key or not cfg.validate_client_api_key(client_api_key):
        logger.warning("Invalid API key provided by client")
        raise HTTPException(
            status_code=401, detail="Invalid API key. Please provide a valid Anthropic API key."
        )

    return client_api_key


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: OpenAIChatCompletionsRequest,
    http_request: Request,
    cfg: Config = Depends(get_config),
    mm: ModelManager = Depends(get_model_manager),
    client_api_key: str | None = Depends(validate_api_key),
) -> JSONResponse | StreamingResponse:
    """OpenAI-compatible chat completions endpoint.

    Uses strategy pattern to handle different provider formats elegantly.
    - If the resolved provider is OpenAI-format: passthrough request/response.
    - If the resolved provider is Anthropic-format: translate OpenAI request to
      Anthropic Messages API and translate response back.
    """
    from src.api.services.metrics_orchestrator import (
        MetricsOrchestrator,
        create_request_id,
    )

    request_id = create_request_id()
    orchestrator = MetricsOrchestrator(config=cfg)

    # Initialize metrics for this request
    metrics_ctx = await orchestrator.initialize_request_metrics(
        request_id=request_id,
        http_request=http_request,
        model=request.model,
        is_streaming=request.stream or False,
        model_manager=mm,
    )

    with ConversationLogger.correlation_context(request_id):
        provider_ctx = await resolve_provider_context(
            model=request.model,
            client_api_key=client_api_key,
            config=cfg,
            model_manager=mm,
        )
        provider_name = provider_ctx.provider_name
        resolved_model = provider_ctx.resolved_model
        provider_config = provider_ctx.provider_config

        # Update metrics with resolved provider context
        await orchestrator.update_provider_resolution(
            ctx=metrics_ctx,
            provider_name=provider_name,
            resolved_model=resolved_model,
        )

        # Build upstream request dict and attach resolved model.
        openai_request: dict[str, Any] = request.model_dump(exclude_none=True)
        openai_request["model"] = resolved_model

        openai_client = cfg.provider_manager.get_client(provider_name, client_api_key)

        # Get appropriate handler and execute
        from src.api.services.chat_completions_handlers import get_chat_completions_handler

        handler = get_chat_completions_handler(provider_config)

        try:
            return await handler.handle(
                openai_request=openai_request,
                resolved_model=resolved_model,
                provider_name=provider_name,
                provider_config=provider_config,
                provider_api_key=provider_ctx.provider_api_key,
                client_api_key=client_api_key,
                config=cfg,
                openai_client=openai_client,
                request_id=request_id,
                http_request=http_request,
                is_metrics_enabled=metrics_ctx.is_enabled,
                metrics=metrics_ctx.metrics,
                tracker=metrics_ctx.tracker,
            )
        except Exception as e:
            if _is_timeout_error(e):
                await orchestrator.finalize_on_timeout(metrics_ctx)
                raise _map_timeout_to_504() from e
            raise


@router.post("/v1/messages", response_model=None)
async def create_message(
    request: ClaudeMessagesRequest,
    http_request: Request,
    cfg: Config = Depends(get_config),
    mm: ModelManager = Depends(get_model_manager),
    client_api_key: str | None = Depends(validate_api_key),
) -> JSONResponse | StreamingResponse:
    """Process a Claude Messages API request.

    This endpoint now delegates all initialization to the RequestOrchestrator,
    making the endpoint code clean and focused on routing.
    """
    # Import orchestrator - placed here to avoid circular imports
    from src.api.orchestrator.request_orchestrator import RequestOrchestrator

    # Create orchestrator
    orchestrator = RequestOrchestrator(config=cfg, model_manager=mm)

    # Prepare the complete request context
    # This handles all initialization: metrics, provider resolution, conversion, etc.
    ctx = await orchestrator.prepare_request_context(
        request=request,
        http_request=http_request,
        client_api_key=client_api_key,
    )

    # Use correlation context for all logs within this request
    with ConversationLogger.correlation_context(ctx.request_id):
        # Log request start
        _log_request_start(ctx)

        # Route to appropriate handler based on streaming mode
        try:
            if ctx.is_streaming:
                return await _handle_streaming(ctx)
            else:
                return await _handle_non_streaming(ctx)
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            await _finalize_metrics_on_error(ctx, "http_error")
            raise
        except Exception as e:
            # Handle unexpected errors
            return await _handle_unexpected_error(ctx, e)


def _log_request_start(ctx: Any) -> None:
    """Log request start with metrics awareness."""
    if log_request_metrics():
        conversation_logger.info(
            f"🚀 START | Model: {ctx.request.model} "
            f"(resolved: {ctx.provider_name}:{ctx.resolved_model}) | "
            f"Stream: {ctx.is_streaming} | "
            f"Messages: {ctx.message_count} | "
            f"Max Tokens: {ctx.request.max_tokens} | "
            f"Size: {ctx.request_size:,} bytes | "
            f"Tools: {len(ctx.request.tools) if ctx.request.tools else 0} | "
            f"Tool Uses: {ctx.tool_use_count} | "
            f"Tool Results: {ctx.tool_result_count}"
        )
    else:
        logger.debug(
            f"Processing Claude request: model={ctx.request.model}, stream={ctx.is_streaming}"
        )


async def _handle_streaming(ctx: Any) -> StreamingResponse | JSONResponse:
    """Handle streaming requests with context."""
    provider_config = ctx.config.provider_manager.get_provider_config(ctx.provider_name)
    handler = get_streaming_handler(ctx.config, provider_config)

    # Use new context-based method
    return await handler.handle_with_context(ctx)


async def _handle_non_streaming(ctx: Any) -> JSONResponse:
    """Handle non-streaming requests with context."""
    provider_config = ctx.config.provider_manager.get_provider_config(ctx.provider_name)
    handler = get_non_streaming_handler(ctx.config, provider_config)

    # Use new context-based method
    return await handler.handle_with_context(ctx)


async def _finalize_metrics_on_error(ctx: Any, error_type: str) -> None:
    """Finalize metrics when an HTTP exception occurs."""
    from src.api.services.metrics_orchestrator import (
        MetricsContext,
        MetricsOrchestrator,
    )

    # Create MetricsContext from RequestContext for unified error handling
    metrics_ctx = MetricsContext(
        request_id=ctx.request_id,
        tracker=ctx.tracker,
        metrics=ctx.metrics,
        is_enabled=log_request_metrics(),
    )

    orchestrator = MetricsOrchestrator(config=ctx.config)
    await orchestrator.finalize_on_error(metrics_ctx, "HTTP exception", ErrorType(error_type))


async def _handle_unexpected_error(
    ctx: Any,
    exception: Exception,
) -> JSONResponse:
    """Handle unexpected errors with proper logging and metrics."""
    from src.api.services.metrics_orchestrator import (
        MetricsContext,
        MetricsOrchestrator,
    )

    duration_ms = (time.time() - ctx.start_time) * 1000
    orchestrator = MetricsOrchestrator(config=ctx.config)

    # Create MetricsContext from RequestContext for unified error handling
    metrics_ctx = MetricsContext(
        request_id=ctx.request_id,
        tracker=ctx.tracker,
        metrics=ctx.metrics,
        is_enabled=log_request_metrics(),
    )

    # Check for timeout
    if _is_timeout_error(exception):
        await orchestrator.finalize_on_timeout(metrics_ctx)
        raise _map_timeout_to_504() from exception

    # Classify error
    if ctx.openai_client is not None:
        error_message = ctx.openai_client.classify_openai_error(str(exception))
    else:
        error_message = str(exception)

    # Finalize metrics using orchestrator
    await orchestrator.finalize_on_error(metrics_ctx, error_message, ErrorType.UNEXPECTED_ERROR)

    # Log error
    if log_request_metrics():
        conversation_logger.error(
            f"❌ ERROR | Duration: {duration_ms:.0f}ms | Error: {error_message}"
        )
        _log_traceback(conversation_logger)
    else:
        logger.error(f"Unexpected error processing request: {exception}")
        _log_traceback()

    raise HTTPException(status_code=500, detail=error_message) from exception


@router.post("/v1/messages/count_tokens")
async def count_tokens(
    request: ClaudeTokenCountRequest,
    cfg: Config = Depends(get_config),
    mm: ModelManager = Depends(get_model_manager),
    _: None = Depends(validate_api_key),
) -> Response:
    """Count tokens using the TokenCountService.

    Tries provider API first, falls back to character-based estimation.
    """
    service = TokenCountService(config=cfg)
    result = await service.execute(
        model=request.model,
        system=request.system,
        messages=request.messages,
        model_manager=mm,
    )

    # Handle error case
    if "error" in result.content:
        raise HTTPException(status_code=result.status, detail=result.content["error"])

    return result.to_response()


@router.get("/health")
async def health_check(cfg: Config = Depends(get_config)) -> Response:
    """Health check endpoint with provider status."""
    service = HealthCheckService(config=cfg)
    result = service.execute()
    return result.to_response()


@router.get("/test-connection")
async def test_connection(cfg: Config = Depends(get_config)) -> Response:
    """Test API connectivity to the default provider."""
    service = TestConnectionService(config=cfg)
    result = await service.execute()
    return result.to_response()


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
    request: ModelsListRequest = Depends(ModelsListRequest.from_fastapi),
    cfg: Config = Depends(get_config),
    models_cache: ModelsDiskCache | None = Depends(get_models_cache),
    _: None = Depends(validate_api_key),
) -> Response:
    """List available models from the specified provider or default provider."""
    service = ModelsListService(
        config=cfg, models_cache=models_cache, fetch_fn=fetch_models_unauthenticated
    )
    result = await service.execute_with_request(request)
    return result.to_response()


@router.get("/v1/aliases")
async def list_aliases(
    cfg: Config = Depends(get_config),
    _: None = Depends(validate_api_key),
) -> Response:
    """List all configured model aliases grouped by provider.

    Only shows aliases for active providers (those with API keys configured).

    Also includes a non-mutating overlay of "suggested" aliases derived from
    `/top-models`.
    """
    service = AliasesListService(config=cfg)
    result = await service.execute()
    return result.to_response()


@router.get("/top-models")
async def top_models(
    request: TopModelsRequest = Depends(TopModelsRequest.from_fastapi),
    cfg: Config = Depends(get_config),
    models_cache: ModelsDiskCache | None = Depends(get_models_cache),
    _: None = Depends(validate_api_key),
) -> Response:
    """List curated top models (proxy metadata, not part of /v1 surface).

    This endpoint is intended as a dashboard-friendly discovery contract.
    """
    service = TopModelsEndpointService(config=cfg, models_cache=models_cache)
    result = await service.execute_with_request(request)
    return result.to_response()


@router.get("/")
async def root(cfg: Config = Depends(get_config)) -> dict[str, Any]:
    """Root endpoint"""
    return {
        "message": "VanDamme Proxy v1.0.0",
        "status": "running",
        "config": {
            "base_url": cfg.base_url,
            "max_tokens_limit": cfg.max_tokens_limit,
            "api_key_configured": bool(cfg.openai_api_key),
            "client_api_key_validation": bool(cfg.proxy_api_key),
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
