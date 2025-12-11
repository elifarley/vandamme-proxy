from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from src.api.endpoints import validate_api_key
from src.api.utils.yaml_formatter import create_hierarchical_structure, format_running_totals_yaml
from src.core.logging import LOG_REQUEST_METRICS, logger, request_tracker

metrics_router = APIRouter()


@metrics_router.get("/running-totals")
async def get_running_totals(
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

        # Get hierarchical data with filtering
        data = request_tracker.get_running_totals_hierarchical(
            provider_filter=provider, model_filter=model
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
