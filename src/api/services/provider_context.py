from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from src.core.config import config
from src.core.model_manager import get_model_manager
from src.core.provider_config import ProviderConfig


@dataclass(frozen=True)
class ProviderContext:
    provider_name: str
    resolved_model: str
    provider_config: ProviderConfig
    client_api_key: str | None
    provider_api_key: str | None


async def resolve_provider_context(*, model: str, client_api_key: str | None) -> ProviderContext:
    """Resolve provider/model and prepare auth context.

    - Resolves provider prefix + model aliasing via ModelManager
    - Fetches provider config
    - Enforces passthrough requirements
    - Selects initial provider API key for non-passthrough providers

    This is intentionally minimal: it returns the pieces endpoints need today.
    """

    provider_name, resolved_model = get_model_manager().resolve_model(model)

    provider_config = config.provider_manager.get_provider_config(provider_name)
    if provider_config is None:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    if provider_config.uses_passthrough and not client_api_key:
        raise HTTPException(
            status_code=401,
            detail=(
                f"Provider '{provider_name}' requires API key passthrough, "
                "but no client API key was provided"
            ),
        )

    provider_api_key: str | None = None
    if not provider_config.uses_passthrough:
        provider_api_key = await config.provider_manager.get_next_provider_api_key(provider_name)

    return ProviderContext(
        provider_name=provider_name,
        resolved_model=resolved_model,
        provider_config=provider_config,
        client_api_key=client_api_key,
        provider_api_key=provider_api_key,
    )
