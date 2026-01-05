import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Union

from src.core.client import OpenAIClient
from src.core.provider_config import PASSTHROUGH_SENTINEL, ProviderConfig
from src.middleware import MiddlewareChain, ThoughtSignatureMiddleware

if TYPE_CHECKING:
    from src.core.anthropic_client import AnthropicClient

logger = logging.getLogger(__name__)


@dataclass
class ProviderLoadResult:
    """Result of loading a provider configuration"""

    name: str
    status: str  # "success", "partial"
    message: str | None = None
    api_key_hash: str | None = None
    base_url: str | None = None


class ProviderManager:
    """Manages multiple OpenAI clients for different providers"""

    def __init__(
        self, default_provider: str | None = None, default_provider_source: str | None = None
    ) -> None:
        # Use provided default_provider or fall back to "openai" for backward compatibility
        self.default_provider = default_provider if default_provider is not None else "openai"
        self.default_provider_source = default_provider_source or "system"
        self._clients: dict[str, OpenAIClient | AnthropicClient] = {}
        self._configs: dict[str, ProviderConfig] = {}
        self._loaded = False
        self._load_results: list[ProviderLoadResult] = []

        # Process-global API key rotation state (per provider)
        self._api_key_locks: dict[str, asyncio.Lock] = {}
        self._api_key_indices: dict[str, int] = {}

        # Initialize middleware chain
        self.middleware_chain = MiddlewareChain()
        self._middleware_initialized = False

    @staticmethod
    def get_api_key_hash(api_key: str) -> str:
        """Return first 8 chars of sha256 hash"""
        # Special handling for passthrough sentinel
        if api_key == PASSTHROUGH_SENTINEL:
            return "PASSTHRU"
        return hashlib.sha256(api_key.encode()).hexdigest()[:8]

    def _select_default_from_available(self) -> None:
        """Select a default provider from available providers if original default is unavailable"""
        if self.default_provider in self._configs:
            return  # Original default is available

        if self._configs:
            # Select the first available provider
            original_default = self.default_provider
            self.default_provider = list(self._configs.keys())[0]

            if self.default_provider_source != "system":
                # User configured a default but it's not available
                logger.info(
                    f"Using '{self.default_provider}' as default provider "
                    f"(configured '{original_default}' not available)"
                )
            else:
                # No user configuration, just pick the first available
                logger.debug(
                    f"Using '{self.default_provider}' as default provider "
                    f"(first available provider)"
                )
        else:
            # No providers available at all
            provider_upper = self.default_provider.upper()
            raise ValueError(
                f"No providers configured. Please set at least one provider API key "
                f"(e.g., {provider_upper}_API_KEY).\n"
                f"Hint: If {provider_upper}_API_KEY is set in your shell, make sure to export it: "
                f"'export {provider_upper}_API_KEY'"
            )

    def load_provider_configs(self) -> None:
        """Load all provider configurations from environment variables"""
        if self._loaded:
            return

        # Reset load results
        self._load_results = []

        # Load default provider (if API key is available)
        self._load_default_provider()

        # Load additional providers from environment
        self._load_additional_providers()

        # Select a default provider from available ones if needed
        self._select_default_from_available()

        self._loaded = True

        # Initialize middleware after loading providers
        self._initialize_middleware()

    def _initialize_middleware(self) -> None:
        """Initialize and register middleware based on loaded providers"""
        if self._middleware_initialized:
            return

        # Register thought signature middleware if enabled
        # The middleware will decide which requests to handle based on model names
        from src.core.config import config as app_config

        if app_config.gemini_thought_signatures_enabled:
            # Create store with configuration options
            from src.middleware.thought_signature import ThoughtSignatureStore

            store = ThoughtSignatureStore(
                max_size=app_config.thought_signature_max_cache_size,
                ttl_seconds=app_config.thought_signature_cache_ttl,
                cleanup_interval=app_config.thought_signature_cleanup_interval,
            )
            self.middleware_chain.add(ThoughtSignatureMiddleware(store=store))

        self._middleware_initialized = True

    async def initialize_middleware(self) -> None:
        """Asynchronously initialize the middleware chain"""
        if not self._middleware_initialized:
            self._initialize_middleware()
        await self.middleware_chain.initialize()

    async def cleanup_middleware(self) -> None:
        """Cleanup middleware resources"""
        await self.middleware_chain.cleanup()

    def _load_default_provider(self) -> None:
        """Load the default provider configuration"""
        # Load provider configuration based on default_provider name
        provider_prefix = f"{self.default_provider.upper()}_"
        api_key = os.environ.get(f"{provider_prefix}API_KEY")
        base_url = os.environ.get(f"{provider_prefix}BASE_URL")
        api_version = os.environ.get(f"{provider_prefix}API_VERSION")

        # Apply provider-specific defaults
        if not base_url:
            # Check TOML configuration first
            toml_config = self._load_provider_toml_config(self.default_provider)
            base_url = toml_config.get("base-url")
            # Final fallback to hardcoded default
            if not base_url:
                base_url = "https://api.openai.com/v1"

        if not api_key:
            # Only warn if this was explicitly configured by the user
            if self.default_provider_source != "system":
                logger.warning(
                    f"Configured default provider '{self.default_provider}' API key not found. "
                    f"Set {provider_prefix}API_KEY to use it as default. "
                    "Will use another provider if available."
                )
            else:
                # This is just a system default, no warning needed
                logger.debug(
                    f"System default provider '{self.default_provider}' not configured. "
                    "Will use another provider if available."
                )
            # Don't create a config for the default provider if no API key
            return

        # Support multiple static keys, whitespace-separated.
        api_keys = api_key.split()
        if len(api_keys) == 0:
            return
        if len(api_keys) > 1 and PASSTHROUGH_SENTINEL in api_keys:
            raise ValueError(
                f"Provider '{self.default_provider}' has mixed configuration: "
                f"'!PASSTHRU' cannot be combined with static keys"
            )

        config = ProviderConfig(
            name=self.default_provider,
            api_key=api_keys[0],
            api_keys=api_keys if len(api_keys) > 1 else None,
            base_url=base_url,
            api_version=api_version,
            timeout=int(os.environ.get("REQUEST_TIMEOUT", "90")),
            max_retries=int(os.environ.get("MAX_RETRIES", "2")),
            custom_headers=self._get_provider_custom_headers(self.default_provider.upper()),
            tool_name_sanitization=bool(
                self._load_provider_toml_config(self.default_provider).get(
                    "tool-name-sanitization", False
                )
            ),
        )

        self._configs[self.default_provider] = config

    def _load_additional_providers(self) -> None:
        """Load additional provider configurations from environment variables"""
        # Scan for all provider environment variables
        for env_key, _env_value in os.environ.items():
            # Look for PROVIDER_API_KEY pattern
            if env_key.endswith("_API_KEY") and not env_key.startswith("CUSTOM_"):
                # Extract provider name (everything before _API_KEY)
                provider_name = env_key[:-8].lower()  # Remove "_API_KEY" suffix

                # Skip if this is the default provider we already loaded
                if provider_name == self.default_provider:
                    continue

                # Load provider configuration
                self._load_provider_config_with_result(provider_name)

    def _load_provider_toml_config(self, provider_name: str) -> dict[str, Any]:
        """Load provider configuration from TOML files.

        Args:
            provider_name: Name of the provider (e.g., "poe", "openai")

        Returns:
            Provider configuration dictionary from TOML
        """
        try:
            from src.core.alias_config import AliasConfigLoader

            loader = AliasConfigLoader()
            return loader.get_provider_config(provider_name)
        except ImportError:
            logger.debug(f"AliasConfigLoader not available for provider '{provider_name}'")
            return {}
        except Exception as e:
            logger.debug(f"Failed to load TOML config for provider '{provider_name}': {e}")
            return {}

    def _load_provider_config_with_result(self, provider_name: str) -> None:
        """Load configuration for a specific provider and track the result"""
        provider_upper = provider_name.upper()

        # First, try to load from TOML configuration
        toml_config = self._load_provider_toml_config(provider_name)

        # Then override with environment variables
        raw_api_key = os.environ.get(f"{provider_upper}_API_KEY") or toml_config.get("api-key")
        if not raw_api_key:
            # Skip entirely if no API key in either source
            return

        # Support multiple static keys, whitespace-separated.
        # Example: OPENAI_API_KEY="key1 key2 key3"
        api_keys = raw_api_key.split()
        if len(api_keys) == 0:
            return
        if len(api_keys) > 1 and PASSTHROUGH_SENTINEL in api_keys:
            raise ValueError(
                f"Provider '{provider_name}' has mixed configuration: "
                f"'!PASSTHRU' cannot be combined with static keys"
            )
        api_key = api_keys[0]

        # Load base URL with precedence: env > TOML > default
        base_url = os.environ.get(f"{provider_upper}_BASE_URL") or toml_config.get("base-url")
        if not base_url:
            # Create result for partial configuration (missing base URL)
            result = ProviderLoadResult(
                name=provider_name,
                status="partial",
                message=(
                    f"Missing {provider_upper}_BASE_URL (configure in environment or "
                    "vandamme-config.toml)"
                ),
                api_key_hash=self.get_api_key_hash(api_key),
                base_url=None,
            )
            self._load_results.append(result)
            return

        # Load other settings with precedence: env > TOML > defaults
        api_format = os.environ.get(
            f"{provider_upper}_API_FORMAT", toml_config.get("api-format", "openai")
        )
        if api_format not in ["openai", "anthropic"]:
            api_format = "openai"  # Default to openai if invalid

        timeout = int(os.environ.get("REQUEST_TIMEOUT", toml_config.get("timeout", "90")))
        max_retries = int(os.environ.get("MAX_RETRIES", toml_config.get("max-retries", "2")))

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
            api_keys=api_keys if len(api_keys) > 1 else None,
            base_url=base_url,
            api_version=os.environ.get(f"{provider_upper}_API_VERSION")
            or toml_config.get("api-version"),
            timeout=timeout,
            max_retries=max_retries,
            custom_headers=self._get_provider_custom_headers(provider_upper),
            api_format=api_format,
            tool_name_sanitization=bool(toml_config.get("tool-name-sanitization", False)),
        )

        self._configs[provider_name] = config

    def _load_provider_config(self, provider_name: str) -> None:
        """Load configuration for a specific provider (legacy method for default provider)"""
        provider_upper = provider_name.upper()

        # Load from TOML first
        toml_config = self._load_provider_toml_config(provider_name)

        # API key is required (from env or TOML)
        raw_api_key = os.environ.get(f"{provider_upper}_API_KEY") or toml_config.get("api-key")
        if not raw_api_key:
            raise ValueError(
                f"API key not found for provider '{provider_name}'. "
                f"Please set {provider_upper}_API_KEY environment variable."
            )

        api_keys = raw_api_key.split()
        if len(api_keys) == 0:
            raise ValueError(
                f"API key not found for provider '{provider_name}'. "
                f"Please set {provider_upper}_API_KEY environment variable."
            )
        if len(api_keys) > 1 and PASSTHROUGH_SENTINEL in api_keys:
            raise ValueError(
                f"Provider '{provider_name}' has mixed configuration: "
                f"'!PASSTHRU' cannot be combined with static keys"
            )
        api_key = api_keys[0]

        # Base URL with precedence: env > TOML > default
        base_url = os.environ.get(f"{provider_upper}_BASE_URL") or toml_config.get("base-url")
        if not base_url:
            raise ValueError(
                f"Base URL not found for provider '{provider_name}'. "
                f"Please set {provider_upper}_BASE_URL environment variable "
                f"or configure in vandamme-config.toml"
            )

        # Load other settings with precedence: env > TOML > defaults
        api_format = os.environ.get(
            f"{provider_upper}_API_FORMAT", toml_config.get("api-format", "openai")
        )
        if api_format not in ["openai", "anthropic"]:
            api_format = "openai"  # Default to openai if invalid

        timeout = int(os.environ.get("REQUEST_TIMEOUT", toml_config.get("timeout", "90")))
        max_retries = int(os.environ.get("MAX_RETRIES", toml_config.get("max-retries", "2")))

        config = ProviderConfig(
            name=provider_name,
            api_key=api_key,
            api_keys=api_keys if len(api_keys) > 1 else None,
            base_url=base_url,
            api_version=os.environ.get(f"{provider_upper}_API_VERSION")
            or toml_config.get("api-version"),
            timeout=timeout,
            max_retries=max_retries,
            custom_headers=self._get_provider_custom_headers(provider_upper),
            api_format=api_format,
            tool_name_sanitization=bool(toml_config.get("tool-name-sanitization", False)),
        )

        self._configs[provider_name] = config

    def _get_provider_custom_headers(self, provider_prefix: str) -> dict[str, str]:
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

    def parse_model_name(self, model: str) -> tuple[str, str]:
        """Parse 'provider:model' into (provider, model)

        Returns:
            Tuple[str, str]: (provider_name, actual_model_name)
        """
        if ":" in model:
            provider, actual_model = model.split(":", 1)
            return provider.lower(), actual_model
        return self.default_provider, model

    def get_client(
        self,
        provider_name: str,
        client_api_key: str | None = None,  # Client's API key for passthrough
    ) -> Union[OpenAIClient, "AnthropicClient"]:
        """Get or create a client for the specified provider"""
        if not self._loaded:
            self.load_provider_configs()

        # Ensure middleware is initialized when clients are accessed
        # Note: We can't await here, so we do sync initialization
        # The full async initialization should be called during app startup
        if not self._middleware_initialized:
            self._initialize_middleware()

        # Check if provider exists
        if provider_name not in self._configs:
            raise ValueError(
                f"Provider '{provider_name}' not configured. "
                f"Available providers: {list(self._configs.keys())}"
            )

        config = self._configs[provider_name]

        # For passthrough providers, we cache clients without API keys
        # The actual API key will be provided per request
        cache_key = provider_name

        # Return cached client or create new one
        if cache_key not in self._clients:
            # Create appropriate client based on API format
            # For passthrough providers, pass None as API key
            api_key_for_init = None if config.uses_passthrough else config.api_key

            if config.is_anthropic_format:
                # Import here to avoid circular imports
                from src.core.anthropic_client import AnthropicClient

                self._clients[cache_key] = AnthropicClient(
                    api_key=api_key_for_init,
                    base_url=config.base_url,
                    timeout=config.timeout,
                    custom_headers=config.custom_headers,
                )
            else:
                self._clients[cache_key] = OpenAIClient(
                    api_key=api_key_for_init,
                    base_url=config.base_url,
                    timeout=config.timeout,
                    api_version=config.api_version,
                    custom_headers=config.custom_headers,
                )

        return self._clients[cache_key]

    async def get_next_provider_api_key(self, provider_name: str) -> str:
        """Return the next provider API key using process-global round-robin.

        Only valid for providers configured with static keys (not passthrough).
        """
        if not self._loaded:
            self.load_provider_configs()

        config = self._configs.get(provider_name)
        if config is None:
            raise ValueError(f"Provider '{provider_name}' not configured")
        if config.uses_passthrough:
            raise ValueError(
                f"Provider '{provider_name}' is configured for passthrough and has no static keys"
            )

        keys = config.get_api_keys()
        lock = self._api_key_locks.setdefault(provider_name, asyncio.Lock())
        async with lock:
            idx = self._api_key_indices.get(provider_name, 0)
            key = keys[idx % len(keys)]
            self._api_key_indices[provider_name] = (idx + 1) % len(keys)
            return key

    def get_provider_config(self, provider_name: str) -> ProviderConfig | None:
        """Get configuration for a specific provider"""
        if not self._loaded:
            self.load_provider_configs()
        return self._configs.get(provider_name)

    def list_providers(self) -> dict[str, ProviderConfig]:
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
        print(f"   {'-' * 2} {'-' * 10} {'-' * 12} {'-' * 50}")

        success_count = 0

        for result in all_results:
            # Check if this is the default provider
            is_default = result.name == self.default_provider
            default_indicator = "  * " if is_default else "    "

            if result.status == "success":
                if is_default:
                    # Build format string for default provider (with color)
                    format_str = (
                        f"   ✅ {result.api_key_hash:<10}{default_indicator}"
                        f"\033[92m{result.name:<12}\033[0m {result.base_url}"
                    )
                    print(format_str)
                else:
                    # Build format string for other providers
                    format_str = (
                        f"   ✅ {result.api_key_hash:<10}{default_indicator}"
                        f"{result.name:<12} {result.base_url}"
                    )
                    print(format_str)
                success_count += 1
            else:  # partial
                if is_default:
                    # Build format string for partial default provider
                    format_str = (
                        f"   ⚠️ {result.api_key_hash:<10}{default_indicator}"
                        f"\033[92m{result.name:<12}\033[0m {result.message}"
                    )
                    print(format_str)
                else:
                    # Build format string for partial other providers
                    format_str = (
                        f"   ⚠️ {result.api_key_hash:<10}{default_indicator}"
                        f"{result.name:<12} {result.message}"
                    )
                    print(format_str)

        print(f"\n{success_count} provider{'s' if success_count != 1 else ''} ready for requests")
        print("  * = default provider")

    def get_load_results(self) -> list[ProviderLoadResult]:
        """Get the load results for all providers"""
        if not self._loaded:
            self.load_provider_configs()
        return self._load_results.copy()
