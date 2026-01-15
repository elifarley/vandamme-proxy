"""Runtime config value accessors.

These functions provide config values at runtime without requiring
direct config imports. They're used to replace module-level constants
that would otherwise create import-time coupling.

Config Context Propagation:
    Config is propagated via ContextVar for O(1) lookup without stack
    inspection. The config_context_middleware in src/main.py sets the
    request-scoped config at the start of each HTTP request.

Usage:
    # Instead of:
    LOG_REQUEST_METRICS = config.log_request_metrics

    # Use:
    from src.core.config.accessors import log_request_metrics
    if log_request_metrics():
        ...
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config

logger = logging.getLogger(__name__)

# Request-scoped config context (async-safe, O(1) lookup)
# Set by config_context_middleware in src/main.py
_config_context: ContextVar[Config | None] = ContextVar("config_context", default=None)


def _get_config_from_context() -> Config | None:
    """Get config from request context via ContextVar (O(1) lookup).

    Returns None if not in a request context (e.g., CLI, tests).
    This allows the same functions to work in multiple contexts.

    The ContextVar is set by config_context_middleware in src/main.py.
    """
    return _config_context.get(None)


def _get_global_fallback() -> Config:
    """Fallback to module-level config for non-request contexts.

    This is used for CLI commands and test scenarios where there's
    no FastAPI request context. It creates a singleton only when needed.

    TODO: Eventually remove this after CLI migration is complete.
    """
    # Lazy import to avoid circular dependency
    from .config import Config

    return Config()


# Runtime accessor functions
# These can be used anywhere without creating import-time coupling


def log_request_metrics() -> bool:
    """Get the log_request_metrics config value."""
    cfg = _get_config_from_context()
    if cfg is None:
        cfg = _get_global_fallback()
    return cfg.log_request_metrics


def max_tokens_limit() -> int:
    """Get the max_tokens_limit config value."""
    cfg = _get_config_from_context()
    if cfg is None:
        cfg = _get_global_fallback()
    return cfg.max_tokens_limit


def min_tokens_limit() -> int:
    """Get the min_tokens_limit config value."""
    cfg = _get_config_from_context()
    if cfg is None:
        cfg = _get_global_fallback()
    return cfg.min_tokens_limit


def request_timeout() -> int:
    """Get the request_timeout config value."""
    cfg = _get_config_from_context()
    if cfg is None:
        cfg = _get_global_fallback()
    return cfg.request_timeout


def streaming_read_timeout() -> float | None:
    """Get the streaming_read_timeout config value."""
    cfg = _get_config_from_context()
    if cfg is None:
        cfg = _get_global_fallback()
    return cfg.streaming_read_timeout


def streaming_connect_timeout() -> float:
    """Get the streaming_connect_timeout config value."""
    cfg = _get_config_from_context()
    if cfg is None:
        cfg = _get_global_fallback()
    return cfg.streaming_connect_timeout


def models_cache_enabled() -> bool:
    """Get the models_cache_enabled config value."""
    cfg = _get_config_from_context()
    if cfg is None:
        cfg = _get_global_fallback()
    return cfg.models_cache_enabled


def cache_dir() -> str:
    """Get the cache_dir config value."""
    cfg = _get_config_from_context()
    if cfg is None:
        cfg = _get_global_fallback()
    return cfg.cache_dir


def models_cache_ttl_hours() -> int:
    """Get the models_cache_ttl_hours config value."""
    cfg = _get_config_from_context()
    if cfg is None:
        cfg = _get_global_fallback()
    return cfg.models_cache_ttl_hours


def active_requests_sse_enabled() -> bool:
    """Get the active_requests_sse_enabled config value."""
    cfg = _get_config_from_context()
    if cfg is None:
        cfg = _get_global_fallback()
    return cfg.active_requests_sse_enabled


def active_requests_sse_interval() -> float:
    """Get the active_requests_sse_interval config value."""
    cfg = _get_config_from_context()
    if cfg is None:
        cfg = _get_global_fallback()
    return cfg.active_requests_sse_interval


def active_requests_sse_heartbeat() -> float:
    """Get the active_requests_sse_heartbeat config value."""
    cfg = _get_config_from_context()
    if cfg is None:
        cfg = _get_global_fallback()
    return cfg.active_requests_sse_heartbeat


# Context management functions for testing and manual control


def set_config_context(config: Config) -> None:
    """Manually set config context (useful for testing).

    In production, this is handled automatically by config_context_middleware.
    Use this in tests to provide config without going through the full request stack.

    Example:
        from src.core.config import Config
        from src.core.config.accessors import set_config_context

        def test_something():
            cfg = Config(log_request_metrics=True)
            set_config_context(cfg)
            assert log_request_metrics() is True
    """
    _config_context.set(config)


def clear_config_context() -> None:
    """Clear config context (useful for testing).

    Resets the config context to None, causing subsequent accessor calls
    to fall back to _get_global_fallback().
    """
    _config_context.set(None)


@asynccontextmanager
async def config_context_middleware(config: Config) -> AsyncGenerator[None, None]:
    """Context manager for setting config context (for middleware use).

    Usage in middleware:
        from src.core.config.accessors import config_context_middleware

        @app.middleware("http")
        async def middleware(request, call_next):
            cfg = getattr(request.app.state, "config", None)
            if cfg is None:
                return await call_next(request)

            async with config_context_middleware(cfg):
                return await call_next(request)
    """
    token = _config_context.set(config)
    try:
        yield
    finally:
        _config_context.reset(token)
