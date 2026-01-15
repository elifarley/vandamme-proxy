import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from src.api.endpoints import validate_api_key
from src.api.services.streaming import sse_headers, streaming_response
from src.api.utils.yaml_formatter import create_hierarchical_structure, format_running_totals_yaml
from src.core.config import Config
from src.core.config.accessors import log_request_metrics
from src.core.config.runtime import get_config
from src.core.logging.configuration import get_logging_mode
from src.core.metrics.runtime import get_request_tracker

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


@metrics_router.get("/active-requests")
async def get_active_requests(
    http_request: Request,
    cfg: Config = Depends(get_config),
    _: None = Depends(validate_api_key),
) -> JSONResponse:
    """Get a snapshot of in-flight requests for the dashboard."""

    if not log_request_metrics():
        return JSONResponse(
            status_code=200,
            content={
                "disabled": True,
                "message": "Request metrics logging is disabled",
                "suggestion": "Set LOG_REQUEST_METRICS=false to disable tracking",
                "active_requests": [],
            },
            headers={"Cache-Control": "no-cache"},
        )

    tracker = get_request_tracker(http_request)
    rows = await tracker.get_active_requests_snapshot()
    return JSONResponse(
        status_code=200,
        content={"disabled": False, "active_requests": rows},
        headers={"Cache-Control": "no-cache"},
    )


@metrics_router.get("/active-requests/stream", response_model=None)
async def stream_active_requests(
    http_request: Request,
    cfg: Config = Depends(get_config),
    _: None = Depends(validate_api_key),
) -> StreamingResponse | JSONResponse:
    """Server-Sent Events stream for active requests.

    Emits active request snapshots at the configured interval (default 2s),
    with immediate updates when requests start or complete.

    SSE Events:
        - update: Active requests snapshot (JSON)
        - disabled: Metrics are disabled (single event, then stream closes)
        - heartbeat: Keep-alive comment every 30s
    """

    if not log_request_metrics():
        # Return disabled state as a single event
        async def disabled_stream() -> AsyncGenerator[str, None]:
            data = {
                "disabled": True,
                "message": "Request metrics logging is disabled",
                "suggestion": "Set LOG_REQUEST_METRICS=false to disable tracking",
            }
            yield "event: disabled\n"
            yield f"data: {json.dumps(data)}\n\n"

        return StreamingResponse(
            disabled_stream(),
            media_type="text/event-stream",
            headers=sse_headers(),
        )

    if not cfg.active_requests_sse_enabled:
        # SSE is disabled via config, return error
        data = {
            "disabled": True,
            "message": "SSE for active requests is disabled",
            "suggestion": "Set VDM_ACTIVE_REQUESTS_SSE_ENABLED=true to enable",
        }
        return JSONResponse(status_code=503, content=data)

    tracker = get_request_tracker(http_request)
    interval = cfg.active_requests_sse_interval
    heartbeat_interval = cfg.active_requests_sse_heartbeat

    async def active_requests_stream() -> AsyncGenerator[str, None]:
        """Stream active requests with push-on-change."""

        last_snapshot: list[dict] = []
        last_heartbeat = asyncio.get_event_loop().time()

        def _format_update(snapshot: list[dict]) -> str:
            data = {
                "disabled": False,
                "active_requests": snapshot,
                "timestamp": time.time(),
            }
            return "event: update\n" + f"data: {json.dumps(data)}\n\n"

        try:
            # Always send an initial snapshot so the client syncs immediately on connect.
            snapshot = await tracker.get_active_requests_snapshot()
            last_snapshot = snapshot
            yield _format_update(snapshot)

            while True:
                # Wait for change event or timeout
                await tracker.wait_for_active_requests_change(timeout=interval)

                # Get current snapshot
                snapshot = await tracker.get_active_requests_snapshot()

                # Only send if snapshot changed
                if snapshot != last_snapshot:
                    yield _format_update(snapshot)
                    last_snapshot = snapshot

                # Send heartbeat every 30s to keep connection alive
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat >= heartbeat_interval:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now

        except asyncio.CancelledError:
            # Client disconnected
            logger.debug("SSE client disconnected from /metrics/active-requests/stream")
            raise
        except (asyncio.TimeoutError, ConnectionError, OSError) as e:
            logger.error(f"Error in active requests SSE stream: {type(e).__name__}: {e}")
            raise

    return streaming_response(stream=active_requests_stream())


@metrics_router.get("/running-totals")
async def get_running_totals(
    http_request: Request,
    provider: str | None = Query(
        None, description="Filter by provider (case-insensitive, supports * and ? wildcards)"
    ),
    model: str | None = Query(
        None, description="Filter by model (case-insensitive, supports * and ? wildcards)"
    ),
    include_active: bool = Query(
        True,
        description=(
            "Include in-flight requests in provider/model breakdown. "
            "Dash rollup grids should use include_active=false and rely on the "
            "Active Requests grid."
        ),
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
        if not log_request_metrics():
            yaml_data = format_running_totals_yaml(
                {
                    "# Message": "Request metrics logging is disabled",
                    "# Suggestion": "Set LOG_REQUEST_METRICS=false to disable tracking",
                }
            )
            return PlainTextResponse(content=yaml_data, media_type="text/yaml; charset=utf-8")

        tracker = get_request_tracker(http_request)

        # Get hierarchical data with filtering
        data = await tracker.get_running_totals_hierarchical(
            provider_filter=provider,
            model_filter=model,
            include_active=include_active,
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

    except (
        asyncio.TimeoutError,
        ConnectionError,
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
    ) as e:
        logger.error(f"Error getting running totals: {type(e).__name__}: {e}")
        # Return error as YAML for consistency
        error_yaml = format_running_totals_yaml(
            {"# Error": None, "error": str(e), "status": "failed"}
        )
        return PlainTextResponse(
            content=error_yaml, media_type="text/yaml; charset=utf-8", status_code=500
        )
