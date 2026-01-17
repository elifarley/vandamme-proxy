"""
PKCE (Proof Key for Code Exchange) utilities for OAuth security.

PKCE is an extension to the Authorization Code flow to prevent
authorization code interception attacks. It's used for public
clients (like CLI apps) that cannot securely store a client secret.

This module generates the code verifier and code challenge used
in the OAuth flow with ChatGPT.
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass

from .constants import PkceProtocol


@dataclass
class PkceCodes:
    """PKCE code verifier and challenge pair.

    Attributes:
        code_verifier: Cryptographically random string (43-128 chars)
        code_challenge: Base64url-encoded SHA256 hash of verifier
    """

    code_verifier: str
    code_challenge: str


def generate_pkce() -> PkceCodes:
    """Generate PKCE code verifier and challenge.

    Uses SHA-256 as the challenge method (S256), which is required
    by OpenAI's OAuth implementation.

    The code verifier is:
    - Cryptographically random using secrets.token_urlsafe()
    - Base64url-encoded (no padding)
    - Between 43 and 128 characters (OAuth 2.1 spec)

    The code challenge is:
    - SHA-256 hash of the verifier
    - Base64url-encoded (no padding)

    Returns:
        PkceCodes containing verifier and challenge

    Example:
        >>> pkce = generate_pkce()
        >>> print(f"Verifier: {pkce.code_verifier[:20]}...")
        >>> print(f"Challenge: {pkce.code_challenge[:20]}...")
    """
    # Generate cryptographically random verifier
    # Using token_hex for URL-safe characters
    # 64 bytes hex = 128 chars, well within 43-128 range
    code_verifier = secrets.token_hex(PkceProtocol.CODE_VERIFIER_BYTES)

    # Create SHA-256 hash of verifier
    digest = hashlib.sha256(code_verifier.encode()).digest()

    # Base64url-encode the hash (remove padding)
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    return PkceCodes(
        code_verifier=code_verifier,
        code_challenge=code_challenge,
    )
