"""Provider management for multi-provider API support.

This module provides the ProviderManager class which manages multiple
OpenAI clients for different providers with automatic failover and
API key rotation.

The ProviderManager implements the ProviderClientFactory protocol for
clean dependency inversion, eliminating circular imports.
"""

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Union

from src.core.client import OpenAIClient
from src.core.protocols import ProviderClientFactory

# Type ignore for local oauth module which doesn't have py.typed marker
try:
    from src.core.oauth.storage import FileSystemAuthStorage  # type: ignore[import-untyped]
    from src.core.oauth.tokens import TokenManager  # type: ignore[import-untyped]
except ImportError:
    TokenManager = None  # type: ignore[assignment, misc]
    FileSystemAuthStorage = None  # type: ignore[assignment, misc]

from src.core.provider_config import (
    OAUTH_SENTINEL,
    PASSTHROUGH_SENTINEL,
    AuthMode,
    ProviderConfig,
)
from src.middleware import MiddlewareChain, ThoughtSignatureMiddleware

if TYPE_CHECKING:
    from src.core.alias_config import AliasConfigLoader
    from src.core.anthropic_client import AnthropicClient
    from src.core.config.middleware import MiddlewareConfig

logger = logging.getLogger(__name__)

# Lazy-loaded singleton for AliasConfigLoader (Phase 5)
_alias_config_loader: "AliasConfigLoader | None" = None


@dataclass
class ProviderLoadResult:
    """Result of loading a provider configuration"""

    name: str
    status: str  # "success", "partial"
    message: str | None = None
    api_key_hash: str | None = None
    base_url: str | None = None


