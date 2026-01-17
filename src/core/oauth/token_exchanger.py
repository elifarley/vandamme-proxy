"""Token exchange logic for OAuth flow.

This module contains the business logic for exchanging OAuth
authorization codes for tokens, separated from HTTP infrastructure.
"""

import datetime
import urllib.parse
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .http_client import HttpClient

from .constants import OAuthProtocol
from .jwt import extract_account_id, get_token_expiry
from .pkce import PkceCodes
from .storage import AuthData


@dataclass
class TokenExchangeContext:
    """Context for token exchange.

    Attributes:
        code: Authorization code from OAuth callback
        redirect_uri: Callback URL for verification
        client_id: OAuth client ID
        pkce: PKCE codes for verification
        token_endpoint: URL for token endpoint
    """

    code: str
    redirect_uri: str
    client_id: str
    pkce: PkceCodes
    token_endpoint: str


class TokenExchanger:
    """Handle OAuth token exchange.

    Separates token exchange logic from HTTP server infrastructure,
    making it easier to test and reason about.
    """

    def __init__(self, http_client: "HttpClient") -> None:
        """Initialize token exchanger.

        Args:
            http_client: HTTP client for making requests
        """
        self.http_client = http_client

    def exchange(self, ctx: TokenExchangeContext) -> AuthData:
        """Exchange authorization code for tokens.

        Args:
            ctx: Token exchange context

        Returns:
            AuthData containing the tokens

        Raises:
            HttpError: If token exchange fails
            TokenError: If JWT parsing fails
            json.JSONDecodeError: If response is invalid JSON
            KeyError: If expected fields are missing from response
        """
        data = urllib.parse.urlencode(
            {
                "grant_type": OAuthProtocol.GRANT_TYPE_AUTH_CODE,
                "code": ctx.code,
                "redirect_uri": ctx.redirect_uri,
                "client_id": ctx.client_id,
                "code_verifier": ctx.pkce.code_verifier,
            }
        ).encode()

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        response = self.http_client.post(
            ctx.token_endpoint,
            data=data,
            headers=headers,
        )

        payload = response.json()

        id_token = payload.get("id_token", "")
        access_token = payload.get("access_token", "")
        refresh_token = payload.get("refresh_token", "")

        # Use strict mode to raise on parse errors during token exchange
        account_id = extract_account_id(id_token, raise_on_error=True) or ""

        expires_at = None
        exp_timestamp = get_token_expiry(access_token, raise_on_error=True)
        if exp_timestamp:
            expires_at = datetime.datetime.fromtimestamp(
                exp_timestamp, tz=datetime.timezone.utc
            ).isoformat()

        return AuthData(
            access_token=access_token,
            refresh_token=refresh_token,
            id_token=id_token,
            account_id=account_id,
            expires_at=expires_at,
            last_refresh=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )


__all__ = [
    "TokenExchanger",
    "TokenExchangeContext",
]
