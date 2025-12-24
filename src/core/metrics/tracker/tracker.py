"""RequestTracker: in-memory request metrics aggregation.

Educational overview
--------------------
The tracker has two kinds of state:

1) **Active requests** (in-flight)
   - stored in `active_requests`
   - updated as streaming responses progress

2) **Completed requests**
   - aggregated into `summary_metrics`
   - also reflected in hierarchical rollups for reporting

The tracker is intentionally process-local. In production, this means metrics are
per-process (and reset on restart). This matches the existing behavior.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, cast

from src.core.logging import ConversationLogger

from ..calculations.hierarchical import (
    accumulate_pm_into_provider_and_model,
    add_active_request_to_split,
    finalize_running_totals,
    matches_pattern,
    new_model_entry,
    new_provider_entry,
)
from ..models.request import RequestMetrics
from ..models.summary import RunningTotals, SummaryMetrics
from ..types import HierarchicalData


class RequestTracker:
    """Track request metrics within a single process."""

    def __init__(self, *, summary_interval: int) -> None:
        self._lock = asyncio.Lock()

        self.active_requests: dict[str, RequestMetrics] = {}
        self.summary_metrics = SummaryMetrics()
        self.summary_interval = summary_interval

        self.request_count = 0
        self.total_completed_requests = 0

        # Dashboard-facing observability buffers (process-local).
        self._recent_errors: deque[dict[str, object]] = deque(maxlen=100)
        self._recent_traces: deque[dict[str, object]] = deque(maxlen=200)

        self._trace_seq: int = 0
        self._error_seq: int = 0

        self._last_error_seen_seq: int = 0
        self._last_trace_seen_seq: int = 0

        # last_accessed timestamps are emitted by providers/models and updated
        # when activity is observed.
        self.last_accessed_timestamps: dict[str, dict[str, str] | str | None] = {
            "models": {},
            "providers": {},
            "top": None,
        }

        self._logger = ConversationLogger.get_logger()

    async def start_request(
        self,
        request_id: str,
        claude_model: str,
        is_streaming: bool = False,
        *,
        provider: str | None = None,
        resolved_model: str | None = None,
    ) -> RequestMetrics:
        """Register a new active request.

        Note: We accept (provider, resolved_model) so the dashboard's *active request*
        display can use canonical model names immediately, rather than showing transient
        alias strings until the request completes.
        """

        metrics = RequestMetrics(
            request_id=request_id,
            start_time=time.time(),
            claude_model=claude_model,
            is_streaming=is_streaming,
        )
        if provider:
            metrics.provider = provider
        if resolved_model:
            metrics.openai_model = resolved_model
        async with self._lock:
            self.active_requests[request_id] = metrics
        return metrics

    async def end_request(self, request_id: str, **kwargs: Any) -> None:
        """Finalize a request and aggregate it into completed metrics."""

        async with self._lock:
            metrics = self.active_requests.get(request_id)
            if metrics is None:
                return

            metrics.end_time = time.time()

            for key, value in kwargs.items():
                if hasattr(metrics, key):
                    setattr(metrics, key, value)

            self.summary_metrics.add_request(metrics)

            # Record dashboard-facing trace/error events.
            provider = metrics.provider or "unknown"
            model = metrics.openai_model or metrics.claude_model or "unknown"
            if model and ":" in model:
                # Strip provider prefix if present (provider:model).
                _, model = model.split(":", 1)

            self._trace_seq += 1
            trace_entry: dict[str, object] = {
                "seq": self._trace_seq,
                "ts": metrics.end_time,
                "request_id": metrics.request_id,
                "provider": provider,
                "model": model,
                "is_streaming": metrics.is_streaming,
                "duration_ms": metrics.duration_ms,
                "input_tokens": metrics.input_tokens,
                "output_tokens": metrics.output_tokens,
                "cache_read_tokens": metrics.cache_read_tokens,
                "cache_creation_tokens": metrics.cache_creation_tokens,
                "tool_use_count": metrics.tool_use_count,
                "tool_call_count": metrics.tool_call_count,
                "tool_result_count": metrics.tool_result_count,
                "status": "error" if metrics.error else "ok",
                "error": metrics.error,
                "error_type": metrics.error_type,
            }
            self._recent_traces.appendleft(trace_entry)
            self._last_trace_seen_seq = self._trace_seq

            if metrics.error:
                self._error_seq += 1
                error_entry = {
                    **trace_entry,
                    "seq": self._error_seq,
                }
                self._recent_errors.appendleft(error_entry)
                self._last_error_seen_seq = self._error_seq

            self.request_count += 1
            self.total_completed_requests += 1

            if self.request_count % self.summary_interval == 0:
                self._emit_summary_locked()

            del self.active_requests[request_id]

    async def get_request(self, request_id: str) -> RequestMetrics | None:
        async with self._lock:
            return self.active_requests.get(request_id)

    async def get_active_requests_snapshot(self) -> list[dict[str, object]]:
        """Return a snapshot of active requests suitable for dashboard display."""

        async with self._lock:
            now = time.time()
            rows: list[dict[str, object]] = []
            for m in self.active_requests.values():
                # Requested model is what the client sent.
                requested_model = m.claude_model or "unknown"
                resolved_model = m.openai_model or ""

                # Derive provider from the tracker if available; otherwise use the prefix
                # of the requested model.
                provider = m.provider
                if not provider and ":" in requested_model:
                    provider, _ = requested_model.split(":", 1)

                duration_ms = int(round((now - float(m.start_time)) * 1000))

                rows.append(
                    {
                        "request_id": m.request_id,
                        "provider": provider or "unknown",
                        "requested_model": requested_model,
                        "resolved_model": resolved_model,
                        "is_streaming": bool(m.is_streaming),
                        "start_time": float(m.start_time),
                        "duration_ms": duration_ms,
                        "input_tokens": int(m.input_tokens or 0),
                        "output_tokens": int(m.output_tokens or 0),
                        "cache_read_tokens": int(m.cache_read_tokens or 0),
                        "cache_creation_tokens": int(m.cache_creation_tokens or 0),
                        "tool_uses": int(m.tool_use_count or 0),
                        "tool_results": int(m.tool_result_count or 0),
                        "tool_calls": int(m.tool_call_count or 0),
                        "request_size": int(m.request_size or 0),
                        "message_count": int(m.message_count or 0),
                    }
                )

            # Most recent first.
            def _start_time_key(row: dict[str, object]) -> float:
                v = row.get("start_time")
                return float(v) if isinstance(v, float) else 0.0

            rows.sort(key=_start_time_key, reverse=True)
            return rows

    async def get_recent_errors(self, *, limit: int = 100) -> list[dict[str, object]]:
        async with self._lock:
            return list(self._recent_errors)[:limit]

    async def get_recent_traces(self, *, limit: int = 200) -> list[dict[str, object]]:
        async with self._lock:
            return list(self._recent_traces)[:limit]

    async def update_last_accessed(self, provider: str, model: str, timestamp: str) -> None:
        """Update last_accessed timestamps for provider, model, and top level."""

        if not timestamp or timestamp in ("N/A", "Invalid timestamp", None):
            return

        async with self._lock:
            model_key = f"{provider}:{model}"
            models_dict = cast(dict[str, str], self.last_accessed_timestamps["models"])
            models_dict[model_key] = timestamp

            providers_dict = cast(dict[str, str], self.last_accessed_timestamps["providers"])
            if provider in providers_dict:
                providers_dict[provider] = max(providers_dict[provider], timestamp)
            else:
                providers_dict[provider] = timestamp

            top_timestamp = cast(str | None, self.last_accessed_timestamps["top"])
            if top_timestamp:
                self.last_accessed_timestamps["top"] = max(top_timestamp, timestamp)
            else:
                self.last_accessed_timestamps["top"] = timestamp

    async def get_running_totals_hierarchical(
        self,
        *,
        provider_filter: str | None = None,
        model_filter: str | None = None,
        include_active: bool = True,
    ) -> HierarchicalData:
        """Return hierarchical provider->models metrics.

        By default, includes in-flight requests. The dashboard's provider/model breakdown
        wants *completed-only* semantics, so it can request include_active=False and use
        the dedicated Active Requests grid for in-flight visibility.
        """

        async with self._lock:
            all_completed = self.summary_metrics
            last_accessed_value = self.last_accessed_timestamps.get("top")

            if last_accessed_value is not None:
                running_totals = RunningTotals(
                    last_accessed={"top": str(last_accessed_value)},
                    active_requests=len(self.active_requests),
                )
            else:
                running_totals = RunningTotals(active_requests=len(self.active_requests))

            # Completed requests
            for provider_model_key, pm in all_completed.provider_model_metrics.items():
                provider, model = (
                    provider_model_key.split(":", 1)
                    if ":" in provider_model_key
                    else (provider_model_key, None)
                )

                # Normalize provider strings written in as "provider:model".
                # In completed metrics we store provider+model as a single key, but the
                # hierarchical view expects provider -> models nesting.
                if model and ":" in model:
                    provider, model = model.split(":", 1)

                # If a provider filter is applied, it should still match the resolved provider.

                if provider_filter and not matches_pattern(provider, provider_filter):
                    continue
                if model_filter and model and not matches_pattern(model, model_filter):
                    continue

                provider_entry = running_totals.providers.get(provider)
                if provider_entry is None:
                    provider_entry = new_provider_entry(
                        cast(dict[str, str], self.last_accessed_timestamps["providers"]).get(
                            provider
                        )
                    )
                    running_totals.providers[provider] = provider_entry

                if model is None:
                    # Provider-level traffic without a model attributed to rollup only.
                    rollup = cast(dict[str, dict[str, float | int]], provider_entry["rollup"])
                    for kind in ("total", "streaming", "non_streaming"):
                        from src.core.metrics.calculations.accumulation import (
                            accumulate_from_provider_metrics,
                        )

                        accumulate_from_provider_metrics(rollup[kind], pm, kind=kind)  # type: ignore[arg-type]
                else:
                    models = cast(dict[str, Any], provider_entry["models"])
                    if model not in models:
                        models[model] = new_model_entry(
                            cast(dict[str, str], self.last_accessed_timestamps["models"]).get(
                                f"{provider}:{model}"
                            )
                        )
                    model_entry = cast(dict[str, Any], models[model])
                    accumulate_pm_into_provider_and_model(provider_entry, model_entry, pm)

            if include_active:
                # Active requests
                for metrics in list(self.active_requests.values()):
                    provider = metrics.provider or "unknown"

                    # Prefer resolved model if available so we never surface alias tokens
                    # like "openrouter:cheap" while a request is in-flight.
                    model = metrics.openai_model or "unknown"
                    if model != "unknown" and ":" in model:
                        _, model = model.split(":", 1)
                    elif metrics.claude_model and ":" in metrics.claude_model:
                        _, model = metrics.claude_model.split(":", 1)
                    elif model == "unknown":
                        model = metrics.claude_model or "unknown"

                    if provider_filter and not matches_pattern(provider, provider_filter):
                        continue
                    if (
                        model_filter
                        and model != "unknown"
                        and not matches_pattern(model, model_filter)
                    ):
                        continue

                    running_totals.total_requests += 1
                    running_totals.total_input_tokens += int(metrics.input_tokens or 0)
                    running_totals.total_output_tokens += int(metrics.output_tokens or 0)
                    running_totals.total_cache_read_tokens += int(metrics.cache_read_tokens or 0)
                    running_totals.total_cache_creation_tokens += int(
                        metrics.cache_creation_tokens or 0
                    )
                    running_totals.total_tool_uses += int(metrics.tool_use_count or 0)
                    running_totals.total_tool_results += int(metrics.tool_result_count or 0)
                    running_totals.total_tool_calls += int(metrics.tool_call_count or 0)
                    if metrics.error:
                        running_totals.total_errors += 1

                    provider_entry = running_totals.providers.get(provider)
                    if provider_entry is None:
                        provider_entry = new_provider_entry(
                            cast(dict[str, str], self.last_accessed_timestamps["providers"]).get(
                                provider
                            )
                        )
                        running_totals.providers[provider] = provider_entry

                    rollup = cast(dict[str, dict[str, float | int]], provider_entry["rollup"])
                    add_active_request_to_split(rollup, metrics)

                    if model != "unknown":
                        models = cast(dict[str, Any], provider_entry["models"])
                        if model not in models:
                            models[model] = new_model_entry(
                                cast(dict[str, str], self.last_accessed_timestamps["models"]).get(
                                    f"{provider}:{model}"
                                )
                            )
                        add_active_request_to_split(
                            cast(dict[str, dict[str, float | int]], models[model]), metrics
                        )

            return finalize_running_totals(running_totals)

        raise RuntimeError("RequestTracker lock acquisition failed")

    def _emit_summary_locked(self) -> None:
        total_requests = max(1, self.summary_metrics.total_requests)
        avg_duration = self.summary_metrics.total_duration_ms / total_requests

        self._logger.info(
            " SUMMARY (last %s requests) | Total: %s | Errors: %s | Avg Duration: %.0fms | "
            "Input Tokens: %s | Output Tokens: %s | Cache Hits: %s | Cache Creation: %s | "
            "Tool Uses: %s | Tool Results: %s | Tool Calls: %s",
            self.summary_interval,
            self.summary_metrics.total_requests,
            self.summary_metrics.total_errors,
            avg_duration,
            f"{self.summary_metrics.total_input_tokens:,}",
            f"{self.summary_metrics.total_output_tokens:,}",
            f"{self.summary_metrics.total_cache_read_tokens:,}",
            f"{self.summary_metrics.total_cache_creation_tokens:,}",
            self.summary_metrics.total_tool_uses,
            self.summary_metrics.total_tool_results,
            self.summary_metrics.total_tool_calls,
        )

        if self.summary_metrics.model_counts:
            model_dist = " | ".join(
                [f"{m}: {c}" for m, c in self.summary_metrics.model_counts.items()]
            )
            self._logger.info(" MODELS | %s", model_dist)

        if self.summary_metrics.error_counts:
            error_dist = " | ".join(
                [f"{e}: {c}" for e, c in self.summary_metrics.error_counts.items()]
            )
            self._logger.warning(" ERRORS | %s", error_dist)

        self.summary_metrics = SummaryMetrics()
