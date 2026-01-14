"""Request orchestrator for preparing request contexts.

This module provides the RequestOrchestrator class which encapsulates
all initialization logic previously scattered throughout the create_message endpoint.
"""

import logging
import time
import uuid
from typing import Any

from fastapi import HTTPException, Request

from src.api.context.request_context import RequestContext, RequestContextBuilder
from src.api.services.metrics_helper import populate_request_metrics
from src.conversion.request_converter import convert_claude_to_openai
from src.core.config import config
from src.core.error_types import ErrorType
from src.core.metrics.runtime import get_request_tracker
from src.core.model_manager import get_model_manager

logger = logging.getLogger(__name__)


class RequestOrchestrator:
    """Orchestrates the setup and initialization for request processing.

    This class encapsulates all the initialization logic that was previously
    scattered throughout the create_message endpoint, providing a clean
    separation of concerns.

    Responsibilities:
    1. Generate request ID and initialize tracking
    2. Resolve provider and model
    3. Convert request format
    4. Initialize metrics
    5. Validate and prepare authentication
    6. Apply middleware preprocessing
    7. Check client disconnection
    """

    def __init__(self, log_request_metrics: bool = True) -> None:
        """Initialize the orchestrator.

        Args:
            log_request_metrics: Whether metrics tracking is enabled.
        """
        self.log_request_metrics = log_request_metrics
        self.logger = logging.getLogger(f"{__name__}.RequestOrchestrator")

    async def prepare_request_context(
        self,
        request: Any,  # ClaudeMessagesRequest
        http_request: Request,
        client_api_key: str | None,
    ) -> RequestContext:
        """Prepare a complete RequestContext for request processing.

        This is the main entry point that orchestrates all initialization steps.

        Args:
            request: The Claude Messages API request.
            http_request: The FastAPI HTTP request object.
            client_api_key: The validated client API key (or None).

        Returns:
            A fully populated RequestContext ready for handlers.

        Raises:
            HTTPException: If preparation fails (auth, validation, etc.).
        """
        builder = RequestContextBuilder()

        # Step 1: Generate request ID and start timing
        request_id = str(uuid.uuid4())
        start_time = time.time()

        builder.with_request_id(request_id)
        builder.with_http_request(http_request)

        # Step 2: Initialize metrics/tracker if enabled
        metrics, tracker = await self._initialize_metrics(
            request_id=request_id,
            request=request,
            http_request=http_request,
            builder=builder,
        )

        # Step 3: Resolve provider and model
        provider_name, resolved_model = get_model_manager().resolve_model(request.model)
        provider_config = config.provider_manager.get_provider_config(provider_name)

        builder.with_provider(
            provider_name=provider_name,
            resolved_model=resolved_model,
            provider_config=provider_config,
        )

        # Step 4: Convert request to OpenAI format
        openai_request = convert_claude_to_openai(request, get_model_manager())
        tool_name_map_inverse = openai_request.pop("_tool_name_map_inverse", None)
        openai_request.pop("_provider", provider_name)

        builder.with_openai_request(openai_request)
        builder.with_tool_mapping(tool_name_map_inverse)

        # Step 5: Validate passthrough and get provider API key
        provider_api_key = await self._prepare_authentication(
            provider_config=provider_config,
            provider_name=provider_name,
            client_api_key=client_api_key,
        )

        builder.with_auth(
            client_api_key=client_api_key,
            provider_api_key=provider_api_key,
        )

        # Step 6: Populate request metrics
        message_count, request_size, tool_use_count = populate_request_metrics(
            metrics=metrics,
            request=request,
        )
        tool_result_count = metrics.tool_result_count if metrics else 0

        builder.with_timing(
            start_time=start_time,
            tool_use_count=tool_use_count,
            tool_result_count=tool_result_count,
            request_size=request_size,
            message_count=message_count,
        )

        # Step 7: Get client for this provider
        openai_client = config.provider_manager.get_client(
            provider_name,
            client_api_key,
        )
        builder.with_client(openai_client)

        # Step 8: Update metrics with provider info
        if self.log_request_metrics and metrics:
            metrics.provider = provider_name
            metrics.openai_model = resolved_model
            await tracker.update_last_accessed(
                provider=provider_name,
                model=resolved_model,
                timestamp=metrics.start_time_iso,
            )

        # Step 9: Apply middleware preprocessing
        await self._apply_middleware_preprocessing(
            builder=builder,
            request=request,
            openai_request=openai_request,
            provider_name=provider_name,
            client_api_key=client_api_key,
            request_id=request_id,
        )

        # Step 10: Check for client disconnection
        if await http_request.is_disconnected():
            await self._handle_client_disconnect(
                metrics=metrics,
                tracker=tracker,
                request_id=request_id,
            )

        # Build and return the complete context
        builder.with_request(request)
        builder.with_metrics(metrics=metrics, tracker=tracker, config=config)
        return builder.build()

    async def _initialize_metrics(
        self,
        request_id: str,
        request: Any,
        http_request: Request,
        builder: RequestContextBuilder,
    ) -> tuple[Any | None, Any]:
        """Initialize metrics and tracker.

        Returns:
            Tuple of (metrics, tracker).
        """
        if not self.log_request_metrics:
            return None, None

        tracker = get_request_tracker(http_request)
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

        builder.with_metrics(metrics=metrics, tracker=tracker, config=config)
        return metrics, tracker

    async def _prepare_authentication(
        self,
        provider_config: Any,
        provider_name: str,
        client_api_key: str | None,
    ) -> str | None:
        """Prepare authentication for the request.

        Returns:
            The provider API key to use, or None for passthrough.

        Raises:
            HTTPException: If passthrough required but no client API key provided.
        """
        # Validate passthrough requirement
        if provider_config and provider_config.uses_passthrough:
            if not client_api_key:
                raise HTTPException(
                    status_code=401,
                    detail=f"Provider '{provider_name}' requires API key passthrough, "
                    f"but no client API key was provided",
                )
            self.logger.debug(f"Using client API key for provider '{provider_name}'")
            return None  # Passthrough uses client key

        # For non-passthrough providers, get next provider API key
        if provider_config and not provider_config.uses_passthrough:
            key = await config.provider_manager.get_next_provider_api_key(provider_name)
            return key  # type: ignore[no-any-return]

        return None

    async def _apply_middleware_preprocessing(
        self,
        builder: RequestContextBuilder,
        request: Any,
        openai_request: dict[str, Any],
        provider_name: str,
        client_api_key: str | None,
        request_id: str,
    ) -> None:
        """Apply middleware preprocessing to the request.

        This modifies the openai_request in place if middleware changes it.
        """
        if not hasattr(config.provider_manager, "middleware_chain"):
            return

        from src.middleware import RequestContext as MiddlewareRequestContext

        request_context = MiddlewareRequestContext(
            messages=openai_request.get("messages", []),
            provider=provider_name,
            model=request.model,
            request_id=request_id,
            conversation_id=None,
            client_api_key=client_api_key,
        )

        processed_context = await config.provider_manager.middleware_chain.process_request(
            request_context
        )

        if processed_context.messages != request_context.messages:
            openai_request["messages"] = processed_context.messages
            self.logger.debug(f"Request modified by middleware, provider={provider_name}")

    async def _handle_client_disconnect(
        self,
        metrics: Any | None,
        tracker: Any,
        request_id: str,
    ) -> None:
        """Handle client disconnection before processing."""
        if self.log_request_metrics and metrics:
            metrics.error = "Client disconnected before processing"
            metrics.error_type = ErrorType.CLIENT_DISCONNECT
            await tracker.end_request(request_id)
        raise HTTPException(status_code=499, detail="Client disconnected")
