"""Fallback alias configuration loader with TOML support.

This module handles loading and merging fallback alias configurations
and provider settings from TOML files, allowing for both package defaults and local overrides.
"""

import logging
from pathlib import Path
from typing import Any

# Use tomli for Python 3.10 compatibility
# Python 3.11+ has tomllib in stdlib, but we use tomli for consistency
try:
    import tomli
except ImportError:
    # Fallback if tomli is not available
    tomli = None  # type: ignore

logger = logging.getLogger(__name__)

# Module-level cache to avoid reloading configuration multiple times
_config_cache: dict[str, Any] | None = None
_configuration_logged = False


class AliasConfigLoader:
    """Loads and merges fallback alias configurations, provider settings, and defaults from TOML."""

    def __init__(self) -> None:
        """Initialize AliasConfigLoader with configuration paths."""
        self._config_paths = [
            # Local override (highest priority)
            Path.cwd() / "vandamme-config.toml",
            # User-specific configuration
            Path.home() / ".config" / "vandamme-proxy" / "vandamme-config.toml",
            # Package defaults (lowest priority)
            Path(__file__).parent.parent / "config" / "defaults.toml",
        ]

    def load_config(self, force_reload: bool = False) -> dict[str, Any]:
        """Load and merge configurations from all TOML files.

        Args:
            force_reload: Force reload even if cached

        Returns:
            Merged configuration dictionary with sections:
            - 'providers': {provider_name: {config_key: value, "aliases": {alias: target}}}
            - 'defaults': {default_key: value}
        """
        global _config_cache, _configuration_logged

        if _config_cache is not None and not force_reload:
            return _config_cache

        # Check for tomli at runtime to allow proper patching in tests
        if globals().get("tomli") is None:
            logger.warning("tomli/tomllib not available, configuration disabled")
            _config_cache = {"providers": {}, "defaults": {}}
            return _config_cache

        merged_config: dict[str, Any] = {"providers": {}, "defaults": {}}

        # Load from lowest priority to highest (so later files override earlier ones)
        for config_path in reversed(self._config_paths):
            if config_path.exists():
                try:
                    with open(config_path, "rb") as f:
                        config_data = globals()["tomli"].load(f)

                    # Extract provider sections (e.g., [poe], [openai])
                    for key, value in config_data.items():
                        if key == "defaults":
                            # Handle defaults section
                            if isinstance(value, dict):
                                for default_key, default_value in value.items():
                                    if isinstance(default_key, str) and isinstance(
                                        default_value, (str, int, float, bool)
                                    ):
                                        merged_config["defaults"][default_key] = default_value
                        elif isinstance(value, dict):
                            # This is a provider configuration section
                            provider_name = key.lower()

                            # Initialize provider config if not exists
                            if provider_name not in merged_config["providers"]:
                                merged_config["providers"][provider_name] = {}

                            # Extract aliases from provider.aliases section
                            if "aliases" in value and isinstance(value["aliases"], dict):
                                aliases_dict = merged_config["providers"][provider_name].setdefault(
                                    "aliases", {}
                                )
                                for alias, target in value["aliases"].items():
                                    if isinstance(alias, str) and isinstance(target, str):
                                        aliases_dict[alias.lower()] = target

                                # Remove aliases from provider config for cleaner structure
                                provider_config = {k: v for k, v in value.items() if k != "aliases"}
                            else:
                                provider_config = value

                            # Merge provider configuration (higher priority overrides)
                            for config_key, config_value in provider_config.items():
                                if isinstance(config_key, str) and isinstance(
                                    config_value, (str, int, float, bool)
                                ):
                                    merged_config["providers"][provider_name][config_key] = (
                                        config_value
                                    )

                    # Log which file we loaded
                    if config_path == Path.cwd() / "vandamme-config.toml":
                        source = "local override"
                    elif (
                        config_path
                        == Path.home() / ".config" / "vandamme-proxy" / "vandamme-config.toml"
                    ):
                        source = "user config"
                    else:
                        source = "package defaults"

                    logger.debug(f"Loaded config from {source}: {config_path}")

                except Exception as e:
                    logger.warning(f"Failed to load {config_path}: {e}")

        _config_cache = merged_config

        # Log provider and alias info (only once per process)
        if not _configuration_logged:
            providers_config = merged_config.get("providers", {})
            total_providers = len(providers_config)
            total_aliases = sum(
                len(provider.get("aliases", {})) for provider in providers_config.values()
            )
            logger.info(
                f"Loaded configuration: {total_providers} providers with {total_aliases} aliases"
            )
            _configuration_logged = True

        return _config_cache

    def get_fallback_alias(self, provider: str, alias: str) -> str | None:
        """Get fallback alias target for a specific provider and alias.

        Args:
            provider: Provider name (lowercase)
            alias: Alias name (lowercase)

        Returns:
            Target model name or None if not found
        """
        config = self.load_config()
        providers_config = config.get("providers", {})
        if isinstance(providers_config, dict):
            provider_config = providers_config.get(provider.lower(), {})
            if isinstance(provider_config, dict):
                aliases = provider_config.get("aliases", {})
                if isinstance(aliases, dict):
                    return aliases.get(alias.lower())
        return None

    def has_provider_defaults(self, provider: str) -> bool:
        """Check if a provider has any fallback aliases configured.

        Args:
            provider: Provider name (lowercase)

        Returns:
            True if provider has fallback aliases
        """
        config = self.load_config()
        provider_config = config.get("providers", {}).get(provider.lower(), {})
        return "aliases" in provider_config and bool(provider_config["aliases"])

    def get_defaults(self) -> dict[str, Any]:
        """Get default configuration values.

        Returns:
            Dictionary of default configuration values
        """
        config = self.load_config()
        defaults = config.get("defaults", {})
        return defaults if isinstance(defaults, dict) else {}  # type: ignore

    def get_provider_config(self, provider_name: str) -> dict[str, Any]:
        """Get provider-specific configuration from TOML.

        Args:
            provider_name: The name of the provider (e.g., "poe", "openai")

        Returns:
            Provider configuration dictionary with settings and aliases
        """
        config = self.load_config()
        provider_config = config.get("providers", {}).get(provider_name.lower(), {})

        # Return a copy to avoid modifying cached data
        return dict(provider_config) if provider_config else {"aliases": {}}

    @staticmethod
    def reset_cache() -> None:
        """Reset the module-level configuration cache.

        This should only be used in tests to ensure test isolation.
        """
        global _config_cache, _configuration_logged
        _config_cache = None
        _configuration_logged = False
