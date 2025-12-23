from __future__ import annotations

from typing import Any

import dash_bootstrap_components as dbc  # type: ignore[import-untyped]
from dash import dcc, html

from src.dashboard.components.breakdown_tables import (
    model_breakdown_table_view,
    provider_breakdown_table_view,
)
from src.dashboard.components.ui import (
    duration_color_class,
    format_duration,
    kpi_card,
    model_details_drawer,
    monospace,
    provider_badge,
    search_box,
    status_badge,
    timestamp_with_hover,
)
from src.dashboard.normalize import (
    MetricTotals,
    detect_metrics_disabled,
    error_rate,
    model_rows_for_provider,
    parse_metric_totals,
    provider_rows,
)


def overview_layout() -> dbc.Container:
    return dbc.Container(
        [
            dbc.Row(
                [
                    dbc.Col(html.H2("Vandamme Proxy"), md=8),
                    dbc.Col(
                        dbc.Stack(
                            [
                                dbc.Switch(
                                    id="vdm-theme-toggle",
                                    label="Dark mode",
                                    value=True,
                                    className="me-2",
                                ),
                                dbc.Button(
                                    "Refresh now",
                                    id="vdm-refresh-now",
                                    color="secondary",
                                    outline=True,
                                ),
                            ],
                            direction="horizontal",
                            gap=2,
                            className="justify-content-end",
                        ),
                        md=4,
                    ),
                ],
                className="align-items-center mb-2",
            ),
            dbc.Row(
                [
                    dbc.Col(html.Div(id="vdm-health-banner"), md=12),
                ],
                className="mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(dbc.Card(dbc.CardBody(id="vdm-metrics-disabled-callout")), md=12),
                ],
                className="mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(dbc.Spinner(id="vdm-kpis"), md=12),
                ],
                className="mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Providers"),
                                dbc.CardBody(dbc.Spinner(id="vdm-providers-table")),
                            ]
                        ),
                        md=7,
                    ),
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Upstream connectivity"),
                                dbc.CardBody(
                                    [
                                        dbc.Button(
                                            "Run test connection",
                                            id="vdm-test-connection",
                                            color="primary",
                                        ),
                                        html.Div(className="mt-3", id="vdm-test-connection-result"),
                                    ]
                                ),
                            ]
                        ),
                        md=5,
                    ),
                ],
                className="mb-3",
            ),
            dcc.Interval(id="vdm-overview-poll", interval=10_000, n_intervals=0),
        ],
        fluid=True,
        className="py-3",
    )


def metrics_layout() -> dbc.Container:
    return dbc.Container(
        [
            dbc.Row(
                [
                    dbc.Col(html.H2("Metrics"), md=8),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Live updates", className="text-muted small me-2"),
                                dbc.Switch(
                                    id="vdm-metrics-poll-toggle",
                                    label="Polling",
                                    value=True,
                                    className="me-2",
                                ),
                                dcc.Dropdown(
                                    id="vdm-metrics-interval",
                                    options=[
                                        {"label": "5s", "value": 5_000},
                                        {"label": "10s", "value": 10_000},
                                        {"label": "30s", "value": 30_000},
                                    ],  # type: ignore[arg-type]
                                    value=10_000,
                                    clearable=False,
                                    style={"minWidth": "7rem"},
                                    className="ms-1",
                                ),
                            ],
                            className="vdm-toolbar justify-content-end",
                        ),
                        md=4,
                    ),
                ],
                className="align-items-center mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(html.Strong("Filters", className="text-primary")),
                                dbc.CardBody(
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                [
                                                    html.Div(
                                                        "Provider", className="text-muted small"
                                                    ),
                                                    dcc.Dropdown(
                                                        id="vdm-provider-filter",
                                                        options=[{"label": "All", "value": ""}],  # type: ignore[arg-type]
                                                        value="",
                                                        clearable=False,
                                                        className="border-primary",
                                                    ),
                                                ]
                                            ),
                                            dbc.Col(
                                                [
                                                    html.Div(
                                                        "Model (supports * and ?)",
                                                        className="text-muted small",
                                                    ),
                                                    dbc.Input(
                                                        id="vdm-model-filter",
                                                        value="",
                                                        placeholder="e.g. gpt*",
                                                        className="border-primary",
                                                    ),
                                                ]
                                            ),
                                            dbc.Col(
                                                dbc.Button(
                                                    "Apply",
                                                    id="vdm-apply-filters",
                                                    color="primary",
                                                    outline=True,
                                                    className="mt-4",
                                                ),
                                                width="auto",
                                            ),
                                            dbc.Col(
                                                html.Div(
                                                    "Supports * and ? wildcards",
                                                    className="text-muted small mt-2",
                                                ),
                                                width="auto",
                                            ),
                                        ],
                                        className="g-3 align-items-end",
                                    )
                                ),
                            ]
                        ),
                        md=12,
                    )
                ],
                className="mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Token composition"),
                                dbc.CardBody(dbc.Spinner(id="vdm-token-chart")),
                            ]
                        ),
                        md=5,
                    ),
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Provider breakdown"),
                                dbc.CardBody(dbc.Spinner(id="vdm-provider-breakdown")),
                            ]
                        ),
                        md=7,
                    ),
                ],
                className="mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    [
                                        html.Span("Model breakdown"),
                                        dbc.Badge(
                                            "Select a provider to enable model breakdown",
                                            color="info",
                                            className="ms-2",
                                        ),
                                        html.Span(
                                            "· Last updated on refresh or polling",
                                            className="text-muted small ms-2",
                                        ),
                                    ]
                                ),
                                dbc.CardBody(dbc.Spinner(id="vdm-model-breakdown")),
                            ]
                        ),
                        md=12,
                    )
                ],
                className="mb-3",
            ),
            dcc.Interval(id="vdm-metrics-poll", interval=10_000, n_intervals=0),
        ],
        fluid=True,
        className="py-3",
    )


