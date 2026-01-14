"""Metrics orchestration for API endpoints.

This module provides centralized initialization and finalization of request metrics,
eliminating duplication across endpoints. It handles the dual-path pattern where
metrics may be enabled or disabled, ensuring consistent behavior.

Design principles:
- DRY: Single source of truth for metrics lifecycle
- Graceful degradation: Works when metrics disabled
- Type safety: Proper handling of optional metrics objects
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.core.error_types import ErrorType
from src.core.logging import ConversationLogger

if TYPE_CHECKING:
    from fastapi import Request

    from src.core.config import Config
    from src.core.metrics.models.request import RequestMetrics
    from src.core.metrics.tracker.tracker import RequestTracker
    from src.core.model_manager import ModelManager

logger = logging.getLogger(__name__)
conversation_logger = ConversationLogger.get_logger()


@dataclass(frozen=True, slots=True)
class MetricsContext:
    """Structured context for metrics operations.

    Encapsulates all metrics-related state, providing None-safe access
    to metrics operations regardless of whether metrics are enabled.
    """

    request_id: str
    tracker: RequestTracker | None
    metrics: RequestMetrics | None
    is_enabled: bool

    def update_provider_context(self, provider_name: str, resolved_model: str) -> None:
        """Update metrics with resolved provider/model information."""
        if not self.is_enabled or not self.metrics or not self.tracker:
            return

        self.metrics.provider = provider_name  # type: ignore[assignment]
        self.metrics.openai_model = resolved_model

    async def update_last_accessed(self, provider_name: str, model: str, timestamp: str) -> None:
        """Update last accessed timestamp for provider/model."""
        if not self.is_enabled or not self.tracker:
            return
        await self.tracker.update_last_accessed(
            provider=provider_name, model=model, timestamp=timestamp
        )

    async def finalize_on_timeout(self) -> None:
        """Finalize metrics when a timeout occurs."""
        if not self.is_enabled or not self.metrics or not self.tracker:
            return
        self.metrics.error = "Upstream timeout"
        self.metrics.error_type = ErrorType.TIMEOUT
        self.metrics.end_time = time.time()
        await self.tracker.end_request(self.request_id)

    async def finalize_on_error(self, error_message: str, error_type: ErrorType) -> None:
        """Finalize metrics when an error occurs."""
        if not self.is_enabled or not self.metrics or not self.tracker:
            return
        self.metrics.error = error_message
        self.metrics.error_type = error_type
        self.metrics.end_time = time.time()
        await self.tracker.end_request(self.request_id)

    async def finalize_success(self) -> None:
        """Finalize metrics on successful completion."""
        if not self.is_enabled or not self.tracker:
            return
        await self.tracker.end_request(self.request_id)


class MetricsOrchestrator:
    """Centralized metrics initialization and lifecycle management.

    This orchestrator handles the common pattern of:
    1. Checking if metrics are enabled
    2. Getting/creating tracker and metrics objects
    3. Initializing request tracking
    4. Finalizing metrics on completion/error

    It encapsulates the dual-path logic (enabled pattern where code must work
    both when metrics are enabled and disabled), reducing cognitive load
    and preventing bugs from inconsistent handling.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the orchestrator with a config instance.

        Args:
            config: The Config instance for checking if metrics are enabled.
        """
        self._config = config
        self._log_request_metrics = config.log_request_metrics

    def is_enabled(self) -> bool:
        """Check if metrics collection is enabled."""
        return self._log_request_metrics

    async def initialize_request_metrics(
        self,
        request_id: str,
        http_request: Request,
        model: str,
        is_streaming: bool,
        model_manager: ModelManager,
    ) -> MetricsContext:
        """Initialize metrics for a new request.

        This method handles the full initialization pattern:
        - Check if metrics are enabled
        - Get tracker from request state
        - Resolve model to get provider info
        - Start request tracking
        - Update last accessed timestamps

        Args:
            request_id: Unique identifier for this request.
            http_request: The FastAPI Request object.
            model: The model name from the request (may be an alias).
            is_streaming: Whether this is a streaming request.
            model_manager: The ModelManager for resolving models.

        Returns:
            A MetricsContext with tracker and metrics (or None if disabled).
        """
        if not self._log_request_metrics:
            return MetricsContext(
                request_id=request_id,
                tracker=None,
                metrics=None,
                is_enabled=False,
            )

        from src.core.metrics.runtime import get_request_tracker

        tracker = get_request_tracker(http_request)

        # Resolve model early so active requests never show provider-prefixed aliases
        provider_name, resolved_model = model_manager.resolve_model(model)

        # Start request tracking
        metrics = await tracker.start_request(
            request_id=request_id,
            claude_model=model,
            is_streaming=is_streaming,
            provider=provider_name,
            resolved_model=resolved_model,
        )

        # Update last accessed timestamp
        await tracker.update_last_accessed(
            provider=provider_name,
            model=resolved_model,
            timestamp=metrics.start_time_iso,
        )

        logger.debug(
            "[metrics] Initialized request_id=%s model=%s provider=%s resolved_model=%s stream=%s",
            request_id,
            model,
            provider_name,
            resolved_model,
            is_streaming,
        )

        return MetricsContext(
            request_id=request_id,
            tracker=tracker,
            metrics=metrics,
            is_enabled=True,
        )

    async def update_provider_resolution(
        self,
        ctx: MetricsContext,
        provider_name: str,
        resolved_model: str,
    ) -> None:
        """Update metrics after provider resolution.

        This is called when provider context is resolved separately from
        initial metrics setup (e.g., after validate_api_key dependency).

        Args:
            ctx: The metrics context to update.
            provider_name: The resolved provider name.
            resolved_model: The resolved model name.
        """
        ctx.update_provider_context(provider_name, resolved_model)

        await ctx.update_last_accessed(
            provider_name,
            resolved_model,
            ctx.metrics.start_time_iso if ctx.metrics else "",
        )

        logger.debug(
            "[metrics] Updated provider resolution request_id=%s provider=%s model=%s",
            ctx.request_id,
            provider_name,
            resolved_model,
        )

    async def finalize_on_timeout(self, ctx: MetricsContext) -> None:
        """Finalize metrics when an upstream timeout occurs.

        Args:
            ctx: The metrics context to finalize.
        """
        await ctx.finalize_on_timeout()
        logger.debug("[metrics] Finalized on timeout request_id=%s", ctx.request_id)

    async def finalize_on_error(
        self,
        ctx: MetricsContext,
        error_message: str,
        error_type: ErrorType = ErrorType.UNEXPECTED_ERROR,
    ) -> None:
        """Finalize metrics when an error occurs.

        Args:
            ctx: The metrics context to finalize.
            error_message: Human-readable error description.
            error_type: Categorized error type from ErrorType enum.
        """
        await ctx.finalize_on_error(error_message, error_type)
        logger.debug(
            "[metrics] Finalized on error request_id=%s type=%s",
            ctx.request_id,
            error_type,
        )

    async def finalize_success(self, ctx: MetricsContext) -> None:
        """Finalize metrics on successful completion.

        Args:
            ctx: The metrics context to finalize.
        """
        await ctx.finalize_success()
        logger.debug("[metrics] Finalized successfully request_id=%s", ctx.request_id)


def create_request_id() -> str:
    """Create a unique request identifier.

    This is a small utility to ensure consistent UUID generation
    across endpoints.

    Returns:
        A unique request ID string.
    """
    return str(uuid.uuid4())


def log_traceback(log: Any = logger) -> None:
    """Log full traceback for debugging.

    This utility centralizes the traceback logging pattern that was
    duplicated across multiple exception handlers.

    Args:
        log: The logger to use (defaults to module logger).
    """
    import traceback

    log.error(traceback.format_exc())
