"""
Storage abstraction for authentication data.

This module provides an abstract interface for storing authentication data,
allowing different backends (filesystem, memory, custom) to be used.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..validation import (
    ValidationError,
    validate_dict_keys,
    validate_iso_timestamp,
    validate_string,
    validate_token,
)

# Allowed fields for AuthData dictionaries (helps catch typos)
_AUTH_DATA_ALLOWED_FIELDS = {
    "access_token",
    "refresh_token",
    "id_token",
    "account_id",
    "expires_at",
    "last_refresh",
}


@dataclass
class AuthData:
    """Container for authentication data.

    Attributes:
        access_token: The OAuth access token for API requests
        refresh_token: The OAuth refresh token for obtaining new access tokens
        id_token: The JWT ID token containing user claims
        account_id: The user's account ID extracted from the ID token
        expires_at: Optional ISO-formatted expiration timestamp
        last_refresh: Optional ISO-formatted timestamp of last refresh

    Raises:
        ValidationError: If created with invalid data
    """

    access_token: str
    refresh_token: str
    id_token: str
    account_id: str
    expires_at: str | None = None
    last_refresh: str | None = None

    def __post_init__(self) -> None:
        """Validate authentication data after initialization."""
        # Validate required tokens
        self.access_token = validate_token(self.access_token, "access_token")
        self.refresh_token = validate_token(self.refresh_token, "refresh_token")
        self.id_token = validate_token(self.id_token, "id_token")

        # Validate account_id (just check it's a non-empty string)
        validate_string(self.account_id, "account_id", allow_empty=False)

        # Validate optional timestamp fields
        if self.expires_at:
            self.expires_at = validate_iso_timestamp(self.expires_at, "expires_at")
        if self.last_refresh:
            self.last_refresh = validate_iso_timestamp(self.last_refresh, "last_refresh")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "id_token": self.id_token,
            "account_id": self.account_id,
            "expires_at": self.expires_at,
            "last_refresh": self.last_refresh or datetime.now(datetime.timezone.utc).isoformat(),  # type: ignore[attr-defined]
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthData":
        """Create from dictionary with validation.

        Args:
            data: Dictionary containing authentication data

        Returns:
            AuthData instance

        Raises:
            ValidationError: If data is invalid or contains unknown fields
        """
        # Check for unknown fields (helps catch typos)
        validate_dict_keys(data, _AUTH_DATA_ALLOWED_FIELDS, "AuthData")

        # Extract and validate required fields
        access_token = data.get("access_token", "")
        refresh_token = data.get("refresh_token", "")
        id_token = data.get("id_token", "")
        account_id = data.get("account_id", "")

        # Validate required fields are present
        if not access_token:
            raise ValidationError(
                "access_token", access_token, "required field is missing or empty"
            )
        if not refresh_token:
            raise ValidationError(
                "refresh_token", refresh_token, "required field is missing or empty"
            )
        if not id_token:
            raise ValidationError("id_token", id_token, "required field is missing or empty")
        if not account_id:
            raise ValidationError("account_id", account_id, "required field is missing or empty")

        # Extract optional fields
        expires_at = data.get("expires_at")
        last_refresh = data.get("last_refresh")

        # Create instance (will trigger __post_init__ validation)
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            id_token=id_token,
            account_id=account_id,
            expires_at=expires_at,
            last_refresh=last_refresh,
        )


class AuthStorage(ABC):
    """Abstract storage backend for authentication data.

    Implementations can store auth data in different backends:
    - FileSystemAuthStorage: Uses ~/.chatgpt-local/auth.json
    - InMemoryAuthStorage: For testing and ephemeral use
    - Custom implementations: Could use databases, keychains, etc.
    """

    @abstractmethod
    def read_auth(self) -> AuthData | None:
        """Read stored authentication data.

        Returns:
            AuthData if found, None otherwise
        """
        pass

    @abstractmethod
    def write_auth(self, data: AuthData) -> None:
        """Write authentication data to storage.

        Args:
            data: The authentication data to store

        Raises:
            StorageError: If write fails
        """
        pass

    @abstractmethod
    def clear_auth(self) -> None:
        """Remove stored authentication data.

        Raises:
            StorageError: If clear fails
        """
        pass

    def is_authenticated(self) -> bool:
        """Check if valid authentication exists.

        Returns:
            True if auth data exists and contains required fields
        """
        data = self.read_auth()
        if not data:
            return False
        return bool(data.access_token and data.refresh_token and data.account_id)


# Import implementations (E402 exemption: conditional implementations)
from .file_storage import FileSystemAuthStorage  # noqa: E402
from .memory_storage import InMemoryAuthStorage  # noqa: E402

__all__ = [
    "AuthData",
    "AuthStorage",
    "FileSystemAuthStorage",
    "InMemoryAuthStorage",
]
