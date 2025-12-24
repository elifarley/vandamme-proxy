"""AG-Grid component for the dashboard with dark theme support."""

from typing import Any

import dash_ag_grid as dag  # type: ignore[import-untyped]

from src.dashboard.ag_grid.factories import build_ag_grid
from src.dashboard.ag_grid.scripts import (
    get_ag_grid_clientside_callback as _get_ag_grid_clientside_callback,
)
from src.dashboard.ag_grid.transformers import (
    logs_errors_row_data,
    logs_traces_row_data,
    metrics_models_row_data,
    metrics_providers_row_data,
    models_row_data,
    top_models_row_data,
)


def metrics_active_requests_ag_grid(
    active_requests_payload: dict[str, Any],
    *,
    grid_id: str = "vdm-metrics-active-requests-grid",
) -> dag.AgGrid:
    """Create an AG-Grid table for in-flight requests."""

    active_requests = active_requests_payload.get("active_requests")
    if not isinstance(active_requests, list):
        active_requests = []

    # Keep columns focused on performance + debuggability.
    column_defs = [
        {
            "headerName": "Streaming",
            "field": "is_streaming",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Provider",
            "field": "provider",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 140,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmProviderBadgeRenderer",
        },
        {
            "headerName": "Requested model",
            "field": "requested_model",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 2,
            "minWidth": 260,
            "cellStyle": {"fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas"},
        },
        {
            "headerName": "Resolved model",
            "field": "resolved_model",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 2,
            "minWidth": 260,
            "cellStyle": {"fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas"},
        },
        {
            "headerName": "Duration",
            "field": "duration_ms",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
            "valueGetter": {"function": "vdmFormatDurationValue(params.data.duration_ms)"},
            "tooltipValueGetter": {"function": "vdmFormatDurationTooltip(params.data.duration_ms)"},
        },
        {
            "headerName": "In",
            "field": "input_tokens",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Out",
            "field": "output_tokens",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Tools",
            "field": "tool_calls",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 90,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Req id",
            "field": "request_id",
            "sortable": False,
            "filter": True,
            "resizable": True,
            "width": 170,
            "suppressSizeToFit": True,
            "cellStyle": {
                "fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas",
                "opacity": 0.8,
            },
        },
    ]

    return build_ag_grid(
        grid_id=grid_id,
        column_defs=column_defs,
        row_data=active_requests,
        no_rows_message="No active requests",
        dash_grid_options_overrides={
            "pagination": False,
            "rowHeight": 37,
        },
        custom_css={
            "height": "260px",
            "width": "100%",
            "minHeight": "260px",
        },
    )


def _coerce_bool(x: object) -> bool:
    return bool(x)


def metrics_active_requests_component(active_requests_payload: dict[str, Any]) -> Any:
    if active_requests_payload.get("disabled"):
        return "Active request metrics are disabled. Set LOG_REQUEST_METRICS=true."
    return metrics_active_requests_ag_grid(active_requests_payload)


def top_models_ag_grid(
    models: list[dict[str, Any]],
    *,
    grid_id: str = "vdm-top-models-grid",
) -> dag.AgGrid:
    """Create an AG-Grid table for Top Models.

    Expects rows shaped like the `/top-models` API output items.
    """
    column_defs = [
        {
            "headerName": "Provider",
            "field": "provider",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 130,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Sub-provider",
            "field": "sub_provider",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 160,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Model ID",
            "field": "id",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 2,
            "minWidth": 260,
            "cellStyle": {"cursor": "copy"},
        },
        {
            "headerName": "Name",
            "field": "name",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 1,
            "minWidth": 160,
        },
        {
            "headerName": "Context",
            "field": "context_window",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Avg $/M",
            "field": "avg_per_million",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Caps",
            "field": "capabilities",
            "sortable": False,
            "filter": True,
            "resizable": True,
            "flex": 1,
            "minWidth": 220,
        },
    ]

    return build_ag_grid(
        grid_id=grid_id,
        column_defs=column_defs,
        row_data=top_models_row_data(models),
        no_rows_message="No models found",
    )


# --- Models AG Grid ---


