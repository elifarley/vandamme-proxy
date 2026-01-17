"""
HTTP client abstraction for oauth library.

Provides a testable, observable interface for HTTP requests using
httpx as the default implementation with built-in retry logic.
"""

from __future__ import annotations

import abc
import json
import logging
import random
import time
import typing
from dataclasses import dataclass, field

import httpx

from .constants import OAuthDefaults
from .exceptions import OAuthError

_logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class HttpClientConfig:
    """Configuration for HTTP client behavior.

    Attributes:
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts (0 to disable)
        retry_jitter: Add random jitter to retry delays
        enable_logging: Enable structured logging of requests/responses
    """

    timeout: float = OAuthDefaults.HTTP_REQUEST_TIMEOUT
    max_retries: int = 3
    retry_jitter: bool = True
    enable_logging: bool = True


# =============================================================================
# Response
# =============================================================================


@dataclass
class HttpResponse:
    """HTTP response wrapper adapting httpx.Response to our interface."""

    _raw: httpx.Response
    _text: str | None = field(init=False, default=None)

    @property
    def status_code(self) -> int:
        return self._raw.status_code

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._raw.headers)

    @property
    def body(self) -> bytes:
        return self._raw.content

    @property
    def text(self) -> str:
        if self._text is None:
            self._text = self._raw.text
        return self._text

    def json(self) -> dict[str, typing.Any]:
        return typing.cast(dict[str, typing.Any], self._raw.json())


# =============================================================================
# Exceptions
# =============================================================================


class HttpError(OAuthError):
    """HTTP request failed.

    Wraps httpx exceptions to provide consistent error handling.

    Attributes:
        status_code: HTTP status code (0 for network errors)
        reason: Human-readable reason
        body: Response body
        url: Request URL
    """

    def __init__(
        self,
        status_code: int,
        reason: str,
        body: str,
        url: str,
    ) -> None:
        self.status_code = status_code
        self.reason = reason
        self.body = body
        self.url = url

        body_preview = body[:200] if body else "(empty)"
        if len(body) > 200:
            body_preview += "..."

        super().__init__(f"HTTP {status_code} - {reason} for {url}\nResponse: {body_preview}")


# =============================================================================
# Abstract Client
# =============================================================================


class HttpClient(abc.ABC):
    """Abstract HTTP client for oauth.

    Implementations must provide the post() method for making HTTP POST
    requests with form-encoded data.
    """

    @abc.abstractmethod
    def post(
        self,
        url: str,
        data: bytes,
        headers: dict[str, str],
        timeout: float | None = None,
    ) -> HttpResponse:
        """Make an HTTP POST request.

        Args:
            url: Request URL
            data: Request body as bytes
            headers: Request headers
            timeout: Optional timeout override in seconds

        Returns:
            HttpResponse

        Raises:
            HttpError: If request fails
        """
        pass


# =============================================================================
# httpx Implementation with Retry
# =============================================================================


