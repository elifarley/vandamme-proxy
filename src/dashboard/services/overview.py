from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import dash_bootstrap_components as dbc  # type: ignore[import-untyped]
from dash import html

from src.dashboard.data_sources import fetch_health, fetch_running_totals
from src.dashboard.pages import (
    health_banner,
    kpis_grid,
    metrics_disabled_callout,
    parse_totals_for_chart,
    providers_table,
)


@dataclass(frozen=True)
class OverviewView:
    banner: Any
    providers_table: Any
    kpis: Any
    metrics_disabled_callout: Any
    global_error: str


async def build_overview_view(*, cfg: Any) -> OverviewView:
    try:
        health = await fetch_health(cfg=cfg)
        running = await fetch_running_totals(cfg=cfg)

        banner = health_banner(health)
        prov_table = providers_table(health)

        callout = metrics_disabled_callout(running)
        totals = parse_totals_for_chart(running)
        kpis = kpis_grid(totals)

        return OverviewView(
            banner=banner,
            providers_table=prov_table,
            kpis=kpis,
            metrics_disabled_callout=callout,
            global_error="",
        )
    except Exception as e:  # noqa: BLE001
        return OverviewView(
            banner=dbc.Alert(f"Failed to refresh: {e}", color="danger"),
            providers_table=html.Div(),
            kpis=html.Div(),
            metrics_disabled_callout=None,
            global_error=str(e),
        )
