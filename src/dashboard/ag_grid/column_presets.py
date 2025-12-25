"""Reusable AG Grid column definitions for the dashboard.

Keep these helpers small and composable. They should return plain dicts that can be
merged/overridden by individual grid builders.

This module is intentionally framework-light so it can be used across pages.
"""

from __future__ import annotations

from typing import Any

_MONO_FONT = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas"


def last_col(
    *,
    width: int = 120,
    sort: str | None = None,
) -> dict[str, Any]:
    return {
        "headerName": "Last",
        "field": "last_accessed",
        "sortable": True,
        "filter": True,
        "resizable": True,
        "width": width,
        "suppressSizeToFit": True,
        "cellRenderer": "vdmRecencyDotRenderer",
        **({"sort": sort} if sort else {}),
    }


def qualified_model_col(
    *,
    header: str = "Model",
    flex: int = 2,
    width: int = 280,
    min_width: int | None = None,
    sort: str | None = None,
) -> dict[str, Any]:
    col: dict[str, Any] = {
        "headerName": header,
        "field": "qualified_model",
        "sortable": True,
        "filter": True,
        "resizable": True,
        "flex": flex,
        "width": width,
        "cellRenderer": "vdmQualifiedModelRenderer",
        "cellStyle": {"fontFamily": _MONO_FONT},
        "tooltipField": "qualified_model",
    }
    if min_width is not None:
        col["minWidth"] = min_width
    if sort is not None:
        col["sort"] = sort
    return col


def resolved_model_col(
    *,
    header: str = "Resolved",
    field: str = "resolved_model",
    flex: int = 2,
    min_width: int = 260,
) -> dict[str, Any]:
    return {
        "headerName": header,
        "field": field,
        "sortable": True,
        "filter": True,
        "resizable": True,
        "flex": flex,
        "minWidth": min_width,
        "cellStyle": {"fontFamily": _MONO_FONT},
        "tooltipField": field,
    }


def numeric_col(
    *,
    header: str,
    field: str,
    width: int,
    renderer: str = "vdmFormattedNumberRenderer",
) -> dict[str, Any]:
    return {
        "headerName": header,
        "field": field,
        "sortable": True,
        "filter": True,
        "resizable": True,
        "width": width,
        "suppressSizeToFit": True,
        "cellRenderer": renderer,
    }


def duration_ms_col(
    *,
    header: str,
    field: str,
    width: int,
    sort: str | None = None,
) -> dict[str, Any]:
    col: dict[str, Any] = {
        "headerName": header,
        "field": field,
        "sortable": True,
        "filter": True,
        "resizable": True,
        "width": width,
        "suppressSizeToFit": True,
        "valueGetter": {"function": f"vdmFormatDurationValue(params.data.{field})"},
        "tooltipValueGetter": {"function": f"vdmFormatDurationTooltip(params.data.{field})"},
    }
    if sort is not None:
        col["sort"] = sort
    return col


def duration_like_last_col(
    *,
    header: str = "Duration",
    duration_field: str = "duration_ms",
    duration_epoch_field: str = "start_time",
    width: int = 120,
    sort: str | None = None,
) -> dict[str, Any]:
    """Render a recency dot + duration label.

    This intentionally mirrors the Model/Provider "Last" column visual treatment.

    Contract:
    - row data must include fields used by `vdmRecencyDotRenderer`:
      - last_accessed_epoch_ms (number)
      - last_accessed_age_s_at_render (number)
      - last_accessed_iso (string)

    For Active Requests, we'll shape these *last_accessed_* fields to represent
    request start time (so the dot + text updater works unchanged).

    Tooltip shows the request start timestamp (ISO) derived from `duration_epoch_field`.
    """

    col: dict[str, Any] = {
        "headerName": header,
        "field": duration_field,
        "sortable": True,
        "filter": True,
        "resizable": True,
        "width": width,
        "suppressSizeToFit": True,
        "cellRenderer": "vdmRecencyDotRenderer",
        "valueGetter": {"function": f"vdmFormatDurationValue(params.data.{duration_field})"},
        "tooltipValueGetter": {
            "function": f"vdmFormatIsoTimestamp(params.data.{duration_epoch_field})"
        },
        # Mark these cells so the Active Requests duration ticker can update the text
        # without affecting other recency columns.
        "cellClass": "vdm-active-req-duration",
    }
    if sort is not None:
        col["sort"] = sort
    return col
