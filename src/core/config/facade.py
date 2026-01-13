"""Configuration facade providing backward-compatible access to all settings.

This module implements the Config class as a facade that delegates to
specialized configuration modules. It maintains the exact same API as
the original monolithic Config class while internally using the new
modular structure.

The facade pattern allows us to refactor the configuration system into
focused modules without breaking any existing imports or usage patterns.
"""

import hashlib
import logging
import os
import sys
from typing import TYPE_CHECKING

from src.core.config.cache import CacheSettings
from src.core.config.defaults import (
    get_default_base_url,
    get_provider_base_url_env_var,
)
from src.core.config.metrics import MetricsSettings
from src.core.config.middleware import MiddlewareSettings
from src.core.config.providers import ProviderSettings
from src.core.config.security import SecuritySettings
from src.core.config.server import ServerSettings
from src.core.config.timeouts import TimeoutSettings
from src.core.config.top_models import TopModelsSettings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.api.services.alias_service import AliasService
    from src.core.alias_manager import AliasManager
    from src.core.provider_manager import ProviderManager


class Config:
    """Facade providing backward-compatible access to all configuration.

    This class maintains the existing API while delegating to specialized
    configuration modules. It enables future dependency injection without
    breaking existing code.

    All attribute access is delegated to the appropriate configuration module,
    while lazy manager initialization is preserved from the original implementation.
    """

    def __init__(self) -> None:
        # Load all configuration modules
        self._provider_config = ProviderSettings.load()
        self._server_config = ServerSettings.load()
        self._security_config = SecuritySettings.load()
        self._timeout_config = TimeoutSettings.load()
        self._cache_config = CacheSettings.load()
        self._metrics_config = MetricsSettings.load()
        self._middleware_config = MiddlewareSettings.load()
        self._top_models_config = TopModelsSettings.load()

        # Lazy manager initialization (same pattern as original)
        self._provider_manager: ProviderManager | None = None
        self._alias_manager: AliasManager | None = None
        self._alias_service: AliasService | None = None

    # === Provider Settings ===

    @property
    def default_provider(self) -> str:
        return self._provider_config.default_provider

    @property
    def default_provider_source(self) -> str:
        return self._provider_config.default_provider_source

    @property
    def openai_api_key(self) -> str | None:
        return self._provider_config.default_provider_api_key

    @property
    def base_url(self) -> str:
        base_url_env_var = get_provider_base_url_env_var(self.default_provider)
        return os.environ.get(base_url_env_var, get_default_base_url(self.default_provider))

    @property
    def azure_api_version(self) -> str | None:
        return os.environ.get("AZURE_API_VERSION")

    # === Server Settings ===

    @property
    def host(self) -> str:
        return self._server_config.host

    @property
    def port(self) -> int:
        return self._server_config.port

    @property
    def log_level(self) -> str:
        return self._server_config.log_level

    # === Security Settings ===

    @property
    def proxy_api_key(self) -> str | None:
        return self._security_config.proxy_api_key

    def validate_client_api_key(self, client_api_key: str) -> bool:
        """Validate client's API key against proxy requirement."""
        return SecuritySettings.validate_client_api_key(self.proxy_api_key, client_api_key)

    def get_custom_headers(self) -> dict[str, str]:
        """Get custom headers from environment variables."""
        return SecuritySettings.get_custom_headers()

    # === Timeout Settings ===

    @property
    def request_timeout(self) -> int:
        return self._timeout_config.request_timeout

    @property
    def streaming_read_timeout(self) -> float | None:
        return self._timeout_config.streaming_read_timeout

    @property
    def streaming_connect_timeout(self) -> float:
        return self._timeout_config.streaming_connect_timeout

    @property
    def max_retries(self) -> int:
        return self._timeout_config.max_retries

    # === Metrics Settings ===

    @property
    def log_request_metrics(self) -> bool:
        return self._metrics_config.log_request_metrics

    @property
    def max_tokens_limit(self) -> int:
        return self._metrics_config.max_tokens_limit

    @property
    def min_tokens_limit(self) -> int:
        return self._metrics_config.min_tokens_limit

    @property
    def active_requests_sse_enabled(self) -> bool:
        return self._metrics_config.active_requests_sse_enabled

    @property
    def active_requests_sse_interval(self) -> float:
        return self._metrics_config.active_requests_sse_interval

    @property
    def active_requests_sse_heartbeat(self) -> float:
        return self._metrics_config.active_requests_sse_heartbeat

    # === Cache Settings ===

    @property
    def cache_dir(self) -> str:
        return self._cache_config.cache_dir

    @property
    def models_cache_enabled(self) -> bool:
        return self._cache_config.models_cache_enabled

    @property
    def models_cache_ttl_hours(self) -> int:
        return self._cache_config.models_cache_ttl_hours

    @property
    def alias_cache_ttl_seconds(self) -> float:
        return self._cache_config.alias_cache_ttl_seconds

    @property
    def alias_cache_max_size(self) -> int:
        return self._cache_config.alias_cache_max_size

    @property
    def alias_max_chain_length(self) -> int:
        return self._cache_config.alias_max_chain_length

    # === Middleware Settings ===

    @property
    def gemini_thought_signatures_enabled(self) -> bool:
        return self._middleware_config.gemini_thought_signatures_enabled

    @property
    def thought_signature_cache_ttl(self) -> float:
        return self._middleware_config.thought_signature_cache_ttl

    @property
    def thought_signature_max_cache_size(self) -> int:
        return self._middleware_config.thought_signature_max_cache_size

    @property
    def thought_signature_cleanup_interval(self) -> float:
        return self._middleware_config.thought_signature_cleanup_interval

    # === Top Models Settings ===

    @property
    def top_models_source(self) -> str:
        return self._top_models_config.source

    @property
    def top_models_rankings_file(self) -> str:
        return self._top_models_config.rankings_file

    @property
    def top_models_timeout_seconds(self) -> float:
        return self._top_models_config.timeout_seconds

    @property
    def top_models_exclude(self) -> tuple[str, ...]:
        return self._top_models_config.exclude

    # === Lazy Manager Properties ===

    @property
    def provider_manager(self) -> "ProviderManager":
        """Lazy initialization of provider manager.

        Creates a MiddlewareConfig DTO and passes it to ProviderManager via
        dependency injection, eliminating the circular dependency.
        """
        if self._provider_manager is None:
            from src.core.config.middleware import MiddlewareConfig
            from src.core.provider_manager import ProviderManager

            # Create middleware config DTO to pass via dependency injection
            middleware_dto = MiddlewareConfig(
                gemini_thought_signatures_enabled=self._middleware_config.gemini_thought_signatures_enabled,
                thought_signature_max_cache_size=self._middleware_config.thought_signature_max_cache_size,
                thought_signature_cache_ttl=self._middleware_config.thought_signature_cache_ttl,
                thought_signature_cleanup_interval=self._middleware_config.thought_signature_cleanup_interval,
            )

            self._provider_manager = ProviderManager(
                default_provider=self.default_provider,
                default_provider_source=getattr(self, "default_provider_source", "system"),
                middleware_config=middleware_dto,
            )
            # Auto-load configurations on first access
            self._provider_manager.load_provider_configs()
        return self._provider_manager

    @property
    def alias_manager(self) -> "AliasManager":
        """Lazy initialization of alias manager with cache configuration."""
        if self._alias_manager is None:
            from src.core.alias_manager import AliasManager

            self._alias_manager = AliasManager(
                cache_ttl_seconds=self.alias_cache_ttl_seconds,
                cache_max_size=self.alias_cache_max_size,
            )
        return self._alias_manager

    @property
    def alias_service(self) -> "AliasService":
        """Lazy initialization of alias service.

        The service coordinates AliasManager and ProviderManager to provide
        aliases filtered to active providers only.
        """
        if self._alias_service is None:
            from src.api.services.alias_service import AliasService

            self._alias_service = AliasService(
                alias_manager=self.alias_manager,
                provider_manager=self.provider_manager,
            )
        return self._alias_service

    # === Utility Methods ===

    def validate_api_key(self) -> bool:
        """Basic API key validation."""
        if not self.openai_api_key:
            return False
        # Basic format check for OpenAI API keys
        return self.openai_api_key.startswith("sk-")

    @property
    def api_key_hash(self) -> str:
        """Get the first few characters of SHA256 hash of the default provider's API key.

        This provides a secure way to identify the API key without exposing it.
        Returns '<not-set>' if the API key is not configured.

        Returns:
            str: First few characters of SHA256 hash or '<not-set>'
        """
        return (
            "<not-set>"
            if not self.openai_api_key
            else "sha256:" + hashlib.sha256(self.openai_api_key.encode()).hexdigest()[:16] + "..."
        )

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset the global config singleton for test isolation.

        .. deprecated::
            Use :func:`src.core.config.context.temporary_config` instead.
            This method is kept for backward compatibility but should not be used.

        The temporary_config context manager provides superior test isolation:
        - No sys.modules mutation
        - No hardcoded module names
        - Automatic environment cleanup
        - Works with parallel test execution

        Example of new pattern:
            with temporary_config({"LOG_LEVEL": "DEBUG"}) as config:
                assert config.log_level == "DEBUG"
            # Environment automatically restored

        WARNING: Never call this in production code!
        """
        import warnings

        warnings.warn(
            "Config.reset_singleton() is deprecated. "
            "Use src.core.config.context.temporary_config instead for superior test isolation.",
            DeprecationWarning,
            stacklevel=2,
        )

        global config
        config = cls()
        # Ensure modules holding a reference to the old singleton see the fresh instance.
        # This is primarily used for test isolation.
        for module_name in (__name__, "src.core.config"):
            module = sys.modules.get(module_name)
            if module is not None:
                module.config = config  # type: ignore[attr-defined]


# Module-level singleton (same pattern as original)
try:
    config = Config()
except Exception as e:
    print(f"=X= Configuration Error: {e}")
    sys.exit(1)
