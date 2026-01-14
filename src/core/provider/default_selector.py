"""Default provider selection with intelligent fallback."""

import logging


class DefaultProviderSelector:
    """Selects default provider with intelligent fallback.

    Responsibilities:
    - Validate configured default provider
    - Fall back to first available provider if default unavailable
    - Raise helpful errors if no providers configured

    This class ensures that there is always a valid default provider available,
    or provides clear error messages if configuration is missing.
    """

    def __init__(
        self,
        default_provider: str,
        source: str = "system",
    ) -> None:
        """Initialize the default provider selector.

        Args:
            default_provider: The configured default provider name.
            source: The source of the configuration ("system", "env", "toml", etc.).
        """
        self._default = default_provider
        self._source = source
        self._actual_default: str | None = None

    def select(self, available_providers: dict[str, object]) -> str:
        """Select default provider from available providers.

        Args:
            available_providers: Dictionary of available provider configurations.

        Returns:
            The selected provider name.

        Raises:
            ValueError: If no providers are available.
        """
        logger = logging.getLogger(__name__)

        # If original default is available, use it
        if self._default in available_providers:
            self._actual_default = self._default
            return self._default

        if available_providers:
            # Select the first available provider
            selected = list(available_providers.keys())[0]
            self._actual_default = selected

            if self._source != "system":
                # User configured a default but it's not available
                logger.info(
                    f"Using '{selected}' as default provider "
                    f"(configured '{self._default}' not available)"
                )
            else:
                # No user configuration, just pick the first available
                logger.debug(f"Using '{selected}' as default provider (first available provider)")
            return selected

        # No providers available at all
        provider_upper = self._default.upper()
        raise ValueError(
            f"No providers configured. Please set at least one provider API key "
            f"(e.g., {provider_upper}_API_KEY).\n"
            f"Hint: If {provider_upper}_API_KEY is set in your shell, make sure to export it: "
            f"'export {provider_upper}_API_KEY'"
        )

    @property
    def configured_default(self) -> str:
        """Get the configured default provider name."""
        return self._default

    @property
    def actual_default(self) -> str | None:
        """Get the actual default provider after selection."""
        return self._actual_default
