"""HTTP callback server for OAuth flow.

This module contains the HTTP server infrastructure for handling
OAuth callbacks, separated from high-level OAuth orchestration.
"""

import http.server
import secrets
import threading
import time
import urllib.parse
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .oauth import OAuthConfig

from .constants import OAuthDefaults, OAuthProtocol
from .pkce import generate_pkce
from .storage import AuthData, AuthStorage
from .token_exchanger import TokenExchanger

# HTML page shown after successful login
_LOGIN_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Login successful</title>
  </head>
  <body>
    <div style="max-width: 640px; margin: 80px auto;
                font-family: system-ui, -apple-system, sans-serif;">
      <h1>Login successful</h1>
      <p>You can now close this window and return to the terminal.</p>
    </div>
  </body>
</html>
"""


class OAuthHTTPServer(http.server.HTTPServer):
    """HTTP server for OAuth callback handling.

    This server listens on localhost for the OAuth callback,
    receives the authorization code, and coordinates with
    TokenExchanger to complete the flow.

    Refactored to separate concerns:
    - Server lifecycle management
    - State management (thread-safe)
    - Delegates token exchange to TokenExchanger
    """

    def __init__(
        self,
        server_address: tuple,
        request_handler_class: type,
        storage: AuthStorage,
        config: "OAuthConfig",
        on_success: Callable[[AuthData], None] | None = None,
        token_exchanger: TokenExchanger | None = None,
    ):
        super().__init__(server_address, request_handler_class, bind_and_activate=True)
        self.storage = storage
        self.config = config
        self.on_success = on_success or (lambda _: None)
        self.token_exchanger = token_exchanger

        # Thread-safe state management
        self._exit_code = 1
        self._exit_event = threading.Event()
        self._lock = threading.Lock()

        self.pkce = generate_pkce()
        self.state = secrets.token_hex(32)
        self.redirect_uri = f"http://localhost:{config.port}/auth/callback"
        self.token_endpoint = f"{config.issuer}/oauth/token"

    @property
    def exit_code(self) -> int:
        """Get exit code with thread safety."""
        with self._lock:
            return self._exit_code

    @exit_code.setter
    def exit_code(self, value: int) -> None:
        """Set exit code with thread safety and signal completion."""
        with self._lock:
            self._exit_code = value
            self._exit_event.set()

    def wait_for_completion(self, timeout: float) -> bool:
        """Wait for OAuth flow completion.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if event was signaled, False if timeout
        """
        return self._exit_event.wait(timeout=timeout)

    def get_completion_result(self) -> bool:
        """Get the completion result after wait_for_completion returns.

        Returns:
            True if authentication succeeded (exit_code == 0), False otherwise

        Note:
            This must be called after wait_for_completion() returns True.
            It checks the actual exit code to distinguish success from failure.
        """
        with self._lock:
            return self._exit_code == 0

    def get_auth_url(self) -> str:
        """Generate the OAuth authorization URL.

        Returns:
            URL to open in browser for user authorization
        """
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "openid offline_access",
            "code_challenge": self.pkce.code_challenge,
            "code_challenge_method": "S256",
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "state": self.state,
        }
        return f"{self.config.issuer}/oauth/authorize?" + urllib.parse.urlencode(params)

    def exchange_code(self, code: str) -> AuthData:
        """Exchange authorization code for tokens.

        Delegates to TokenExchanger for the actual exchange.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            AuthData containing the tokens

        Raises:
            HttpError: If token exchange fails
            TokenError: If JWT parsing fails
            RuntimeError: If TokenExchanger is not configured
        """
        if self.token_exchanger is None:
            raise RuntimeError("TokenExchanger not configured")

        from .token_exchanger import TokenExchangeContext

        ctx = TokenExchangeContext(
            code=code,
            redirect_uri=self.redirect_uri,
            client_id=self.config.client_id,
            pkce=self.pkce,
            token_endpoint=self.token_endpoint,
        )
        return self.token_exchanger.exchange(ctx)


class OAuthHandler(http.server.BaseHTTPRequestHandler):
    """Handle OAuth callback requests.

    Processes the callback from OAuth server, coordinates token exchange,
    stores results, and shows success/error page.
    """

    server: OAuthHTTPServer

    def do_GET(self) -> None:
        """Handle GET request."""
        path = urllib.parse.urlparse(self.path).path

        if path == "/success":
            # Already authenticated, showing success page
            self._send_html(_LOGIN_SUCCESS_HTML)
            self._shutdown_after_delay(OAuthDefaults.SUCCESS_PAGE_SHUTDOWN_DELAY)
            return

        if path != "/auth/callback":
            self.send_error(OAuthProtocol.HTTP_NOT_FOUND, "Not Found")
            self._shutdown()
            return

        # Parse query parameters for authorization code
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]

        if error:
            self._send_error_page(error or "Authorization failed")
            self._shutdown_after_delay(OAuthDefaults.ERROR_PAGE_SHUTDOWN_DELAY)
            return

        if not code:
            self._send_error_page("Missing authorization code")
            self._shutdown_after_delay(OAuthDefaults.ERROR_PAGE_SHUTDOWN_DELAY)
            return

        if state != self.server.state:
            self._send_error_page("Invalid state parameter")
            self._shutdown_after_delay(OAuthDefaults.ERROR_PAGE_SHUTDOWN_DELAY)
            return

        try:
            # Exchange code for tokens
            auth_data = self.server.exchange_code(code)

            # Store the tokens (may raise StorageError)
            self.server.storage.write_auth(auth_data)
            self.server.exit_code = 0
            self.server.on_success(auth_data)
            self._send_html(_LOGIN_SUCCESS_HTML)

        except Exception as e:
            self._send_error_page(f"Token exchange failed: {e}")
            self.server.exit_code = 1

        self._shutdown_after_delay(OAuthDefaults.ERROR_PAGE_SHUTDOWN_DELAY)

    def do_POST(self) -> None:
        """Handle POST request (not supported)."""
        self.send_error(OAuthProtocol.HTTP_NOT_FOUND, "Not Found")
        self._shutdown()

    def log_message(self, fmt: str, *args: object) -> None:
        """Suppress log messages."""
        pass

    def _send_html(self, body: str) -> None:
        """Send HTML response."""
        encoded = body.encode()
        self.send_response(OAuthProtocol.HTTP_OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_error_page(self, error: str) -> None:
        """Send error page."""
        html = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Login failed</title>
  </head>
  <body>
    <div style="max-width: 640px; margin: 80px auto;
                font-family: system-ui, -apple-system, sans-serif;">
      <h1>Login failed</h1>
      <p>{error}</p>
    </div>
  </body>
</html>
"""
        self._send_html(html)

    def _shutdown(self) -> None:
        """Shutdown server in background thread."""
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _shutdown_after_delay(
        self, seconds: float = OAuthDefaults.ERROR_PAGE_SHUTDOWN_DELAY
    ) -> None:
        """Shutdown server after delay."""

        def _later() -> None:
            try:
                time.sleep(seconds)
            finally:
                self._shutdown()

        threading.Thread(target=_later, daemon=True).start()


__all__ = [
    "OAuthHTTPServer",
    "OAuthHandler",
]
