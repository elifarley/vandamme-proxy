"""
ChatGPT Auth Library

Framework-agnostic OAuth authentication for ChatGPT.
Can be used in Flask, FastAPI, CLI tools, or any Python application.

This library provides:
- OAuth 2.0 + PKCE flow for ChatGPT authentication
- Token management with automatic refresh
- Storage abstraction (filesystem, memory, custom)
- JWT parsing utilities

Basic Usage:
    >>> from oauth import OAuthFlow, FileSystemAuthStorage, TokenManager
    >>>
    >>> # One-time authentication
    >>> storage = FileSystemAuthStorage()
    >>> oauth = OAuthFlow(storage)
    >>> success = oauth.authenticate()
    >>>
    >>> # Get access token (auto-refreshes if needed)
    >>> token_mgr = TokenManager(storage)
    >>> access_token, account_id = token_mgr.get_access_token()
    >>>
    >>> # Use in API requests
    >>> headers = {
    ...     "Authorization": f"Bearer {access_token}",
    ...     "x-account-id": account_id,
    ... }

For Testing:
    >>> from oauth import InMemoryAuthStorage
    >>> storage = InMemoryAuthStorage()
    >>> # No file I/O, data persists only in memory
"""

# Storage backend
from .callback_server import OAuthHandler, OAuthHTTPServer

# Exceptions
from .exceptions import (
    ConfigurationError,
    OAuthError,
    OAuthFlowError,
    StorageError,
    TokenError,
    ValidationError,
)

# HTTP client
from .http_client import (
    HttpClient,
    HttpClientConfig,
    HttpError,
    HttpResponse,
    HttpxHttpClient,
    MockHttpClient,
)

# Utilities
from .jwt import extract_account_id, get_token_expiry, parse_jwt_claims

# OAuth flow
from .oauth import OAuthConfig, OAuthFlow
from .pkce import PkceCodes, generate_pkce
from .storage import (
    AuthData,
    AuthStorage,
    FileSystemAuthStorage,
    InMemoryAuthStorage,
)
from .token_exchanger import TokenExchangeContext, TokenExchanger

# Token management
from .tokens import TokenManager

__all__ = [
    # Storage
    "AuthStorage",
    "AuthData",
    "FileSystemAuthStorage",
    "InMemoryAuthStorage",
    # OAuth
    "OAuthFlow",
    "OAuthConfig",
    "OAuthHTTPServer",
    "OAuthHandler",
    "TokenExchanger",
    "TokenExchangeContext",
    # Tokens
    "TokenManager",
    # Utilities
    "parse_jwt_claims",
    "extract_account_id",
    "get_token_expiry",
    "generate_pkce",
    "PkceCodes",
    # HTTP client
    "HttpClient",
    "HttpClientConfig",
    "HttpResponse",
    "HttpError",
    "HttpxHttpClient",
    "MockHttpClient",
    # Exceptions
    "OAuthError",
    "ValidationError",
    "ConfigurationError",
    "TokenError",
    "StorageError",
    "OAuthFlowError",
]

__version__ = "0.1.0"