def providers_table(health: dict[str, Any]) -> dbc.Table:
    providers = health.get("providers")
    if not isinstance(providers, dict):
        providers = {}

    default_provider = health.get("default_provider")
    if not isinstance(default_provider, str):
        default_provider = ""

    header = html.Thead(
        html.Tr(
            [
                html.Th("Provider"),
                html.Th("Format"),
                html.Th("Base URL"),
                html.Th("API key (sha256)"),
            ]
        )
    )

    body_rows = []
    for provider_name in sorted(providers.keys()):
        pdata = providers.get(provider_name)
        if not isinstance(pdata, dict):
            continue
        api_format = pdata.get("api_format", "unknown")
        base_url = pdata.get("base_url")
        api_key_hash = pdata.get("api_key_hash", "<not set>")

        is_default = bool(default_provider) and provider_name == default_provider

        provider_cell = [provider_badge(provider_name)]
        if is_default:
            provider_cell.append(
                dbc.Badge(
                    "default",
                    color="info",
                    pill=True,
                    className="ms-1",
                )
            )

        # api_key_hash is already in the same format we log (sha256:<8>)
        key_text = str(api_key_hash)
        key_missing = key_text == "<not set>"

        body_rows.append(
            html.Tr(
                [
                    html.Td(provider_cell),
                    html.Td(monospace(api_format)),
                    html.Td(monospace(base_url or "—")),
                    html.Td(
                        monospace(key_text)
                        if not key_missing
                        else html.Span("<not set>", className="text-muted")
                    ),
                ],
                className="table-active" if is_default else None,
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


def health_banner(health: dict[str, Any]) -> dbc.Alert:
    status = str(health.get("status", "unknown"))
    ts = str(health.get("timestamp", ""))

    color = (
        "success"
        if status.lower() == "healthy"
        else "warning"
        if status.lower() == "degraded"
        else "secondary"
    )

    details = [
        html.Div(
            [
                status_badge(status=status),
                html.Span(" "),
                html.Span("System status"),
                html.Span(" · ", className="text-muted"),
                html.Span("Updated "),
                monospace(ts),
            ]
        )
    ]

    suggestions = health.get("suggestions")
    if isinstance(suggestions, list) and suggestions:
        details.append(html.Div(html.Hr()))
        details.append(html.Div("Suggestions", className="text-muted small"))
        details.append(html.Div(html.Ul([html.Li(str(s)) for s in suggestions])))

    return dbc.Alert(details, color=color, className="mb-0")


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
            dbc.Col(
                kpi_card(title="Total requests", value=f"{totals.total_requests:,}"),
                md=2,
                sm=6,
                xs=12,
            ),
            dbc.Col(
                kpi_card(
                    title="Errors",
                    value=f"{totals.total_errors:,}",
                    subtitle=f"{err_rate:.2f}% error rate",
                ),
                md=2,
                sm=6,
                xs=12,
            ),
            dbc.Col(
                kpi_card(title="Input tokens", value=f"{totals.total_input_tokens:,}"),
                md=2,
                sm=6,
                xs=12,
            ),
            dbc.Col(
                kpi_card(title="Output tokens", value=f"{totals.total_output_tokens:,}"),
                md=2,
                sm=6,
                xs=12,
            ),
            dbc.Col(
                kpi_card(title="Active requests", value=f"{totals.active_requests:,}"),
                md=2,
                sm=6,
                xs=12,
            ),
            dbc.Col(
                kpi_card(title="Tool calls", value=f"{totals.tool_calls:,}"), md=2, sm=6, xs=12
            ),
            dbc.Col(
                kpi_card(
                    title="Avg duration",
                    value=html.Span(
                        format_duration(totals.average_duration_ms),
                        className=duration_color_class(totals.average_duration_ms),
                    ),
                ),
                md=2,
                sm=6,
                xs=12,
            ),
            dbc.Col(
                kpi_card(
                    title="Streaming avg",
                    value=html.Span(
                        format_duration(totals.streaming_average_duration_ms),
                        className=duration_color_class(totals.streaming_average_duration_ms),
                    ),
                ),
                md=2,
                sm=6,
                xs=12,
            ),
            dbc.Col(
                kpi_card(
                    title="Non-streaming avg",
                    value=html.Span(
                        format_duration(totals.non_streaming_average_duration_ms),
                        className=duration_color_class(totals.non_streaming_average_duration_ms),
                    ),
                ),
                md=2,
                sm=6,
                xs=12,
            ),
            dbc.Col(
                kpi_card(
                    title="Last activity",
                    value=timestamp_with_hover(totals.last_accessed),
                ),
                md=2,
                sm=6,
                xs=12,
            ),
        ],
        className="g-3",
    )


