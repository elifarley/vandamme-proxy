"""FastAPI dependency injection for ModelsDiskCache.

This module provides the standard DI accessor pattern for models cache,
eliminating the module-level singleton in endpoints.py.
"""

from fastapi import Request

from src.models.cache import ModelsDiskCache


def get_models_cache(request: Request) -> ModelsDiskCache | None:
    """Return the ModelsDiskCache instance owned by the FastAPI app.

    The cache may be None if disabled via configuration.

    Args:
        request: The FastAPI request object

    Returns:
        ModelsDiskCache instance, or None if disabled

    Raises:
        TypeError: If app.state.models_cache exists but is not a ModelsDiskCache
    """
    cache = getattr(request.app.state, "models_cache", None)
    if cache is None:
        return None
    if not isinstance(cache, ModelsDiskCache):
        raise TypeError(
            f"app.state.models_cache must be ModelsDiskCache or None, got {type(cache).__name__}"
        )
    return cache
