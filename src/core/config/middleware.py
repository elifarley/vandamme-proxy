"""Middleware configuration module.

This module handles middleware-related settings including:
- Gemini thought signature middleware configuration
- Thought signature cache settings

Now uses schema-based loading for automatic type coercion and validation.
"""

from dataclasses import dataclass

from src.core.config.schema import ConfigSchema
from src.core.config.validation import load_env_var


@dataclass(frozen=True)
class MiddlewareConfig:
    """Configuration for middleware settings.

    This is a frozen dataclass that provides immutable configuration
    for the middleware system. It can be passed to ProviderManager
    via dependency injection to avoid circular dependencies.

    Attributes:
        gemini_thought_signatures_enabled: Whether Gemini thought signature middleware is enabled
        thought_signature_cache_ttl: TTL in seconds for thought signature cache entries
        thought_signature_max_cache_size: Maximum number of entries in thought signature cache
        thought_signature_cleanup_interval: Interval in seconds for cache cleanup
    """

    gemini_thought_signatures_enabled: bool
    thought_signature_cache_ttl: float
    thought_signature_max_cache_size: int
    thought_signature_cleanup_interval: float


class MiddlewareSettings:
    """Manages middleware configuration from environment variables.

    This class uses the schema-based loading approach which provides:
    - Automatic type coercion (str -> int/float/bool)
    - Validation with clear error messages
    - Single source of truth for default values
    """

    @staticmethod
    def load() -> MiddlewareConfig:
        """Load middleware configuration using schema-based validation.

        Returns:
            MiddlewareConfig with values from environment or defaults

        Raises:
            ConfigError: If any environment variable fails validation
        """
        return MiddlewareConfig(
            gemini_thought_signatures_enabled=load_env_var(
                ConfigSchema.GEMINI_THOUGHT_SIGNATURES_ENABLED
            ),
            thought_signature_cache_ttl=load_env_var(ConfigSchema.THOUGHT_SIGNATURE_CACHE_TTL),
            thought_signature_max_cache_size=load_env_var(
                ConfigSchema.THOUGHT_SIGNATURE_MAX_CACHE_SIZE
            ),
            thought_signature_cleanup_interval=load_env_var(
                ConfigSchema.THOUGHT_SIGNATURE_CLEANUP_INTERVAL
            ),
        )
