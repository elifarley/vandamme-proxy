from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.wsgi import WSGIMiddleware

from src.core.config import Config
from src.dashboard.app import create_dashboard
from src.dashboard.data_sources import DashboardConfig


def mount_dashboard(*, fastapi_app: FastAPI, cfg: DashboardConfig | None = None) -> None:
    """Mount the dashboard with lazy API base URL detection.

    The dashboard will detect the actual host/port when it makes its first API request,
    not during mounting. This avoids the AttributeError when accessing fastapi_app.state.host.
    """
    config = Config()
    dash_cfg = cfg or DashboardConfig(api_base_url=f"http://localhost:{config.port}")
    dash_app = create_dashboard(cfg=dash_cfg)
    fastapi_app.mount("/dashboard", WSGIMiddleware(dash_app.server))


class RuntimeApiConfig:
    """Detects API base URL lazily when the dashboard makes requests.

    This class detects the actual host and port from the current Flask request context,
    ensuring the dashboard always talks to the same server the client accessed.
    """

    @property
    def api_base_url(self) -> str:
        """Dynamically detect the API base URL from the current request."""
        from src.core.config import Config

        config = Config()

        # Import here to avoid circular imports and access Flask request context
        try:
            from flask import request

            if request:
                # Get host from request headers
                # The host header contains both hostname and port (e.g., "localhost:8881")
                host = request.headers.get("host", f"localhost:{config.port}")

                # Get scheme from request
                scheme = request.scheme or "http"

                # Build the API base URL
                return f"{scheme}://{host}"
        except (RuntimeError, ImportError, AttributeError):
            # Flask request context not available
            pass

        # Fallback to configured port
        return f"http://localhost:{config.port}"
