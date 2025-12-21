"""Cache for /v1/models endpoint responses.

Caches provider-specific model lists to avoid repeated API calls.
"""

# type: ignore

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from src.core.cache.disk import DiskJsonCache, make_cache_key


class ModelsDiskCache(DiskJsonCache):
    """Cache for provider model lists from /v1/models endpoint."""

    def __init__(self, cache_dir: Path, ttl_hours: int) -> None:
        super().__init__(
            cache_dir=cache_dir,
            ttl=timedelta(hours=ttl_hours),
            schema_version=1,
            namespace="models",
        )

    def make_file_path(self, provider: str, base_url: str, custom_headers: dict[str, str]) -> Path:
        """Generate cache file path for specific provider configuration."""
        # Create deterministic cache key from provider config
        headers_str = ",".join(f"{k}:{v}" for k, v in sorted(custom_headers.items()))
        cache_key = make_cache_key(provider, base_url, headers_str)
        return self.cache_dir / self.namespace / provider / f"models-{cache_key}.json"

    def _file_path(self) -> Path:
        """This is overridden by make_file_path - should not be called directly."""
        raise NotImplementedError("Use make_file_path(provider, base_url, headers) instead")

    def read_models_if_fresh(
        self,
        provider: str,
        base_url: str,
        custom_headers: dict[str, str],
    ) -> list[dict[str, Any]] | None:
        """Read models from cache if fresh.

        Args:
            provider: Provider name (e.g., "openrouter", "openai")
            base_url: Base URL for the provider's API
            custom_headers: Custom headers sent with the request

        Returns:
            List of model dicts if cache is fresh and valid, None otherwise
        """
        if self._should_skip_cache():
            return None

        path = self.make_file_path(provider, base_url, custom_headers)
        cache_data = self._read_cache_file(path)

        if not cache_data:
            return None

        if not self._is_cache_fresh(cache_data):
            return None

        # Extract models from cached response
        models = cache_data.get("models")
        if not isinstance(models, list):
            return None

        return models

    def write_models(
        self,
        provider: str,
        base_url: str,
        custom_headers: dict[str, str],
        models: list[dict[str, Any]],
    ) -> None:
        """Write models to cache.

        Args:
            provider: Provider name
            base_url: Base URL for the provider's API
            custom_headers: Custom headers sent with the request
            models: List of model objects from the provider's /models endpoint
        """
        if self._should_skip_cache():
            return

        path = self.make_file_path(provider, base_url, custom_headers)

        # Prepare cache data
        cache_data = {
            "provider": provider,
            "base_url": base_url,
            "models": models,
        }

        # Add metadata via base class
        full_data = {
            "schema_version": self.schema_version,
            "last_updated": self._get_timestamp(),
            **cache_data,
        }

        self._atomic_write(path, full_data)

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _serialize(self, payload: Any) -> dict[str, Any]:  # noqa: ANN401
        """Not used - we implement custom read/write methods."""
        return payload  # pragma: no cover

    def _deserialize(self, cache_data: dict[str, Any]) -> Any:  # noqa: ANN401
        """Not used - we implement custom read/write methods."""
        return cache_data  # pragma: no cover
