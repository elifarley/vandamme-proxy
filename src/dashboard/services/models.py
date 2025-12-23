from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dash import html

from src.dashboard.components.ag_grid import models_row_data
from src.dashboard.components.ui import provider_badge
from src.dashboard.data_sources import fetch_all_providers, fetch_health, fetch_models


@dataclass(frozen=True)
class ModelsView:
    row_data: list[dict[str, Any]]
    provider_options: list[dict[str, str]]
    provider_value: str | None
    hint: Any


async def build_models_view(*, cfg: Any, provider_value: str | None) -> ModelsView:
    """Fetch models and build view fragments for the Models page."""

    health = await fetch_health(cfg=cfg)
    providers = await fetch_all_providers(cfg=cfg)

    default_provider = health.get("default_provider")
    if not isinstance(default_provider, str):
        default_provider = ""

    sorted_providers = sorted(p for p in providers if isinstance(p, str) and p)

    selected_provider = provider_value.strip() if provider_value else ""
    if not selected_provider:
        if default_provider:
            selected_provider = default_provider
        elif sorted_providers:
            selected_provider = sorted_providers[0]

    provider_options: list[dict[str, str]] = []
    if default_provider and default_provider in sorted_providers:
        provider_options.append(
            {"label": f"{default_provider} (default)", "value": default_provider}
        )

    provider_options.extend(
        [{"label": p, "value": p} for p in sorted_providers if p != default_provider]
    )

    hint = [
        html.Span("Listing models for "),
        provider_badge(selected_provider)
        if selected_provider
        else html.Span("(no providers)", className="text-muted"),
    ]

    models_data = await fetch_models(cfg=cfg, provider=selected_provider or None)
    models = models_data.get("data", [])

    inferred_provider = selected_provider or default_provider or "multiple"
    for model in models:
        if not model.get("provider"):
            model["provider"] = inferred_provider

    if not models:
        return ModelsView(
            row_data=[],
            provider_options=provider_options,
            provider_value=selected_provider or None,
            hint=hint,
        )

    return ModelsView(
        row_data=models_row_data(models),
        provider_options=provider_options,
        provider_value=selected_provider or None,
        hint=hint,
    )
