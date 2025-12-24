from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricTotals:
    total_requests: int = 0
    total_errors: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    tool_calls: int = 0
    active_requests: int = 0
    average_duration_ms: float = 0.0
    total_duration_ms: float = 0.0
    streaming_average_duration_ms: float = 0.0
    non_streaming_average_duration_ms: float = 0.0
    last_accessed: str | None = None


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def error_rate(*, total_requests: int, total_errors: int) -> float:
    if total_requests <= 0:
        return 0.0
    return total_errors / total_requests


def detect_metrics_disabled(running_totals_yaml: dict[str, Any]) -> bool:
    # metrics endpoint returns "# Message" key when LOG_REQUEST_METRICS is disabled
    # src/api/metrics.py:37-44
    return "# Message" in running_totals_yaml and "disabled" in str(
        running_totals_yaml.get("# Message")
    )


def parse_metric_totals(running_totals_yaml: dict[str, Any]) -> MetricTotals:
    if detect_metrics_disabled(running_totals_yaml):
        return MetricTotals()

    # Extract metrics from the summary section
    summary = running_totals_yaml.get("summary", {})

    # Extract last_accessed from summary
    last_accessed_data = summary.get("last_accessed", {})
    last_accessed = last_accessed_data.get("top") if isinstance(last_accessed_data, dict) else None

    return MetricTotals(
        total_requests=_as_int(summary.get("total_requests")),
        total_errors=_as_int(summary.get("total_errors")),
        total_input_tokens=_as_int(summary.get("total_input_tokens")),
        total_output_tokens=_as_int(summary.get("total_output_tokens")),
        cache_read_tokens=_as_int(summary.get("cache_read_tokens")),
        cache_creation_tokens=_as_int(summary.get("cache_creation_tokens")),
        tool_calls=_as_int(
            summary.get("total_tool_calls")
            or summary.get("tool_calls")
            or summary.get("tool_uses")
            or summary.get("tool_results")
        ),
        active_requests=_as_int(summary.get("active_requests")),
        average_duration_ms=_as_float(summary.get("average_duration_ms")),
        total_duration_ms=_as_float(summary.get("total_duration_ms")),
        streaming_average_duration_ms=_as_float(summary.get("streaming_average_duration_ms")),
        non_streaming_average_duration_ms=_as_float(
            summary.get("non_streaming_average_duration_ms")
        ),
        last_accessed=last_accessed,
    )


def provider_rows(running_totals_yaml: dict[str, Any]) -> list[dict[str, Any]]:
    if detect_metrics_disabled(running_totals_yaml):
        return []

    providers = running_totals_yaml.get("providers")
    if not isinstance(providers, dict):
        return []

    rows: list[dict[str, Any]] = []
    for provider_name, pdata in providers.items():
        if not isinstance(pdata, dict):
            continue

        # Extract metrics from provider.rollup structure
        rollup = pdata.get("rollup", {})
        total_metrics = rollup.get("total", {})
        streaming_metrics = rollup.get("streaming", {})
        non_streaming_metrics = rollup.get("non_streaming", {})

        # Map keys from the actual data structure
        total_requests = _as_int(total_metrics.get("requests"))
        total_errors = _as_int(total_metrics.get("errors"))
        input_tokens = _as_int(total_metrics.get("input_tokens"))
        output_tokens = _as_int(total_metrics.get("output_tokens"))
        cache_read_tokens = _as_int(total_metrics.get("cache_read_tokens"))
        cache_creation_tokens = _as_int(total_metrics.get("cache_creation_tokens"))
        tool_calls = _as_int(
            total_metrics.get("tool_calls")
            or total_metrics.get("tool_uses")
            or total_metrics.get("tool_results")
        )

        # Extract timing metrics
        avg_duration = _as_float(rollup.get("avg_duration_ms"))
        total_duration_ms = _as_float(total_metrics.get("total_duration_ms"))
        streaming_avg_duration = _as_float(streaming_metrics.get("average_duration_ms"))
        non_streaming_avg_duration = _as_float(non_streaming_metrics.get("average_duration_ms"))

        # Extract last accessed timestamp
        last_accessed = pdata.get("last_accessed")

        rows.append(
            {
                "provider": str(provider_name),
                "requests": total_requests,
                "errors": total_errors,
                "error_rate": error_rate(total_requests=total_requests, total_errors=total_errors),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cache_creation_tokens": cache_creation_tokens,
                "tool_calls": tool_calls,
                "models": pdata.get("models", {}),
                "average_duration_ms": avg_duration,
                "total_duration_ms": total_duration_ms,
                "streaming_average_duration_ms": streaming_avg_duration,
                "non_streaming_average_duration_ms": non_streaming_avg_duration,
                "last_accessed": last_accessed,
            }
        )

    rows.sort(key=lambda r: (r.get("requests", 0), r.get("provider", "")), reverse=True)
    return rows


def model_rows_for_provider(provider_entry: dict[str, Any]) -> list[dict[str, Any]]:
    models = provider_entry.get("models")
    if not isinstance(models, dict):
        return []

    rows: list[dict[str, Any]] = []
    for model_name, mdata in models.items():
        if not isinstance(mdata, dict):
            continue

        # Extract metrics from model structure
        total_metrics = mdata.get("total", {})
        streaming_metrics = mdata.get("streaming", {})
        non_streaming_metrics = mdata.get("non_streaming", {})

        # Map keys from the actual data structure
        total_requests = _as_int(total_metrics.get("requests"))
        total_errors = _as_int(total_metrics.get("errors"))
        input_tokens = _as_int(total_metrics.get("input_tokens"))
        output_tokens = _as_int(total_metrics.get("output_tokens"))
        tool_calls = _as_int(
            total_metrics.get("tool_calls")
            or total_metrics.get("tool_uses")
            or total_metrics.get("tool_results")
        )

        # Extract timing metrics
        avg_duration = _as_float(total_metrics.get("average_duration_ms"))
        total_duration_ms = _as_float(total_metrics.get("total_duration_ms"))
        streaming_avg_duration = _as_float(streaming_metrics.get("average_duration_ms"))
        non_streaming_avg_duration = _as_float(non_streaming_metrics.get("average_duration_ms"))

        # Extract last accessed timestamp
        last_accessed = mdata.get("last_accessed")

        rows.append(
            {
                "model": str(model_name),
                "requests": total_requests,
                "errors": total_errors,
                "error_rate": error_rate(total_requests=total_requests, total_errors=total_errors),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "tool_calls": tool_calls,
                "average_duration_ms": avg_duration,
                "total_duration_ms": total_duration_ms,
                "streaming_average_duration_ms": streaming_avg_duration,
                "non_streaming_average_duration_ms": non_streaming_avg_duration,
                "last_accessed": last_accessed,
            }
        )

    rows.sort(key=lambda r: (r.get("requests", 0), r.get("model", "")), reverse=True)
    return rows
