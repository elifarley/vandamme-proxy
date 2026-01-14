"""Provider configuration loading from environment and TOML files."""

import logging
import os
from dataclasses import dataclass
from typing import Any

from src.core.provider_config import PASSTHROUGH_SENTINEL, ProviderConfig


@dataclass
class ProviderLoadResult:
    """Result of loading a provider configuration."""

    name: str
    status: str  # "success", "partial"
    message: str | None = None
    api_key_hash: str | None = None
    base_url: str | None = None


class ProviderConfigLoader:
    """Loads provider configurations from environment variables and TOML files.

    Responsibilities:
    - Scan environment for {PROVIDER}_API_KEY patterns
    - Load TOML configurations via AliasConfigLoader
    - Merge env vars with TOML defaults
    - Parse provider-specific headers
    """

    def __init__(self) -> None:
        """Initialize a new provider config loader."""
        self._logger = logging.getLogger(__name__)

    def scan_providers(self) -> list[str]:
        """Scan environment for all providers with API keys configured.

        Returns:
            List of provider names (lowercase) that have API keys configured.
        """
        providers = []
        for env_key in os.environ:
            if env_key.endswith("_API_KEY") and not env_key.startswith("CUSTOM_"):
                provider_name = env_key[:-8].lower()  # Remove "_API_KEY" suffix
                providers.append(provider_name)
        return providers

    def get_custom_headers(self, provider_prefix: str) -> dict[str, str]:
        """Extract provider-specific custom headers from environment.

        Args:
            provider_prefix: The uppercase provider prefix (e.g., "OPENAI").

        Returns:
            Dictionary of header names to values.
        """
        custom_headers = {}
        provider_prefix = provider_prefix.upper()
        env_vars = dict(os.environ)

        for env_key, env_value in env_vars.items():
            if env_key.startswith(f"{provider_prefix}_CUSTOM_HEADER_"):
                # Convert PROVIDER_CUSTOM_HEADER_KEY to Header-Key
                header_name = env_key[
                    len(provider_prefix) + 15 :
                ]  # Remove 'PROVIDER_CUSTOM_HEADER_' prefix

                if header_name:  # Make sure it's not empty
                    # Convert underscores to hyphens for HTTP header format
                    header_name = header_name.replace("_", "-")
                    custom_headers[header_name] = env_value

        return custom_headers

    def load_toml_config(self, provider_name: str) -> dict[str, Any]:
        """Load provider configuration from TOML files.

        Args:
            provider_name: Name of the provider (e.g., "poe", "openai").

        Returns:
            Provider configuration dictionary from TOML.
        """
        try:
            from src.core.alias_config import AliasConfigLoader

            loader = AliasConfigLoader()
            return loader.get_provider_config(provider_name)
        except ImportError:
            self._logger.debug(f"AliasConfigLoader not available for provider '{provider_name}'")
            return {}
        except Exception as e:
            self._logger.debug(f"Failed to load TOML config for provider '{provider_name}': {e}")
            return {}

    def load_provider(
        self,
        provider_name: str,
        *,
        require_api_key: bool = True,
    ) -> ProviderConfig | None:
        """Load a single provider configuration.

        Args:
            provider_name: The name of the provider (lowercase).
            require_api_key: If True, raises ValueError when API key is missing.
                If False, returns None when API key is missing.

        Returns:
            ProviderConfig if loaded successfully, None if not found and
            require_api_key is False.

        Raises:
            ValueError: If provider is required but not found or misconfigured.
        """
        provider_upper = provider_name.upper()
        toml_config = self.load_toml_config(provider_name)

        # API key from env or TOML
        raw_api_key = os.environ.get(f"{provider_upper}_API_KEY") or toml_config.get("api-key")
        if not raw_api_key:
            if require_api_key:
                raise ValueError(
                    f"API key not found for provider '{provider_name}'. "
                    f"Please set {provider_upper}_API_KEY environment variable."
                )
            return None

        # Support multiple static keys, whitespace-separated
        api_keys = raw_api_key.split()
        if len(api_keys) == 0:
            if require_api_key:
                raise ValueError(
                    f"API key not found for provider '{provider_name}'. "
                    f"Please set {provider_upper}_API_KEY environment variable."
                )
            return None

        if len(api_keys) > 1 and PASSTHROUGH_SENTINEL in api_keys:
            raise ValueError(
                f"Provider '{provider_name}' has mixed configuration: "
                f"'!PASSTHRU' cannot be combined with static keys"
            )

        api_key = api_keys[0]

        # Base URL with precedence: env > TOML > default
        base_url = os.environ.get(f"{provider_upper}_BASE_URL") or toml_config.get("base-url")
        if not base_url:
            # Apply provider-specific defaults for backward compatibility
            if provider_name == "openai":
                base_url = "https://api.openai.com/v1"
            elif require_api_key:
                raise ValueError(
                    f"Base URL not found for provider '{provider_name}'. "
                    f"Please set {provider_upper}_BASE_URL environment variable "
                    f"or configure in vandamme-config.toml"
                )
            else:
                # For optional providers, return None if base URL is missing
                return None

        # API format
        api_format = os.environ.get(
            f"{provider_upper}_API_FORMAT", toml_config.get("api-format", "openai")
        )
        if api_format not in ("openai", "anthropic"):
            api_format = "openai"

        # Other settings
        timeout = int(os.environ.get("REQUEST_TIMEOUT", toml_config.get("timeout", "90")))
        max_retries = int(os.environ.get("MAX_RETRIES", toml_config.get("max-retries", "2")))

        return ProviderConfig(
            name=provider_name,
            api_key=api_key,
            api_keys=api_keys if len(api_keys) > 1 else None,
            base_url=base_url,
            api_version=os.environ.get(f"{provider_upper}_API_VERSION")
            or toml_config.get("api-version"),
            timeout=timeout,
            max_retries=max_retries,
            custom_headers=self.get_custom_headers(provider_upper),
            api_format=api_format,
            tool_name_sanitization=bool(toml_config.get("tool-name-sanitization", False)),
        )

    def load_provider_with_result(self, provider_name: str) -> ProviderLoadResult | None:
        """Load configuration for a specific provider and track the result.

        This is similar to load_provider but returns a ProviderLoadResult
        that can be used for reporting load status.

        Args:
            provider_name: The name of the provider (lowercase).

        Returns:
            ProviderLoadResult if provider was found, None otherwise.
        """
        provider_upper = provider_name.upper()
        toml_config = self.load_toml_config(provider_name)

        raw_api_key = os.environ.get(f"{provider_upper}_API_KEY") or toml_config.get("api-key")
        if not raw_api_key:
            return None

        api_keys = raw_api_key.split()
        if len(api_keys) == 0:
            return None

        if len(api_keys) > 1 and PASSTHROUGH_SENTINEL in api_keys:
            raise ValueError(
                f"Provider '{provider_name}' has mixed configuration: "
                f"'!PASSTHRU' cannot be combined with static keys"
            )

        api_key = api_keys[0]

        base_url = os.environ.get(f"{provider_upper}_BASE_URL") or toml_config.get("base-url")

        if not base_url:
            # Return partial result
            return ProviderLoadResult(
                name=provider_name,
                status="partial",
                message=(
                    f"Missing {provider_upper}_BASE_URL (configure in environment or "
                    "vandamme-config.toml)"
                ),
                api_key_hash=self._get_api_key_hash(api_key),
                base_url=None,
            )

        # Success
        return ProviderLoadResult(
            name=provider_name,
            status="success",
            api_key_hash=self._get_api_key_hash(api_key),
            base_url=base_url,
        )

    @staticmethod
    def _get_api_key_hash(api_key: str) -> str:
        """Return first 8 chars of sha256 hash."""
        import hashlib

        if api_key == PASSTHROUGH_SENTINEL:
            return "PASSTHRU"
        return hashlib.sha256(api_key.encode()).hexdigest()[:8]
