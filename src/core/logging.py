import fnmatch
import hashlib
import logging
import os
import re
import threading
import time
from collections import defaultdict
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypedDict, cast

from typing_extensions import NotRequired

from src.core.config import config

# Parse log level - extract just the first word to handle comments
log_level = config.log_level.split()[0].upper()

# Validate and set default if invalid
valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
if log_level not in valid_levels:
    log_level = "INFO"


NOISY_HTTP_LOGGERS = (
    "openai",
    "httpx",
    "httpcore",
    "httpcore.http11",
    "httpcore.connection",
)


def set_noisy_http_logger_levels(current_log_level: str) -> None:
    """Ensure HTTP client noise only surfaces at DEBUG level."""

    noisy_level = logging.DEBUG if current_log_level == "DEBUG" else logging.WARNING
    for logger_name in NOISY_HTTP_LOGGERS:
        logging.getLogger(logger_name).setLevel(noisy_level)


def get_api_key_hash(api_key: str) -> str:
    """Return first 8 chars of sha256 hash for API keys"""
    if not api_key or api_key == "REDACTED":
        return "REDACTED"
    return hashlib.sha256(api_key.encode()).hexdigest()[:8]


def hash_api_keys_in_message(message: str) -> str:
    """Replace API keys in log messages with their hashes"""
    if not message:
        return message

    # Pattern for API keys in various formats
    # Matches: sk-xxx, Bearer xxx, x-api-key: xxx, Authorization: xxx
    patterns = [
        (r"(sk-[a-zA-Z0-9]{20,})", lambda m: f"sk-{get_api_key_hash(m.group(1)[3:])}"),
        (
            r"(Bearer\s+[a-zA-Z0-9\-_\.]{20,})",
            lambda m: f"Bearer {get_api_key_hash(m.group(0)[7:])}",
        ),
        (
            r"(x-api-key:\s*[a-zA-Z0-9\-_\.]{20,})",
            lambda m: f"x-api-key: {get_api_key_hash(m.group(0)[11:])}",
        ),
        (
            r'("api_key":\s*"[a-zA-Z0-9\-_\.]{20,}")',
            lambda m: f'"api_key": "{get_api_key_hash(m.group(0)[13:-1])}"',
        ),
    ]

    for pattern, replacement in patterns:
        message = re.sub(pattern, replacement, message, flags=re.IGNORECASE)

    return message


# Custom formatter that hashes API keys
class HashingFormatter(logging.Formatter):
    """Formatter that automatically hashes API keys in log messages"""

    def format(self, record: logging.LogRecord) -> str:
        # Get the original formatted message
        message = super().format(record)

        # Hash API keys in the message
        return hash_api_keys_in_message(message)


# Enhanced Logging Infrastructure
@dataclass
class RequestMetrics:
    """Metrics for a single request"""

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
    request_size: int = 0  # bytes
    response_size: int = 0  # bytes
    is_streaming: bool = False
    error: str | None = None
    error_type: str | None = None
    tool_use_count: int = 0  # Number of tool_use blocks in the request
    tool_result_count: int = 0  # Number of tool_result blocks in the request
    tool_call_count: int = 0  # Number of tool calls made (OpenAI function calls)

    @property
    def duration_ms(self) -> float:
        """Request duration in milliseconds"""
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0

    @property
    def start_time_iso(self) -> str:
        """Get start time as ISO format with second precision"""
        return datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class ProviderModelMetrics:
    """Metrics for a specific provider/model combination"""

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


