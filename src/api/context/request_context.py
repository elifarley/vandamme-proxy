"""Request context dataclass for encapsulating request processing data."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, cast

from src.models.claude import ClaudeMessagesRequest


@dataclass(frozen=True)
class RequestContext:
    """Immutable context object encapsulating all request-related data.

    This eliminates the 13-16 parameter passing anti-pattern by providing
    a single, well-structured object that handlers can access.

    Design decisions:
    - frozen=True: Ensures immutability for thread safety
    - No builder pattern: Simpler, Pythonic construction is sufficient
    - Computed properties: For derived values (avoids redundancy)
    """

    # === Core Request ===
    request: ClaudeMessagesRequest  # Original Claude request
    openai_request: dict[str, Any]  # Converted OpenAI format

    # === Identity & Tracking ===
    request_id: str
    http_request: Any  # FastAPI Request

    # === Provider Context ===
    provider_name: str
    resolved_model: str
    provider_config: Any  # ProviderConfig

    # === Authentication ===
    client_api_key: str | None
    provider_api_key: str | None

    # === Tool Mapping ===
    tool_name_map_inverse: dict[str, str] | None

    # === Clients ===
    openai_client: Any  # OpenAI/Anthropic client

    # === Metrics & Tracking ===
    metrics: Any | None  # RequestMetrics (may be None if disabled)
    tracker: Any  # RequestTracker (may be None if metrics disabled)
    config: Any  # Application config

    # === Timing & Size (for non-streaming) ===
    start_time: float
    tool_use_count: int
    tool_result_count: int
    request_size: int
    message_count: int

    # === Computed Properties ===
    @property
    def is_streaming(self) -> bool:
        """Check if this is a streaming request."""
        return self.request.stream or False

    @property
    def is_metrics_enabled(self) -> bool:
        """Check if metrics tracking is enabled."""
        return self.metrics is not None

    @property
    def uses_passthrough(self) -> bool:
        """Check if provider uses client API key passthrough."""
        return self.provider_config.uses_passthrough if self.provider_config else False

    @property
    def is_anthropic_format(self) -> bool:
        """Check if provider uses Anthropic API format."""
        return self.provider_config.is_anthropic_format if self.provider_config else False

    @property
    def openai_messages(self) -> list[dict[str, Any]]:
        """Get messages from OpenAI request."""
        messages = self.openai_request.get("messages", [])
        # The dict stores lists, but type checker needs explicit cast
        if isinstance(messages, list):
            return messages  # type: ignore[return-value]
        return []

    # === Convenience Methods ===
    def with_updates(self, **kwargs: Any) -> RequestContext:
        """Create a new context with specified fields updated.

        Since we're frozen, this creates a new instance with updated values.
        Useful for middleware or step-by-step construction.
        """
        return replace(self, **kwargs)


@dataclass
class RequestContextBuilder:
    """Builder for RequestContext to enable gradual construction.

    This allows the orchestrator to build the context incrementally
    without requiring all parameters at once.
    """

    request: ClaudeMessagesRequest | None = None
    openai_request: dict[str, Any] | None = None
    request_id: str | None = None
    http_request: Any = None
    provider_name: str | None = None
    resolved_model: str | None = None
    provider_config: Any = None
    client_api_key: str | None = None
    provider_api_key: str | None = None
    tool_name_map_inverse: dict[str, str] | None = None
    openai_client: Any = None
    metrics: Any | None = None
    tracker: Any = None
    config: Any = None
    start_time: float = 0.0
    tool_use_count: int = 0
    tool_result_count: int = 0
    request_size: int = 0
    message_count: int = 0

    def with_request(self, request: ClaudeMessagesRequest) -> RequestContextBuilder:
        self.request = request
        return self

    def with_openai_request(self, openai_request: dict[str, Any]) -> RequestContextBuilder:
        self.openai_request = openai_request
        return self

    def with_request_id(self, request_id: str) -> RequestContextBuilder:
        self.request_id = request_id
        return self

    def with_http_request(self, http_request: Any) -> RequestContextBuilder:
        self.http_request = http_request
        return self

    def with_provider(
        self,
        provider_name: str,
        resolved_model: str,
        provider_config: Any,
    ) -> RequestContextBuilder:
        self.provider_name = provider_name
        self.resolved_model = resolved_model
        self.provider_config = provider_config
        return self

    def with_auth(
        self,
        client_api_key: str | None,
        provider_api_key: str | None,
    ) -> RequestContextBuilder:
        self.client_api_key = client_api_key
        self.provider_api_key = provider_api_key
        return self

    def with_tool_mapping(
        self, tool_name_map_inverse: dict[str, str] | None
    ) -> RequestContextBuilder:
        self.tool_name_map_inverse = tool_name_map_inverse
        return self

    def with_client(self, openai_client: Any) -> RequestContextBuilder:
        self.openai_client = openai_client
        return self

    def with_metrics(
        self,
        metrics: Any | None,
        tracker: Any,
        config: Any,
    ) -> RequestContextBuilder:
        self.metrics = metrics
        self.tracker = tracker
        self.config = config
        return self

    def with_timing(
        self,
        start_time: float,
        tool_use_count: int,
        tool_result_count: int,
        request_size: int,
        message_count: int,
    ) -> RequestContextBuilder:
        self.start_time = start_time
        self.tool_use_count = tool_use_count
        self.tool_result_count = tool_result_count
        self.request_size = request_size
        self.message_count = message_count
        return self

    def build(self) -> RequestContext:
        """Build the RequestContext with all required fields.

        Raises:
            ValueError: If required fields are missing.
        """
        # Validate required fields
        required_fields = {
            "request": self.request,
            "openai_request": self.openai_request,
            "request_id": self.request_id,
            "provider_name": self.provider_name,
            "resolved_model": self.resolved_model,
            "provider_config": self.provider_config,
        }
        missing = [name for name, value in required_fields.items() if value is None]
        if missing:
            raise ValueError(f"Missing required fields for RequestContext: {missing}")

        # Cast to non-None types after validation (mypy doesn't track validation)
        return RequestContext(
            request=cast(ClaudeMessagesRequest, self.request),
            openai_request=cast(dict[str, Any], self.openai_request),
            request_id=cast(str, self.request_id),
            http_request=self.http_request,
            provider_name=cast(str, self.provider_name),
            resolved_model=cast(str, self.resolved_model),
            provider_config=self.provider_config,
            client_api_key=self.client_api_key,
            provider_api_key=self.provider_api_key,
            tool_name_map_inverse=self.tool_name_map_inverse,
            openai_client=self.openai_client,
            metrics=self.metrics,
            tracker=self.tracker,
            config=self.config,
            start_time=self.start_time,
            tool_use_count=self.tool_use_count,
            tool_result_count=self.tool_result_count,
            request_size=self.request_size,
            message_count=self.message_count,
        )
