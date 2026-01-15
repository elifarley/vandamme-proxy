import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, Response

from src import __version__
from src.api.metrics import metrics_router
from src.api.middleware_integration import MiddlewareAwareRequestProcessor
from src.api.routers.v1 import router as api_router
from src.core.config import Config
from src.core.config.accessors import (
    cache_dir,
    config_context_middleware,
    models_cache_enabled,
    models_cache_ttl_hours,
)
from src.core.metrics import create_request_tracker
from src.core.model_manager import ModelManager
from src.models.cache import ModelsDiskCache

app = FastAPI(title="Vandamme Proxy", version=__version__)

# Process-local state owned by the FastAPI app instance.
# This avoids module-level singletons and keeps imports side-effect free.
app.state.request_tracker = create_request_tracker()
app.state.config = Config()  # Eager initialization at startup
app.state.model_manager = ModelManager(app.state.config)
app.state.middleware_processor = MiddlewareAwareRequestProcessor()

# Initialize models cache if enabled (not in pytest)
_cache_dir = Path(cache_dir())
if models_cache_enabled() and not os.environ.get("PYTEST_CURRENT_TEST"):
    app.state.models_cache = ModelsDiskCache(
        cache_dir=_cache_dir,
        ttl_hours=models_cache_ttl_hours(),
    )
else:
    app.state.models_cache = None


@app.middleware("http")
async def config_context_middleware_handler(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Set request-scoped config context for O(1) accessor lookup.

    This middleware replaces the expensive stack inspection approach with
    ContextVar-based config propagation, eliminating the performance penalty
    of walking the call stack on every config access.

    The config is available to all accessor functions via _config_context.get()
    in src/core/config/accessors.py without any stack inspection.
    """
    config = getattr(request.app.state, "config", None)
    if config is None:
        # No config on app state, proceed without context
        return await call_next(request)

    async with config_context_middleware(config):
        response = await call_next(request)
        return response


app.include_router(api_router)
app.include_router(metrics_router, prefix="/metrics", tags=["metrics"])


@app.on_event("startup")
async def startup_middleware_processor() -> None:
    """Initialize middleware processor on startup."""
    await app.state.middleware_processor.initialize()


@app.on_event("shutdown")
async def shutdown_middleware_processor() -> None:
    """Cleanup middleware processor on shutdown."""
    if hasattr(app.state, "middleware_processor"):
        await app.state.middleware_processor.cleanup()


# Dashboard (Dash) mounted under /dashboard
try:
    from src.dashboard.mount import mount_dashboard

    mount_dashboard(fastapi_app=app)
except ImportError as e:
    # Dashboard dependencies not installed
    print(f"⚠️ Dashboard not mounted: missing dependencies ({e})")
except Exception as e:
    # Other error mounting dashboard
    print(f"⚠️ Dashboard not mounted: {e}")
    import traceback

    traceback.print_exc()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print(f"Vandamme Proxy v{__version__}")
        print("")
        print("Usage: python src/main.py")
        print("       or: vdm start")
        print("")
        print("Required environment variables:")
        print("  OPENAI_API_KEY - Your OpenAI API key")
        print("")
        print("Optional environment variables:")
        print("  PROXY_API_KEY - Expected API key for client validation at the proxy")
        print("                      If set, clients must provide this exact API key")
        print("  HOST - Server host (default: 0.0.0.0)")
        print("  PORT - Server port (default: 8082)")
        print("  LOG_LEVEL - Logging level (default: WARNING)")
        print("  MAX_TOKENS_LIMIT - Token limit (default: 4096)")
        print("  MIN_TOKENS_LIMIT - Minimum token limit (default: 100)")
        print("  REQUEST_TIMEOUT - Request timeout in seconds (default: 90)")
        print("")
        print("")
        print("For more options, use the vdm CLI:")
        print("  vdm config show  - Show current configuration")
        print("  vdm config setup - Interactive configuration setup")
        print("  vdm health check - Check API connectivity")
        sys.exit(0)

    # Configure logging FIRST before any console output
    # This suppresses noisy HTTP client logs (openai, httpx, httpcore) unless DEBUG
    from src.core.logging.configuration import configure_root_logging

    configure_root_logging(use_systemd=False)

    # Configuration summary
    cfg = app.state.config
    print("🚀 Vandamme Proxy v1.0.0")
    print("✅ Configuration loaded successfully")
    print(f"   API Key : {cfg.api_key_hash}")
    print(f"   Base URL: {cfg.base_url}")
    print(f"   Max Tokens Limit: {cfg.max_tokens_limit}")
    print(f"   Request Timeout : {cfg.request_timeout}s")
    print(f"   Server: {cfg.host}:{cfg.port}")
    print(f"   Client API Key Validation: {'Enabled' if cfg.proxy_api_key else 'Disabled'}")
    print("")

    # Show provider summary
    cfg.provider_manager.print_provider_summary()

    # Parse log level - extract just the first word to handle comments
    log_level = cfg.log_level.split()[0].lower()

    # Validate and set default if invalid
    valid_levels = ["debug", "info", "warning", "error", "critical"]
    if log_level not in valid_levels:
        log_level = "info"

    # Start server
    uvicorn.run(
        "src.main:app",
        host=cfg.host,
        port=cfg.port,
        log_level=log_level,
        access_log=(log_level == "debug"),  # Only show access logs at DEBUG level
        reload=False,
    )


if __name__ == "__main__":
    main()
