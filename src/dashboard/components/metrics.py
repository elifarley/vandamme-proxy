from __future__ import annotations

from typing import Any

import dash_bootstrap_components as dbc  # type: ignore[import-untyped]
from dash import html

from src.dashboard.components.ui import duration_color_class, format_duration
from src.dashboard.normalize import MetricTotals, detect_metrics_disabled, error_rate


def metrics_disabled_callout(running_totals: dict[str, Any]) -> dbc.Alert | None:
    if not detect_metrics_disabled(running_totals):
        return None
    message = running_totals.get("# Message", "Request metrics logging is disabled")
    suggestion = running_totals.get(
        "# Suggestion", "Set LOG_REQUEST_METRICS=true to enable tracking"
    )
    return dbc.Alert(
        [
            html.Div("Request metrics are disabled", className="fw-semibold"),
            html.Div(str(message), className="text-muted"),
            html.Div(str(suggestion), className="text-muted"),
        ],
        color="info",
    )


def kpis_grid(totals: MetricTotals) -> dbc.Row:
    err_rate = (
        error_rate(total_requests=totals.total_requests, total_errors=totals.total_errors) * 100.0
    )

    return dbc.Row(
        [
            _kpi_col("Total requests", f"{totals.total_requests:,}"),
            _kpi_col(
                "Errors",
                f"{totals.total_errors:,}",
                subtitle=f"{err_rate:.2f}% error rate",
            ),
            _kpi_col("Input tokens", f"{totals.total_input_tokens:,}"),
            _kpi_col("Output tokens", f"{totals.total_output_tokens:,}"),
            _kpi_col("Active requests", f"{totals.active_requests:,}"),
            _kpi_col("Tool calls", f"{totals.tool_calls:,}"),
            _kpi_duration_col("Avg duration", totals.average_duration_ms),
            _kpi_duration_col("Streaming avg", totals.streaming_average_duration_ms),
            _kpi_duration_col("Non-streaming avg", totals.non_streaming_average_duration_ms),
            _kpi_col("Last activity", totals.last_accessed, raw=True),
        ],
        className="g-3",
    )


def _kpi_col(title: str, value: Any, *, subtitle: str | None = None, raw: bool = False) -> dbc.Col:
    from src.dashboard.components.ui import (
        kpi_card,
        monospace,
        timestamp_with_recency_dot,
    )

    display = (
        timestamp_with_recency_dot(value, id_override="vdm-overview-last-activity")
        if raw and title == "Last activity"
        else monospace(value)
    )

    return dbc.Col(
        kpi_card(title=title, value=display, subtitle=subtitle),
        md=2,
        sm=6,
        xs=12,
    )


def _kpi_duration_col(title: str, ms: float) -> dbc.Col:
    from src.dashboard.components.ui import kpi_card

    return dbc.Col(
        kpi_card(
            title=title,
            value=html.Span(format_duration(ms), className=duration_color_class(ms)),
        ),
        md=2,
        sm=6,
        xs=12,
    )
