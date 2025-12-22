import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

from src.api.endpoints import validate_api_key
from src.api.utils.yaml_formatter import create_hierarchical_structure, format_running_totals_yaml
from src.core.config import config
from src.core.logging.configuration import get_logging_mode
from src.core.metrics.runtime import get_request_tracker

LOG_REQUEST_METRICS = config.log_request_metrics
logger = logging.getLogger(__name__)

metrics_router = APIRouter()


@metrics_router.get("/logs")
async def get_logs(
    http_request: Request,
    limit_errors: int = Query(100, ge=1, le=1000),
    limit_traces: int = Query(200, ge=1, le=2000),
    _: None = Depends(validate_api_key),
) -> dict[str, object]:
    """Get recent errors and request traces for the dashboard.

    This is intentionally process-local (in-memory ring buffers).
    """

    tracker = get_request_tracker(http_request)
    logging_mode = get_logging_mode()

    errors = await tracker.get_recent_errors(limit=limit_errors)
    traces = await tracker.get_recent_traces(limit=limit_traces)

    return {
        "systemd": {
            "requested": logging_mode["requested_systemd"],
            "effective": logging_mode["effective_systemd"],
            "handler": logging_mode["effective_handler"],
        },
        "errors": errors,
        "traces": traces,
    }


@metrics_router.get("/running-totals")
async def get_running_totals(
    http_request: Request,
    provider: str | None = Query(
        None, description="Filter by provider (case-insensitive, supports * and ? wildcards)"
    ),
    model: str | None = Query(
        None, description="Filter by model (case-insensitive, supports * and ? wildcards)"
    ),
    _: None = Depends(validate_api_key),
) -> PlainTextResponse:
    """Get running totals for all API requests with optional filtering.

    Returns hierarchical provider→model breakdown in YAML format.

    Query Parameters:
        provider: Optional provider filter (case-insensitive, supports wildcards)
        model: Optional model filter (case-insensitive, supports wildcards)

    Examples:
        /metrics/running-totals                    # All data
        /metrics/running-totals?provider=openai   # Filter by provider
        /metrics/running-totals?model=gpt*        # Filter by model with wildcard
    """
    try:
        if not LOG_REQUEST_METRICS:
            yaml_data = format_running_totals_yaml(
                {
                    "# Message": "Request metrics logging is disabled",
                    "# Suggestion": "Set LOG_REQUEST_METRICS=true to enable tracking",
                }
            )
            return PlainTextResponse(content=yaml_data, media_type="text/yaml; charset=utf-8")

        tracker = get_request_tracker(http_request)

        # Get hierarchical data with filtering
        data = await tracker.get_running_totals_hierarchical(
            provider_filter=provider,
            model_filter=model,
        )

        # Create YAML structure - data now has flattened structure
        # Convert HierarchicalData TypedDict to regular dict for compatibility
        hierarchical_data = create_hierarchical_structure(
            summary_data=dict(data), provider_data=data["providers"]
        )

        # Format as YAML with metadata
        filters = {}
        if provider:
            filters["provider"] = provider
        if model:
            filters["model"] = model

        yaml_output = format_running_totals_yaml(hierarchical_data, filters)

        return PlainTextResponse(
            content=yaml_output,
            media_type="text/yaml; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "Content-Disposition": (
                    f"inline; filename=running-totals-"
                    f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.yaml"
                ),
            },
        )

    except Exception as e:
        logger.error(f"Error getting running totals: {e}")
        # Return error as YAML for consistency
        error_yaml = format_running_totals_yaml(
            {"# Error": None, "error": str(e), "status": "failed"}
        )
        return PlainTextResponse(
            content=error_yaml, media_type="text/yaml; charset=utf-8", status_code=500
        )
