"""
JWT parsing utilities for ChatGPT OAuth tokens.

This module provides functions to parse JWT (JSON Web Tokens) without
verification, extracting claims from the ID token returned by OAuth.

Note: These functions do NOT verify JWT signatures. They simply decode
the payload for extracting user information. This is acceptable for the
use case since we receive tokens directly from OpenAI's OAuth servers.
"""

import base64
import binascii
import json
from typing import Any

from .constants import JwtProtocol
from .exceptions import TokenError


def parse_jwt_claims(token: str) -> dict[str, Any]:
    """Parse JWT payload without signature verification.

    Decodes the payload section of a JWT token to access the claims.
    Does not verify the signature - suitable only when the token source
    is trusted (e.g., directly from OAuth server).

    Args:
        token: JWT token string (format: header.payload.signature)

    Returns:
        Parsed claims dictionary

    Raises:
        ValueError: If token is malformed or not a valid JWT

    Example:
        >>> token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM..."
        >>> claims = parse_jwt_claims(token)
        >>> print(claims.get("sub"))
    """
    if not token:
        raise ValueError("Token is empty")

    if token.count(".") != JwtProtocol.JWT_PART_COUNT:
        raise ValueError(f"Invalid JWT format: expected 2 dots, got {token.count('.')}")

    try:
        # Split token into header.payload.signature
        _, payload, _ = token.split(".")

        # Add padding if needed (base64url may omit trailing =)
        padded = payload + "=" * (-len(payload) % JwtProtocol.BASE64_PADDING_LENGTH)

        # Decode base64url
        data = base64.urlsafe_b64decode(padded.encode())

        # Parse JSON
        return json.loads(data.decode())  # type: ignore[no-any-return]
    except (ValueError, binascii.Error) as e:
        raise ValueError(f"Failed to decode JWT payload: {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JWT claims as JSON: {e}") from e


def extract_account_id(token: str, raise_on_error: bool = False) -> str | None:
    """Extract account_id from JWT custom claims.

    ChatGPT ID tokens may contain the account ID in various locations.
    This function tries multiple possible claim paths.

    Args:
        token: JWT ID token string
        raise_on_error: If True, raise TokenError on parse failure.
                       If False (default), return None on parse failure.

    Returns:
        Account ID string if found, None otherwise

    Raises:
        TokenError: If raise_on_error is True and token is malformed

    The account ID may be found in:
    1. https://api.openai.com/auth.user_id (OpenAI custom claim)
    2. user_id (direct claim)
    3. sub (standard subject claim)
    """
    try:
        claims = parse_jwt_claims(token)
    except ValueError as e:
        if raise_on_error:
            raise TokenError(f"Failed to parse JWT: {e}") from e
        return None

    # Try OpenAI's custom claim first
    openai_auth = claims.get("https://api.openai.com/auth")
    if isinstance(openai_auth, dict):
        account_id = openai_auth.get("user_id")
        if isinstance(account_id, str):
            return account_id

    # Try direct user_id claim
    account_id = claims.get("user_id")
    if isinstance(account_id, str):
        return account_id

    # Fall back to standard 'sub' claim
    sub = claims.get("sub")
    return sub if isinstance(sub, str) else None


def get_token_expiry(token: str, raise_on_error: bool = False) -> int | None:
    """Get expiration timestamp from JWT claims.

    Args:
        token: JWT token string
        raise_on_error: If True, raise TokenError on parse failure.
                       If False (default), return None on parse failure.

    Returns:
        Unix timestamp of expiration, or None if not found

    Raises:
        TokenError: If raise_on_error is True and token is malformed
    """
    try:
        claims = parse_jwt_claims(token)
    except ValueError as e:
        if raise_on_error:
            raise TokenError(f"Failed to parse JWT: {e}") from e
        return None

    return claims.get("exp")
