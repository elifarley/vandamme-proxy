"""OAuth 2.0 + PKCE flow for ChatGPT authentication.

This module provides high-level OAuth flow orchestration.
HTTP server infrastructure is in callback_server.py.
"""

import threading
import typing
from dataclasses import dataclass

from .callback_server import OAuthHandler, OAuthHTTPServer
from .constants import OAuthClient, OAuthDefaults, ValidationLimits
from .http_client import HttpClient
from .storage import AuthData, AuthStorage
from .token_exchanger import TokenExchanger
from .validation import (
    validate_port,
    validate_range,
    validate_storage_instance,
    validate_string,
    validate_url,
)


@dataclass
class OAuthConfig:
    """Configuration for OAuth flow.

    Attributes:
        client_id: OAuth client ID (defaults to Codex CLI client)
        issuer: OAuth issuer URL (must be HTTPS)
        port: Local port for callback server (1024-65535)
        timeout: Seconds to wait for callback before giving up (1-3600)

    Raises:
        ValidationError: If any parameter fails validation
    """

    client_id: str = OAuthClient.CLIENT_ID
    issuer: str = OAuthClient.ISSUER
    port: int = OAuthDefaults.CALLBACK_PORT
    timeout: int = OAuthDefaults.CALLBACK_TIMEOUT

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        validate_string(self.client_id, "client_id", allow_empty=False)
        validate_url(self.issuer, "issuer", require_https=True)
        validate_port(self.port, "port")
        validate_range(
            self.timeout,
            "timeout",
            min_value=ValidationLimits.MIN_TIMEOUT_SECONDS,
            max_value=ValidationLimits.MAX_TIMEOUT_SECONDS,
        )


class OAuthFlow:
    """High-level OAuth flow manager.

    This class provides a simple interface for running the OAuth flow:
    1. Creates and starts a local HTTP server
    2. Generates the authorization URL
    3. Optionally opens browser automatically
    4. Waits for callback
    5. Exchanges code for tokens
    6. Stores tokens using provided storage

    Example:
        >>> from oauth import OAuthFlow, FileSystemAuthStorage
        >>> storage = FileSystemAuthStorage()
        >>> oauth = OAuthFlow(storage)
        >>> success = oauth.authenticate()
        >>> print(f"Success: {success}")
    """

    def __init__(
        self,
        storage: AuthStorage,
        config: OAuthConfig | None = None,
        http_client: HttpClient | None = None,
    ):
        """Initialize OAuth flow.

        Args:
            storage: Storage backend for persisting tokens
            config: OAuth configuration (uses defaults if None)
            http_client: HTTP client for token requests (uses default if None)

        Raises:
            ValidationError: If storage is not a valid AuthStorage instance
        """
        validate_storage_instance(storage, "storage")
        self.storage = storage
        self.config = config or OAuthConfig()
        self.http_client = http_client

    def authenticate(
        self,
        open_browser: bool = True,
        on_success: typing.Callable[[AuthData], None] | None = None,
    ) -> bool:
        """Run the OAuth authentication flow.

        Starts a local HTTP server, generates authorization URL,
        opens browser (if requested), waits for callback, exchanges
        code for tokens, and stores them.

        Args:
            open_browser: If True, automatically open browser with auth URL
            on_success: Optional callback called after successful auth

        Returns:
            True if authentication succeeded, False otherwise
        """
        # Try to import webbrowser only if needed
        if open_browser:
            try:
                import webbrowser
            except ImportError:
                open_browser = False

        # Create token exchanger if http_client is provided
        token_exchanger = None
        if self.http_client:
            token_exchanger = TokenExchanger(self.http_client)

        server = OAuthHTTPServer(
            ("localhost", self.config.port),
            OAuthHandler,
            self.storage,
            self.config,
            on_success,
            token_exchanger,
        )

        auth_url = server.get_auth_url()

        if open_browser:
            webbrowser.open(auth_url)
        else:
            print(f"Visit this URL to authenticate:\n{auth_url}")

        # Start server in background thread
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        # Wait for callback or timeout using event
        completed = server.wait_for_completion(self.config.timeout)

        # Shutdown server
        server.shutdown()

        # Check actual result
        if not completed:
            return False  # Timeout

        return server.get_completion_result()  # Check exit code

    def get_auth_url(self) -> str:
        """Get the authorization URL without running the flow.

        Useful for custom OAuth implementations or testing.

        Returns:
            Authorization URL to open in browser
        """
        server = OAuthHTTPServer(
            ("localhost", self.config.port),
            OAuthHandler,
            self.storage,
            self.config,
            None,
            None,
        )
        return server.get_auth_url()


__all__ = [
    "OAuthConfig",
    "OAuthFlow",
]
