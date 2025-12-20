"""Pure accumulation helpers for metrics.

These functions are intentionally kept free of RequestTracker state so they can
be tested in isolation.
"""

from __future__ import annotations

from typing import Literal

from ..models.provider import ProviderModelMetrics

Totals = dict[str, float | int]
Split = dict[str, Totals]
Kind = Literal["total", "streaming", "non_streaming"]


def new_metric_totals() -> Totals:
    return {
        "requests": 0,
        "errors": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "tool_uses": 0,
        "tool_results": 0,
        "tool_calls": 0,
        "total_duration_ms": 0.0,
        "average_duration_ms": 0,
    }


def new_streaming_split() -> dict[str, Totals]:
    return {
        "total": new_metric_totals(),
        "streaming": new_metric_totals(),
        "non_streaming": new_metric_totals(),
    }


def accumulate_from_provider_metrics(
    target: Totals, pm: ProviderModelMetrics, *, kind: Kind
) -> None:
    """Accumulate ProviderModelMetrics into a totals dict."""

    if kind == "total":
        target["requests"] += pm.total_requests
        target["errors"] += pm.total_errors
        target["input_tokens"] += pm.total_input_tokens
        target["output_tokens"] += pm.total_output_tokens
        target["cache_read_tokens"] += pm.total_cache_read_tokens
        target["cache_creation_tokens"] += pm.total_cache_creation_tokens
        target["tool_uses"] += pm.total_tool_uses
        target["tool_results"] += pm.total_tool_results
        target["tool_calls"] += pm.total_tool_calls
        target["total_duration_ms"] += pm.total_duration_ms
        return

    if kind == "streaming":
        target["requests"] += pm.streaming_requests
        target["errors"] += pm.streaming_errors
        target["input_tokens"] += pm.streaming_input_tokens
        target["output_tokens"] += pm.streaming_output_tokens
        target["cache_read_tokens"] += pm.streaming_cache_read_tokens
        target["cache_creation_tokens"] += pm.streaming_cache_creation_tokens
        target["tool_uses"] += pm.streaming_tool_uses
        target["tool_results"] += pm.streaming_tool_results
        target["tool_calls"] += pm.streaming_tool_calls
        target["total_duration_ms"] += pm.streaming_duration_ms
        return

    # non_streaming
    target["requests"] += pm.non_streaming_requests
    target["errors"] += pm.non_streaming_errors
    target["input_tokens"] += pm.non_streaming_input_tokens
    target["output_tokens"] += pm.non_streaming_output_tokens
    target["cache_read_tokens"] += pm.non_streaming_cache_read_tokens
    target["cache_creation_tokens"] += pm.non_streaming_cache_creation_tokens
    target["tool_uses"] += pm.non_streaming_tool_uses
    target["tool_results"] += pm.non_streaming_tool_results
    target["tool_calls"] += pm.non_streaming_tool_calls
    target["total_duration_ms"] += pm.non_streaming_duration_ms
