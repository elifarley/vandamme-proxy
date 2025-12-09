import hashlib
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.core.client import OpenAIClient
from src.core.provider_config import ProviderConfig


@dataclass
class ProviderLoadResult:
    """Result of loading a provider configuration"""

    name: str
    status: str  # "success", "partial"
    message: Optional[str] = None
    api_key_hash: Optional[str] = None
    base_url: Optional[str] = None


class ProviderManager:
    """Manages multiple OpenAI clients for different providers"""

    def __init__(self, default_provider: str = "openai") -> None:
        self.default_provider = default_provider
        self._clients: Dict[str, OpenAIClient] = {}
        self._configs: Dict[str, ProviderConfig] = {}
        self._loaded = False
        self._load_results: List[ProviderLoadResult] = []

    @staticmethod
    def get_api_key_hash(api_key: str) -> str:
        """Return first 8 chars of sha256 hash"""
        return hashlib.sha256(api_key.encode()).hexdigest()[:8]

    @staticmethod
    def get_default_base_url(provider_name: str) -> Optional[str]:
        """Return default base URL for special providers"""
        defaults = {
            "openai": "https://api.openai.com/v1",
            "poe": "https://api.poe.com/v1",
        }
        return defaults.get(provider_name.lower())

    def load_provider_configs(self) -> None:
        """Load all provider configurations from environment variables"""
        if self._loaded:
            return

        # Reset load results
        self._load_results = []

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
                self._load_provider_config_with_result(provider_name)

    def _load_provider_config_with_result(self, provider_name: str) -> None:
        """Load configuration for a specific provider and track the result"""
        provider_upper = provider_name.upper()

        api_key = os.environ.get(f"{provider_upper}_API_KEY")
        if not api_key:
            # Skip entirely if no API key - don't even track it
            return

        # Check if we have a base URL or can use a default
        base_url = os.environ.get(f"{provider_upper}_BASE_URL")
        if not base_url:
            base_url = self.get_default_base_url(provider_name)
            if not base_url:
                # Create result for partial configuration (missing base URL)
                result = ProviderLoadResult(
                    name=provider_name,
                    status="partial",
                    message=f"Missing {provider_upper}_BASE_URL",
                    api_key_hash=self.get_api_key_hash(api_key),
                    base_url=None,
                )
                self._load_results.append(result)
                return

        # Load API format (default to "openai")
        api_format = os.environ.get(f"{provider_upper}_API_FORMAT", "openai")
        if api_format not in ["openai", "anthropic"]:
            api_format = "openai"  # Default to openai if invalid

        # Create result for successful configuration
        result = ProviderLoadResult(
            name=provider_name,
            status="success",
            api_key_hash=self.get_api_key_hash(api_key),
            base_url=base_url,
        )
        self._load_results.append(result)

        # Create the config
        config = ProviderConfig(
            name=provider_name,
            api_key=api_key,
            base_url=base_url,
            api_version=os.environ.get(f"{provider_upper}_API_VERSION"),
            timeout=int(os.environ.get("REQUEST_TIMEOUT", "90")),
            max_retries=int(os.environ.get("MAX_RETRIES", "2")),
            custom_headers=self._get_provider_custom_headers(provider_upper),
            api_format=api_format,
        )

        self._configs[provider_name] = config

    def _load_provider_config(self, provider_name: str) -> None:
        """Load configuration for a specific provider (legacy method for default provider)"""
        provider_upper = provider_name.upper()

        api_key = os.environ.get(f"{provider_upper}_API_KEY")
        if not api_key:
            raise ValueError(
                f"API key not found for provider '{provider_name}'. Please set {provider_upper}_API_KEY environment variable."
            )

        base_url = os.environ.get(f"{provider_upper}_BASE_URL")
        if not base_url:
            # For default provider, also try defaults
            base_url = self.get_default_base_url(provider_name)
            if not base_url:
                raise ValueError(
                    f"Base URL not found for provider '{provider_name}'. Please set {provider_upper}_BASE_URL environment variable."
                )

        # Load API format (default to "openai")
        api_format = os.environ.get(f"{provider_upper}_API_FORMAT", "openai")
        if api_format not in ["openai", "anthropic"]:
            api_format = "openai"  # Default to openai if invalid

        config = ProviderConfig(
            name=provider_name,
            api_key=api_key,
            base_url=base_url,
            api_version=os.environ.get(f"{provider_upper}_API_VERSION"),
            timeout=int(os.environ.get("REQUEST_TIMEOUT", "90")),
            max_retries=int(os.environ.get("MAX_RETRIES", "2")),
            custom_headers=self._get_provider_custom_headers(provider_upper),
            api_format=api_format,
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

    def get_client(self, provider_name: str):
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

            # Create appropriate client based on API format
            if config.is_anthropic_format:
                # Import here to avoid circular imports
                from src.core.anthropic_client import AnthropicClient
                self._clients[provider_name] = AnthropicClient(
                    api_key=config.api_key,
                    base_url=config.base_url,
                    timeout=config.timeout,
                    custom_headers=config.custom_headers,
                )
            else:
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

    def print_provider_summary(self) -> None:
        """Print a summary of loaded providers"""
        if not self._loaded:
            self.load_provider_configs()

        # Always show the default provider, whether in _load_results or not
        all_results = self._load_results.copy()

        # Check if default provider is already in results
        default_in_results = any(r.name == self.default_provider for r in all_results)

        # If not, add it from _configs
        if not default_in_results and self.default_provider in self._configs:
            default_config = self._configs[self.default_provider]
            default_result = ProviderLoadResult(
                name=self.default_provider,
                status="success",
                api_key_hash=self.get_api_key_hash(default_config.api_key),
                base_url=default_config.base_url,
            )
            all_results.insert(0, default_result)  # Insert at beginning

        if not all_results:
            return

        print("\n📊 Active Providers:")
        print(f"   {'Status':<2} {'SHA256':<10} {'Name':<12} Base URL")
        print(f"   {'-'*2} {'-'*10} {'-'*12} {'-'*50}")

        success_count = 0

        for result in all_results:
            # Check if this is the default provider
            is_default = result.name == self.default_provider
            default_indicator = "  * " if is_default else "    "

            if result.status == "success":
                if is_default:
                    print(
                        f"   ✅ {result.api_key_hash:<10}{default_indicator}\033[92m{result.name:<12}\033[0m {result.base_url}"
                    )
                else:
                    print(
                        f"   ✅ {result.api_key_hash:<10}{default_indicator}{result.name:<12} {result.base_url}"
                    )
                success_count += 1
            else:  # partial
                if is_default:
                    print(
                        f"   ⚠️ {result.api_key_hash:<10}{default_indicator}\033[92m{result.name:<12}\033[0m {result.message}"
                    )
                else:
                    print(
                        f"   ⚠️ {result.api_key_hash:<10}{default_indicator}{result.name:<12} {result.message}"
                    )

        print(f"\n{success_count} provider{'s' if success_count != 1 else ''} ready for requests")
        print(f"  * = default provider")

    def get_load_results(self) -> List[ProviderLoadResult]:
        """Get the load results for all providers"""
        if not self._loaded:
            self.load_provider_configs()
        return self._load_results.copy()
