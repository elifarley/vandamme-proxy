"""Provider management package.

This package provides a modular, single-responsibility approach to provider management,
splitting the monolithic ProviderManager into focused components:

- ProviderRegistry: Stores and retrieves provider configurations
- ApiKeyRotator: Manages round-robin API key rotation
- ClientFactory: Creates and caches API client instances
- ProviderConfigLoader: Loads provider configs from environment and TOML
- DefaultProviderSelector: Handles default provider selection with fallback
- MiddlewareManager: Owns and initializes middleware chain
- ProviderManager: Facade that coordinates all components
"""

from src.core.provider.api_key_rotator import ApiKeyRotator
from src.core.provider.client_factory import ClientFactory
from src.core.provider.default_selector import DefaultProviderSelector
from src.core.provider.middleware_manager import MiddlewareManager
from src.core.provider.provider_config_loader import ProviderConfigLoader
from src.core.provider.provider_registry import ProviderRegistry

__all__ = [
    "ProviderRegistry",
    "ApiKeyRotator",
    "ClientFactory",
    "ProviderConfigLoader",
    "DefaultProviderSelector",
    "MiddlewareManager",
]
