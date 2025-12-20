from __future__ import annotations

import asyncio
import logging
from typing import Any

import dash
import dash_bootstrap_components as dbc  # type: ignore[import-untyped]
from dash import Input, Output, State, dcc, html

from src.dashboard.components.ui import (
    alias_table,
    empty_state,
    monospace,
    provider_badge,
    token_display,
)
from src.dashboard.data_sources import (
    DashboardConfigProtocol,
    fetch_aliases,
    fetch_all_providers,
    fetch_health,
    fetch_models,
    fetch_running_totals,
    fetch_test_connection,
)
from src.dashboard.pages import (
    compute_metrics_views,
    health_banner,
    kpis_grid,
    metrics_disabled_callout,
    metrics_layout,
    model_breakdown_table,
    overview_layout,
    parse_totals_for_chart,
    provider_breakdown_table,
    providers_table,
    token_composition_chart,
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
                        dbc.NavbarBrand("Vandamme", href="/dashboard/"),
                        dbc.Nav(
                            [
                                dbc.NavLink("Overview", href="/dashboard/", active="exact"),
                                dbc.NavLink("Metrics", href="/dashboard/metrics", active="exact"),
                                dbc.NavLink("Models", href="/dashboard/models", active="exact"),
                                dbc.NavLink("Aliases", href="/dashboard/aliases", active="exact"),
                                dbc.NavLink(
                                    "Token Counter", href="/dashboard/token-counter", active="exact"
                                ),
                            ],
                            pills=True,
                            className="me-3",
                        ),
                        dbc.Nav(
                            [
                                dbc.NavLink(
                                    "API Docs", href="/redoc", target="_blank", external_link=True
                                ),
                            ],
                            pills=True,
                        ),
                        html.Span(id="vdm-global-error", className="text-danger ms-auto"),
                    ]
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
        if pathname in ("/dashboard/aliases", "/dashboard/aliases/"):
            from src.dashboard.pages import aliases_layout

            return aliases_layout()
        if pathname in ("/dashboard/token-counter", "/dashboard/token-counter/"):
            from src.dashboard.pages import token_counter_layout

            return token_counter_layout()
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
    from src.dashboard.components.ag_grid import CELL_RENDERER_SCRIPTS

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
        try:
            health = _run(fetch_health(cfg=cfg))
            running = _run(fetch_running_totals(cfg=cfg))

            banner = health_banner(health)
            prov_table = providers_table(health)

            callout = metrics_disabled_callout(running)
            totals = parse_totals_for_chart(running)
            kpis = kpis_grid(totals)

            return banner, prov_table, kpis, callout, ""
        except Exception as e:  # noqa: BLE001
            return (
                dbc.Alert(f"Failed to refresh: {e}", color="danger"),
                html.Div(),
                html.Div(),
                None,
                str(e),
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
        Input("vdm-apply-filters", "n_clicks"),
        State("vdm-provider-filter", "value"),
        State("vdm-model-filter", "value"),
        State("vdm-metrics-poll-toggle", "value"),
        prevent_initial_call=False,
    )
    def refresh_metrics(
        _n: int,
        _apply: int | None,
        provider_value: str,
        model_value: str,
        polling: bool,
    ) -> tuple[Any, Any, Any, Any]:
        _ = _apply
        if not polling and _n:
            # Keep existing UI stable when polling is disabled.
            raise dash.exceptions.PreventUpdate

        provider_filter = provider_value or None
        model_filter = model_value.strip() or None

        running = _run(fetch_running_totals(cfg=cfg, provider=provider_filter, model=model_filter))

        if "# Message" in running:
            totals = parse_totals_for_chart(running)
            return (
                dbc.Alert("Metrics are disabled. Set LOG_REQUEST_METRICS=true.", color="info"),
                html.Div(),
                html.Div(),
                [{"label": "All", "value": ""}],
            )

        totals = parse_totals_for_chart(running)
        prov_rows, model_rows = compute_metrics_views(running, provider_filter)

        options = [{"label": "All", "value": ""}] + [
            {"label": r["provider"], "value": r["provider"]} for r in prov_rows
        ]

        token_chart = token_composition_chart(totals)
        prov_table = provider_breakdown_table(prov_rows)
        model_table = (
            model_breakdown_table(model_rows)
            if provider_filter
            else dbc.Alert("Select a provider to see model breakdown.", color="secondary")
        )

        return token_chart, prov_table, model_table, options

    @app.callback(Output("vdm-metrics-poll", "interval"), Input("vdm-metrics-interval", "value"))
    def set_metrics_interval(ms: int) -> int:
        return ms

    # -------------------- Models page callbacks --------------------

    @app.callback(
        Output("vdm-models-content", "children"),
        Output("vdm-models-provider", "options"),
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
    ) -> tuple[Any, list[dict[str, str]], Any]:
        try:
            # Provider dropdown options come from /health.
            health = _run(fetch_health(cfg=cfg))
            providers = _run(fetch_all_providers(cfg=cfg))
            default_provider = health.get("default_provider")
            if not isinstance(default_provider, str):
                default_provider = ""

            default_label = (
                ["Default provider (", default_provider, ")"]
                if default_provider
                else ["Default provider"]
            )

            provider_options = [{"label": "".join(default_label), "value": ""}] + [
                {"label": p, "value": p} for p in sorted(providers)
            ]

            # Normalize provider selection (empty -> None)
            provider = provider_value.strip() if provider_value else None

            hint = (
                [html.Span("Listing models for "), provider_badge(provider)]
                if provider
                else [
                    html.Span("Listing models for default provider "),
                    provider_badge(default_provider)
                    if default_provider
                    else html.Span("(unknown)", className="text-muted"),
                    html.Span(" · clear to override", className="text-muted"),
                ]
            )

            # Fetch models (filtering/sorting handled in-grid)
            models_data = _run(fetch_models(cfg=cfg, provider=provider))
            models = models_data.get("data", [])

            logger.debug(
                "dashboard.models: fetched models",
                extra={
                    "model_count": len(models),
                    "first_model_id": (models[0].get("id") if models else None),
                    "provider": provider or "<default>",
                },
            )

            # Provider is not always encoded per model when fetching without a provider filter.
            # Keep a consistent value for display.
            #
            # IMPORTANT: When the user selects "Default provider" (provider is None), we still
            # want model-page links to work. Prefer the actual default provider from /health
            # for missing provider fields.
            inferred_provider = provider or default_provider or "multiple"
            for model in models:
                if not model.get("provider"):
                    model["provider"] = inferred_provider

            if not models:
                return empty_state("No models found", "🔍"), provider_options, hint

            from src.dashboard.components.ui import models_table

            return (
                models_table(
                    models,
                    sort_field="id",
                    sort_desc=False,
                    show_provider=True,
                ),
                provider_options,
                hint,
            )

        except Exception:
            logger.exception("dashboard.models: refresh failed")
            return (
                dbc.Alert("Failed to load models. See server logs for details.", color="danger"),
                [{"label": "Default provider", "value": ""}],
                html.Span("Failed to load providers", className="text-muted"),
            )

    # Copy-to-clipboard is implemented as a clientside callback in app.py (see below).

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
            aliases_data = _run(fetch_aliases(cfg=cfg))
            aliases = aliases_data.get("aliases", {})

            # Filter aliases based on search term
            if search_term and search_term.strip():
                search_lower = search_term.lower().strip()
                filtered_aliases = {}
                for provider, provider_aliases in aliases.items():
                    if isinstance(provider_aliases, dict):
                        filtered = {
                            alias: mapping
                            for alias, mapping in provider_aliases.items()
                            if search_lower in alias.lower() or search_lower in mapping.lower()
                        }
                        if filtered:
                            filtered_aliases[provider] = filtered
                aliases = filtered_aliases

            if not aliases:
                return empty_state("No aliases found matching your criteria", "🔍")

            # Create expandable sections for each provider
            sections = []
            for provider, provider_aliases in aliases.items():
                if not isinstance(provider_aliases, dict):
                    continue

                # Create table for this provider's aliases
                rows = []
                for alias_name, maps_to in provider_aliases.items():
                    rows.append(
                        html.Tr(
                            [
                                html.Td(alias_name),
                                html.Td(monospace(maps_to)),
                            ]
                        )
                    )

                if rows:
                    sections.append(
                        dbc.AccordionItem(
                            [
                                html.H5([provider_badge(provider), f" {provider}"]),
                                alias_table({provider: provider_aliases}),
                            ],
                            title=f"{provider} ({len(rows)} aliases)",
                            item_id=provider,
                        )
                    )

            if not sections:
                return empty_state("No aliases configured", "📋")

            return dbc.Accordion(sections, start_collapsed=True, flush=True)

        except Exception as e:
            return dbc.Alert(f"Failed to load aliases: {e}", color="danger")

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
    from src.dashboard.components.ag_grid import CELL_RENDERER_SCRIPTS

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
                          setTimeout(function(){
                            window.vdmAttachModelCellCopyListener('vdm-models-grid');
                          }, 250);
                          setTimeout(function(){
                            window.vdmAttachModelCellCopyListener('vdm-models-grid');
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
