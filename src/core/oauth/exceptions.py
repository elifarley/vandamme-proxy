"""
Custom exception hierarchy for oauth library.

Provides specific, actionable error messages for validation failures
and runtime errors.

All exceptions inherit from OAuthError, allowing users to
catch all library-specific errors with a single except clause.

Example:
    >>> try:
    ...     oauth.authenticate()
    ... except OAuthError as e:
    ...     print(f"Authentication failed: {e}")
"""

from __future__ import annotations


class OAuthError(Exception):
    """Base exception for all oauth errors.

    All library-specific exceptions inherit from this, allowing
    users to catch all library errors with a single except clause.

    Example:
        >>> try:
        ...     oauth.authenticate()
        ... except OAuthError as e:
        ...     print(f"Authentication failed: {e}")
    """

    pass


class ValidationError(OAuthError):
    """Raised when input validation fails.

    This exception is raised when user-provided parameters don't
    meet the required constraints (type, format, range, etc.).

    Attributes:
        field: Name of the field that failed validation
        value: The invalid value that was provided
        message: Human-readable explanation of the validation error

    Example:
        >>> config = OAuthConfig(port=99999)  # Invalid port
        >>> ValidationError: Invalid 'port': must be at most 65535 (got 99999)
    """

    def __init__(self, field: str, value: object, message: str) -> None:
        self.field = field
        self.value = value
        self.message = message
        super().__init__(f"Invalid {field!r}: {message} (got {value!r})")

    def __repr__(self) -> str:
        return (
            f"ValidationError(field={self.field!r}, value={self.value!r}, message={self.message!r})"
        )


class ConfigurationError(OAuthError):
    """Raised when configuration is invalid or incomplete.

    This differs from ValidationError in that it typically indicates
    a more serious configuration problem (e.g., missing required fields,
    incompatible settings, etc.) rather than a simple validation failure.

    Example:
        >>> storage = InMemoryAuthStorage()
        >>> storage.write_auth(None)  # Invalid configuration
        >>> ConfigurationError: Cannot write None to storage
    """

    pass


class TokenError(OAuthError):
    """Raised when token operations fail.

    This covers token refresh failures, missing tokens, expired tokens,
    and other token-related issues.

    Example:
        >>> token_mgr = TokenManager(storage)
        >>> token_mgr.get_access_token()
        >>> TokenError: Token refresh failed: HTTP 401 - Unauthorized
    """

    pass


class StorageError(OAuthError):
    """Raised when storage operations fail.

    This covers file I/O errors, permission issues, corruption,
    and other storage-related problems.

    Example:
        >>> storage = FileSystemAuthStorage()
        >>> storage.read_auth()
        >>> StorageError: Failed to read auth file: Permission denied
    """

    pass


class OAuthFlowError(OAuthError):
    """Raised when OAuth flow execution fails.

    This covers network errors, server errors, callback failures,
    and other OAuth flow issues.

    Example:
        >>> oauth = OAuthFlow(storage)
        >>> oauth.authenticate()
        >>> OAuthFlowError: Token exchange failed: Connection timeout
    """

    pass


__all__ = [
    "OAuthError",
    "ValidationError",
    "ConfigurationError",
    "TokenError",
    "StorageError",
    "OAuthFlowError",
]
