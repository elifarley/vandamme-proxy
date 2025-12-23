from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import dash
import dash_bootstrap_components as dbc  # type: ignore[import-untyped]
from dash import Input, Output, State, dcc, html

from src.dashboard.components.ui import (
    monospace,
    provider_badge,
    token_display,
)
from src.dashboard.data_sources import (
    DashboardConfigProtocol,
    fetch_models,
    fetch_test_connection,
)
from src.dashboard.pages import (
    logs_layout,
    metrics_layout,
    overview_layout,
    top_models_layout,
)

logger = logging.getLogger(__name__)

# NOTE: AG-Grid JS helpers are imported inside create_dashboard when building index_string.
# Keeping this import out of module scope avoids scoping pitfalls.


def _run(coro: Any) -> Any:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Dash callbacks are sync; when we are already in an event loop (rare in prod),
        # run in a new loop.
        return asyncio.run(coro)

    return asyncio.run(coro)


def create_dashboard(*, cfg: DashboardConfigProtocol) -> dash.Dash:
    app = dash.Dash(
        __name__,
        requests_pathname_prefix="/dashboard/",
        assets_folder=str(Path(__file__).resolve().parents[2] / "assets"),
        assets_url_path="assets",
        external_stylesheets=[dbc.themes.DARKLY],
        suppress_callback_exceptions=True,
        title="Vandamme Dashboard",
    )

    app.layout = html.Div(
        [
            dcc.Location(id="vdm-url"),
            dcc.Store(id="vdm-theme-store", data={"theme": "dark"}),
            dbc.Navbar(
                dbc.Container(
                    [
                        html.Div(
                            [
                                dbc.NavbarBrand(
                                    html.A(
                                        html.Img(
                                            src=app.get_asset_url("vandamme-93x64px.png"),
                                            alt="Vandamme Dashboard",
                                            className="vdm-navbar-logo",
                                        ),
                                        href="/dashboard/",
                                        className="d-flex align-items-center",
                                        title="Vandamme",
                                    ),
                                    href="/dashboard/",
                                ),
                                dbc.Nav(
                                    [
                                        dbc.NavLink("Overview", href="/dashboard/", active="exact"),
                                        dbc.NavLink(
                                            "Metrics", href="/dashboard/metrics", active="exact"
                                        ),
                                        dbc.NavLink(
                                            "Models", href="/dashboard/models", active="exact"
                                        ),
                                        dbc.NavLink(
                                            "Top Models",
                                            href="/dashboard/top-models",
                                            active="exact",
                                        ),
                                        dbc.NavLink(
                                            "Aliases", href="/dashboard/aliases", active="exact"
                                        ),
                                        dbc.NavLink(
                                            "Token Counter",
                                            href="/dashboard/token-counter",
                                            active="exact",
                                        ),
                                        dbc.NavLink("Logs", href="/dashboard/logs", active="exact"),
                                    ],
                                    pills=True,
                                ),
                                dbc.Nav(
                                    [
                                        dbc.NavLink(
                                            "API Docs",
                                            href="/docs",
                                            target="_blank",
                                            external_link=True,
                                        ),
                                    ],
                                    pills=True,
                                ),
                            ],
                            className="d-flex align-items-center gap-2 ps-2",
                        ),
                        html.Span(id="vdm-global-error", className="text-danger ms-auto"),
                    ],
                    fluid=True,
                    className="px-0",
                ),
                color="dark",
                dark=True,
                className="mb-0",
            ),
            html.Div(id="vdm-page"),
        ]
    )

    @app.callback(Output("vdm-page", "children"), Input("vdm-url", "pathname"))
    def route(pathname: str | None) -> Any:
        if pathname in (None, "/dashboard", "/dashboard/"):
            return overview_layout()
        if pathname in ("/dashboard/metrics", "/dashboard/metrics/"):
            return metrics_layout()
        if pathname in ("/dashboard/models", "/dashboard/models/"):
            from src.dashboard.pages import models_layout

            return models_layout()
        if pathname in ("/dashboard/top-models", "/dashboard/top-models/"):
            return top_models_layout()
        if pathname in ("/dashboard/aliases", "/dashboard/aliases/"):
            from src.dashboard.pages import aliases_layout

            return aliases_layout()
        if pathname in ("/dashboard/token-counter", "/dashboard/token-counter/"):
            from src.dashboard.pages import token_counter_layout

            return token_counter_layout()
        if pathname in ("/dashboard/logs", "/dashboard/logs/"):
            return logs_layout()
        return dbc.Container(
            dbc.Alert(
                [html.Div("Not found"), html.Div(dcc.Link("Back", href="/dashboard/"))],
                color="secondary",
            ),
            className="py-3",
            fluid=True,
        )

    # Inject clientside renderer scripts for AG-Grid (models grid)
    # Inline-inject the JS so dash-ag-grid can use vdmModelPageLinkRenderer.
    from src.dashboard.ag_grid.scripts import CELL_RENDERER_SCRIPTS

    app.index_string = app.index_string.replace(
        "</body>", f"<script>{CELL_RENDERER_SCRIPTS}</script></body>"
    )

    # -------------------- Overview callbacks --------------------

    # Simple no-op clientside callback placeholder (keeps dash happy, avoids attribute errors)
    app.clientside_callback(
        "function(pathname){return pathname;}",
        Output("vdm-models-grid", "id"),
        Input("vdm-url", "pathname"),
        prevent_initial_call=True,
    )

    # No-op callbacks for logs grids (prevents grid recreation on updates)
    app.clientside_callback(
        "function(){return arguments[0];}",
        Output("vdm-logs-errors-grid", "id"),
        Input("vdm-logs-poll", "n_intervals"),
        prevent_initial_call=True,
    )
    app.clientside_callback(
        "function(){return arguments[0];}",
        Output("vdm-logs-traces-grid", "id"),
        Input("vdm-logs-poll", "n_intervals"),
        prevent_initial_call=True,
    )

    # -------------------- Overview callbacks --------------------

    @app.callback(
        Output("vdm-health-banner", "children"),
        Output("vdm-providers-table", "children"),
        Output("vdm-kpis", "children"),
        Output("vdm-metrics-disabled-callout", "children"),
        Output("vdm-global-error", "children"),
        Input("vdm-overview-poll", "n_intervals"),
        Input("vdm-refresh-now", "n_clicks"),
        prevent_initial_call=False,
    )
    def refresh_overview(_n: int, _clicks: int | None) -> tuple[Any, Any, Any, Any, str]:
        from src.dashboard.services.overview import build_overview_view

        view = _run(build_overview_view(cfg=cfg))
        return (
            view.banner,
            view.providers_table,
            view.kpis,
            view.metrics_disabled_callout,
            view.global_error,
        )

    @app.callback(
        Output("vdm-test-connection-result", "children"),
        Input("vdm-test-connection", "n_clicks"),
        prevent_initial_call=True,
    )
    def run_test_connection(n_clicks: int) -> Any:
        _ = n_clicks
        payload = _run(fetch_test_connection(cfg=cfg))
        status = str(payload.get("status", "unknown"))
        http_status = payload.get("_http_status", "")

        color = "success" if status == "success" else "danger"
        rows: list[Any] = [
            html.Div(
                [
                    dbc.Badge(status.upper(), color=color, pill=True),
                    html.Span(" "),
                    html.Span(f"HTTP {http_status}"),
                ]
            ),
            html.Div([html.Span("provider: "), html.Span(str(payload.get("provider", "")))]),
            html.Div([html.Span("timestamp: "), html.Span(str(payload.get("timestamp", "")))]),
        ]

        if status == "success":
            rows.append(
                html.Div(
                    [html.Span("response_id: "), html.Code(str(payload.get("response_id", "")))]
                )
            )
        else:
            rows.append(
                html.Div([html.Span("message: "), html.Span(str(payload.get("message", "")))])
            )
            suggestions = payload.get("suggestions")
            if isinstance(suggestions, list) and suggestions:
                rows.append(html.Div("Suggestions", className="text-muted small mt-2"))
                rows.append(html.Ul([html.Li(str(s)) for s in suggestions]))

        return dbc.Alert(rows, color="light", className="mt-2")

    # -------------------- Theme toggle (minimal, elegant) --------------------

    @app.callback(
        Output("vdm-theme-store", "data"),
        Input("vdm-theme-toggle", "value"),
        prevent_initial_call=True,
    )
    def set_theme(is_dark: bool) -> dict[str, str]:
        return {"theme": "dark" if is_dark else "light"}

    # NOTE: For now, theme toggling primarily affects the switch state; changing
    # Bootstrap theme at runtime requires reloading stylesheets. We can implement
    # a reload-on-toggle pattern later if desired.

    # -------------------- Metrics callbacks --------------------

    @app.callback(
        Output("vdm-token-chart", "children"),
        Output("vdm-provider-breakdown", "children"),
        Output("vdm-model-breakdown", "children"),
        Output("vdm-provider-filter", "options"),
        Input("vdm-metrics-poll", "n_intervals"),
        Input("vdm-provider-filter", "value"),
        Input("vdm-model-filter", "value"),
        State("vdm-metrics-poll-toggle", "value"),
        prevent_initial_call=False,
    )
    def refresh_metrics(
        _n: int,
        provider_value: str,
        model_value: str,
        polling: bool,
    ) -> tuple[Any, Any, Any, Any]:
        if not polling and _n:
            # Keep existing UI stable when polling is disabled.
            raise dash.exceptions.PreventUpdate

        from src.dashboard.services.metrics import build_metrics_view

        view = _run(
            build_metrics_view(cfg=cfg, provider_value=provider_value, model_value=model_value)
        )
        return (
            view.token_chart,
            view.provider_breakdown,
            view.model_breakdown,
            view.provider_options,
        )

    @app.callback(Output("vdm-metrics-poll", "interval"), Input("vdm-metrics-interval", "value"))
    def set_metrics_interval(ms: int) -> int:
        return ms

    # -------------------- Models page callbacks --------------------

    @app.callback(
        Output("vdm-models-grid", "rowData"),
        Output("vdm-models-provider", "options"),
        Output("vdm-models-provider", "value"),
        Output("vdm-models-provider-hint", "children"),
        Input("vdm-models-poll", "n_intervals"),
        Input("vdm-models-refresh", "n_clicks"),
        Input("vdm-models-provider", "value"),
        prevent_initial_call=False,
    )
    def refresh_models(
        _n: int,
        _clicks: int | None,
        provider_value: str | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]], str | None, Any]:
        """Refresh models and keep provider selection normalized.

        Provider selection is always a real provider name; the default provider is
        pre-selected and labeled in the dropdown.
        """
        try:
            from src.dashboard.services.models import build_models_view

            view = _run(build_models_view(cfg=cfg, provider_value=provider_value))
            return view.row_data, view.provider_options, view.provider_value, view.hint

        except Exception:
            logger.exception("dashboard.models: refresh failed")
            return (
                [],
                [],
                None,
                html.Span("Failed to load providers", className="text-muted"),
            )

    # Copy-to-clipboard is implemented as a clientside callback in app.py (see below).

    # -------------------- Models detail drawer --------------------

    @app.callback(
        Output("vdm-models-detail-store", "data"),
        Output("vdm-model-details-drawer", "is_open"),
        Input("vdm-models-grid", "selectedRows"),
        Input("vdm-model-details-close", "n_clicks"),
        State("vdm-model-details-drawer", "is_open"),
        prevent_initial_call=True,
    )
    def set_model_details_state(
        selected_rows: list[dict[str, Any]] | None,
        _close_clicks: int | None,
        is_open: bool,
    ) -> tuple[Any, bool]:
        trigger = dash.callback_context.triggered_id

        if trigger == "vdm-model-details-close":
            return None, False

        rows = selected_rows or []
        if not rows:
            return None, False

        focused = rows[0] if isinstance(rows[0], dict) else None
        return {"focused": focused, "selected_count": len(rows)}, True

    # NOTE: We intentionally handle both open + close in the single callback above
    # to avoid Dash's "Duplicate callback outputs" errors.

    @app.callback(
        Output("vdm-model-details-header", "children"),
        Output("vdm-model-details-body", "children"),
        Input("vdm-models-detail-store", "data"),
        prevent_initial_call=True,
    )
    def render_model_details(detail_store: dict[str, Any] | None) -> tuple[Any, Any]:
        if not isinstance(detail_store, dict):
            return html.Div(), html.Div()

        focused = detail_store.get("focused")
        if not isinstance(focused, dict):
            return html.Div(), html.Div()

        selected_count = detail_store.get("selected_count")
        selected_count_i = int(selected_count) if isinstance(selected_count, int) else None

        model_id = str(focused.get("id") or "")
        provider = str(focused.get("provider") or "")
        owned_by = focused.get("owned_by")
        modality = focused.get("architecture_modality")
        context_length = focused.get("context_length")
        max_output_tokens = focused.get("max_output_tokens")
        created_iso = focused.get("created_iso")
        description_full = focused.get("description_full")
        pricing_in = focused.get("pricing_prompt_per_million")
        pricing_out = focused.get("pricing_completion_per_million")
        model_page_url = focused.get("model_page_url")
        model_icon_url = focused.get("model_icon_url")

        raw_json_obj = {
            k: v for k, v in focused.items() if k not in {"description_full", "description_preview"}
        }
        raw_json = json.dumps(raw_json_obj, sort_keys=True, indent=2, ensure_ascii=False)
        raw_json_preview = "\n".join(raw_json.splitlines()[:40])
        if len(raw_json_preview) < len(raw_json):
            raw_json_preview = raw_json_preview + "\n..."

        title_left_bits: list[Any] = []
        if provider:
            title_left_bits.append(provider_badge(provider))
        title_left_bits.append(html.Span(monospace(model_id), className="fw-semibold"))
        if selected_count_i and selected_count_i > 1:
            title_left_bits.append(
                dbc.Badge(
                    f"Showing 1 of {selected_count_i} selected",
                    color="secondary",
                    pill=True,
                    className="ms-2",
                )
            )

        icon = (
            html.Img(
                src=str(model_icon_url),
                style={
                    "width": "96px",
                    "height": "96px",
                    "objectFit": "contain",
                    "borderRadius": "10px",
                    "backgroundColor": "rgba(255,255,255,0.06)",
                    "padding": "8px",
                },
            )
            if isinstance(model_icon_url, str) and model_icon_url
            else html.Div(
                style={"width": "96px", "height": "96px"},
            )
        )

        header = dbc.Row(
            [
                dbc.Col(icon, width="auto"),
                dbc.Col(html.Div(title_left_bits), width=True),
                dbc.Col(
                    (
                        dbc.Button(
                            "Open provider page",
                            href=str(model_page_url),
                            target="_blank",
                            external_link=True,
                            color="primary",
                            outline=True,
                            size="sm",
                        )
                        if isinstance(model_page_url, str) and model_page_url
                        else html.Div()
                    ),
                    width="auto",
                ),
            ],
            align="center",
            className="mb-3",
        )

        header = html.Div(header, className="mb-3")

        def _row(label: str, value: Any) -> html.Tr:
            return html.Tr([html.Td(label, className="text-muted"), html.Td(value)])

        created_cell: Any
        created_day = str(created_iso) if created_iso is not None else ""
        if created_day and len(created_day) == 10:
            # created_iso in row data is a YYYY-MM-DD string. Show it directly.
            created_cell = monospace(created_day)
        else:
            created_cell = html.Span("—", className="text-muted")

        pricing_in_cell = (
            monospace(pricing_in) if pricing_in else html.Span("—", className="text-muted")
        )
        pricing_out_cell = (
            monospace(pricing_out) if pricing_out else html.Span("—", className="text-muted")
        )

        body_children: list[Any] = [
            html.Div("Overview", className="text-muted small"),
            dbc.Table(
                html.Tbody(
                    [
                        _row("Model", monospace(model_id)),
                        _row("Provider", monospace(provider or "—")),
                        _row("Sub-provider", monospace(owned_by or "—")),
                        _row("Modality", monospace(modality or "—")),
                        _row("Created", created_cell),
                    ]
                ),
                bordered=False,
                striped=True,
                size="sm",
                className="table-dark mt-2",
            ),
            html.Hr(),
            html.Div("Context", className="text-muted small"),
            dbc.Table(
                html.Tbody(
                    [
                        _row("Context length", monospace(context_length or "—")),
                        _row("Max output", monospace(max_output_tokens or "—")),
                    ]
                ),
                bordered=False,
                striped=True,
                size="sm",
                className="table-dark mt-2",
            ),
            html.Hr(),
            html.Div("Pricing", className="text-muted small"),
            dbc.Table(
                html.Tbody(
                    [
                        _row("$/M input", pricing_in_cell),
                        _row("$/M output", pricing_out_cell),
                    ]
                ),
                bordered=False,
                striped=True,
                size="sm",
                className="table-dark mt-2",
            ),
            html.Hr(),
            html.Div("Description", className="text-muted small"),
            html.Div(
                str(description_full)
                if isinstance(description_full, str) and description_full
                else "—",
                className="mt-2",
                style={"whiteSpace": "pre-wrap"},
            ),
            html.Hr(),
            html.Details(
                [
                    html.Summary(
                        "Raw JSON",
                        style={"cursor": "pointer"},
                        className="text-muted small",
                    ),
                    html.Pre(
                        raw_json_preview,
                        className="mt-2",
                        style={
                            "whiteSpace": "pre-wrap",
                            "fontFamily": ("ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas"),
                            "fontSize": "0.8rem",
                            "maxHeight": "40vh",
                            "overflow": "auto",
                            "backgroundColor": "rgba(255,255,255,0.06)",
                            "padding": "10px",
                            "borderRadius": "6px",
                        },
                    ),
                ],
                className="mt-2",
            ),
        ]

        body = dbc.Card(
            dbc.CardBody(body_children),
            className="bg-dark text-white",
        )

        return header, body

    # -------------------- Copy selected model IDs (client-side) --------------------

    # vdmToast is defined by injected dashboard JS (see CELL_RENDERER_SCRIPTS).
    # Avoid a Dash callback here to prevent duplicate outputs.

    # Single toast renderer for BOTH:
    # - "Copy selected IDs" button
    # - click-to-copy on Model ID cells
    app.clientside_callback(
        """
        async function(copy_clicks, toast_clicks) {
            // If the user clicked the "Copy selected IDs" button, perform copy-selected.
            if (copy_clicks) {
                try {
                    const r = await window.vdmCopySelectedModelIds('vdm-models-grid');
                    const ok = r && r.ok;
                    const msg = (r && r.message) ? r.message : 'Copy failed';
                    return [
                        true,
                        msg,
                        ok ? 'success' : 'warning',
                        copy_clicks,
                        dash_clientside.no_update,
                    ];
                } catch (e) {
                    const msg = 'Copy failed: ' + (e && e.message ? e.message : String(e));
                    return [
                        true,
                        msg,
                        'danger',
                        copy_clicks,
                        dash_clientside.no_update,
                    ];
                }
            }

            // If grid JS triggered a toast click, render its payload.
            if (toast_clicks) {
                const payload = window.__vdm_last_toast_payload;
                if (payload) {
                    let obj;
                    try {
                        obj = JSON.parse(payload);
                    } catch (e) {
                        obj = { level: 'info', message: String(payload) };
                    }

                    const modelId = obj && obj.model_id;
                    if (modelId && !obj.message) {
                        obj.message = 'Copied model id: ' + String(modelId);
                        obj.level = obj.level || 'success';
                    }

                    const level = obj.level || 'info';
                    const message = obj.message || '';
                    const icon =
                        level === 'success'
                            ? 'success'
                            : level === 'danger'
                              ? 'danger'
                              : 'warning';
                    return [
                        true,
                        message,
                        icon,
                        dash_clientside.no_update,
                        payload,
                    ];
                }
            }

            return [
                false,
                dash_clientside.no_update,
                dash_clientside.no_update,
                dash_clientside.no_update,
                dash_clientside.no_update,
            ];
        }
        """,
        Output("vdm-models-copy-toast", "is_open"),
        Output("vdm-models-copy-toast", "children"),
        Output("vdm-models-copy-toast", "icon"),
        Output("vdm-models-copy-sink", "children"),
        Output("vdm-models-toast-payload", "children"),
        Input("vdm-models-copy-ids", "n_clicks"),
        Input("vdm-models-toast-trigger", "n_clicks"),
        prevent_initial_call=True,
    )

    # -------------------- Top Models page callbacks --------------------

    @app.callback(
        Output("vdm-top-models-content", "children"),
        Output("vdm-top-models-provider", "options"),
        Output("vdm-top-models-status", "children"),
        Output("vdm-top-models-meta", "children"),
        Output("vdm-top-models-aliases", "children"),
        Input("vdm-top-models-poll", "n_intervals"),
        Input("vdm-top-models-refresh", "n_clicks"),
        Input("vdm-top-models-provider", "value"),
        Input("vdm-top-models-limit", "value"),
        Input("vdm-top-models-search", "value"),
        prevent_initial_call=False,
    )
    def refresh_top_models(
        _n: int,
        refresh_clicks: int | None,
        provider_value: str | None,
        limit_value: int | None,
        search_value: str | None,
    ) -> tuple[Any, list[dict[str, str]], Any, Any, Any]:
        try:
            from src.dashboard.services.top_models import build_top_models_view

            view = _run(
                build_top_models_view(
                    cfg=cfg,
                    provider_value=provider_value,
                    limit_value=limit_value,
                    search_value=search_value,
                    force_refresh=bool(refresh_clicks),
                )
            )
            return view.content, view.provider_options, view.status, view.meta, view.aliases

        except Exception:
            logger.exception("dashboard.top-models: refresh failed")
            return (
                dbc.Alert(
                    "Failed to load top models. See server logs for details.", color="danger"
                ),
                [{"label": "All", "value": ""}],
                html.Span("Failed", className="text-muted"),
                html.Div(),
                html.Div(),
            )

    # -------------------- Aliases page callbacks --------------------

    @app.callback(
        Output("vdm-aliases-content", "children"),
        Input("vdm-aliases-poll", "n_intervals"),
        Input("vdm-aliases-refresh", "n_clicks"),
        Input("vdm-aliases-search", "value"),
        prevent_initial_call=False,
    )
    def refresh_aliases(
        _n: int,
        _clicks: int | None,
        search_term: str | None,
    ) -> Any:
        try:
            from src.dashboard.services.aliases import build_aliases_view

            view = _run(build_aliases_view(cfg=cfg, search_term=search_term))
            return view.content

        except Exception as e:
            return dbc.Alert(f"Failed to load aliases: {e}", color="danger")

    # -------------------- Logs callbacks --------------------

    @app.callback(
        Output("vdm-logs-disabled-callout", "children"),
        Output("vdm-logs-errors-grid", "rowData"),
        Output("vdm-logs-traces-grid", "rowData"),
        Input("vdm-logs-poll", "n_intervals"),
        prevent_initial_call=False,
    )
    def refresh_logs(_n: int) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]:
        """Refresh logs and update grid rowData only (avoids grid recreation/blinking)."""
        try:
            from src.dashboard.services.logs import build_logs_view

            view = _run(build_logs_view(cfg=cfg))
            return view.disabled_callout, view.errors_row_data, view.traces_row_data

        except Exception as e:  # noqa: BLE001
            return (
                dbc.Alert(f"Failed to load logs: {e}", color="danger"),
                [],
                [],
            )

    # -------------------- Token Counter callbacks --------------------

    @app.callback(
        Output("vdm-token-counter-model", "options"),
        Input("vdm-url", "pathname"),
        prevent_initial_call=False,
    )
    def load_token_counter_models(_pathname: str) -> list[dict[str, Any]]:
        """Load available models for the token counter."""
        try:
            models_data = _run(fetch_models(cfg=cfg))
            models = models_data.get("data", [])

            # Extract unique model IDs with display names
            model_options = []
            seen = set()
            for model in models:
                model_id = model.get("id", "")
                display_name = model.get("display_name", model_id)
                if model_id and model_id not in seen:
                    seen.add(model_id)
                    label = f"{display_name} ({model_id})" if display_name != model_id else model_id
                    model_options.append({"label": label, "value": model_id})

            return sorted(model_options, key=lambda x: x["label"])

        except Exception:
            # Return some common defaults if API call fails
            return [
                {"label": "Claude 3.5 Sonnet", "value": "claude-3-5-sonnet-20241022"},
                {"label": "Claude 3.5 Haiku", "value": "claude-3-5-haiku-20241022"},
                {"label": "GPT-4o", "value": "gpt-4o"},
                {"label": "GPT-4o Mini", "value": "gpt-4o-mini"},
            ]

    @app.callback(
        Output("vdm-token-counter-result", "children"),
        Input("vdm-token-counter-message", "value"),
        Input("vdm-token-counter-system", "value"),
        Input("vdm-token-counter-model", "value"),
        prevent_initial_call=False,
    )
    def count_tokens(
        message: str | None,
        system_message: str | None,
        model: str | None,
    ) -> Any:
        """Count tokens for the current input."""
        if not message and not system_message:
            return html.Div("Enter a message to count tokens", className="text-muted small")

        if not model:
            return html.Div("Select a model to count tokens", className="text-warning small")

        # For now, use a simple character-based estimation
        # In a real implementation, you would call the /v1/messages/count_tokens endpoint
        total_chars = len(message or "") + len(system_message or "")
        estimated_tokens = max(1, total_chars // 4)

        return token_display(estimated_tokens, "Estimated Tokens")

    @app.callback(
        Output("vdm-token-counter-message", "value"),
        Output("vdm-token-counter-system", "value"),
        Input("vdm-token-counter-clear", "n_clicks"),
        prevent_initial_call=True,
    )
    def clear_token_counter(_n_clicks: int) -> tuple[None, None]:
        """Clear all token counter inputs."""
        return None, None

    # Add AG-Grid JavaScript and custom CSS to layout
    from src.dashboard.ag_grid.scripts import CELL_RENDERER_SCRIPTS

    # Custom CSS for AG-Grid dark theme (general theme lives in /assets/theme.css)
    ag_grid_css = """
    <style>
    .ag-theme-alpine-dark {
        background-color: #2b3035 !important;
    }
    .ag-theme-alpine-dark .ag-header {
        background-color: #343a40 !important;
        color: #ffffff !important;
        border-bottom: 1px solid #495057 !important;
    }
    .ag-theme-alpine-dark .ag-row {
        background-color: #2b3035 !important;
        border-bottom: 1px solid #343a40 !important;
        color: #ffffff !important;
    }
    .ag-theme-alpine-dark .ag-row:hover {
        background-color: #343a40 !important;
    }
    .ag-theme-alpine-dark .ag-root-wrapper {
        background-color: #2b3035 !important;
        border: 1px solid #495057 !important;
    }
    .ag-theme-alpine-dark .ag-cell {
        color: #ffffff !important;
    }
    .ag-theme-alpine-dark .ag-header-cell-text {
        color: #ffffff !important;
    }
    .ag-theme-alpine-dark .ag-paging-panel {
        background-color: #343a40 !important;
        color: #ffffff !important;
        border-top: 1px solid #495057 !important;
    }
    .ag-theme-alpine-dark .ag-paging-page-summary-panel {
        color: #ffffff !important;
    }
    .ag-theme-alpine-dark .ag-theme-alpine .ag-header-cell {
        border-right: 1px solid #495057 !important;
    }
    .ag-theme-alpine-dark .ag-ltr .ag-has-focus .ag-cell-focus {
        border: 1px solid #0d6efd !important;
    }
    .ag-theme-alpine-dark .ag-icon {
        color: #ffffff !important;
    }
    /* Pagination controls */
    .ag-theme-alpine-dark .ag-paging-button {
        background-color: #495057 !important;
        color: #ffffff !important;
        border-color: #6c757d !important;
    }
    .ag-theme-alpine-dark .ag-paging-button:hover {
        background-color: #6c757d !important;
        color: #ffffff !important;
    }
    .ag-theme-alpine-dark .ag-paging-button:disabled {
        background-color: #343a40 !important;
        color: #6c757d !important;
    }
    .ag-theme-alpine-dark .ag-paging-button.ag-current {
        background-color: #0d6efd !important;
        color: #ffffff !important;
    }
    /* Filter controls */
    .ag-theme-alpine-dark .ag-filter {
        background-color: #343a40 !important;
        color: #ffffff !important;
        border-color: #495057 !important;
    }
    .ag-theme-alpine-dark .ag-filter input,
    .ag-theme-alpine-dark .ag-filter select {
        background-color: #2b3035 !important;
        color: #ffffff !important;
        border-color: #495057 !important;
    }
    /* Column menu */
    .ag-theme-alpine-dark .ag-menu {
        background-color: #343a40 !important;
        color: #ffffff !important;
        border-color: #495057 !important;
    }
    .ag-theme-alpine-dark .ag-menu-option {
        color: #ffffff !important;
    }
    .ag-theme-alpine-dark .ag-menu-option-active {
        background-color: #495057 !important;
    }
    /* Dropdown high-contrast overrides (in addition to /assets/theme.css) */
    .dash-dropdown .Select-control,
    .dash-dropdown .Select-menu-outer,
    .dash-dropdown .Select-menu,
    .dcc-dropdown .Select-control,
    .dcc-dropdown .Select-menu-outer,
    .dcc-dropdown .Select-menu,
    .Select-control,
    .Select-menu-outer,
    .Select-menu {
        background-color: #2b3035 !important;
        border-color: #0d6efd !important;
        color: #ffffff !important;
        border-radius: 0.375rem !important;
    }
    .Select-menu-outer, .Select-menu {
        box-shadow: 0 4px 12px rgba(0,0,0,0.4) !important;
    }
    .Select-placeholder,
    .Select--single > .Select-control .Select-value-label,
    .Select-value-label {
        color: #dee2e6 !important;
    }
    .Select-input > input {
        color: #ffffff !important;
    }
    .Select-option {
        background-color: #2b3035 !important;
        color: #ffffff !important;
    }
    .Select-option.is-focused {
        background-color: #0d6efd !important;
        color: #ffffff !important;
    }
    .Select-option.is-selected {
        background-color: #0b5ed7 !important;
        color: #ffffff !important;
    }
    .Select-control:hover {
        border-color: #66b2ff !important;
    }
    .Select-control.is-open,
    .Select-control.is-focused {
        box-shadow: 0 0 0 1px #0d6efd !important;
        border-color: #0d6efd !important;
    }
    .Select-clear-zone,
    .Select-arrow-zone,
    .Select-clear,
    .Select-arrow {
        color: #ffffff !important;
    }
    .Select-control,
    .dash-dropdown .Select-control,
    .dcc-dropdown .Select-control {
        min-height: 40px !important;
    }
    </style>
    """

    # Inject the AG-Grid CSS and JavaScript into the page.
    # Note: General theming moved to /assets/theme.css.
    # This inline block keeps only AG-Grid specifics and helper bootstrapping.
    app.index_string = (
        """
    <!DOCTYPE html>
    <html>
        <head>
            {%metas%}
            <title>{%title%}</title>
            {%favicon%}
            {%css%}
            """
        + ag_grid_css
        + """
        </head>
        <body>
            {%app_entry%}
            <footer>
                {%config%}
                {%scripts%}
                <script>
                // Ensure dash-ag-grid runtime is loaded before running our helpers.
                (function(){
                  function boot(){
                    if (window.dash_ag_grid && window.dash_ag_grid.getApi) {
                      try {
                        """
        + CELL_RENDERER_SCRIPTS
        + """
                        if (window.vdmAttachModelCellCopyListener) {
                          // Re-attach on every boot tick to handle grid re-renders.
                          window.vdmAttachModelCellCopyListener('vdm-models-grid');
                          window.vdmAttachModelCellCopyListener('vdm-top-models-grid');
                          setTimeout(function(){
                            window.vdmAttachModelCellCopyListener('vdm-models-grid');
                            window.vdmAttachModelCellCopyListener('vdm-top-models-grid');
                          }, 250);
                          setTimeout(function(){
                            window.vdmAttachModelCellCopyListener('vdm-models-grid');
                            window.vdmAttachModelCellCopyListener('vdm-top-models-grid');
                          }, 1500);
                        }
                      } catch (e) {
                        console.error('[vdm] dashboard helpers failed to initialize', e);
                      }
                      return;
                    }
                    setTimeout(boot, 25);
                  }
                  boot();
                })();
                </script>
                {%renderer%}
            </footer>
        </body>
    </html>
    """
    )

    return app
