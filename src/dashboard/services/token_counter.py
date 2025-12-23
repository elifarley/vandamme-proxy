from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.dashboard.data_sources import fetch_models


@dataclass(frozen=True)
class TokenCounterModelsView:
    options: list[dict[str, Any]]

    def as_options(self) -> list[dict[str, Any]]:
        # Provide a concrete return type for callers (Dash callback typing).
        return list(self.options)

    def __iter__(self) -> Any:  # type: ignore[override]
        # Make it obvious this object isn't meant to be treated as a list.
        raise TypeError("TokenCounterModelsView is not iterable; use .as_options()")


async def build_token_counter_model_options(*, cfg: Any) -> TokenCounterModelsView:
    """Build dropdown options for the token counter model selector."""

    try:
        models_data = await fetch_models(cfg=cfg)
        models = models_data.get("data", [])

        model_options: list[dict[str, Any]] = []
        seen: set[str] = set()

        for model in models:
            if not isinstance(model, dict):
                continue

            model_id = str(model.get("id") or "")
            if not model_id or model_id in seen:
                continue

            seen.add(model_id)
            display_name = model.get("display_name")
            display_name_s = str(display_name) if isinstance(display_name, str) else model_id

            label = f"{display_name_s} ({model_id})" if display_name_s != model_id else model_id
            model_options.append({"label": label, "value": model_id})

        model_options.sort(key=lambda x: str(x.get("label") or ""))
        return TokenCounterModelsView(options=model_options)

    except Exception:  # noqa: BLE001
        # Return some common defaults if API call fails
        return TokenCounterModelsView(
            options=[
                {"label": "Claude 3.5 Sonnet", "value": "claude-3-5-sonnet-20241022"},
                {"label": "Claude 3.5 Haiku", "value": "claude-3-5-haiku-20241022"},
                {"label": "GPT-4o", "value": "gpt-4o"},
                {"label": "GPT-4o Mini", "value": "gpt-4o-mini"},
            ]
        )
