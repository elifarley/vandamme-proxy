"""
Centralized constants for oauth library.

This module organizes all magic numbers into logical categories,
making the codebase more maintainable and self-documenting.

Constants are grouped by:
- Configurable defaults: Values users may want to override
- Protocol constants: Fixed by OAuth/JWT/PKCE specifications
- Internal constants: Implementation details
- Validation limits: Valid ranges for parameters
"""

from __future__ import annotations

# =============================================================================
# CONFIGURABLE DEFAULTS
# =============================================================================
# These values can be overridden via OAuthConfig or environment variables.
# They are tuned for typical OAuth flows but may need adjustment.


class OAuthClient:
    """OAuth client credentials for ChatGPT authentication.

    These values identify the application to the OAuth server and must
    match the registered client configuration.
    """

    CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
    ISSUER = "https://auth.openai.com"
    SCOPE = "openid profile email offline_access"


class OAuthDefaults:
    """Default values for OAuth configuration.

    These are chosen based on:
    - Port 1455: Unregistered port, unlikely to conflict with common services
    - 300s timeout: 5 minutes is reasonable for user interaction
    - 30s HTTP timeout: Balance between responsiveness and slow networks
    """

    # Callback server configuration
    CALLBACK_PORT = 1455
    CALLBACK_TIMEOUT = 300  # seconds (5 minutes)

    # HTTP request timeouts
    HTTP_REQUEST_TIMEOUT = 30  # seconds

    # Server shutdown delays (seconds)
    SUCCESS_PAGE_SHUTDOWN_DELAY = 1.0
    ERROR_PAGE_SHUTDOWN_DELAY = 2.0


class TokenRefreshDefaults:
    """Default values for token refresh logic.

    These thresholds ensure tokens are refreshed before they expire,
    preventing API calls with stale tokens.

    Access tokens typically last 1 hour. We refresh 5 minutes before
    expiry to provide a safety buffer.
    """

    # Refresh token 5 minutes (300 seconds) before expiry
    REFRESH_THRESHOLD_SECONDS = 300

    # Fallback: if no expiry info, refresh after 55 minutes (3300 seconds)
    # This is slightly less than the typical 1-hour token lifetime
    FALLBACK_REFRESH_INTERVAL_SECONDS = 3300


# =============================================================================
# PROTOCOL CONSTANTS (Fixed by Standards)
# =============================================================================
# These values are defined by OAuth 2.0, JWT, or PKCE specifications.
# Changing them would break compatibility with the protocols.


class OAuthProtocol:
    """Constants defined by OAuth 2.0 and related RFCs."""

    # HTTP status codes
    HTTP_OK = 200
    HTTP_NOT_FOUND = 404

    # OAuth grant types
    GRANT_TYPE_AUTH_CODE = "authorization_code"
    GRANT_TYPE_REFRESH_TOKEN = "refresh_token"

    # OAuth scopes
    SCOPE_OPENID = "openid"
    SCOPE_PROFILE = "profile"
    SCOPE_EMAIL = "email"
    SCOPE_OFFLINE_ACCESS = "offline_access"


class JwtProtocol:
    """Constants defined by JWT (RFC 7519) specification."""

    # JWT structure: header.payload.signature
    # Count of dots separating the three parts
    JWT_PART_COUNT = 2

    # Base64url encoding: padding length is a multiple of 4
    BASE64_PADDING_LENGTH = 4


class PkceProtocol:
    """Constants defined by PKCE (RFC 7636) specification.

    Code verifier requirements (RFC 7636 Section 4.1):
    - Must be 43-128 characters
    - Using URL-safe characters (A-Z, a-z, 0-9, -, ., _, ~)
    """

    # Number of random bytes to generate
    # 64 bytes hex = 128 chars (within spec's 43-128 range)
    CODE_VERIFIER_BYTES = 64

    # SHA-256 is the challenge method
    CODE_CHALLENGE_METHOD = "S256"


# =============================================================================
# INTERNAL CONSTANTS
# =============================================================================
# Implementation details that users shouldn't need to override.


class StorageDefaults:
    """Filesystem storage defaults."""

    # Unix file permissions (read/write for owner only)
    # octal 0600 = rw------- (user: rw, group: -, other: -)
    FILE_PERMISSIONS = 0o600


# =============================================================================
# VALIDATION RANGES
# =============================================================================
# Valid ranges for user-configurable parameters.


class ValidationLimits:
    """Valid ranges for user-configurable parameters."""

    # Port range: 1024-65535 (non-privileged ports)
    # Ports below 1024 require root/admin privileges
    MIN_PORT = 1024
    MAX_PORT = 65535

    # Timeout limits (seconds)
    MIN_TIMEOUT_SECONDS = 1
    MAX_TIMEOUT_SECONDS = 3600  # 1 hour

    # Token length requirements
    # Minimum reasonable length for OAuth tokens
    MIN_TOKEN_LENGTH = 20


__all__ = [
    "OAuthClient",
    "OAuthDefaults",
    "TokenRefreshDefaults",
    "OAuthProtocol",
    "JwtProtocol",
    "PkceProtocol",
    "StorageDefaults",
    "ValidationLimits",
]