def provider_breakdown_table(rows: list[dict[str, Any]]) -> html.Div:
    return provider_breakdown_table_view(rows)


def model_breakdown_table(rows: list[dict[str, Any]]) -> dbc.Table:
    return model_breakdown_table_view(rows)


def token_composition_chart(totals: MetricTotals) -> dcc.Graph:
    import plotly.graph_objects as go  # type: ignore[import-untyped]

    labels = ["input", "output", "cache_read", "cache_creation"]
    values = [
        totals.total_input_tokens,
        totals.total_output_tokens,
        totals.cache_read_tokens,
        totals.cache_creation_tokens,
    ]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.6,
                sort=False,
                textinfo="label+percent",
            )
        ]
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        height=260,
    )
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def compute_metrics_views(
    running_totals: dict[str, Any], selected_provider: str | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prov_rows = provider_rows(running_totals)

    model_rows: list[dict[str, Any]] = []
    if selected_provider:
        chosen = next((r for r in prov_rows if r.get("provider") == selected_provider), None)
        if chosen:
            model_rows = model_rows_for_provider(chosen)

    return prov_rows, model_rows


def parse_totals_for_chart(running_totals: dict[str, Any]) -> MetricTotals:
    return parse_metric_totals(running_totals)


def models_layout() -> dbc.Container:
    """Layout for the Models page.

    Filtering and sorting are handled directly in the AG-Grid table.
    """

    from src.dashboard.components.ui import models_table

    return dbc.Container(
        [
            dbc.Row(
                [
                    dbc.Col(html.H2("Available Models"), md=6),
                    dbc.Col(
                        dbc.Stack(
                            [
                                dbc.Label("Provider", className="text-muted small mb-0"),
                                dcc.Dropdown(
                                    id="vdm-models-provider",
                                    options=[],
                                    value=None,
                                    placeholder="Provider",
                                    clearable=False,
                                    style={"minWidth": "14rem"},
                                ),
                            ],
                            gap=1,
                        ),
                        md=3,
                    ),
                    dbc.Col(
                        dbc.ButtonGroup(
                            [
                                dbc.Button(
                                    "Copy selected IDs",
                                    id="vdm-models-copy-ids",
                                    color="primary",
                                    outline=False,
                                    size="sm",
                                ),
                                dbc.Button(
                                    "Refresh",
                                    id="vdm-models-refresh",
                                    color="primary",
                                    outline=True,
                                    size="sm",
                                ),
                            ],
                            size="sm",
                        ),
                        md=3,
                        className="text-end",
                    ),
                ],
                className="align-items-center mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Toast(
                            id="vdm-models-copy-toast",
                            header="Models",
                            is_open=False,
                            dismissable=True,
                            duration=4000,
                            icon="success",
                            className="vdm-toast-wide",
                            style={
                                "position": "fixed",
                                "top": 80,
                                "right": 20,
                                "width": 360,
                                "zIndex": 2000,
                            },
                        ),
                        md=12,
                    ),
                ],
            ),
            dcc.Store(id="vdm-models-selected-ids", data=[]),
            dcc.Store(id="vdm-models-detail-store", data=None),
            model_details_drawer(),
            # Hidden sinks used by clientside callbacks.
            html.Div(id="vdm-models-copy-sink", style={"display": "none"}),
            # We use a hidden button click as a reliable trigger (Dash-owned n_clicks).
            dbc.Button(
                "",
                id="vdm-models-toast-trigger",
                n_clicks=0,
                style={"display": "none"},
            ),
            # Payload is stored on window.__vdm_last_toast_payload by injected JS.
            html.Div(id="vdm-models-toast-payload", style={"display": "none"}),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            id="vdm-models-provider-hint",
                            className="text-muted small",
                        ),
                        md=12,
                        className="mb-2",
                    ),
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                models_table(
                                    [],
                                    sort_field="id",
                                    sort_desc=False,
                                    show_provider=True,
                                )
                            ],
                            id="vdm-models-content",
                        ),
                        md=12,
                    ),
                ],
            ),
            dcc.Store(id="vdm-models-rowdata", data=[]),
            dcc.Store(id="vdm-models-grid-initialized", data=False),
            # Dedicated rowData output avoids recreating the grid and preserves filters.
            html.Div(id="vdm-models-rowdata-sink", style={"display": "none"}),
            dcc.Interval(id="vdm-models-poll", interval=30_000, n_intervals=0),
        ],
        fluid=True,
        className="py-3",
    )