def models_ag_grid(
    models: list[dict[str, Any]],
    grid_id: str = "vdm-models-grid",
) -> dag.AgGrid:
    """Create an AG-Grid table for models with dark theme and advanced features.

    Args:
        models: List of model dictionaries
        grid_id: Unique ID for the grid component

    Returns:
        AG-Grid component with models data
    """
    row_data = models_row_data(models)

    # Define column definitions with new order: Created → Actions → Model ID → metadata
    column_defs = [
        {
            "headerName": "Created",
            "field": "created_iso",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,  # Fixed width for yyyy-mm-dd format (plus padding)
            "suppressSizeToFit": True,
            "suppressMovable": False,
            "sort": "desc",  # Default sort by creation date (newest first)
            "tooltipField": "created_relative",
            "comparator": {"function": "vdmDateComparator"},
        },
        {
            "headerName": "Actions",
            "field": "actions",
            "sortable": False,
            "filter": False,
            "resizable": False,
            "width": 80,  # Fixed width for emoji icon with padding
            "suppressSizeToFit": True,
            "suppressMovable": True,
            "cellRenderer": "vdmModelPageLinkRenderer",
        },
        {
            "headerName": "Sub-Provider",
            "field": "owned_by",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 1,
            "minWidth": 140,
        },
        {
            "headerName": "Model ID",
            "field": "id",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 2,
            "minWidth": 220,
            "suppressMovable": False,
            "cellStyle": {"cursor": "copy"},
            "tooltipField": "description_full",
            # Render as: icon + id (cell click-to-copy is attached by JS listener)
            "cellRenderer": "vdmModelIdWithIconRenderer",
        },
        {
            "headerName": "Modality",
            "field": "architecture_modality",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 1,
            "minWidth": 170,
        },
        {
            "headerName": "Context",
            "field": "context_length",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Max out",
            "field": "max_output_tokens",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "$/M in",
            "field": "pricing_prompt_per_million",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 100,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "$/M out",
            "field": "pricing_completion_per_million",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 100,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Description",
            "field": "description_preview",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 3,
            "minWidth": 360,
            "tooltipField": "description_full",
        },
    ]

    return build_ag_grid(
        grid_id=grid_id,
        column_defs=column_defs,
        row_data=row_data,
        no_rows_message="No models found",
        dash_grid_options_overrides={
            "rowSelection": {"enableClickSelection": True},
        },
    )


def logs_errors_ag_grid(
    errors: list[dict[str, Any]],
    grid_id: str = "vdm-logs-errors-grid",
) -> dag.AgGrid:
    """Create an AG-Grid table for error logs with dark theme and provider badges.

    Args:
        errors: List of error log dictionaries
        grid_id: Unique ID for the grid component

    Returns:
        AG-Grid component with error logs data
    """
    row_data = logs_errors_row_data(errors)

    # Define column definitions for errors
    column_defs = [
        {
            "headerName": "Time",
            "field": "time_formatted",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 100,
            "suppressSizeToFit": True,
            "tooltipField": "time_relative",
            "sort": "desc",  # Default sort by time (newest first)
        },
        {
            "headerName": "Provider",
            "field": "provider",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 130,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmProviderBadgeRenderer",
        },
        {
            "headerName": "Model",
            "field": "model",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 1,
            "minWidth": 200,
            "cellStyle": {"fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas"},
        },
        {
            "headerName": "Error Type",
            "field": "error_type",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 160,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Error Message",
            "field": "error",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 3,
            "minWidth": 300,
            "cellStyle": {"fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas"},
            "tooltipField": "error",
        },
    ]

    return build_ag_grid(
        grid_id=grid_id,
        column_defs=column_defs,
        row_data=row_data,
        no_rows_message="No errors found",
    )


