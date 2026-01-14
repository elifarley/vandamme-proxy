from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.config import Config
from src.top_models.manual_rankings import ManualRankingsConfig, ManualRankingsTopModelsSource
from src.top_models.openrouter import OpenRouterTopModelsSource
from src.top_models.source import TopModelsSourceConfig
from src.top_models.types import TopModel, TopModelsResult, TopModelsSourceName

TopModelsSource = OpenRouterTopModelsSource | ManualRankingsTopModelsSource


@dataclass(frozen=True, slots=True)
class TopModelsServiceConfig:
    source: TopModelsSourceName
    rankings_file: Path
    timeout_seconds: float
    exclude: tuple[str, ...]


def _parse_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    parts = [p.strip() for p in value.split(",")]
    return tuple(p for p in parts if p)


def _default_service_config() -> TopModelsServiceConfig:
    """Create default service config from Config singleton (fallback)."""
    cfg = Config()
    source = cfg.top_models_source
    if source not in {"manual_rankings", "openrouter"}:
        raise ValueError(f"Unsupported top-models source: {source}")

    typed_source: TopModelsSourceName = source  # type: ignore[assignment]
    # mypy can't narrow `cfg.top_models_source` (a str) to the Literal, even after validation.

    rankings_file = Path(cfg.top_models_rankings_file)

    timeout_seconds = cfg.top_models_timeout_seconds

    exclude = tuple(cfg.top_models_exclude)

    return TopModelsServiceConfig(
        source=typed_source,
        rankings_file=rankings_file,
        timeout_seconds=timeout_seconds,
        exclude=exclude,
    )


def _apply_exclusions(
    models: tuple[TopModel, ...], exclude: tuple[str, ...]
) -> tuple[TopModel, ...]:
    if not exclude:
        return models

    def allowed(m: TopModel) -> bool:
        return all(not (rule and rule in m.id) for rule in exclude)

    return tuple(m for m in models if allowed(m))


def _suggest_aliases(models: tuple[TopModel, ...]) -> dict[str, str]:
    # Minimal + deterministic suggestions.
    if not models:
        return {}

    aliases: dict[str, str] = {
        "top": models[0].id,
    }

    # Cheapest by average cost (if available)
    cheapest: tuple[float, str] | None = None
    for m in models:
        avg = m.pricing.average_per_million
        if avg is None:
            continue
        if cheapest is None or avg < cheapest[0]:
            cheapest = (avg, m.id)
    if cheapest is not None:
        aliases["top-cheap"] = cheapest[1]

    # Longest context
    longest: tuple[int, str] | None = None
    for m in models:
        if m.context_window is None:
            continue
        if longest is None or m.context_window > longest[0]:
            longest = (m.context_window, m.id)
    if longest is not None:
        aliases["top-longctx"] = longest[1]

    return aliases


class TopModelsService:
    def __init__(self, cfg: TopModelsServiceConfig | None = None) -> None:
        # Do not capture env-derived config at import time; tests rely on resetting
        # src.core.config.config between cases.
        self._cfg = cfg or _default_service_config()

        self._source: TopModelsSource
        if self._cfg.source == "openrouter":
            self._source = OpenRouterTopModelsSource(
                TopModelsSourceConfig(timeout_seconds=self._cfg.timeout_seconds)
            )
        elif self._cfg.source == "manual_rankings":
            # We inject a small fetcher so the manual source can reuse the same
            # fetch+cache semantics as `/v1/models`, while preserving OpenRouter
            # catalog metadata (pricing/context) that `/v1/models?format=openai`
            # intentionally strips.
            from src.api.endpoints import fetch_models_unauthenticated, models_cache
            from src.conversion.models_converter import raw_to_openai_models

            async def fetch_openrouter_openai_models(
                *, provider: str, refresh: bool
            ) -> dict[str, Any]:
                # DRY reuse: same caching semantics as /v1/models,
                # without using the endpoint converter that drops pricing/context metadata.
                if provider != "openrouter":
                    raise ValueError(
                        f"manual_rankings only supports provider=openrouter (got {provider})"
                    )

                base_url = "https://openrouter.ai/api/v1"
                custom_headers: dict[str, str] = {}

                raw: dict[str, Any] | None = None
                if models_cache and not refresh:
                    raw = models_cache.read_response_if_fresh(
                        provider=provider,
                        base_url=base_url,
                        custom_headers=custom_headers,
                    )

                if raw is None:
                    raw = await fetch_models_unauthenticated(base_url, custom_headers)
                    if models_cache:
                        models_cache.write_response(
                            provider=provider,
                            base_url=base_url,
                            custom_headers=custom_headers,
                            response=raw,
                        )

                return raw_to_openai_models(raw)

            self._source = ManualRankingsTopModelsSource(
                cfg=ManualRankingsConfig(rankings_file=self._cfg.rankings_file),
                app_fetch_openai_models=fetch_openrouter_openai_models,
            )
        else:
            raise ValueError(f"Unsupported top-models source: {self._cfg.source}")

    async def get_top_models(
        self,
        *,
        limit: int,
        refresh: bool,
        provider: str | None,
    ) -> TopModelsResult:
        if self._cfg.source == "manual_rankings":
            source = self._source
            assert isinstance(source, ManualRankingsTopModelsSource)
            models = await source.fetch_models(refresh=refresh)
        else:
            source = self._source
            assert isinstance(source, OpenRouterTopModelsSource)
            models = await source.fetch_models()

        last_updated = datetime.now(tz=dt.timezone.utc)

        models = _apply_exclusions(models, self._cfg.exclude)
        aliases = _suggest_aliases(models)

        return self._finalize(
            models=models,
            aliases=aliases,
            last_updated=last_updated,
            cached=False,
            limit=limit,
            provider=provider,
        )

    def _finalize(
        self,
        *,
        models: tuple[TopModel, ...],
        aliases: dict[str, str],
        last_updated: datetime,
        cached: bool,
        limit: int,
        provider: str | None,
    ) -> TopModelsResult:
        filtered = models
        if provider:
            filtered = tuple(m for m in filtered if m.provider == provider)

        limited = filtered[:limit]

        # Only keep aliases that point to an ID that survived filtering.
        ids = {m.id for m in limited}
        filtered_aliases = {k: v for k, v in aliases.items() if v in ids}

        return TopModelsResult(
            source=self._cfg.source,
            cached=cached,
            last_updated=last_updated,
            models=limited,
            aliases=filtered_aliases,
        )
