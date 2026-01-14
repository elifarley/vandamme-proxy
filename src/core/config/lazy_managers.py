"""Lazy initialization for provider and alias managers.

This module provides lazy initialization logic without requiring
the full Config facade. The managers are initialized on first access
to avoid circular dependencies.
"""

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.api.services.alias_service import AliasService
    from src.core.alias_manager import AliasManager
    from src.core.config.cache import CacheConfig
    from src.core.config.middleware import MiddlewareConfig
    from src.core.config.providers import ProviderConfig
    from src.core.provider_manager import ProviderManager


class LazyManagers:
    """Lazy initialization for manager singletons.

    This class defers expensive initialization until first access,
    preventing circular dependencies between config and managers.

    Thread-safety is ensured via threading.Lock for each lazy property.
    The double-check pattern is used to minimize lock contention.
    """

    def __init__(
        self,
        provider_config: "ProviderConfig",
        middleware_config: "MiddlewareConfig",
        cache_config: "CacheConfig",
    ) -> None:
        """Initialize with already-loaded configuration via dependency injection.

        Args:
            provider_config: Provider configuration loaded at Config init time
            middleware_config: Middleware configuration loaded at Config init time
            cache_config: Cache configuration loaded at Config init time
        """
        self._provider_config = provider_config
        self._middleware_config = middleware_config
        self._cache_config = cache_config

        self._provider_manager: ProviderManager | None = None
        self._alias_manager: AliasManager | None = None
        self._alias_service: AliasService | None = None

        # Thread-safe locks for lazy initialization
        self._provider_manager_lock = threading.Lock()
        self._alias_manager_lock = threading.Lock()
        self._alias_service_lock = threading.Lock()

    @property
    def provider_manager(self) -> "ProviderManager":
        """Get or create the provider manager.

        The provider manager is initialized with a MiddlewareConfig DTO
        passed via dependency injection to avoid circular dependencies.

        Thread-safe: Uses double-check locking pattern to ensure only one
        instance is created even under concurrent access.

        Returns:
            The ProviderManager instance
        """
        if self._provider_manager is None:
            with self._provider_manager_lock:
                # Double-check: another thread may have initialized while we waited
                if self._provider_manager is None:
                    from src.core.config.middleware import MiddlewareConfig
                    from src.core.provider_manager import ProviderManager

                    # Create middleware config DTO from injected config
                    middleware_dto = MiddlewareConfig(
                        gemini_thought_signatures_enabled=self._middleware_config.gemini_thought_signatures_enabled,
                        thought_signature_max_cache_size=self._middleware_config.thought_signature_max_cache_size,
                        thought_signature_cache_ttl=self._middleware_config.thought_signature_cache_ttl,
                        thought_signature_cleanup_interval=self._middleware_config.thought_signature_cleanup_interval,
                    )

                    self._provider_manager = ProviderManager(
                        default_provider=self._provider_config.default_provider,
                        default_provider_source=self._provider_config.default_provider_source,
                        middleware_config=middleware_dto,
                    )
                    self._provider_manager.load_provider_configs()

        return self._provider_manager

    @property
    def alias_manager(self) -> "AliasManager":
        """Get or create the alias manager.

        The alias manager is initialized with cache configuration
        from the injected CacheConfig.

        Thread-safe: Uses double-check locking pattern to ensure only one
        instance is created even under concurrent access.

        Returns:
            The AliasManager instance
        """
        if self._alias_manager is None:
            with self._alias_manager_lock:
                # Double-check: another thread may have initialized while we waited
                if self._alias_manager is None:
                    from src.core.alias_manager import AliasManager

                    self._alias_manager = AliasManager(
                        cache_ttl_seconds=self._cache_config.alias_cache_ttl_seconds,
                        cache_max_size=self._cache_config.alias_cache_max_size,
                    )

        return self._alias_manager

    @property
    def alias_service(self) -> "AliasService":
        """Get or create the alias service.

        The alias service coordinates AliasManager and ProviderManager
        to provide aliases filtered to active providers only.

        Thread-safe: Uses double-check locking pattern to ensure only one
        instance is created even under concurrent access.

        Returns:
            The AliasService instance
        """
        if self._alias_service is None:
            with self._alias_service_lock:
                # Double-check: another thread may have initialized while we waited
                if self._alias_service is None:
                    from src.api.services.alias_service import AliasService

                    self._alias_service = AliasService(
                        alias_manager=self.alias_manager,
                        provider_manager=self.provider_manager,
                    )

        return self._alias_service
