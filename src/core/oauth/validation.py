"""
Validation utilities for oauth library.

This module provides reusable validation functions that follow
the D.R.Y. principle and provide clear, actionable error messages.

All validation functions raise ValidationError with descriptive
messages when validation fails, making it easy to debug configuration
issues.

Example:
    >>> validate_port(80, "port")
    ValidationError: Invalid 'port': must be at least 1024 (got 80)
"""

from __future__ import annotations

import datetime
import urllib.parse
from typing import Any

from .constants import ValidationLimits
from .exceptions import ValidationError

# =============================================================================
# TYPE VALIDATION
# =============================================================================


def validate_type(value: object, expected_type: type | tuple[type, ...], field_name: str) -> None:
    """Validate that value is of expected type.

    Args:
        value: The value to validate
        expected_type: Type or tuple of types to check against
        field_name: Name of the field (for error messages)

    Raises:
        ValidationError: If value is not of expected type

    Example:
        >>> validate_type("hello", str, "name")
        >>> validate_type(123, str, "name")
        ValidationError: Invalid 'name': must be str (got int)
    """
    if not isinstance(value, expected_type):
        type_names = (
            expected_type.__name__
            if isinstance(expected_type, type)
            else " or ".join(t.__name__ for t in expected_type)
        )
        raise ValidationError(
            field_name, value, f"must be {type_names}, got {type(value).__name__}"
        )


def validate_string(value: object, field_name: str, allow_empty: bool = False) -> str:
    """Validate that value is a string (optionally non-empty).

    Args:
        value: The value to validate
        field_name: Name of the field (for error messages)
        allow_empty: If True, empty strings are allowed

    Returns:
        The validated string

    Raises:
        ValidationError: If value is not a string or is empty when not allowed

    Example:
        >>> validate_string("hello", "name")
        'hello'
        >>> validate_string("", "name", allow_empty=False)
        ValidationError: Invalid 'name': must be a non-empty string (got '')
    """
    validate_type(value, str, field_name)

    # At this point mypy knows value is str due to validate_type
    assert isinstance(value, str)  # for type narrowing

    if not allow_empty and not value:
        raise ValidationError(field_name, value, "must be a non-empty string")

    return value


# =============================================================================
# RANGE VALIDATION
# =============================================================================


def validate_range(
    value: int,
    field_name: str,
    min_value: int | None = None,
    max_value: int | None = None,
) -> None:
    """Validate that integer is within specified range.

    Args:
        value: The integer value to validate
        field_name: Name of the field (for error messages)
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive)

    Raises:
        ValidationError: If value is outside range

    Example:
        >>> validate_range(50, "port", min_value=1024, max_value=65535)
        ValidationError: Invalid 'port': must be at least 1024 (got 50)
    """
    validate_type(value, int, field_name)

    if min_value is not None and value < min_value:
        raise ValidationError(field_name, value, f"must be at least {min_value}")

    if max_value is not None and value > max_value:
        raise ValidationError(field_name, value, f"must be at most {max_value}")


def validate_port(port: int, field_name: str = "port") -> None:
    """Validate that port number is in valid range.

    Valid ports are 1024-65535 (non-privileged ports).

    Args:
        port: Port number to validate
        field_name: Name of the field (for error messages)

    Raises:
        ValidationError: If port is invalid

    Example:
        >>> validate_port(80, "port")
        ValidationError: Invalid 'port': must be at least 1024 (got 80)
    """
    validate_range(
        port,
        field_name,
        min_value=ValidationLimits.MIN_PORT,
        max_value=ValidationLimits.MAX_PORT,
    )


# =============================================================================
# FORMAT VALIDATION
# =============================================================================


def validate_url(value: str, field_name: str, require_https: bool = False) -> str:
    """Validate that value is a well-formed URL.

    Args:
        value: URL string to validate
        field_name: Name of the field (for error messages)
        require_https: If True, only HTTPS URLs are allowed

    Returns:
        The validated URL string

    Raises:
        ValidationError: If URL is malformed or has wrong scheme

    Example:
        >>> validate_url("http://example.com", "issuer", require_https=True)
        ValidationError: Invalid 'issuer': URL must use HTTPS scheme (got 'http://example.com')
    """
    validate_string(value, field_name)

    try:
        parsed = urllib.parse.urlparse(value)
    except Exception as e:
        raise ValidationError(field_name, value, f"malformed URL: {e}") from e

    if not parsed.scheme or not parsed.netloc:
        raise ValidationError(field_name, value, "URL must have scheme and netloc")

    if require_https and parsed.scheme != "https":
        raise ValidationError(field_name, value, "URL must use HTTPS scheme")

    return value


