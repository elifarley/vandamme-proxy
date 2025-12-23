from __future__ import annotations

from typing import Any, Literal

import dash_bootstrap_components as dbc  # type: ignore[import-untyped]
from dash import html

from src.dashboard.components.ui import (
    duration_color_class,
    format_duration,
    format_timestamp,
    monospace,
)


def breakdown_table(
    *,
    kind: Literal["provider", "model"],
    rows: list[dict[str, Any]],
) -> dbc.Table:
    """Build a metrics breakdown table.

    `kind` controls the first column label and which key to read from each row.
    This consolidates the duplicated provider/model breakdown table builders.
    """

    if kind == "provider":
        first_header = "Provider"
        first_key = "provider"
    else:
        first_header = "Model"
        first_key = "model"

    header = html.Thead(
        html.Tr(
            [
                html.Th(first_header),
                html.Th("Requests", className="text-end"),
                html.Th("Errors", className="text-end"),
                html.Th("Error rate", className="text-end"),
                html.Th("Input", className="text-end"),
                html.Th("Output", className="text-end"),
                html.Th("Tools", className="text-end"),
                html.Th("Avg Duration", className="text-end"),
                html.Th("Streaming Avg", className="text-end"),
                html.Th("Non-Streaming Avg", className="text-end"),
                html.Th("Last Accessed", className="text-end"),
            ]
        )
    )

    body_rows: list[html.Tr] = []
    for r in rows:
        avg_ms = r.get("average_duration_ms", 0)
        streaming_avg_ms = r.get("streaming_average_duration_ms", 0)
        non_streaming_avg_ms = r.get("non_streaming_average_duration_ms", 0)

        body_rows.append(
            html.Tr(
                [
                    html.Td(monospace(r.get(first_key))),
                    html.Td(f"{int(r.get('requests', 0)):,}", className="text-end"),
                    html.Td(f"{int(r.get('errors', 0)):,}", className="text-end"),
                    html.Td(
                        f"{float(r.get('error_rate', 0.0)) * 100.0:.2f}%",
                        className="text-end",
                    ),
                    html.Td(f"{int(r.get('input_tokens', 0)):,}", className="text-end"),
                    html.Td(f"{int(r.get('output_tokens', 0)):,}", className="text-end"),
                    html.Td(f"{int(r.get('tool_calls', 0)):,}", className="text-end"),
                    html.Td(
                        html.Span(
                            format_duration(avg_ms),
                            className=duration_color_class(avg_ms),
                            title=f"{avg_ms:.1f}ms",
                        ),
                        className="text-end",
                    ),
                    html.Td(
                        html.Span(
                            format_duration(streaming_avg_ms),
                            className=duration_color_class(streaming_avg_ms),
                            title=f"{streaming_avg_ms:.1f}ms",
                        ),
                        className="text-end",
                    ),
                    html.Td(
                        html.Span(
                            format_duration(non_streaming_avg_ms),
                            className=duration_color_class(non_streaming_avg_ms),
                            title=f"{non_streaming_avg_ms:.1f}ms",
                        ),
                        className="text-end",
                    ),
                    html.Td(
                        monospace(format_timestamp(r.get("last_accessed"))),
                        className="text-end",
                    ),
                ]
            )
        )

    return dbc.Table(
        [header, html.Tbody(body_rows)],
        bordered=False,
        hover=True,
        responsive=True,
        striped=True,
        size="sm",
    )


def provider_breakdown_table_view(rows: list[dict[str, Any]]) -> html.Div:
    table = breakdown_table(kind="provider", rows=rows)
    return html.Div(
        [
            table,
            html.Div(
                "💡 To view models for a specific provider, use the filter dropdown above",
                className="text-muted small mt-2",
            ),
        ]
    )


def model_breakdown_table_view(rows: list[dict[str, Any]]) -> dbc.Table:
    return breakdown_table(kind="model", rows=rows)
