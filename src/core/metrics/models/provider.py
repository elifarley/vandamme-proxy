"""Provider/model aggregate metrics.

We track both total counts and a streaming vs non-streaming split.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProviderModelMetrics:
    """Metrics for a specific provider/model combination."""

    total_requests: int = 0
    total_errors: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_duration_ms: float = 0
    total_tool_uses: int = 0
    total_tool_results: int = 0
    total_tool_calls: int = 0

    streaming_requests: int = 0
    streaming_errors: int = 0
    streaming_input_tokens: int = 0
    streaming_output_tokens: int = 0
    streaming_cache_read_tokens: int = 0
    streaming_cache_creation_tokens: int = 0
    streaming_duration_ms: float = 0
    streaming_tool_uses: int = 0
    streaming_tool_results: int = 0
    streaming_tool_calls: int = 0

    non_streaming_requests: int = 0
    non_streaming_errors: int = 0
    non_streaming_input_tokens: int = 0
    non_streaming_output_tokens: int = 0
    non_streaming_cache_read_tokens: int = 0
    non_streaming_cache_creation_tokens: int = 0
    non_streaming_duration_ms: float = 0
    non_streaming_tool_uses: int = 0
    non_streaming_tool_results: int = 0
    non_streaming_tool_calls: int = 0
