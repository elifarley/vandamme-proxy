"""Middleware lifecycle management."""

import logging
from typing import TYPE_CHECKING

from src.middleware import MiddlewareChain, ThoughtSignatureMiddleware

if TYPE_CHECKING:
    from src.core.config.middleware import MiddlewareConfig


class MiddlewareManager:
    """Owns and initializes middleware chain.

    Responsibilities:
    - Create MiddlewareChain instance
    - Register middleware based on config
    - Handle async initialization/cleanup

    This class manages the lifecycle of middleware components independently
    of provider management.
    """

    def __init__(self, config: "MiddlewareConfig | None" = None) -> None:
        """Initialize the middleware manager.

        Args:
            config: Optional middleware configuration.
        """
        self._config = config
        self.middleware_chain = MiddlewareChain()
        self._initialized = False
        self._logger = logging.getLogger(__name__)

    def initialize_sync(self) -> None:
        """Synchronously initialize middleware (for non-async contexts)."""
        if self._initialized:
            return

        if self._config and self._config.gemini_thought_signatures_enabled:
            from src.middleware.thought_signature import ThoughtSignatureStore

            store = ThoughtSignatureStore(
                max_size=self._config.thought_signature_max_cache_size,
                ttl_seconds=self._config.thought_signature_cache_ttl,
                cleanup_interval=self._config.thought_signature_cleanup_interval,
            )
            self.middleware_chain.add(ThoughtSignatureMiddleware(store=store))

        self._initialized = True

    async def initialize(self) -> None:
        """Asynchronously initialize middleware chain."""
        if not self._initialized:
            self.initialize_sync()
        await self.middleware_chain.initialize()

    async def cleanup(self) -> None:
        """Cleanup middleware resources."""
        await self.middleware_chain.cleanup()

    @property
    def is_initialized(self) -> bool:
        """Check if middleware has been initialized."""
        return self._initialized