class ProviderManager(ProviderClientFactory):
    """Manages multiple OpenAI clients for different providers.

    The provider manager can be configured with an optional MiddlewareConfig
    to avoid circular dependencies with the global config singleton.

    This class implements the ProviderClientFactory protocol for clean
    dependency inversion.
    """

    def __init__(
        self,
        default_provider: str | None = None,
        default_provider_source: str | None = None,
        middleware_config: "MiddlewareConfig | None" = None,
    ) -> None:
        # Use provided default_provider or fall back to "openai" for backward compatibility
        self._default_provider = default_provider if default_provider is not None else "openai"
        self.default_provider_source = default_provider_source or "system"
        self._clients: dict[str, OpenAIClient | AnthropicClient] = {}
        self._configs: dict[str, ProviderConfig] = {}
        self._loaded = False
        self._load_results: list[ProviderLoadResult] = []

        # Process-global API key rotation state (per provider)
        self._api_key_locks: dict[str, asyncio.Lock] = {}
        self._api_key_indices: dict[str, int] = {}

        # Store middleware config explicitly (dependency injection)
        self._middleware_config = middleware_config

        # Initialize middleware chain
        self.middleware_chain = MiddlewareChain()
        self._middleware_initialized = False

    @property
    def default_provider(self) -> str:
        """Get the default provider name.

        This property is part of the ProviderClientFactory protocol.
        It can be modified internally by _select_default_from_available()
        but appears read-only to external code.
        """
        return self._default_provider

    @staticmethod
    def get_api_key_hash(api_key: str) -> str:
        """Return first 8 chars of sha256 hash"""
        # Special handling for passthrough and OAuth sentinels
        if api_key == PASSTHROUGH_SENTINEL:
            return "PASSTHRU"
        if api_key == OAUTH_SENTINEL:
            return "OAUTH"
        return hashlib.sha256(api_key.encode()).hexdigest()[:8]

    def _select_default_from_available(self) -> None:
        """Select a default provider from available providers if original default is unavailable"""
        if self._default_provider in self._configs:
            return  # Original default is available

        if self._configs:
            # Select the first available provider
            original_default = self._default_provider
            self._default_provider = list(self._configs.keys())[0]

            if self.default_provider_source != "system":
                # User configured a default but it's not available
                logger.info(
                    f"Using '{self._default_provider}' as default provider "
                    f"(configured '{original_default}' not available)"
                )
            else:
                # No user configuration, just pick the first available
                logger.debug(
                    f"Using '{self._default_provider}' as default provider "
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

    # ==================== Phase 1: OAuth Token Manager ====================

    def _create_oauth_token_manager(self, provider_name: str) -> Any | None:
        """Create TokenManager for OAuth providers.

        Args:
            provider_name: Name of the provider (e.g., "chatgpt", "openai")

        Returns:
            TokenManager instance if OAuth dependencies are available, None otherwise.

        Raises:
            ImportError: If oauth dependencies are not installed.
        """
        if TokenManager is None or FileSystemAuthStorage is None:
            raise ImportError(
                "oauth is required for OAuth providers. Please ensure the dependency is installed."
            )
        storage_path = Path.home() / ".vandamme" / "oauth" / provider_name
        storage = FileSystemAuthStorage(base_path=storage_path)
        return TokenManager(storage=storage, raise_on_refresh_failure=False)

    # ==================== Phase 5: AliasConfigLoader Singleton ====================

    def _get_alias_config_loader(self) -> "AliasConfigLoader":
        """Get or create the singleton AliasConfigLoader instance.

        Returns:
            The shared AliasConfigLoader instance.
        """
        global _alias_config_loader
        if _alias_config_loader is None:
            from src.core.alias_config import AliasConfigLoader

            _alias_config_loader = AliasConfigLoader()
        return _alias_config_loader

    # ==================== Phase 4: Provider Name Normalization ====================

    @staticmethod
    def _normalize_provider_name(provider_name: str) -> str:
        """Normalize provider name to lowercase for consistent handling.

        Args:
            provider_name: The provider name to normalize.

        Returns:
            The normalized (lowercase) provider name.
        """
        return provider_name.lower()

    # ==================== Phase 2: Auth Mode Detection Helper ====================

    def _detect_auth_mode(
        self,
        provider_name: str,
        toml_config: dict[str, Any],
    ) -> AuthMode:
        """Detect authentication mode (env var > sentinel > TOML).

        Priority order:
        1. Explicit {PROVIDER}_AUTH_MODE environment variable
        2. Sentinel values in API key (!OAUTH or !PASSTHRU)
        3. TOML configuration auth-mode setting

        Args:
            provider_name: Name of the provider.
            toml_config: Provider configuration from TOML files.

        Returns:
            The detected AuthMode (API_KEY, OAUTH, or PASSTHROUGH).
        """
        provider_upper = provider_name.upper()
        auth_mode = AuthMode.API_KEY

        # 1. Check explicit AUTH_MODE environment variable
        env_auth_mode = os.environ.get(f"{provider_upper}_AUTH_MODE", "").lower()
        if env_auth_mode == "oauth":
            return AuthMode.OAUTH
        elif env_auth_mode == "passthrough":
            return AuthMode.PASSTHROUGH

        # 2. Check for sentinel values in API key
        raw_api_key = os.environ.get(f"{provider_upper}_API_KEY") or toml_config.get("api-key", "")
        if raw_api_key == OAUTH_SENTINEL:
            return AuthMode.OAUTH
        elif raw_api_key == PASSTHROUGH_SENTINEL:
            return AuthMode.PASSTHROUGH

        # 3. Check TOML configuration auth-mode setting
        toml_auth_mode = toml_config.get("auth-mode", "").lower()
        if toml_auth_mode == "oauth":
            return AuthMode.OAUTH
        elif toml_auth_mode == "passthrough":
            return AuthMode.PASSTHROUGH

        return auth_mode

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
        """Initialize and register middleware based on loaded providers.

        Uses injected middleware_config instead of runtime import to avoid
        circular dependency with the global config singleton.
        """
        if self._middleware_initialized:
            return

        # Register thought signature middleware if enabled
        # Use injected config instead of runtime import
        if self._middleware_config and self._middleware_config.gemini_thought_signatures_enabled:
            # Create store with configuration options from injected config
            from src.middleware.thought_signature import ThoughtSignatureStore

            store = ThoughtSignatureStore(
                max_size=self._middleware_config.thought_signature_max_cache_size,
                ttl_seconds=self._middleware_config.thought_signature_cache_ttl,
                cleanup_interval=self._middleware_config.thought_signature_cleanup_interval,
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
        else:
            # Still need to load TOML for auth-mode detection
            toml_config = self._load_provider_toml_config(self.default_provider)

        # Phase 2: Use centralized auth mode detection
        auth_mode = self._detect_auth_mode(self.default_provider, toml_config)

        if not api_key:
            # For OAuth mode, empty API key is allowed
            if auth_mode != AuthMode.OAUTH:
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
            api_key = ""  # OAuth mode uses empty API key

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
            auth_mode=auth_mode,
        )

        self._configs[self.default_provider] = config

    def _load_additional_providers(self) -> None:
        """Load additional provider configurations from environment variables and TOML"""
        # Track which providers we've already attempted to load
        loaded_providers = set()

        # Phase 3: Improved error handling with specific exception types
        # First: Discover providers from TOML configuration
        try:
            loader = self._get_alias_config_loader()
            config = loader.load_config()
            toml_providers = config.get("providers", {})

            for provider_name, provider_config in toml_providers.items():
                # Skip if this is the default provider (already loaded)
                if provider_name == self.default_provider:
                    continue

                # Load provider if:
                # 1. It has OAuth auth-mode (no API key needed)
                # 2. It has an api-key in TOML config
                # 3. It has a PROVIDER_API_KEY env var
                auth_mode = provider_config.get("auth-mode", "").lower()
                has_toml_api_key = bool(provider_config.get("api-key"))
                has_env_api_key = bool(os.environ.get(f"{provider_name.upper()}_API_KEY"))

                if auth_mode in ("oauth", "passthrough") or has_toml_api_key or has_env_api_key:
                    self._load_provider_config_with_result(provider_name)
                    loaded_providers.add(provider_name)
        except ImportError as e:
            logger.warning(
                f"TOML configuration loading not available: {e}. "
                "Only environment variables will be used for provider discovery."
            )
        except OSError as e:
            logger.error(
                f"Cannot read TOML configuration files: {e}. Check file permissions and paths."
            )
        except Exception as e:
            logger.error(
                f"Failed to load TOML configuration: {e}. "
                "Falling back to environment variable scanning."
            )

        # Second: Scan environment for any additional providers (backward compatibility)
        for env_key, _env_value in os.environ.items():
            if env_key.endswith("_API_KEY") and not env_key.startswith("CUSTOM_"):
                # Phase 4: Use normalization helper
                provider_name = self._normalize_provider_name(env_key[:-8])
                # Skip if this is the default provider or already loaded from TOML
                if provider_name == self.default_provider or provider_name in loaded_providers:
                    continue
                self._load_provider_config_with_result(provider_name)

    def _load_provider_toml_config(self, provider_name: str) -> dict[str, Any]:
        """Load provider configuration from TOML files.

        Args:
            provider_name: Name of the provider (e.g., "poe", "openai")

        Returns:
            Provider configuration dictionary from TOML
        """
        # Phase 3: Improved error handling
        # Phase 5: Use singleton AliasConfigLoader
        try:
            loader = self._get_alias_config_loader()
            return loader.get_provider_config(provider_name)
        except ImportError:
            logger.debug(
                f"AliasConfigLoader not available for provider '{provider_name}'. "
                "TOML configuration will be skipped."
            )
            return {}
        except OSError as e:
            logger.warning(f"Cannot read TOML configuration for provider '{provider_name}': {e}")
            return {}
        except Exception as e:
            logger.warning(f"Failed to load TOML config for provider '{provider_name}': {e}")
            return {}

    def _load_provider_config_with_result(self, provider_name: str) -> None:
        """Load configuration for a specific provider and track the result"""
        provider_upper = provider_name.upper()

        # First, try to load from TOML configuration
        toml_config = self._load_provider_toml_config(provider_name)

        # Phase 2: Use centralized auth mode detection
        auth_mode = self._detect_auth_mode(provider_name, toml_config)

        # For OAuth mode, we don't require an API key
        if auth_mode == AuthMode.OAUTH:
            raw_api_key = ""  # OAuth uses tokens, not API keys
        else:
            raw_api_key = os.environ.get(f"{provider_upper}_API_KEY") or toml_config.get(
                "api-key", ""
            )
            if not raw_api_key:
                # Skip entirely if no API key and not OAuth mode
                return

        # Support multiple static keys, whitespace-separated.
        # Example: OPENAI_API_KEY="key1 key2 key3"
        # For OAuth mode, we don't need an API key (tokens are managed separately)
        if auth_mode != AuthMode.OAUTH:
            api_keys = raw_api_key.split()
            if len(api_keys) == 0:
                return
            if len(api_keys) > 1 and PASSTHROUGH_SENTINEL in api_keys:
                raise ValueError(
                    f"Provider '{provider_name}' has mixed configuration: "
                    f"'!PASSTHRU' cannot be combined with static keys"
                )
            api_key = api_keys[0]
        else:
            # OAuth mode: no API key needed, use empty string as placeholder
            api_key = ""
            api_keys = None

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

        # Create the config with auth_mode properly set
        config = ProviderConfig(
            name=provider_name,
            api_key=api_key,
            api_keys=api_keys if api_keys is not None and len(api_keys) > 1 else None,
            base_url=base_url,
            api_version=os.environ.get(f"{provider_upper}_API_VERSION")
            or toml_config.get("api-version"),
            timeout=timeout,
            max_retries=max_retries,
            custom_headers=self._get_provider_custom_headers(provider_upper),
            api_format=api_format,
            tool_name_sanitization=bool(toml_config.get("tool-name-sanitization", False)),
            auth_mode=auth_mode,  # Properly set the auth_mode
        )

        self._configs[provider_name] = config

    def _load_provider_config(self, provider_name: str) -> None:
        """Load configuration for a specific provider (legacy method for default provider)"""
        provider_upper = provider_name.upper()

        # Load from TOML first
        toml_config = self._load_provider_toml_config(provider_name)

        # Phase 2: Use centralized auth mode detection
        auth_mode = self._detect_auth_mode(provider_name, toml_config)

        # For OAuth mode, API key is not required
        if auth_mode != AuthMode.OAUTH:
            # API key is required (from env or TOML)
            raw_api_key = os.environ.get(f"{provider_upper}_API_KEY") or toml_config.get("api-key")
            if not raw_api_key:
                raise ValueError(
                    f"API key not found for provider '{provider_name}'. "
                    f"Please set {provider_upper}_API_KEY environment variable."
                )
        else:
            raw_api_key = ""

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
            auth_mode=auth_mode,  # Phase 2: Add auth_mode to ProviderConfig
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
            # For passthrough or OAuth providers, pass None as API key
            api_key_for_init = (
                None if config.uses_passthrough or config.uses_oauth else config.api_key
            )

            # Phase 1: Create TokenManager for OAuth providers
            oauth_token_manager = None
            if config.uses_oauth:
                oauth_token_manager = self._create_oauth_token_manager(config.name)

            if config.is_anthropic_format:
                # Import here to avoid circular imports
                from src.core.anthropic_client import AnthropicClient

                self._clients[cache_key] = AnthropicClient(
                    api_key=api_key_for_init,
                    base_url=config.base_url,
                    timeout=config.timeout,
                    custom_headers=config.custom_headers,
                    oauth_token_manager=oauth_token_manager,  # Phase 1: Add OAuth support
                )
            else:
                self._clients[cache_key] = OpenAIClient(
                    api_key=api_key_for_init,
                    base_url=config.base_url,
                    timeout=config.timeout,
                    api_version=config.api_version,
                    custom_headers=config.custom_headers,
                    oauth_token_manager=oauth_token_manager,  # Phase 1: Add OAuth support
                )

        return self._clients[cache_key]

    async def get_next_provider_api_key(self, provider_name: str) -> str:
        """Return the next provider API key using process-global round-robin.

        Only valid for providers configured with static keys (not passthrough, not OAuth).
        """
        if not self._loaded:
            self.load_provider_configs()

        config = self._configs.get(provider_name)
        if config is None:
            raise ValueError(f"Provider '{provider_name}' not configured")
        if config.uses_passthrough or config.uses_oauth:
            raise ValueError(
                f"Provider '{provider_name}' uses {config.auth_mode} "
                f"authentication and has no static keys"
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

            # Check if this provider uses OAuth authentication
            provider_config = self._configs.get(result.name)
            is_oauth = provider_config and provider_config.uses_oauth
            oauth_indicator = "  🔐" if is_oauth else ""

            if result.status == "success":
                if is_default:
                    # Build format string for default provider (with color)
                    format_str = (
                        f"   ✅ {result.api_key_hash:<10}{default_indicator}"
                        f"\033[92m{result.name:<12}\033[0m {result.base_url}{oauth_indicator}"
                    )
                    print(format_str)
                else:
                    # Build format string for other providers
                    format_str = (
                        f"   ✅ {result.api_key_hash:<10}{default_indicator}"
                        f"{result.name:<12} {result.base_url}{oauth_indicator}"
                    )
                    print(format_str)
                success_count += 1
            else:  # partial
                if is_default:
                    # Build format string for partial default provider
                    format_str = (
                        f"   ⚠️ {result.api_key_hash:<10}{default_indicator}"
                        f"\033[92m{result.name:<12}\033[0m {result.message}{oauth_indicator}"
                    )
                    print(format_str)
                else:
                    # Build format string for partial other providers
                    format_str = (
                        f"   ⚠️ {result.api_key_hash:<10}{default_indicator}"
                        f"{result.name:<12} {result.message}{oauth_indicator}"
                    )
                    print(format_str)

        print(f"\n{success_count} provider{'s' if success_count != 1 else ''} ready for requests")
        print("  * = default provider")
        print("  🔐 = OAuth authentication")

    def get_load_results(self) -> list[ProviderLoadResult]:
        """Get the load results for all providers"""
        if not self._loaded:
            self.load_provider_configs()
        return self._load_results.copy()
