import hashlib
import logging
import os
import sys
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.core.alias_manager import AliasManager
    from src.core.provider_manager import ProviderManager


# Configuration
class Config:
    def __init__(self) -> None:
        # First, check if default provider is set via environment variable
        env_default_provider = os.environ.get("VDM_DEFAULT_PROVIDER")

        if env_default_provider:
            self.default_provider = env_default_provider
            self.default_provider_source = "env"
            logger.debug(f"Using default provider from environment: {self.default_provider}")
        else:
            # Try to load from TOML configuration
            try:
                from src.core.alias_config import AliasConfigLoader

                loader = AliasConfigLoader()
                defaults = loader.get_defaults()
                toml_default = defaults.get("default-provider")
                if toml_default:
                    self.default_provider = toml_default
                    self.default_provider_source = "toml"
                    logger.debug(
                        f"Using default provider from configuration: {self.default_provider}"
                    )
                else:
                    self.default_provider = "openai"
                    self.default_provider_source = "system"
                    logger.debug(f"Using system default provider: {self.default_provider}")
            except Exception as e:
                logger.debug(f"Failed to load default provider from config: {e}")
                self.default_provider = "openai"
                self.default_provider_source = "system"
                logger.debug(f"Using system default provider: {self.default_provider}")

        # Get API key for the default provider
        provider_upper = self.default_provider.upper()
        api_key_env_var = f"{provider_upper}_API_KEY"
        self.openai_api_key = os.environ.get(api_key_env_var)

        if not self.openai_api_key and self.default_provider_source != "system":
            # Only warn about missing API key if the provider was explicitly configured
            warning_msg = (
                f"Warning: {api_key_env_var} not found in environment variables. "
                f"{self.default_provider} provider will not be available."
            )
            print(warning_msg)
            # Don't raise error - allow server to start for testing

        # Add Anthropic API key for client validation
        self.proxy_api_key = os.environ.get("PROXY_API_KEY")
        if not self.proxy_api_key:
            print("Warning: PROXY_API_KEY not set. Client API key validation will be disabled.")

        # Get base URL for the default provider
        provider_upper = self.default_provider.upper()
        base_url_env_var = f"{provider_upper}_BASE_URL"
        # Use provider-specific default if not set
        if provider_upper == "OPENAI":
            default_base_url = "https://api.openai.com/v1"
        elif provider_upper == "POE":
            default_base_url = "https://api.poe.com/v1"
        else:
            default_base_url = "https://api.openai.com/v1"  # Fallback

        self.base_url = os.environ.get(base_url_env_var, default_base_url)
        self.azure_api_version = os.environ.get("AZURE_API_VERSION")  # For Azure OpenAI
        self.host = os.environ.get("HOST", "0.0.0.0")
        self.port = int(os.environ.get("PORT", "8082"))
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")
        self.max_tokens_limit = int(os.environ.get("MAX_TOKENS_LIMIT", "4096"))
        self.min_tokens_limit = int(os.environ.get("MIN_TOKENS_LIMIT", "100"))

        # Connection settings
        self.request_timeout = int(os.environ.get("REQUEST_TIMEOUT", "90"))
        self.max_retries = int(os.environ.get("MAX_RETRIES", "2"))

        # Thought signature middleware settings
        self.gemini_thought_signatures_enabled = (
            os.environ.get("GEMINI_THOUGHT_SIGNATURES_ENABLED", "true").lower() == "true"
        )
        self.thought_signature_cache_ttl = float(
            os.environ.get("THOUGHT_SIGNATURE_CACHE_TTL", "3600")
        )  # 1 hour
        self.thought_signature_max_cache_size = int(
            os.environ.get("THOUGHT_SIGNATURE_MAX_CACHE_SIZE", "1000")
        )
        self.thought_signature_cleanup_interval = float(
            os.environ.get("THOUGHT_SIGNATURE_CLEANUP_INTERVAL", "300")
        )  # 5 minutes

        # Provider manager will be initialized lazily
        self._provider_manager: ProviderManager | None = None

        # Alias manager will be initialized lazily
        self._alias_manager: AliasManager | None = None

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset the global config singleton for test isolation.

        This method should ONLY be called from test fixtures to ensure
        each test starts with a fresh configuration state.

        WARNING: Never call this in production code!
        """
        global config
        config = cls()

    @property
    def provider_manager(self) -> "ProviderManager":
        """Lazy initialization of provider manager to avoid circular imports.

        Auto-loads provider configurations on first access to ensure providers
        are ready when the manager is used.
        """
        if self._provider_manager is None:
            from src.core.provider_manager import ProviderManager

            self._provider_manager = ProviderManager(
                default_provider=self.default_provider,
                default_provider_source=getattr(self, "default_provider_source", "system"),
            )
            # Auto-load configurations on first access
            self._provider_manager.load_provider_configs()
        return self._provider_manager

    @property
    def alias_manager(self) -> "AliasManager":
        """Lazy initialization of alias manager to avoid circular imports"""
        if self._alias_manager is None:
            from src.core.alias_manager import AliasManager

            self._alias_manager = AliasManager()
        return self._alias_manager

    def validate_api_key(self) -> bool:
        """Basic API key validation"""
        if not self.openai_api_key:
            return False
        # Basic format check for OpenAI API keys
        return self.openai_api_key.startswith("sk-")

    def validate_client_api_key(self, client_api_key: str) -> bool:
        """Validate client's Anthropic API key"""
        # If no PROXY_API_KEY is set in environment, skip validation
        if not self.proxy_api_key:
            return True

        # Check if the client's API key matches the expected value
        return client_api_key == self.proxy_api_key

    def get_custom_headers(self) -> dict[str, str]:
        """Get custom headers from environment variables"""
        custom_headers = {}

        # Get all environment variables
        env_vars = dict(os.environ)

        # Find CUSTOM_HEADER_* environment variables
        for env_key, env_value in env_vars.items():
            if env_key.startswith("CUSTOM_HEADER_"):
                # Convert CUSTOM_HEADER_KEY to Header-Key
                # Remove 'CUSTOM_HEADER_' prefix and convert to header format
                header_name = env_key[14:]  # Remove 'CUSTOM_HEADER_' prefix

                if header_name:  # Make sure it's not empty
                    # Convert underscores to hyphens for HTTP header format
                    header_name = header_name.replace("_", "-")
                    custom_headers[header_name] = env_value

        return custom_headers

    @property
    def api_key_hash(self) -> str:
        """Get the first few characters of SHA256 hash of the default provider's API key.

        This provides a secure way to identify the API key without exposing it.
        Returns '<not-set>' if the API key is not configured.

        Returns:
            str: First few characters of SHA256 hash or '<not-set>'
        """
        return (
            "<not-set>"
            if not self.openai_api_key
            else "sha256:" + hashlib.sha256(self.openai_api_key.encode()).hexdigest()[:16] + "..."
        )


try:
    config = Config()
except Exception as e:
    print(f"=4 Configuration Error: {e}")
    sys.exit(1)
