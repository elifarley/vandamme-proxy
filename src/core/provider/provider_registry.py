"""Provider registry for storing and querying provider configurations."""

from src.core.provider_config import ProviderConfig


class ProviderRegistry:
    """Central registry for provider configurations.

    Responsibilities:
    - Store and retrieve provider configs
    - List all configured providers
    - Query for specific provider config

    This is a simple in-memory registry. For production use with dynamic
    provider configuration, consider adding persistence and change notification.
    """

    def __init__(self) -> None:
        """Initialize an empty provider registry."""
        self._configs: dict[str, ProviderConfig] = {}

    def register(self, config: ProviderConfig) -> None:
        """Register a provider configuration.

        Args:
            config: The provider configuration to register.
        """
        self._configs[config.name] = config

    def get(self, provider_name: str) -> ProviderConfig | None:
        """Get provider config by name.

        Args:
            provider_name: The name of the provider to retrieve.

        Returns:
            The ProviderConfig if found, None otherwise.
        """
        return self._configs.get(provider_name)

    def list_all(self) -> dict[str, ProviderConfig]:
        """Return a copy of all registered providers.

        Returns:
            A dictionary mapping provider names to their configurations.
        """
        return self._configs.copy()

    def exists(self, provider_name: str) -> bool:
        """Check if provider is configured.

        Args:
            provider_name: The name of the provider to check.

        Returns:
            True if the provider is registered, False otherwise.
        """
        return provider_name in self._configs

    def clear(self) -> None:
        """Clear all registered providers.

        This is primarily useful for testing.
        """
        self._configs.clear()