def logs_traces_ag_grid(
    traces: list[dict[str, Any]],
    grid_id: str = "vdm-logs-traces-grid",
) -> dag.AgGrid:
    """Create an AG-Grid table for trace logs with dark theme and provider badges.

    Args:
        traces: List of trace log dictionaries
        grid_id: Unique ID for the grid component

    Returns:
        AG-Grid component with trace logs data
    """
    row_data = logs_traces_row_data(traces)

    # Define column definitions for traces
    column_defs = [
        {
            "headerName": "Time",
            "field": "time_formatted",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 100,
            "suppressSizeToFit": True,
            "tooltipField": "time_relative",
            "sort": "desc",  # Default sort by time (newest first)
        },
        {
            "headerName": "Provider",
            "field": "provider",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 130,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmProviderBadgeRenderer",
        },
        {
            "headerName": "Model",
            "field": "model",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 1,
            "minWidth": 200,
            "cellStyle": {"fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas"},
        },
        {
            "headerName": "Status",
            "field": "status",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 100,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmStatusBadgeRenderer",
        },
        {
            "headerName": "Duration",
            "field": "duration_formatted",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 100,
            "suppressSizeToFit": True,
            "tooltipField": "duration_ms",
            "comparator": {"function": "vdmNumericComparator"},
        },
        {
            "headerName": "In Tokens",
            "field": "input_tokens_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Out Tokens",
            "field": "output_tokens_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Cache Read",
            "field": "cache_read_tokens_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Cache Create",
            "field": "cache_creation_tokens_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
    ]

    return build_ag_grid(
        grid_id=grid_id,
        column_defs=column_defs,
        row_data=row_data,
        no_rows_message="No traces found",
    )


def metrics_providers_ag_grid(
    running_totals: dict[str, Any],
    *,
    grid_id: str = "vdm-metrics-providers-grid",
) -> dag.AgGrid:
    """Create an AG-Grid table for Metrics provider rollups."""

    column_defs = [
        {
            "headerName": "Last",
            "field": "last_accessed",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmRecencyDotRenderer",
        },
        {
            "headerName": "Provider",
            "field": "provider",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 160,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmProviderBadgeRenderer",
            "sort": "asc",
        },
        {
            "headerName": "Avg",
            "field": "average_duration_ms",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 90,
            "suppressSizeToFit": True,
            "valueGetter": {"function": "params.data.average_duration"},
            "tooltipValueGetter": {"function": "params.data.average_duration"},
        },
        {
            "headerName": "Total\ntime",
            "field": "total_duration_ms_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
            "valueGetter": {
                "function": "vdmFormatDurationValue(params.data.total_duration_ms_raw)"
            },
            "tooltipValueGetter": {
                "function": "vdmFormatDurationTooltip(params.data.total_duration_ms_raw)"
            },
        },
        {
            "headerName": "Tools",
            "field": "tool_calls_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 90,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Requests",
            "field": "requests",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "In\ntokens",
            "field": "input_tokens_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Out\ntokens",
            "field": "output_tokens_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Cache\nread",
            "field": "cache_read_tokens_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Cache\ncreate",
            "field": "cache_creation_tokens_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Errors",
            "field": "errors",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 100,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Error rate",
            "field": "error_rate_pct",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
            "tooltipField": "error_rate",
        },
    ]

    return build_ag_grid(
        grid_id=grid_id,
        column_defs=column_defs,
        row_data=metrics_providers_row_data(running_totals),
        no_rows_message="No provider metrics yet",
        dash_grid_options_overrides={
            "paginationPageSize": 5,
            "paginationPageSizeSelector": [5, 15, 50],
            "rowHeight": 37,
        },
        custom_css={
            # TODO(dashboard/metrics): Header wrapping + row height tweaks appear to be
            # ignored by AG Grid in Dash (likely header DOM structure/CSS precedence,
            # or grid height constrained by surrounding layout). Investigate a metrics-
            # scoped solution (e.g., headerClass + targeted CSS, or container sizing).
            "height": "286px",
            "width": "100%",
            "minHeight": "286px",
        },
    )


def metrics_models_ag_grid(
    running_totals: dict[str, Any],
    *,
    grid_id: str = "vdm-metrics-models-grid",
) -> dag.AgGrid:
    """Create an AG-Grid table for Metrics model rollups across providers."""

    column_defs = [
        {
            "headerName": "Last",
            "field": "last_accessed",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmRecencyDotRenderer",
        },
        {
            "headerName": "Model",
            "field": "qualified_model",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 2,
            "width": 280,
            # Display: <provider badge> : <model id>
            # Sort/filter should use the underlying text value.
            "cellRenderer": "vdmQualifiedModelRenderer",
            "cellStyle": {"fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas"},
            "sort": "asc",
            # Keep the underlying string accessible in the browser for debugging.
            "tooltipField": "qualified_model",
        },
        {
            "headerName": "Avg",
            "field": "average_duration_ms",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 90,
            "suppressSizeToFit": True,
            "valueGetter": {"function": "params.data.average_duration"},
            "tooltipValueGetter": {"function": "params.data.average_duration"},
        },
        {
            "headerName": "Total\ntime",
            "field": "total_duration_ms_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
            "valueGetter": {
                "function": "vdmFormatDurationValue(params.data.total_duration_ms_raw)"
            },
            "tooltipValueGetter": {
                "function": "vdmFormatDurationTooltip(params.data.total_duration_ms_raw)"
            },
        },
        {
            "headerName": "Tools",
            "field": "tool_calls_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 90,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Requests",
            "field": "requests",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "In\ntokens",
            "field": "input_tokens_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Out\ntokens",
            "field": "output_tokens_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
    ]

    return build_ag_grid(
        grid_id=grid_id,
        column_defs=column_defs,
        row_data=metrics_models_row_data(running_totals),
        no_rows_message="No model metrics yet",
        dash_grid_options_overrides={
            "paginationPageSize": 15,
            "paginationPageSizeSelector": [5, 15, 50, 100],
            "rowHeight": 37,
        },
        custom_css={
            "height": "600px",
            "width": "100%",
            "minHeight": "600px",
        },
    )


def get_ag_grid_clientside_callback() -> dict[str, dict[str, str]]:
    """Return the clientside callback for AG-Grid cell renderers.

    Note: the keys must match the Dash component id(s) of the AgGrid instances.
    Delegates to the scripts module.
    """
    return _get_ag_grid_clientside_callback()
