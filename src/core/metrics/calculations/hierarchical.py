"""Hierarchical rollup helpers.

These helpers build the provider -> models schema consumed by the YAML
formatter.
"""

from __future__ import annotations

import fnmatch
from typing import Any, cast

from ..models.provider import ProviderModelMetrics
from ..models.request import RequestMetrics
from ..models.summary import RunningTotals
from ..types import HierarchicalData
from .accumulation import accumulate_from_provider_metrics, new_streaming_split
from .duration import finalize_split


def matches_pattern(text: str, pattern: str) -> bool:
    """Case-insensitive wildcard matcher supporting * and ?."""

    if not pattern or not text:
        return False
    return fnmatch.fnmatch(text.lower(), pattern.lower())


def new_provider_entry(last_accessed: str | None) -> dict[str, Any]:
    return {"last_accessed": last_accessed, "rollup": new_streaming_split(), "models": {}}


def new_model_entry(last_accessed: str | None) -> dict[str, Any]:
    return {"last_accessed": last_accessed, **new_streaming_split()}


def add_active_request_to_split(
    split: dict[str, dict[str, float | int]], metrics: RequestMetrics
) -> None:
    def add(target: dict[str, float | int]) -> None:
        target["requests"] += 1
        if metrics.error:
            target["errors"] += 1
        target["input_tokens"] += int(metrics.input_tokens or 0)
        target["output_tokens"] += int(metrics.output_tokens or 0)
        target["cache_read_tokens"] += int(metrics.cache_read_tokens or 0)
        target["cache_creation_tokens"] += int(metrics.cache_creation_tokens or 0)
        target["tool_uses"] += int(metrics.tool_use_count or 0)
        target["tool_results"] += int(metrics.tool_result_count or 0)
        target["tool_calls"] += int(metrics.tool_call_count or 0)
        target["total_duration_ms"] += float(metrics.duration_ms or 0)

    add(split["total"])
    add(split["streaming"] if metrics.is_streaming else split["non_streaming"])


def accumulate_pm_into_provider_and_model(
    provider_entry: dict[str, Any], model_entry: dict[str, Any], pm: ProviderModelMetrics
) -> None:
    provider_rollup = cast(dict[str, dict[str, float | int]], provider_entry["rollup"])
    accumulate_from_provider_metrics(provider_rollup["total"], pm, kind="total")
    accumulate_from_provider_metrics(provider_rollup["streaming"], pm, kind="streaming")
    accumulate_from_provider_metrics(provider_rollup["non_streaming"], pm, kind="non_streaming")

    for kind in ("total", "streaming", "non_streaming"):
        accumulate_from_provider_metrics(
            cast(dict[str, float | int], model_entry[kind]), pm, kind=kind
        )  # type: ignore[arg-type]


def sum_split_into_running_totals(
    running_totals: RunningTotals, split: dict[str, dict[str, float | int]]
) -> None:
    total = split["total"]
    running_totals.total_requests += int(total["requests"])
    running_totals.total_errors += int(total["errors"])
    running_totals.total_input_tokens += int(total["input_tokens"])
    running_totals.total_output_tokens += int(total["output_tokens"])
    running_totals.total_cache_read_tokens += int(total["cache_read_tokens"])
    running_totals.total_cache_creation_tokens += int(total["cache_creation_tokens"])
    running_totals.total_tool_uses += int(total["tool_uses"])
    running_totals.total_tool_results += int(total["tool_results"])
    running_totals.total_tool_calls += int(total["tool_calls"])


def finalize_running_totals(running_totals: RunningTotals) -> HierarchicalData:
    """Finalize averages and return the TypedDict expected by the API."""

    total_duration_ms = 0.0

    for provider_entry in running_totals.providers.values():
        provider_entry_dict = cast(dict[str, Any], provider_entry)
        provider_rollup = cast(dict[str, dict[str, float | int]], provider_entry_dict["rollup"])

        total_duration_ms += float(provider_rollup["total"]["total_duration_ms"])
        finalize_split(provider_rollup)

        for model_entry in cast(dict[str, Any], provider_entry_dict.get("models", {})).values():
            finalize_split(cast(dict[str, dict[str, float | int]], model_entry))

        sum_split_into_running_totals(running_totals, provider_rollup)

    if running_totals.total_requests > 0:
        running_totals.average_duration_ms = int(
            round(total_duration_ms / max(1, running_totals.total_requests))
        )
    else:
        running_totals.average_duration_ms = 0

    return {
        "last_accessed": running_totals.last_accessed,
        "total_requests": running_totals.total_requests,
        "total_errors": running_totals.total_errors,
        "total_input_tokens": running_totals.total_input_tokens,
        "total_output_tokens": running_totals.total_output_tokens,
        "total_cache_read_tokens": running_totals.total_cache_read_tokens,
        "total_cache_creation_tokens": running_totals.total_cache_creation_tokens,
        "total_tool_uses": running_totals.total_tool_uses,
        "total_tool_results": running_totals.total_tool_results,
        "total_tool_calls": running_totals.total_tool_calls,
        "active_requests": running_totals.active_requests,
        "average_duration_ms": running_totals.average_duration_ms,
        "providers": running_totals.providers,
    }