def aliases_layout() -> dbc.Container:
    """Layout for the Aliases page with search and provider grouping."""
    return dbc.Container(
        [
            dbc.Row(
                [
                    dbc.Col(html.H2("Model Aliases"), md=8),
                    dbc.Col(
                        dbc.Button(
                            "Refresh",
                            id="vdm-aliases-refresh",
                            color="primary",
                            outline=True,
                            size="sm",
                        ),
                        md=4,
                        className="text-end",
                    ),
                ],
                className="align-items-center mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(html.Strong("Search", className="text-primary")),
                                dbc.CardBody(search_box("vdm-aliases-search", "Search aliases...")),
                            ]
                        ),
                        md=12,
                    ),
                ],
                className="mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Spinner(id="vdm-aliases-content"),
                        md=12,
                    ),
                ],
            ),
            dcc.Interval(id="vdm-aliases-poll", interval=60_000, n_intervals=0),
        ],
        fluid=True,
        className="py-3",
    )


def top_models_layout() -> dbc.Container:
    """Layout for the Top Models discovery page."""
    return dbc.Container(
        [
            dbc.Row(
                [
                    dbc.Col(html.H2("Top Models"), md=6),
                    dbc.Col(
                        dbc.Button(
                            "Refresh",
                            id="vdm-top-models-refresh",
                            color="primary",
                            outline=True,
                            size="sm",
                        ),
                        md=6,
                        className="text-end",
                    ),
                ],
                className="align-items-center mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(html.Strong("Filters", className="text-primary")),
                                dbc.CardBody(
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                [
                                                    html.Div(
                                                        "Sub-provider", className="text-muted small"
                                                    ),
                                                    dcc.Dropdown(
                                                        id="vdm-top-models-provider",
                                                        options=[{"label": "All", "value": ""}],  # type: ignore[arg-type]
                                                        value="",
                                                        clearable=False,
                                                        className="border-primary",
                                                    ),
                                                ]
                                            ),
                                            dbc.Col(
                                                [
                                                    html.Div("Limit", className="text-muted small"),
                                                    dcc.Dropdown(
                                                        id="vdm-top-models-limit",
                                                        options=[
                                                            {"label": "5", "value": 5},
                                                            {"label": "10", "value": 10},
                                                            {"label": "20", "value": 20},
                                                            {"label": "50", "value": 50},
                                                        ],  # type: ignore[arg-type]
                                                        value=10,
                                                        clearable=False,
                                                        className="border-primary",
                                                        style={"minWidth": "6rem"},
                                                    ),
                                                ]
                                            ),
                                            dbc.Col(
                                                [
                                                    html.Div(
                                                        "Search", className="text-muted small"
                                                    ),
                                                    search_box(
                                                        "vdm-top-models-search",
                                                        placeholder="Search id or name...",
                                                    ),
                                                ]
                                            ),
                                        ],
                                        className="g-3 align-items-end",
                                    )
                                ),
                            ]
                        ),
                        md=12,
                    )
                ],
                className="mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Status"),
                                dbc.CardBody(id="vdm-top-models-status"),
                            ]
                        ),
                        md=4,
                    ),
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Metadata"),
                                dbc.CardBody(id="vdm-top-models-meta"),
                            ]
                        ),
                        md=8,
                    ),
                ],
                className="mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Models"),
                                dbc.CardBody(dbc.Spinner(id="vdm-top-models-content")),
                            ]
                        ),
                        md=12,
                    )
                ],
                className="mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Suggested aliases"),
                                dbc.CardBody(id="vdm-top-models-aliases"),
                            ]
                        ),
                        md=12,
                    )
                ],
                className="mb-3",
            ),
            dcc.Interval(id="vdm-top-models-poll", interval=60_000, n_intervals=0),
        ],
        fluid=True,
        className="py-3",
    )


