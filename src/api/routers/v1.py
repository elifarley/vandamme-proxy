from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

# Register v1 routes using the proven working implementations from src.api.endpoints
# This provides a clean router module while preserving exact runtime behavior.
def _register_routes() -> None:
    from src.api.endpoints import chat_completions, create_message

    router.post("/v1/chat/completions", response_model=None)(chat_completions)
    router.post("/v1/messages", response_model=None)(create_message)


_register_routes()

# Include remaining legacy routes (models, aliases, health, etc.)
def _include_legacy_routes() -> None:
    from src.api.endpoints import router as legacy_router

    skip_paths = {"/v1/chat/completions", "/v1/messages"}

    for route in legacy_router.routes:
        path = getattr(route, "path", None)
        if path and path in skip_paths:
            continue
        router.routes.append(route)


_include_legacy_routes()
