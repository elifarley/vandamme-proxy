from __future__ import annotations

from fastapi import APIRouter

from src.api.handlers.chat_completions import chat_completions_route
from src.api.handlers.messages import messages_route

router = APIRouter()

# TEMPORARY: Use legacy endpoints directly to debug
# Import inside function to avoid issues
def _register_routes() -> None:
    from src.api.endpoints import create_message, chat_completions

    router.post("/v1/chat/completions", response_model=None)(chat_completions)
    router.post("/v1/messages", response_model=None)(create_message)


_register_routes()

# Import legacy router and selectively include its routes, EXCLUDING /v1/chat/completions
# and /v1/messages since we already registered them above.
def _include_legacy_routes() -> None:
    # Import inside function to keep module import order clean (ruff E402)
    from src.api.endpoints import router as legacy_router

    # Paths we've already registered (skip these)
    skip_paths = {"/v1/chat/completions", "/v1/messages"}

    for route in legacy_router.routes:
        path = getattr(route, "path", None)
        if path and path in skip_paths:
            continue
        router.routes.append(route)


_include_legacy_routes()
