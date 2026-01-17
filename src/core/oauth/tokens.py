"""
Token management with automatic refresh.

This module provides functionality for managing OAuth access tokens,
including automatic refresh before expiration.
"""

import contextlib
import datetime
import json
import logging
import urllib.parse

from .constants import OAuthClient, OAuthProtocol, TokenRefreshDefaults
from .exceptions import StorageError, TokenError
from .http_client import HttpClient, HttpError, HttpxHttpClient
from .jwt import extract_account_id, get_token_expiry
from .storage import AuthData, AuthStorage
from .validation import (
    validate_storage_instance,
    validate_string,
    validate_url,
)

_logger = logging.getLogger(__name__)


# Refresh token 5 minutes before expiry
_REFRESH_THRESHOLD_SECONDS = TokenRefreshDefaults.REFRESH_THRESHOLD_SECONDS


class TokenManager:
    """Manages access tokens with automatic refresh.

    This class handles:
    - Reading stored tokens from storage backend
    - Checking if tokens need refresh
    - Refreshing tokens using refresh_token grant
    - Writing refreshed tokens back to storage

    Example:
        >>> from oauth import TokenManager, FileSystemAuthStorage
        >>> storage = FileSystemAuthStorage()
        >>> token_mgr = TokenManager(storage)
        >>> access_token, account_id = token_mgr.get_access_token()
    """

    def __init__(
        self,
        storage: AuthStorage,
        client_id: str = OAuthClient.CLIENT_ID,
        issuer: str = OAuthClient.ISSUER,
        http_client: HttpClient | None = None,
        raise_on_refresh_failure: bool = False,
    ):
        """Initialize token manager.

        Args:
            storage: Storage backend for reading/writing tokens
            client_id: OAuth client ID for token refresh
            issuer: OAuth issuer URL (must be HTTPS)
            http_client: HTTP client for token requests (uses default if None)
            raise_on_refresh_failure: If True, raise TokenError when refresh fails.

        Raises:
            ValidationError: If parameters fail validation
        """
        validate_storage_instance(storage, "storage")
        validate_string(client_id, "client_id", allow_empty=False)
        validate_url(issuer, "issuer", require_https=True)

        self.storage = storage
        self.client_id = client_id
        self.issuer = issuer
        self.token_url = f"{issuer}/oauth/token"
        self.http_client = http_client or HttpxHttpClient()
        self._raise_on_refresh_failure = raise_on_refresh_failure

    def get_access_token(self) -> tuple[str | None, str | None]:
        """Get current access token, refreshing if needed.

        Checks if the stored token needs refresh (either expired or
        approaching expiry), performs refresh if needed, and returns
        the current access token.

        Returns:
            (access_token, account_id) tuple, or (None, None) if not authenticated

        Raises:
            TokenError: If token refresh fails and raise_on_refresh_failure is True
        """
        auth_data = self.storage.read_auth()
        if not auth_data:
            return None, None

        # Check if token needs refresh
        if self._should_refresh(auth_data):
            try:
                refreshed_data = self._refresh_token(auth_data)
                if refreshed_data:
                    self.storage.write_auth(refreshed_data)
                    auth_data = refreshed_data
                else:
                    # Refresh failed, continue with existing (possibly stale) token
                    if self._raise_on_refresh_failure:
                        raise TokenError("Token refresh failed")
                    # Errors have been logged by _refresh_token()
                    _logger.warning("Token refresh failed, using existing token (may be stale)")
            except TokenError:
                # Re-raise in strict mode
                raise
            except StorageError as e:
                # Storage failed - wrap as TokenError for consistent error handling
                _logger.error("Failed to write refreshed tokens: %s", e)
                raise TokenError(f"Token refresh succeeded but storage failed: {e}") from e

        return auth_data.access_token, auth_data.account_id

    def is_authenticated(self) -> bool:
        """Check if valid authentication exists.

        Returns:
            True if auth data exists and has required tokens
        """
        return self.storage.is_authenticated()

    def _should_refresh(self, auth_data: AuthData) -> bool:
        """Check if token should be refreshed.

        A token should be refreshed if:
        - No access token exists
        - Token is expired or expires within REFRESH_THRESHOLD_SECONDS

        Args:
            auth_data: Current authentication data

        Returns:
            True if token should be refreshed
        """
        if not auth_data.access_token:
            return True

        # Check expiry from expires_at field
        if auth_data.expires_at:
            try:
                expiry = datetime.datetime.fromisoformat(auth_data.expires_at)
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=datetime.timezone.utc)
                now = datetime.datetime.now(datetime.timezone.utc)
                # Refresh if expires within threshold
                return (expiry - now).total_seconds() < _REFRESH_THRESHOLD_SECONDS
            except Exception:
                pass

        # Fallback: check last_refresh time
        # Access tokens typically last ~1 hour, refresh after 55 minutes
        if auth_data.last_refresh:
            try:
                last_refresh = datetime.datetime.fromisoformat(auth_data.last_refresh)
                if last_refresh.tzinfo is None:
                    last_refresh = last_refresh.replace(tzinfo=datetime.timezone.utc)
                now = datetime.datetime.now(datetime.timezone.utc)
                # Refresh after 55 minutes
                return (
                    now - last_refresh
                ).total_seconds() > TokenRefreshDefaults.FALLBACK_REFRESH_INTERVAL_SECONDS
            except Exception:
                pass

        # No expiry info, assume token is fresh
        return False

    def _refresh_token(self, auth_data: AuthData) -> AuthData | None:
        """Refresh the access token using refresh_token grant.

        Args:
            auth_data: Current authentication data with refresh_token

        Returns:
            New AuthData if refresh succeeded, None otherwise

        Raises:
            TokenError: If raise_on_refresh_failure is True and refresh fails
        """
        if not auth_data.refresh_token:
            error_msg = "Cannot refresh token: no refresh_token available"
            _logger.warning(error_msg)
            if self._raise_on_refresh_failure:
                raise TokenError(error_msg)
            return None

        data = urllib.parse.urlencode(
            {
                "grant_type": OAuthProtocol.GRANT_TYPE_REFRESH_TOKEN,
                "refresh_token": auth_data.refresh_token,
                "client_id": self.client_id,
                "scope": OAuthClient.SCOPE,
            }
        ).encode()

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            response = self.http_client.post(
                self.token_url,
                data=data,
                headers=headers,
            )

            payload = response.json()

            id_token = payload.get("id_token", "")
            access_token = payload.get("access_token", "")
            refresh_token = payload.get("refresh_token", auth_data.refresh_token)

            if not access_token or not id_token:
                error_msg = "Token refresh failed: response missing access_token or id_token"
                _logger.error(error_msg)
                if self._raise_on_refresh_failure:
                    raise TokenError(error_msg)
                return None

            # Extract account ID from new ID token
            account_id = extract_account_id(id_token) or auth_data.account_id

            # Get expiry from access token
            exp_timestamp = get_token_expiry(access_token)
            expires_at = None
            if exp_timestamp:
                with contextlib.suppress(Exception):
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

        except HttpError as e:
            # Log with appropriate level based on status code
            if e.status_code == 0:
                # Network error
                error_msg = f"Token refresh failed: Network error - {e.reason}"
                _logger.warning(error_msg)
            elif e.status_code >= 500:
                # Server error
                error_msg = f"Token refresh failed: HTTP {e.status_code} - {e.reason}"
                _logger.error(error_msg)
            else:
                # Client error (4xx)
                error_msg = f"Token refresh failed: HTTP {e.status_code} - {e.reason}"
                _logger.error(error_msg)
            if self._raise_on_refresh_failure:
                raise TokenError(error_msg) from e
            return None
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            error_msg = f"Token refresh failed: Invalid response - {e}"
            _logger.error(error_msg)
            if self._raise_on_refresh_failure:
                raise TokenError(error_msg) from e
            return None
        except Exception as e:
            error_msg = f"Token refresh failed: Unexpected error - {e}"
            _logger.exception(error_msg)
            if self._raise_on_refresh_failure:
                raise TokenError(error_msg) from e
            return None


__all__ = ["TokenManager"]
