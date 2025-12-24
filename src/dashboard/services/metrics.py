from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import dash_bootstrap_components as dbc  # type: ignore[import-untyped]
from dash import html

from src.dashboard.components.ag_grid import (
    metrics_active_requests_component,
    metrics_models_ag_grid,
    metrics_providers_ag_grid,
)
from src.dashboard.data_sources import fetch_active_requests, fetch_running_totals
from src.dashboard.pages import parse_totals_for_chart, token_composition_chart


def _provider_breakdown_component(running_totals: dict[str, Any]) -> Any:
    return metrics_providers_ag_grid(running_totals)


def _model_breakdown_component(running_totals: dict[str, Any]) -> Any:
    return metrics_models_ag_grid(running_totals)


@dataclass(frozen=True)
class MetricsView:
    token_chart: Any
    active_requests: Any
    provider_breakdown: Any
    model_breakdown: Any


async def build_metrics_view(*, cfg: Any) -> MetricsView:
    """Fetch metrics data and build dashboard view fragments.

    This keeps Dash callbacks thin and makes the shape easy to unit test.
    """

    # Rollup grids should be completed-only. Active requests are shown separately.
    running = await fetch_running_totals(cfg=cfg, include_active=False)
    active = await fetch_active_requests(cfg=cfg)

    if "# Message" in running:
        return MetricsView(
            token_chart=dbc.Alert(
                "Metrics are disabled. Set LOG_REQUEST_METRICS=true.", color="info"
            ),
            active_requests=html.Div(),
            provider_breakdown=html.Div(),
            model_breakdown=html.Div(),
        )

    totals = parse_totals_for_chart(running)

    token_chart = token_composition_chart(totals)
    active_requests = metrics_active_requests_component(active)
    provider_breakdown = _provider_breakdown_component(running)
    model_breakdown = _model_breakdown_component(running)

    return MetricsView(
        token_chart=token_chart,
        active_requests=active_requests,
        provider_breakdown=provider_breakdown,
        model_breakdown=model_breakdown,
    )
