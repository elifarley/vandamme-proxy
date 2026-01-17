"""OAuth client mixin for token-based authentication.

This module provides a reusable mixin for API clients that need to inject
OAuth tokens into their requests instead of traditional API keys.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.oauth.tokens import TokenManager  # type: ignore[import-untyped]


class OAuthClientMixin:
    """Mixin for API clients that use OAuth authentication.

    This mixin provides methods to retrieve OAuth tokens and inject them
    into request headers. It can be used with both OpenAIClient and
    AnthropicClient.

    Classes using this mixin must:
    1. Have a _oauth_token_manager attribute (optional, can be None)
    2. Call _inject_oauth_headers when making authenticated requests
    """

    _oauth_token_manager: "TokenManager | None"

    def _get_oauth_token(self) -> tuple[str, str]:
        """Get the current OAuth access token and account ID.

        Returns:
            A tuple of (access_token, account_id) from the TokenManager.

        Raises:
            ValueError: If not authenticated or TokenManager is not available.
        """
        if self._oauth_token_manager is None:
            raise ValueError(
                "OAuth authentication not available. Run 'vdm oauth login <provider>' first."
            )

        access_token, account_id = self._oauth_token_manager.get_access_token()

        if access_token is None:
            raise ValueError("Not authenticated. Please run 'vdm oauth login <provider>' first.")

        if account_id is None:
            raise ValueError("No account ID found. Please run 'vdm oauth login <provider>' first.")

        return access_token, account_id

    def _inject_oauth_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Inject OAuth authentication headers into a headers dict.

        Args:
            headers: The existing headers dictionary (will be modified in-place).

        Returns:
            The same headers dict with OAuth headers added.

        Raises:
            ValueError: If OAuth authentication is not available.
        """
        access_token, account_id = self._get_oauth_token()

        # Add OAuth-specific headers
        headers["Authorization"] = f"Bearer {access_token}"
        headers["x-account-id"] = account_id

        return headers
