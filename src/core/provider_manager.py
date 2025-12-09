import os
from typing import Dict, Optional, Tuple

from src.core.client import OpenAIClient
from src.core.provider_config import ProviderConfig


class ProviderManager:
    """Manages multiple OpenAI clients for different providers"""

    def __init__(self, default_provider: str = "openai") -> None:
        self.default_provider = default_provider
        self._clients: Dict[str, OpenAIClient] = {}
        self._configs: Dict[str, ProviderConfig] = {}
        self._loaded = False

    def load_provider_configs(self) -> None:
        """Load all provider configurations from environment variables"""
        if self._loaded:
            return

        # Load default provider (OpenAI)
        self._load_default_provider()

        # Load additional providers from environment
        self._load_additional_providers()

        self._loaded = True

    def _load_default_provider(self) -> None:
        """Load the default provider configuration"""
        # For backward compatibility, we support both OPENAI_* and DEFAULT_PROVIDER_*
        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        api_version = os.environ.get("AZURE_API_VERSION")

        if self.default_provider != "openai":
            # Try to load from VDM_DEFAULT_PROVIDER_*
            provider_prefix = f"{self.default_provider.upper()}_"
            api_key = os.environ.get(f"{provider_prefix}API_KEY")
            base_url = os.environ.get(f"{provider_prefix}BASE_URL", "https://api.openai.com/v1")
            api_version = os.environ.get(f"{provider_prefix}API_VERSION")

        if not api_key:
            raise ValueError(f"API key not found for default provider '{self.default_provider}'")

        config = ProviderConfig(
            name=self.default_provider,
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
            api_version=api_version,
            timeout=int(os.environ.get("REQUEST_TIMEOUT", "90")),
            max_retries=int(os.environ.get("MAX_RETRIES", "2")),
            custom_headers=self._get_provider_custom_headers(self.default_provider.upper()),
        )

        self._configs[self.default_provider] = config

    def _load_additional_providers(self) -> None:
        """Load additional provider configurations from environment variables"""
        # Scan for all provider environment variables
        for env_key, env_value in os.environ.items():
            # Look for PROVIDER_API_KEY pattern
            if env_key.endswith("_API_KEY") and not env_key.startswith(("OPENAI_", "CUSTOM_")):
                # Extract provider name (everything before _API_KEY)
                provider_name = env_key[:-8].lower()  # Remove "_API_KEY" suffix

                # Skip if this is the default provider we already loaded
                if provider_name == self.default_provider:
                    continue

                # Load provider configuration
                try:
                    self._load_provider_config(provider_name)
                except ValueError as e:
                    # Log warning but continue loading other providers
                    import sys

                    print(
                        f"Warning: Failed to load provider '{provider_name}': {e}", file=sys.stderr
                    )
                    continue

    def _load_provider_config(self, provider_name: str) -> None:
        """Load configuration for a specific provider"""
        provider_upper = provider_name.upper()

        api_key = os.environ.get(f"{provider_upper}_API_KEY")
        if not api_key:
            raise ValueError(
                f"API key not found for provider '{provider_name}'. Please set {provider_upper}_API_KEY environment variable."
            )

        base_url = os.environ.get(f"{provider_upper}_BASE_URL")
        if not base_url:
            raise ValueError(
                f"Base URL not found for provider '{provider_name}'. Please set {provider_upper}_BASE_URL environment variable."
            )

        config = ProviderConfig(
            name=provider_name,
            api_key=api_key,
            base_url=base_url,
            api_version=os.environ.get(f"{provider_upper}_API_VERSION"),
            timeout=int(os.environ.get("REQUEST_TIMEOUT", "90")),
            max_retries=int(os.environ.get("MAX_RETRIES", "2")),
            custom_headers=self._get_provider_custom_headers(provider_upper),
        )

        self._configs[provider_name] = config

    def _get_provider_custom_headers(self, provider_prefix: str) -> Dict[str, str]:
        """Get custom headers for a specific provider"""
        custom_headers = {}
        provider_prefix = provider_prefix.upper()

        # Get all environment variables
        env_vars = dict(os.environ)

        # Find provider-specific CUSTOM_HEADER_* environment variables
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

    def parse_model_name(self, model: str) -> Tuple[str, str]:
        """Parse 'provider:model' into (provider, model)

        Returns:
            Tuple[str, str]: (provider_name, actual_model_name)
        """
        if ":" in model:
            provider, actual_model = model.split(":", 1)
            return provider.lower(), actual_model
        return self.default_provider, model

    def get_client(self, provider_name: str) -> OpenAIClient:
        """Get or create a client for the specified provider"""
        if not self._loaded:
            self.load_provider_configs()

        # Check if provider exists
        if provider_name not in self._configs:
            raise ValueError(
                f"Provider '{provider_name}' not configured. "
                f"Available providers: {list(self._configs.keys())}"
            )

        # Return cached client or create new one
        if provider_name not in self._clients:
            config = self._configs[provider_name]
            self._clients[provider_name] = OpenAIClient(
                api_key=config.api_key,
                base_url=config.base_url,
                timeout=config.timeout,
                api_version=config.api_version,
                custom_headers=config.custom_headers,
            )

        return self._clients[provider_name]

    def get_provider_config(self, provider_name: str) -> Optional[ProviderConfig]:
        """Get configuration for a specific provider"""
        if not self._loaded:
            self.load_provider_configs()
        return self._configs.get(provider_name)

    def list_providers(self) -> Dict[str, ProviderConfig]:
        """List all configured providers"""
        if not self._loaded:
            self.load_provider_configs()
        return self._configs.copy()
