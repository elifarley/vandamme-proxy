from __future__ import annotations

from typing import Any

import dash
from dash import Input, Output, State

from src.dashboard.data_sources import DashboardConfigProtocol


def register_metrics_callbacks(
    *,
    app: dash.Dash,
    cfg: DashboardConfigProtocol,
    run: Any,
) -> None:
    @app.callback(
        Output("vdm-token-chart", "children"),
        Output("vdm-active-requests", "children"),
        Output("vdm-provider-breakdown", "children"),
        Output("vdm-model-breakdown", "children"),
        Input("vdm-metrics-poll", "n_intervals"),
        Input("vdm-metrics-refresh", "n_clicks"),
        State("vdm-metrics-poll-toggle", "value"),
        prevent_initial_call=False,
    )
    def refresh_metrics(
        n: int,
        refresh_clicks: int | None,
        polling: bool,
    ) -> tuple[Any, Any, Any, Any]:
        # Manual refresh should always work. Polling can be disabled.
        if not refresh_clicks and (not polling) and n:
            raise dash.exceptions.PreventUpdate

        from src.dashboard.services.metrics import build_metrics_view

        view = run(build_metrics_view(cfg=cfg))
        return (
            view.token_chart,
            view.active_requests,
            view.provider_breakdown,
            view.model_breakdown,
        )

    @app.callback(Output("vdm-metrics-poll", "interval"), Input("vdm-metrics-interval", "value"))
    def set_metrics_interval(ms: int) -> int:
        return ms

    app.clientside_callback(
        """
        function(n) {
            if (window.dash_clientside
                && window.dash_clientside.vdm_metrics
                && window.dash_clientside.vdm_metrics.user_active) {
                return window.dash_clientside.vdm_metrics.user_active(n);
            }
            return false;
        }
        """,
        Output("vdm-metrics-user-active", "data"),
        Input("vdm-metrics-user-active-poll", "n_intervals"),
        prevent_initial_call=False,
    )

    @app.callback(
        Output("vdm-metrics-poll", "disabled"),
        Input("vdm-metrics-user-active", "data"),
        State("vdm-metrics-poll-toggle", "value"),
    )
    def pause_polling_while_active(user_active: bool, polling_enabled: bool) -> bool:
        # Disable polling if user is interacting; also disable if polling is manually off.
        return (not polling_enabled) or bool(user_active)
