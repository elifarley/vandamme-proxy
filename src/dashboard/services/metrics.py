from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import dash_bootstrap_components as dbc  # type: ignore[import-untyped]
from dash import html

from src.dashboard.components.breakdown_tables import breakdown_table
from src.dashboard.data_sources import fetch_all_providers, fetch_running_totals
from src.dashboard.pages import (
    compute_metrics_views,
    parse_totals_for_chart,
    token_composition_chart,
)


def _provider_breakdown_component(rows: list[dict[str, Any]]) -> Any:
    from src.dashboard.components.breakdown_tables import provider_breakdown_table_view

    return provider_breakdown_table_view(rows)


def _model_breakdown_component(rows: list[dict[str, Any]], provider_selected: bool) -> Any:
    if not provider_selected:
        return dbc.Alert("Select a provider to see model breakdown.", color="secondary")

    return breakdown_table(kind="model", rows=rows)


@dataclass(frozen=True)
class MetricsView:
    token_chart: Any
    provider_breakdown: Any
    model_breakdown: Any
    provider_options: list[dict[str, str]]


async def build_metrics_view(*, cfg: Any, provider_value: str, model_value: str) -> MetricsView:
    """Fetch metrics data and build dashboard view fragments.

    This keeps Dash callbacks thin and makes the shape easy to unit test.
    """
    provider_filter = provider_value or None
    model_filter = model_value.strip() or None

    providers = await fetch_all_providers(cfg=cfg)
    running = await fetch_running_totals(cfg=cfg, provider=provider_filter, model=model_filter)

    if "# Message" in running:
        return MetricsView(
            token_chart=dbc.Alert(
                "Metrics are disabled. Set LOG_REQUEST_METRICS=true.", color="info"
            ),
            provider_breakdown=html.Div(),
            model_breakdown=html.Div(),
            provider_options=[{"label": "All", "value": ""}],
        )

    totals = parse_totals_for_chart(running)
    prov_rows, model_rows = compute_metrics_views(running, provider_filter)

    sorted_providers = sorted(p for p in providers if isinstance(p, str) and p)
    options = [{"label": "All", "value": ""}] + [{"label": p, "value": p} for p in sorted_providers]

    token_chart = token_composition_chart(totals)
    provider_breakdown = _provider_breakdown_component(prov_rows)
    model_breakdown = _model_breakdown_component(
        model_rows, provider_selected=bool(provider_filter)
    )

    return MetricsView(
        token_chart=token_chart,
        provider_breakdown=provider_breakdown,
        model_breakdown=model_breakdown,
        provider_options=options,
    )
