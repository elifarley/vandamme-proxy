"""Summary metrics models.

SummaryMetrics accumulates completed-request metrics; RunningTotals is a
hierarchical output container used by the metrics endpoint.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .provider import ProviderModelMetrics
from .request import RequestMetrics


@dataclass
class SummaryMetrics:
    """Accumulated metrics across completed requests.

    Note:
        The legacy `src.core.logging` module exposed a filtered totals API.
        We keep an equivalent method here for unit tests and any internal
        consumers that want a *flat* (non-hierarchical) summary.
    """

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

    model_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    error_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    provider_model_metrics: dict[str, ProviderModelMetrics] = field(
        default_factory=lambda: defaultdict(ProviderModelMetrics)
    )

    def add_request(self, metrics: RequestMetrics) -> None:
        """Aggregate a completed request into summary totals."""

        self.total_requests += 1
        self.total_input_tokens += metrics.input_tokens
        self.total_output_tokens += metrics.output_tokens
        self.total_cache_read_tokens += metrics.cache_read_tokens
        self.total_cache_creation_tokens += metrics.cache_creation_tokens
        self.total_duration_ms += metrics.duration_ms
        self.total_tool_uses += metrics.tool_use_count
        self.total_tool_results += metrics.tool_result_count
        self.total_tool_calls += metrics.tool_call_count

        # Keep model_counts keyed by actual model (not provider-prefixed strings).
        if metrics.openai_model:
            model_key = metrics.openai_model
            if ":" in model_key:
                _, model_key = model_key.split(":", 1)
            self.model_counts[model_key] += 1

        if metrics.error:
            self.total_errors += 1
            self.error_counts[metrics.error_type or "unknown"] += 1

        # IMPORTANT: Keep provider/model keys canonical.
        #
        # `metrics.openai_model` is the resolved model name from the provider.
        # It does NOT contain a provider prefix - that was stripped during model
        # resolution. The model name may legitimately contain colons (e.g., OpenRouter
        # models like "kwaipilot/kat-coder-pro:free" or
        # "anthropic/claude-3-5-sonnet:context-flash").
        #
        # Canonical rule:
        # - bucket key is always "{provider}:{resolved_model}" when both exist
        # - otherwise fall back to provider or model or "unknown"
        model_name = metrics.openai_model

        provider_key = (
            f"{metrics.provider}:{model_name}"
            if metrics.provider and model_name
            else metrics.provider or model_name or "unknown"
        )

        pm = self.provider_model_metrics[provider_key]
        pm.total_requests += 1
        pm.total_input_tokens += metrics.input_tokens
        pm.total_output_tokens += metrics.output_tokens
        pm.total_cache_read_tokens += metrics.cache_read_tokens
        pm.total_cache_creation_tokens += metrics.cache_creation_tokens
        pm.total_duration_ms += metrics.duration_ms
        pm.total_tool_uses += metrics.tool_use_count
        pm.total_tool_results += metrics.tool_result_count
        pm.total_tool_calls += metrics.tool_call_count

        if metrics.error:
            pm.total_errors += 1

        if metrics.is_streaming:
            pm.streaming_requests += 1
            pm.streaming_input_tokens += metrics.input_tokens
            pm.streaming_output_tokens += metrics.output_tokens
            pm.streaming_cache_read_tokens += metrics.cache_read_tokens
            pm.streaming_cache_creation_tokens += metrics.cache_creation_tokens
            pm.streaming_duration_ms += metrics.duration_ms
            pm.streaming_tool_uses += metrics.tool_use_count
            pm.streaming_tool_results += metrics.tool_result_count
            pm.streaming_tool_calls += metrics.tool_call_count
            if metrics.error:
                pm.streaming_errors += 1
        else:
            pm.non_streaming_requests += 1
            pm.non_streaming_input_tokens += metrics.input_tokens
            pm.non_streaming_output_tokens += metrics.output_tokens
            pm.non_streaming_cache_read_tokens += metrics.cache_read_tokens
            pm.non_streaming_cache_creation_tokens += metrics.cache_creation_tokens
            pm.non_streaming_duration_ms += metrics.duration_ms
            pm.non_streaming_tool_uses += metrics.tool_use_count
            pm.non_streaming_tool_results += metrics.tool_result_count
            pm.non_streaming_tool_calls += metrics.tool_call_count
            if metrics.error:
                pm.non_streaming_errors += 1

    def get_running_totals(
        self, *, provider_filter: str | None = None, model_filter: str | None = None
    ) -> dict[str, object]:
        """Return a flat summary of completed request totals with optional filtering.

        This mirrors the legacy `RequestTracker.get_filtered_running_totals(...)` behavior,
        but only considers *completed* requests (active requests are included in the
        hierarchical endpoint output).
        """

        filtered = ProviderModelMetrics()
        provider_model_distribution: list[dict[str, object]] = []

        for provider_model_key, pm in self.provider_model_metrics.items():
            provider, model = (
                provider_model_key.split(":", 1)
                if ":" in provider_model_key
                else (provider_model_key, None)
            )

            if provider_filter and provider != provider_filter:
                continue
            if model_filter and model != model_filter:
                continue

            filtered.total_requests += pm.total_requests
            filtered.total_errors += pm.total_errors
            filtered.total_input_tokens += pm.total_input_tokens
            filtered.total_output_tokens += pm.total_output_tokens
            filtered.total_cache_read_tokens += pm.total_cache_read_tokens
            filtered.total_cache_creation_tokens += pm.total_cache_creation_tokens
            filtered.total_duration_ms += pm.total_duration_ms
            filtered.total_tool_uses += pm.total_tool_uses
            filtered.total_tool_results += pm.total_tool_results
            filtered.total_tool_calls += pm.total_tool_calls

            avg_duration = (
                pm.total_duration_ms / max(1, pm.total_requests) if pm.total_requests > 0 else 0
            )
            provider_model_distribution.append(
                {
                    "provider_model": provider_model_key,
                    "total_requests": pm.total_requests,
                    "total_errors": pm.total_errors,
                    "total_input_tokens": pm.total_input_tokens,
                    "total_output_tokens": pm.total_output_tokens,
                    "total_cache_read_tokens": pm.total_cache_read_tokens,
                    "total_cache_creation_tokens": pm.total_cache_creation_tokens,
                    "total_tool_uses": pm.total_tool_uses,
                    "total_tool_results": pm.total_tool_results,
                    "total_tool_calls": pm.total_tool_calls,
                    "average_duration_ms": avg_duration,
                }
            )

        avg_duration_ms = (
            filtered.total_duration_ms / max(1, filtered.total_requests)
            if filtered.total_requests > 0
            else 0
        )

        return {
            "total_requests": filtered.total_requests,
            "total_errors": filtered.total_errors,
            "total_input_tokens": filtered.total_input_tokens,
            "total_output_tokens": filtered.total_output_tokens,
            "total_cache_read_tokens": filtered.total_cache_read_tokens,
            "total_cache_creation_tokens": filtered.total_cache_creation_tokens,
            "total_tool_uses": filtered.total_tool_uses,
            "total_tool_results": filtered.total_tool_results,
            "total_tool_calls": filtered.total_tool_calls,
            "provider_model_distribution": provider_model_distribution,
            "average_duration_ms": avg_duration_ms,
        }


@dataclass
class RunningTotals:
    """Running totals output container with hierarchical provider structure."""

    last_accessed: dict[str, str] | None = None
    total_requests: int = 0
    total_errors: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_tool_uses: int = 0
    total_tool_results: int = 0
    total_tool_calls: int = 0
    active_requests: int = 0
    average_duration_ms: float = 0.0

    providers: dict[str, dict[str, object]] = field(default_factory=dict)
