"""Error type enumeration for Vandamme Proxy.

Provides type-safe error categorization for metrics and error responses.
"""

from enum import Enum


class ErrorType(str, Enum):
    """Error type categories for metrics and error responses.

    These error types are used throughout the codebase for:
    - RequestMetrics.error_type field
    - SSE error events (type field)
    - Error aggregation and reporting

    When adding new error types:
    1. Add the enum value here
    2. Update error_counts aggregation if needed
    3. Document when the error type is used
    """

    # Request lifecycle errors
    CANCELLED = "cancelled"  # Request cancelled by client or server
    TIMEOUT = "timeout"  # Request timeout
    UPSTREAM_TIMEOUT = "upstream_timeout"  # Upstream provider timeout
    CLIENT_DISCONNECT = "client_disconnect"  # Client disconnected mid-stream

    # HTTP/API errors
    HTTP_ERROR = "http_error"  # Generic HTTP error
    UPSTREAM_HTTP_ERROR = "upstream_http_error"  # Upstream HTTP error
    API_ERROR = "api_error"  # Generic API error
    UPSTREAM_ERROR = "upstream_error"  # Generic upstream error

    # Authentication/rate limiting
    AUTH_ERROR = "auth_error"  # Authentication/authorization failure
    RATE_LIMIT = "rate_limit"  # Rate limit exceeded
    BAD_REQUEST = "bad_request"  # Invalid request

    # Streaming errors
    STREAMING_ERROR = "streaming_error"  # Generic streaming error

    # Catch-all
    UNEXPECTED_ERROR = "unexpected_error"  # Unhandled/unexpected error