def validate_iso_timestamp(value: str | None, field_name: str) -> str | None:
    """Validate that value is a valid ISO 8601 timestamp.

    Args:
        value: Timestamp string to validate (None is allowed)
        field_name: Name of the field (for error messages)

    Returns:
        The validated timestamp string or None

    Raises:
        ValidationError: If timestamp is malformed

    Example:
        >>> validate_iso_timestamp("2025-01-01T00:00:00", "expires_at")
        '2025-01-01T00:00:00'
        >>> validate_iso_timestamp("not-a-date", "expires_at")
        ValidationError: Invalid 'expires_at': invalid ISO 8601 timestamp...
    """
    if value is None:
        return None

    validate_string(value, field_name)

    try:
        datetime.datetime.fromisoformat(value)
    except ValueError as e:
        raise ValidationError(field_name, value, f"invalid ISO 8601 timestamp: {e}") from e

    return value


def validate_token(value: str, field_name: str = "token") -> str:
    """Validate that value looks like a valid token.

    This is a basic sanity check, not cryptographic validation.
    Tokens should be reasonably long and contain valid characters.

    Args:
        value: Token string to validate
        field_name: Name of the field (for error messages)

    Returns:
        The validated token string

    Raises:
        ValidationError: If token appears invalid

    Example:
        >>> validate_token("short", "access_token")
        ValidationError: Invalid 'access_token': token too short (minimum 20
        characters) (got 'short')
    """
    validate_string(value, field_name)

    if len(value) < ValidationLimits.MIN_TOKEN_LENGTH:
        raise ValidationError(
            field_name,
            value,
            f"token too short (minimum {ValidationLimits.MIN_TOKEN_LENGTH} characters)",
        )

    # Basic character check: tokens should be printable
    if not value.isprintable():
        raise ValidationError(field_name, value, "token contains non-printable characters")

    return value


# =============================================================================
# INSTANCE VALIDATION
# =============================================================================


def validate_storage_instance(storage: Any, param_name: str = "storage") -> None:
    """Validate that storage is a proper AuthStorage instance.

    Args:
        storage: Object to validate
        param_name: Parameter name (for error messages)

    Raises:
        ValidationError: If storage is not a valid AuthStorage

    Example:
        >>> validate_storage_instance("not_a_storage", "storage")
        ValidationError: Invalid 'storage': must be an instance of AuthStorage, got str
    """
    # Import here to avoid circular imports
    from .storage import AuthStorage

    if not isinstance(storage, AuthStorage):
        raise ValidationError(
            param_name, storage, f"must be an instance of AuthStorage, got {type(storage).__name__}"
        )


# =============================================================================
# DICT VALIDATION
# =============================================================================


def validate_dict_keys(data: dict[str, Any], allowed_keys: set[str], context: str) -> None:
    """Validate that dict contains only allowed keys.

    This helps catch typos in configuration dictionaries.

    Args:
        data: Dictionary to validate
        allowed_keys: Set of valid key names
        context: Context string for error messages

    Raises:
        ValidationError: If dict contains unknown keys

    Example:
        >>> validate_dict_keys({"typo_field": "value"}, {"name", "value"}, "MyConfig")
        ValidationError: Invalid 'MyConfig.keys': unknown field(s): typo_field...
    """
    unknown_keys = set(data.keys()) - allowed_keys

    if unknown_keys:
        raise ValidationError(
            f"{context}.keys",
            sorted(unknown_keys),
            f"unknown field(s): {', '.join(sorted(unknown_keys))}. "
            f"Valid fields are: {', '.join(sorted(allowed_keys))}",
        )


__all__ = [
    "validate_type",
    "validate_string",
    "validate_range",
    "validate_port",
    "validate_url",
    "validate_iso_timestamp",
    "validate_token",
    "validate_storage_instance",
    "validate_dict_keys",
]