@dataclass
class SummaryMetrics:
    """Accumulated metrics for summary"""

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
        """Add request metrics to summary"""
        self.total_requests += 1
        self.total_input_tokens += metrics.input_tokens
        self.total_output_tokens += metrics.output_tokens
        self.total_cache_read_tokens += metrics.cache_read_tokens
        self.total_cache_creation_tokens += metrics.cache_creation_tokens
        self.total_duration_ms += metrics.duration_ms
        self.total_tool_uses += metrics.tool_use_count
        self.total_tool_results += metrics.tool_result_count
        self.total_tool_calls += metrics.tool_call_count

        if metrics.openai_model:
            self.model_counts[metrics.openai_model] += 1

        if metrics.error:
            self.total_errors += 1
            error_key = metrics.error_type or "unknown"
            self.error_counts[error_key] += 1

        # Track metrics by provider/model combination
        # Ensure openai_model doesn't already have provider prefix
        if metrics.openai_model and ":" in metrics.openai_model:
            # If openai_model already has prefix, use it directly
            provider_key = metrics.openai_model
        elif metrics.provider and metrics.openai_model:
            provider_key = f"{metrics.provider}:{metrics.openai_model}"
        else:
            provider_key = metrics.provider or metrics.openai_model or "unknown"
        pm_metrics = self.provider_model_metrics[provider_key]
        pm_metrics.total_requests += 1
        pm_metrics.total_input_tokens += metrics.input_tokens
        pm_metrics.total_output_tokens += metrics.output_tokens
        pm_metrics.total_cache_read_tokens += metrics.cache_read_tokens
        pm_metrics.total_cache_creation_tokens += metrics.cache_creation_tokens
        pm_metrics.total_duration_ms += metrics.duration_ms
        pm_metrics.total_tool_uses += metrics.tool_use_count
        pm_metrics.total_tool_results += metrics.tool_result_count
        pm_metrics.total_tool_calls += metrics.tool_call_count

        if metrics.error:
            pm_metrics.total_errors += 1


@dataclass
class RunningTotals:
    """Type-safe container for running totals with hierarchical structure."""

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
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add_active_request_metrics(self, metrics: RequestMetrics) -> None:
        """Type-safe method to add metrics from an active request."""
        self.total_requests += 1
        self.total_input_tokens += int(metrics.input_tokens or 0)
        self.total_output_tokens += int(metrics.output_tokens or 0)
        self.total_tool_uses += int(metrics.tool_use_count or 0)
        self.total_tool_results += int(metrics.tool_result_count or 0)


class HierarchicalData(TypedDict):
    """TypedDict for the final hierarchical output structure."""

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


