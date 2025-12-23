from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import HTTPException

from src.core.config import config

NextApiKey = Callable[[set[str]], Awaitable[str]]


def make_next_provider_key_fn(*, provider_name: str, api_keys: list[str]) -> NextApiKey:
    """Create a reusable provider API key rotator.

    Providers may be configured with multiple API keys. Upstream calls can "exclude" keys
    that have failed (e.g. 401/403/429) and ask for the next viable key.

    This helper centralizes the repeated logic previously in src/api/endpoints.py.
    """

    async def _next_provider_key(exclude: set[str]) -> str:
        if len(exclude) >= len(api_keys):
            raise HTTPException(status_code=429, detail="All provider API keys exhausted")

        while True:
            k = await config.provider_manager.get_next_provider_api_key(provider_name)
            if k not in exclude:
                return k

    return _next_provider_key
