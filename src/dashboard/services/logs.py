from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import dash_bootstrap_components as dbc  # type: ignore[import-untyped]

from src.dashboard.ag_grid.transformers import logs_errors_row_data, logs_traces_row_data
from src.dashboard.data_sources import fetch_logs


@dataclass(frozen=True)
class LogsView:
    disabled_callout: Any
    errors_row_data: list[dict[str, Any]]
    traces_row_data: list[dict[str, Any]]


async def build_logs_view(*, cfg: Any) -> LogsView:
    payload = await fetch_logs(cfg=cfg)

    systemd = payload.get("systemd")
    if not isinstance(systemd, dict):
        systemd = {}

    effective = bool(systemd.get("effective"))
    handler = str(systemd.get("handler") or "")

    if not effective:
        msg = (
            "Logs are disabled. Start the server with --systemd (and ensure /dev/log is available)."
        )
        return LogsView(
            disabled_callout=dbc.Alert(msg, color="secondary"),
            errors_row_data=[],
            traces_row_data=[],
        )

    errors = payload.get("errors")
    if not isinstance(errors, list):
        errors = []

    traces = payload.get("traces")
    if not isinstance(traces, list):
        traces = []

    disabled_callout = dbc.Alert(f"systemd active (handler={handler})", color="dark")

    return LogsView(
        disabled_callout=disabled_callout,
        errors_row_data=logs_errors_row_data(errors),
        traces_row_data=logs_traces_row_data(traces),
    )
