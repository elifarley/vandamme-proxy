"""Context managers for test isolation without mutating global state.

This module provides elegant alternatives to the fragile reset_singleton()
pattern, allowing tests to create isolated configuration without:
- Mutating sys.modules
- Hardcoding module names
- Dealing with stale state capture

The context managers handle environment variable setup/teardown automatically.
"""

import os
from collections.abc import Generator
from contextlib import contextmanager

from src.core.config.facade import Config


@contextmanager
def temporary_config(
    env_overrides: dict[str, str] | None = None,
    clear_providers: bool = True,
) -> Generator[Config, None, None]:
    """Create a temporary config instance for testing.

    This context manager creates an isolated Config instance with custom
    environment variables, without mutating the global singleton or sys.modules.

    Args:
        env_overrides: Environment variables to set for this context.
            Keys are env var names (e.g., "LOG_LEVEL"), values are strings.
        clear_providers: If True, clear provider-related env vars first.
            This removes {PROVIDER}_API_KEY and {PROVIDER}_ALIAS_* variables.

    Yields:
        A new Config instance with the test environment

    Example:
        with temporary_config({"LOG_LEVEL": "DEBUG", "PORT": "9999"}) as config:
            assert config.log_level == "DEBUG"
            assert config.port == 9999
        # Original environment restored automatically

    Note:
        This creates a NEW Config instance each time. The global singleton
        is not modified, so tests don't interfere with each other.
    """
    # Store original environment
    original_env = os.environ.copy()

    try:
        # Clear provider env vars if requested
        if clear_providers:
            for key in list(os.environ.keys()):
                if "_API_KEY" in key or "_ALIAS_" in key:
                    os.environ.pop(key, None)

        # Apply test overrides
        if env_overrides:
            os.environ.update(env_overrides)

        # Create fresh config instance (no global mutation)
        test_config = Config()

        yield test_config

    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


@contextmanager
def mock_config(**overrides: str | int | float | bool) -> Generator[Config, None, None]:
    """Create a mock config with direct property overrides.

    This is faster than temporary_config for unit tests that don't
    need environment variable loading. It directly modifies the frozen
    dataclass attributes using object.__setattr__.

    Args:
        **overrides: Property names and values to override.
            Values must be the correct type (int, str, float, bool).

    Yields:
        A Config instance with overridden values

    Example:
        with mock_config(log_level="DEBUG", port=9999) as config:
            assert config.log_level == "DEBUG"
            assert config.port == 9999

    Raises:
        AttributeError: If an invalid property name is provided

    Note:
        This modifies the config object in-place but doesn't change
        the environment. Use temporary_config() for env var testing.
    """
    # Create base config from current environment
    test_config = Config()

    # Map property names to internal config objects
    # Format: (property_name, internal_config_attr, dataclass_field)
    property_mappings = {
        # Server settings
        "host": ("_server_config", "host"),
        "port": ("_server_config", "port"),
        "log_level": ("_server_config", "log_level"),
        # Middleware settings
        "gemini_thought_signatures_enabled": (
            "_middleware_config",
            "gemini_thought_signatures_enabled",
        ),
        "thought_signature_cache_ttl": ("_middleware_config", "thought_signature_cache_ttl"),
        "thought_signature_max_cache_size": (
            "_middleware_config",
            "thought_signature_max_cache_size",
        ),
        "thought_signature_cleanup_interval": (
            "_middleware_config",
            "thought_signature_cleanup_interval",
        ),
        # Timeout settings
        "request_timeout": ("_timeout_config", "request_timeout"),
        "streaming_read_timeout": ("_timeout_config", "streaming_read_timeout"),
        "streaming_connect_timeout": ("_timeout_config", "streaming_connect_timeout"),
        "max_retries": ("_timeout_config", "max_retries"),
        # Metrics settings
        "log_request_metrics": ("_metrics_config", "log_request_metrics"),
        "max_tokens_limit": ("_metrics_config", "max_tokens_limit"),
        "min_tokens_limit": ("_metrics_config", "min_tokens_limit"),
        # Provider settings
        "default_provider": ("_provider_config", "default_provider"),
    }

    for key, value in overrides.items():
        if key not in property_mappings:
            raise AttributeError(
                f"Cannot mock unknown property '{key}'. "
                f"Valid properties: {list(property_mappings.keys())}"
            )

        config_attr, field_name = property_mappings[key]
        config_object = getattr(test_config, config_attr)

        # Use object.__setattr__ because dataclasses are frozen
        object.__setattr__(config_object, field_name, value)

    yield test_config
