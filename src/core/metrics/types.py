"""Typed outputs for metrics APIs.

We keep these in a dedicated module so they can be imported without pulling in
tracker logic (useful for API layers and tests).
"""

from __future__ import annotations

from typing import Any, TypedDict

from typing_extensions import NotRequired


class HierarchicalData(TypedDict):
    """Final hierarchical output structure returned by RequestTracker."""

    last_accessed: NotRequired[dict[str, str] | None]
    total_requests: int
    total_errors: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_creation_tokens: int
    total_tool_uses: int
    total_tool_results: int
    total_tool_calls: int
    active_requests: int
    average_duration_ms: float

    providers: dict[str, dict[str, Any]]
