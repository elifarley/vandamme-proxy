"""Request-level metrics model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class RequestMetrics:
    """Metrics for a single request.

    Notes:
        - `start_time`/`end_time` are unix timestamps.
        - Some upstreams do not report all token types; keep counters defaulting
          to 0 rather than None for simpler aggregation.
    """

    request_id: str
    start_time: float
    end_time: float | None = None
    claude_model: str | None = None
    openai_model: str | None = None
    provider: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    message_count: int = 0
    request_size: int = 0
    response_size: int = 0
    is_streaming: bool = False
    error: str | None = None
    error_type: str | None = None
    tool_use_count: int = 0
    tool_result_count: int = 0
    tool_call_count: int = 0

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return 0
        return (self.end_time - self.start_time) * 1000

    @property
    def start_time_iso(self) -> str:
        """Render `start_time` as an ISO-like string with second precision."""

        try:
            # Unix timestamp range: -62135596800 to 253402300799
            if not (-62135596800 <= self.start_time <= 253402300799):
                return "N/A"
            return datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%dT%H:%M:%S")
        except (ValueError, OSError, OverflowError):
            return "N/A"