class _RetryTransport(httpx.HTTPTransport):
    """Custom transport with exponential backoff retry.

    Implements retry logic for transient failures (429, 500, 502, 503, 504).
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_jitter: bool = True,
        **kwargs: typing.Any,
    ) -> None:
        super().__init__(**kwargs)
        self.max_retries = max_retries
        self.retry_jitter = retry_jitter

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Handle request with retry logic."""
        last_exception: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = super().handle_request(request)

                # Check if we should retry based on status code
                if (
                    response.status_code in (429, 500, 502, 503, 504)
                    and attempt < self.max_retries - 1
                ):
                    delay = self._calculate_delay(attempt)
                    _logger.warning(
                        "HTTP %s from %s, retrying in %.1fs (attempt %s/%s)",
                        response.status_code,
                        request.url,
                        delay,
                        attempt + 1,
                        self.max_retries,
                    )
                    time.sleep(delay)
                    continue

                return response

            except (httpx.NetworkError, httpx.TimeoutException) as e:
                last_exception = e

                if attempt < self.max_retries - 1:
                    delay = self._calculate_delay(attempt)
                    _logger.warning(
                        "Network error for %s: %s, retrying in %.1fs (attempt %s/%s)",
                        request.url,
                        e,
                        delay,
                        attempt + 1,
                        self.max_retries,
                    )
                    time.sleep(delay)
                    continue

                raise

        # Should not reach here, but handle gracefully
        if last_exception:
            raise last_exception

        raise RuntimeError("Unexpected error in retry logic")

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with optional jitter."""
        delay: float = 1.0 * (2**attempt)
        if self.retry_jitter:
            delay += random.uniform(0, 1)
        return delay


class HttpxHttpClient(HttpClient):
    """Default HTTP client using httpx with retry logic.

    Features:
    - Connection pooling via httpx.Client
    - Retry with exponential backoff for transient failures
    - Structured logging of requests/responses
    - Proper error context with response bodies

    Example:
        >>> client = HttpxHttpClient()
        >>> response = client.post(
        ...     "https://example.com/api",
        ...     b"key=value",
        ...     {"Content-Type": "application/x-www-form-urlencoded"},
        ... )
    """

    def __init__(self, config: HttpClientConfig | None = None) -> None:
        """Initialize HTTP client.

        Args:
            config: Client configuration (uses defaults if None)
        """
        self.config = config or HttpClientConfig()

        # Create httpx client with retry transport
        transport = None
        if self.config.max_retries > 0:
            transport = _RetryTransport(
                max_retries=self.config.max_retries,
                retry_jitter=self.config.retry_jitter,
            )

        self._client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(self.config.timeout),
        )

    def post(
        self,
        url: str,
        data: bytes,
        headers: dict[str, str],
        timeout: float | None = None,
    ) -> HttpResponse:
        """Make HTTP POST request.

        Args:
            url: Request URL
            data: Request body as bytes
            headers: Request headers
            timeout: Optional timeout override in seconds

        Returns:
            HttpResponse

        Raises:
            HttpError: If request fails after retries
        """
        effective_timeout = timeout or self.config.timeout

        if self.config.enable_logging:
            _logger.debug(
                "HTTP POST %s (timeout=%ds, headers=%s)",
                url,
                effective_timeout,
                headers,
            )

        try:
            response = self._client.post(
                url,
                content=data,
                headers=headers,
                timeout=httpx.Timeout(effective_timeout),
            )

            if self.config.enable_logging:
                _logger.debug(
                    "HTTP %s from %s (body=%d bytes)",
                    response.status_code,
                    url,
                    len(response.content),
                )

            # Check for HTTP errors (4xx, 5xx)
            # Note: Retryable errors are already handled by transport
            response.raise_for_status()

            return HttpResponse(response)

        except httpx.HTTPStatusError as e:
            raise HttpError(
                status_code=e.response.status_code,
                reason=str(e.response.reason_phrase),
                body=e.response.text,
                url=str(e.request.url),
            ) from e

        except (httpx.NetworkError, httpx.TimeoutException) as e:
            raise HttpError(
                status_code=0,
                reason=str(e),
                body="",
                url=url,
            ) from e


# =============================================================================
# Mock Client for Testing
# =============================================================================


class MockHttpClient(HttpClient):
    """Mock HTTP client for testing.

    Returns predefined responses without making network requests.
    Tracks all requests made for test assertions.

    Example:
        >>> mock = MockHttpClient(status_code=200, json_response={"access_token": "test"})
        >>> response = mock.post("https://example.com", b"", {})
        >>> assert response.json()["access_token"] == "test"
        >>> assert len(mock.requests) == 1
    """

    def __init__(
        self,
        status_code: int = 200,
        json_response: dict[str, typing.Any] | None = None,
        text_response: str = "",
        raise_error: type[Exception] | None = None,
    ) -> None:
        """Initialize mock client.

        Args:
            status_code: HTTP status code to return
            json_response: JSON response body (converted to bytes)
            text_response: Text response body (used if json_response is None)
            raise_error: Exception to raise on every request (for testing errors)
        """
        self.status_code = status_code
        self.json_response = json_response
        self.text_response = text_response
        self.raise_error = raise_error

        # Track requests made
        self.requests: list[dict[str, typing.Any]] = []

    def post(
        self,
        url: str,
        data: bytes,
        headers: dict[str, str],
        timeout: float | None = None,
    ) -> HttpResponse:
        """Record request and return mock response."""
        # Track request
        self.requests.append(
            {
                "url": url,
                "data": data,
                "headers": headers,
                "timeout": timeout,
            }
        )

        # Raise error if configured
        if self.raise_error:
            raise self.raise_error

        # Build response body
        if self.json_response:
            body = json.dumps(self.json_response).encode()
        else:
            body = self.text_response.encode()

        # Create mock httpx.Response
        mock_response = httpx.Response(
            status_code=self.status_code,
            content=body,
            request=httpx.Request("POST", url),
        )

        return HttpResponse(mock_response)


__all__ = [
    "HttpClient",
    "HttpClientConfig",
    "HttpResponse",
    "HttpError",
    "HttpxHttpClient",
    "MockHttpClient",
]