class RequestTracker:
    """Singleton tracker for request metrics"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls) -> "RequestTracker":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "initialized"):
            self.active_requests: dict[str, RequestMetrics] = {}
            self.summary_metrics = SummaryMetrics()
            self.summary_interval = int(os.environ.get("LOG_SUMMARY_INTERVAL", "100"))
            self.request_count = 0
            self.total_completed_requests = 0
            self.last_accessed_timestamps: dict[str, dict[str, str] | str | None] = {
                "models": {},  # provider:model -> timestamp
                "providers": {},  # provider -> timestamp
                "top": None,  # overall -> timestamp
            }
            self.initialized = True

    def start_request(
        self, request_id: str, claude_model: str, is_streaming: bool = False
    ) -> RequestMetrics:
        """Start tracking a new request"""
        metrics = RequestMetrics(
            request_id=request_id,
            start_time=time.time(),
            claude_model=claude_model,
            is_streaming=is_streaming,
        )
        self.active_requests[request_id] = metrics
        return metrics

    def end_request(self, request_id: str, **kwargs: Any) -> None:
        """End request tracking and update summary"""
        if request_id not in self.active_requests:
            return

        metrics = self.active_requests[request_id]
        metrics.end_time = time.time()

        # Update any provided fields
        for key, value in kwargs.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)

        # Add to summary
        self.summary_metrics.add_request(metrics)
        self.request_count += 1
        self.total_completed_requests += 1

        # Check if we should emit summary
        if self.request_count % self.summary_interval == 0:
            self._emit_summary()

        # Remove from active
        del self.active_requests[request_id]

    def get_request(self, request_id: str) -> RequestMetrics | None:
        """Get active request metrics"""
        return self.active_requests.get(request_id)

    def update_last_accessed(self, provider: str, model: str, timestamp: str) -> None:
        """Update last_accessed timestamps for provider, model, and top level."""
        # Update model timestamp
        model_key = f"{provider}:{model}"
        models_dict = cast(dict[str, str], self.last_accessed_timestamps["models"])
        models_dict[model_key] = timestamp

        # Update provider timestamp (take max if exists)
        providers_dict = cast(dict[str, str], self.last_accessed_timestamps["providers"])
        if provider in providers_dict:
            providers_dict[provider] = max(providers_dict[provider], timestamp)
        else:
            providers_dict[provider] = timestamp

        # Update top timestamp (take max if exists)
        top_timestamp = cast(str | None, self.last_accessed_timestamps["top"])
        if top_timestamp:
            self.last_accessed_timestamps["top"] = max(top_timestamp, timestamp)
        else:
            self.last_accessed_timestamps["top"] = timestamp

    def get_running_totals(self) -> dict[str, Any]:
        """Get running totals across all requests"""
        # Include both completed and active requests
        all_completed_metrics = self.summary_metrics

        # Add metrics from currently active requests
        active_input_tokens = sum(m.input_tokens for m in self.active_requests.values())
        active_output_tokens = sum(m.output_tokens for m in self.active_requests.values())
        active_cache_read = sum(m.cache_read_tokens for m in self.active_requests.values())
        active_cache_creation = sum(m.cache_creation_tokens for m in self.active_requests.values())
        active_tool_uses = sum(m.tool_use_count for m in self.active_requests.values())
        active_tool_results = sum(m.tool_result_count for m in self.active_requests.values())
        active_tool_calls = sum(m.tool_call_count for m in self.active_requests.values())

        return {
            "total_requests": self.total_completed_requests + len(self.active_requests),
            "total_errors": all_completed_metrics.total_errors,
            "total_input_tokens": all_completed_metrics.total_input_tokens + active_input_tokens,
            "total_output_tokens": all_completed_metrics.total_output_tokens + active_output_tokens,
            "total_cache_read_tokens": all_completed_metrics.total_cache_read_tokens
            + active_cache_read,
            "total_cache_creation_tokens": all_completed_metrics.total_cache_creation_tokens
            + active_cache_creation,
            "total_tool_uses": all_completed_metrics.total_tool_uses + active_tool_uses,
            "total_tool_results": all_completed_metrics.total_tool_results + active_tool_results,
            "total_tool_calls": all_completed_metrics.total_tool_calls + active_tool_calls,
            "active_requests": len(self.active_requests),
            "model_distribution": dict(all_completed_metrics.model_counts),
            "error_distribution": dict(all_completed_metrics.error_counts),
            "average_duration_ms": (
                all_completed_metrics.total_duration_ms
                / max(1, all_completed_metrics.total_requests)
                if all_completed_metrics.total_requests > 0
                else 0
            ),
        }

    def get_filtered_running_totals(
        self, provider_filter: str | None = None, model_filter: str | None = None
    ) -> dict[str, Any]:
        """Get running totals filtered by provider and/or model"""
        # Include both completed and active requests
        all_completed_metrics = self.summary_metrics

        # Filter completed requests by provider/model
        filtered_metrics = ProviderModelMetrics()

        # Process completed requests
        for provider_model_key, pm_metrics in all_completed_metrics.provider_model_metrics.items():
            provider, model = (
                provider_model_key.split(":", 1)
                if ":" in provider_model_key
                else (provider_model_key, None)
            )

            # Apply filters
            if provider_filter and provider != provider_filter:
                continue
            if model_filter and model != model_filter:
                continue

            # Accumulate metrics
            filtered_metrics.total_requests += pm_metrics.total_requests
            filtered_metrics.total_errors += pm_metrics.total_errors
            filtered_metrics.total_input_tokens += pm_metrics.total_input_tokens
            filtered_metrics.total_output_tokens += pm_metrics.total_output_tokens
            filtered_metrics.total_cache_read_tokens += pm_metrics.total_cache_read_tokens
            filtered_metrics.total_cache_creation_tokens += pm_metrics.total_cache_creation_tokens
            filtered_metrics.total_duration_ms += pm_metrics.total_duration_ms
            filtered_metrics.total_tool_uses += pm_metrics.total_tool_uses
            filtered_metrics.total_tool_results += pm_metrics.total_tool_results
            filtered_metrics.total_tool_calls += pm_metrics.total_tool_calls

        # Process active requests if requested
        active_requests_count = 0
        active_input_tokens = 0
        active_output_tokens = 0
        active_cache_read = 0
        active_cache_creation = 0
        active_tool_uses = 0
        active_tool_results = 0
        active_tool_calls = 0

        for metrics in self.active_requests.values():
            if provider_filter and metrics.provider != provider_filter:
                continue
            if model_filter and metrics.openai_model != model_filter:
                continue

            active_requests_count += 1
            active_input_tokens += metrics.input_tokens
            active_output_tokens += metrics.output_tokens
            active_cache_read += metrics.cache_read_tokens
            active_cache_creation += metrics.cache_creation_tokens
            active_tool_uses += metrics.tool_use_count
            active_tool_results += metrics.tool_result_count
            active_tool_calls += metrics.tool_call_count

        # Build provider/model distribution
        provider_model_distribution = []
        for provider_model_key, pm_metrics in all_completed_metrics.provider_model_metrics.items():
            provider, model = (
                provider_model_key.split(":", 1)
                if ":" in provider_model_key
                else (provider_model_key, None)
            )

            # Apply filters for distribution
            if provider_filter and provider != provider_filter:
                continue
            if model_filter and model != model_filter:
                continue

            avg_duration = (
                pm_metrics.total_duration_ms / max(1, pm_metrics.total_requests)
                if pm_metrics.total_requests > 0
                else 0
            )

            provider_model_distribution.append(
                {
                    "provider_model": provider_model_key,
                    "total_requests": pm_metrics.total_requests,
                    "total_errors": pm_metrics.total_errors,
                    "total_input_tokens": pm_metrics.total_input_tokens,
                    "total_output_tokens": pm_metrics.total_output_tokens,
                    "total_cache_read_tokens": pm_metrics.total_cache_read_tokens,
                    "total_cache_creation_tokens": pm_metrics.total_cache_creation_tokens,
                    "total_tool_uses": pm_metrics.total_tool_uses,
                    "total_tool_results": pm_metrics.total_tool_results,
                    "total_tool_calls": pm_metrics.total_tool_calls,
                    "average_duration_ms": avg_duration,
                }
            )

        # Calculate average duration
        total_requests = filtered_metrics.total_requests
        avg_duration_ms = (
            filtered_metrics.total_duration_ms / max(1, total_requests) if total_requests > 0 else 0
        )

        return {
            "total_requests": filtered_metrics.total_requests + active_requests_count,
            "total_errors": filtered_metrics.total_errors,
            "total_input_tokens": filtered_metrics.total_input_tokens + active_input_tokens,
            "total_output_tokens": filtered_metrics.total_output_tokens + active_output_tokens,
            "total_cache_read_tokens": filtered_metrics.total_cache_read_tokens + active_cache_read,
            "total_cache_creation_tokens": filtered_metrics.total_cache_creation_tokens
            + active_cache_creation,
            "total_tool_uses": filtered_metrics.total_tool_uses + active_tool_uses,
            "total_tool_results": filtered_metrics.total_tool_results + active_tool_results,
            "total_tool_calls": filtered_metrics.total_tool_calls + active_tool_calls,
            "provider_model_distribution": provider_model_distribution,
            "average_duration_ms": avg_duration_ms,
        }

    def get_running_totals_hierarchical(
        self, provider_filter: str | None = None, model_filter: str | None = None
    ) -> HierarchicalData:
        """Get running totals with hierarchical provider->model structure.

        Args:
            provider_filter: Case-insensitive provider filter with wildcard support
            model_filter: Case-insensitive model filter with wildcard support

        Returns:
            Hierarchical data structure suitable for YAML formatting
        """
        # Get all data
        all_completed_metrics = self.summary_metrics

        # Initialize RunningTotals with summary statistics
        last_accessed_value = self.last_accessed_timestamps.get("top")
        if last_accessed_value is not None:
            # Ensure we have the correct type: dict[str, str] | None
            running_totals = RunningTotals(
                last_accessed={"top": str(last_accessed_value)},
                active_requests=len(self.active_requests),
            )
        else:
            running_totals = RunningTotals(
                active_requests=len(self.active_requests),
            )

        # Process completed requests
        for provider_model_key, pm_metrics in all_completed_metrics.provider_model_metrics.items():
            provider, model = (
                provider_model_key.split(":", 1)
                if ":" in provider_model_key
                else (provider_model_key, None)
            )

            # Apply filters
            if provider_filter and not self._matches_pattern(provider, provider_filter):
                continue
            if model_filter and model and not self._matches_pattern(model, model_filter):
                continue

            # Initialize provider if not exists
            if provider not in running_totals.providers:
                running_totals.providers[provider] = {
                    "last_accessed": cast(
                        dict[str, str], self.last_accessed_timestamps["providers"]
                    ).get(provider),
                    "total_requests": 0,
                    "total_errors": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_cache_read_tokens": 0,
                    "total_cache_creation_tokens": 0,
                    "total_tool_uses": 0,
                    "total_tool_results": 0,
                    "total_tool_calls": 0,
                    "total_duration_ms": 0,
                    "models": {},
                }

            # Update provider stats
            provider_stats: dict[str, Any] = running_totals.providers[provider]
            provider_stats["total_requests"] += int(pm_metrics.total_requests)
            provider_stats["total_errors"] += int(pm_metrics.total_errors)
            provider_stats["total_input_tokens"] += int(pm_metrics.total_input_tokens)
            provider_stats["total_output_tokens"] += int(pm_metrics.total_output_tokens)
            provider_stats["total_cache_read_tokens"] += int(pm_metrics.total_cache_read_tokens)
            provider_stats["total_cache_creation_tokens"] += int(
                pm_metrics.total_cache_creation_tokens
            )
            provider_stats["total_tool_uses"] += int(pm_metrics.total_tool_uses)
            provider_stats["total_tool_results"] += int(pm_metrics.total_tool_results)
            provider_stats["total_tool_calls"] += int(pm_metrics.total_tool_calls)
            provider_stats["total_duration_ms"] += float(pm_metrics.total_duration_ms)

            # Update model stats if model exists
            if model:
                if model not in provider_stats["models"]:
                    model_key = f"{provider}:{model}"
                    provider_stats["models"][model] = {
                        "last_accessed": cast(
                            dict[str, str], self.last_accessed_timestamps["models"]
                        ).get(model_key),
                        "total_requests": 0,
                        "total_errors": 0,
                        "total_duration_ms": 0,
                    }

                model_stats = provider_stats["models"][model]
                model_stats["total_requests"] += int(pm_metrics.total_requests)
                model_stats["total_errors"] += int(pm_metrics.total_errors)
                model_stats["total_duration_ms"] += float(pm_metrics.total_duration_ms)

            # Update summary stats
            running_totals.total_requests += int(pm_metrics.total_requests)
            running_totals.total_errors += int(pm_metrics.total_errors)
            running_totals.total_input_tokens += int(pm_metrics.total_input_tokens)
            running_totals.total_output_tokens += int(pm_metrics.total_output_tokens)
            running_totals.total_cache_read_tokens += int(pm_metrics.total_cache_read_tokens)
            running_totals.total_cache_creation_tokens += int(
                pm_metrics.total_cache_creation_tokens
            )
            running_totals.total_tool_uses += int(pm_metrics.total_tool_uses)
            running_totals.total_tool_results += int(pm_metrics.total_tool_results)
            running_totals.total_tool_calls += int(pm_metrics.total_tool_calls)

        # Process active requests
        for _request_id, metrics in self.active_requests.items():
            provider = metrics.provider or "unknown"
            # Extract model without provider prefix for consistency with completed requests
            if metrics.claude_model and ":" in metrics.claude_model:
                _, model = metrics.claude_model.split(":", 1)
            else:
                model = metrics.claude_model or "unknown"

            # Apply filters to active requests
            if provider_filter and not self._matches_pattern(provider, provider_filter):
                continue
            if (
                model_filter
                and model != "unknown"
                and not self._matches_pattern(model, model_filter)
            ):
                continue

            # Update summary for active requests using type-safe method
            running_totals.add_active_request_metrics(metrics)

            # Initialize provider if not exists
            if provider not in running_totals.providers:
                running_totals.providers[provider] = {
                    "last_accessed": cast(
                        dict[str, str], self.last_accessed_timestamps["providers"]
                    ).get(provider),
                    "total_requests": 0,
                    "total_errors": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_cache_read_tokens": 0,
                    "total_cache_creation_tokens": 0,
                    "total_tool_uses": 0,
                    "total_tool_results": 0,
                    "total_tool_calls": 0,
                    "total_duration_ms": 0,
                    "models": {},
                }

            # Update provider stats for active request
            active_provider_stats: dict[str, Any] = running_totals.providers[provider]
            active_provider_stats["total_requests"] += 1
            active_provider_stats["total_input_tokens"] += int(metrics.input_tokens or 0)
            active_provider_stats["total_tool_uses"] += int(metrics.tool_use_count or 0)
            active_provider_stats["total_tool_results"] += int(metrics.tool_result_count or 0)

            # Update model stats if model exists
            if model != "unknown":
                if model not in active_provider_stats["models"]:
                    model_key = f"{provider}:{model}"
                    active_provider_stats["models"][model] = {
                        "last_accessed": cast(
                            dict[str, str], self.last_accessed_timestamps["models"]
                        ).get(model_key),
                        "total_requests": 0,
                        "total_errors": 0,
                        "total_duration_ms": 0,
                    }

                active_provider_stats["models"][model]["total_requests"] += 1

        # Calculate average durations
        if running_totals.total_requests > 0:
            summary_total_duration = sum(
                float(cast(dict[str, Any], p).get("total_duration_ms", 0))
                for p in running_totals.providers.values()
            )
            summary_avg = summary_total_duration / max(1, running_totals.total_requests)
            running_totals.average_duration_ms = int(round(summary_avg))
        else:
            running_totals.average_duration_ms = 0

        for _provider_name, provider_stats in running_totals.providers.items():
            provider_stats_dict = cast(dict[str, Any], provider_stats)
            provider_requests = provider_stats_dict["total_requests"]
            if provider_requests > 0:
                provider_avg = provider_stats_dict["total_duration_ms"] / max(1, provider_requests)
                provider_stats_dict["average_duration_ms"] = int(round(provider_avg))
            else:
                provider_stats_dict["average_duration_ms"] = 0

            # Calculate model averages
            for _model_name, model_stats in provider_stats_dict.get("models", {}).items():
                model_requests = model_stats["total_requests"]
                if model_requests > 0:
                    model_avg = model_stats["total_duration_ms"] / max(1, model_requests)
                    model_stats["average_duration_ms"] = int(round(model_avg))
                else:
                    model_stats["average_duration_ms"] = 0
                # Remove duration from model stats (not needed in output)
                del model_stats["total_duration_ms"]

            # Remove duration from provider stats (not needed in output)
            del provider_stats["total_duration_ms"]

        # Convert to HierarchicalData TypedDict format
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

    @staticmethod
    def _matches_pattern(text: str, pattern: str) -> bool:
        """Check if text matches pattern (case-insensitive, supports wildcards).

        Args:
            text: Text to match
            pattern: Pattern with optional * and ? wildcards

        Returns:
            True if text matches pattern
        """
        if not pattern or not text:
            return False

        # Case-insensitive matching
        text_lower = text.lower()
        pattern_lower = pattern.lower()

        # Use fnmatch for wildcard support
        return fnmatch.fnmatch(text_lower, pattern_lower)

    def _emit_summary(self) -> None:
        """Emit summary log"""
        total_requests = max(1, self.summary_metrics.total_requests)
        avg_duration = self.summary_metrics.total_duration_ms / total_requests

        logger.info(
            f"📊 SUMMARY (last {self.summary_interval} requests) | "
            f"Total: {self.summary_metrics.total_requests} | "
            f"Errors: {self.summary_metrics.total_errors} | "
            f"Avg Duration: {avg_duration:.0f}ms | "
            f"Input Tokens: {self.summary_metrics.total_input_tokens:,} | "
            f"Output Tokens: {self.summary_metrics.total_output_tokens:,} | "
            f"Cache Hits: {self.summary_metrics.total_cache_read_tokens:,} | "
            f"Cache Creation: {self.summary_metrics.total_cache_creation_tokens:,} | "
            f"Tool Uses: {self.summary_metrics.total_tool_uses} | "
            f"Tool Results: {self.summary_metrics.total_tool_results} | "
            f"Tool Calls: {self.summary_metrics.total_tool_calls}"
        )

        # Log model distribution
        if self.summary_metrics.model_counts:
            model_dist = " | ".join(
                [f"{model}: {count}" for model, count in self.summary_metrics.model_counts.items()]
            )
            logger.info(f"📊 MODELS | {model_dist}")

        # Log errors if any
        if self.summary_metrics.error_counts:
            error_dist = " | ".join(
                [f"{error}: {count}" for error, count in self.summary_metrics.error_counts.items()]
            )
            logger.warning(f"📊 ERRORS | {error_dist}")

        # Reset summary metrics
        self.summary_metrics = SummaryMetrics()


class ConversationLogger:
    """Logger with correlation ID support"""

    @staticmethod
    def get_logger() -> logging.Logger:
        """Get logger with correlation ID support"""
        return logging.getLogger("conversation")

    @staticmethod
    @contextmanager
    def correlation_context(request_id: str) -> Generator[None, None, None]:
        """Context manager for correlation ID"""
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = old_factory(*args, **kwargs)
            record.correlation_id = request_id
            return record

        logging.setLogRecordFactory(record_factory)
        try:
            yield
        finally:
            logging.setLogRecordFactory(old_factory)


# Custom formatter with correlation ID (for backward compatibility)
class CorrelationFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Add correlation ID if available
        if hasattr(record, "correlation_id"):
            record.msg = f"[{record.correlation_id[:8]}] {record.msg}"
        return super().format(record)


# Custom formatter with correlation ID and API key hashing
class CorrelationHashingFormatter(HashingFormatter):
    """Formatter that adds correlation ID and hashes API keys"""

    def format(self, record: logging.LogRecord) -> str:
        # Add correlation ID if available
        if hasattr(record, "correlation_id"):
            record.msg = f"[{record.correlation_id[:8]}] {record.msg}"

        # Call parent to hash API keys
        return super().format(record)


# Configure root logger with combined formatter
formatter = CorrelationHashingFormatter(
    "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
)


class HttpRequestLogDowngradeFilter(logging.Filter):
    """Downgrade noisy third-party HTTP logs to DEBUG."""

    def __init__(self, *prefixes: str) -> None:
        super().__init__()
        self.prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno == logging.INFO:
            for prefix in self.prefixes:
                if record.name.startswith(prefix):
                    record.levelno = logging.DEBUG
                    record.levelname = logging.getLevelName(logging.DEBUG)
                    break
        return True


handler = logging.StreamHandler()
handler.addFilter(HttpRequestLogDowngradeFilter(*NOISY_HTTP_LOGGERS))
handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.handlers.clear()
root_logger.addHandler(handler)
root_logger.setLevel(getattr(logging, log_level))

# Configure uvicorn to be quieter
for uvicorn_logger in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
    logging.getLogger(uvicorn_logger).setLevel(logging.WARNING)

set_noisy_http_logger_levels(log_level)

# Global instances
logger = logging.getLogger(__name__)
request_tracker = RequestTracker()
conversation_logger = ConversationLogger.get_logger()

# Check if request metrics are enabled
LOG_REQUEST_METRICS = os.environ.get("LOG_REQUEST_METRICS", "true").lower() == "true"