def logs_layout() -> dbc.Container:
    """Layout for the Logs page with AG-Grid tables."""
    from src.dashboard.components.ag_grid import logs_errors_ag_grid, logs_traces_ag_grid

    return dbc.Container(
        [
            dbc.Row([dbc.Col(html.H2("Logs"), md=12)], className="mb-4"),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(html.Strong("Recent")),
                                dbc.CardBody(
                                    [
                                        html.Div(id="vdm-logs-disabled-callout"),
                                        dbc.Tabs(
                                            [
                                                dbc.Tab(
                                                    [
                                                        # Grid created once.
                                                        # Row data updated via callback.
                                                        logs_errors_ag_grid(
                                                            [], grid_id="vdm-logs-errors-grid"
                                                        ),
                                                    ],
                                                    label="Errors",
                                                    tab_id="errors-tab",
                                                ),
                                                dbc.Tab(
                                                    [
                                                        # Grid created once.
                                                        # Row data updated via callback.
                                                        logs_traces_ag_grid(
                                                            [], grid_id="vdm-logs-traces-grid"
                                                        ),
                                                    ],
                                                    label="Traces",
                                                    tab_id="traces-tab",
                                                ),
                                            ],
                                            id="vdm-logs-tabs",
                                            active_tab="errors-tab",
                                        ),
                                    ]
                                ),
                            ]
                        ),
                        md=12,
                    )
                ],
                className="mb-3",
            ),
            dcc.Interval(id="vdm-logs-poll", interval=5_000, n_intervals=0),
        ],
        fluid=True,
        className="py-3",
    )


def token_counter_layout() -> dbc.Container:
    """Layout for the Token Counter tool with real-time counting."""
    return dbc.Container(
        [
            dbc.Row(
                [
                    dbc.Col(html.H2("Token Counter"), md=12),
                ],
                className="mb-4",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(html.Strong("Configuration")),
                                dbc.CardBody(
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                [
                                                    html.Label("Model", className="form-label"),
                                                    dcc.Dropdown(
                                                        id="vdm-token-counter-model",
                                                        placeholder="Select a model...",
                                                        clearable=False,
                                                        className="border-primary",
                                                    ),
                                                    html.Div(
                                                        [
                                                            "Model list loads automatically;",
                                                            " select to enable counting.",
                                                        ],
                                                        className="text-muted small mt-1",
                                                    ),
                                                ]
                                            ),
                                            dbc.Col(
                                                [
                                                    html.Label(
                                                        "System Message (Optional)",
                                                        className="form-label",
                                                    ),
                                                    dbc.Textarea(
                                                        id="vdm-token-counter-system",
                                                        placeholder="Enter system message...",
                                                        rows=3,
                                                        className="mb-3",
                                                    ),
                                                ]
                                            ),
                                        ],
                                        className="g-3",
                                    )
                                ),
                            ]
                        ),
                        md=12,
                    ),
                ],
                className="mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(html.Strong("Message")),
                                dbc.CardBody(
                                    [
                                        dbc.Textarea(
                                            id="vdm-token-counter-message",
                                            placeholder=(
                                                "Enter your message here to count tokens..."
                                            ),
                                            rows=10,
                                            className="mb-3",
                                        ),
                                        html.Div(
                                            "Token estimate uses a quick approximation (chars/4).",
                                            className="text-muted small mb-2",
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    dbc.Button(
                                                        "Clear",
                                                        id="vdm-token-counter-clear",
                                                        color="primary",
                                                        outline=True,
                                                        size="sm",
                                                    ),
                                                    width="auto",
                                                ),
                                                dbc.Col(
                                                    html.Div(id="vdm-token-counter-result"),
                                                    width="auto",
                                                    className="text-end",
                                                ),
                                            ],
                                            className="align-items-center",
                                        ),
                                    ]
                                ),
                            ]
                        ),
                        md=12,
                    ),
                ],
            ),
        ],
        fluid=True,
        className="py-3",
    )
