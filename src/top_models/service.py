from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from src.core import config as config_module
from src.top_models.cache import TopModelsDiskCache
from src.top_models.openrouter import OpenRouterTopModelsSource
from src.top_models.source import TopModelsSourceConfig
from src.top_models.types import TopModel, TopModelsResult, TopModelsSourceName


@dataclass(frozen=True, slots=True)
class TopModelsServiceConfig:
    source: TopModelsSourceName
    cache_dir: Path
    ttl: timedelta
    timeout_seconds: float
    exclude: tuple[str, ...]


def _parse_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    parts = [p.strip() for p in value.split(",")]
    return tuple(p for p in parts if p)


def _default_service_config() -> TopModelsServiceConfig:
    cfg = config_module.config

    # If tests reset the Config singleton, some already-imported modules may still
    # hold references to the old instance. Prefer the module's own `config` global
    # if it exists.
    from src.core.config import config as imported_singleton

    cfg = imported_singleton

    source: TopModelsSourceName = "openrouter"

    cache_dir_raw = cfg.top_models_cache_dir
    cache_dir = Path(cache_dir_raw).expanduser()

    ttl_days = cfg.top_models_cache_ttl_days
    ttl = timedelta(days=ttl_days)

    timeout_seconds = cfg.top_models_timeout_seconds

    exclude = tuple(cfg.top_models_exclude)

    return TopModelsServiceConfig(
        source=source,
        cache_dir=cache_dir,
        ttl=ttl,
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
        self._cache = TopModelsDiskCache(cache_dir=self._cfg.cache_dir, ttl=self._cfg.ttl)

        if self._cfg.source == "openrouter":
            self._source = OpenRouterTopModelsSource(
                TopModelsSourceConfig(timeout_seconds=self._cfg.timeout_seconds)
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
        cached = False
        if not refresh:
            cached_result = self._cache.read_if_fresh(expected_source=self._cfg.source)
            if cached_result is not None:
                models = cached_result.models
                aliases = cached_result.aliases
                last_updated = cached_result.last_updated
                cached = True
                return self._finalize(
                    models=models,
                    aliases=aliases,
                    last_updated=last_updated,
                    cached=cached,
                    limit=limit,
                    provider=provider,
                )

        models = await self._source.fetch_models()
        last_updated = datetime.now(tz=dt.timezone.utc)

        models = _apply_exclusions(models, self._cfg.exclude)
        aliases = _suggest_aliases(models)

        self._cache._write_legacy(
            source=self._cfg.source,
            last_updated=last_updated,
            models=models,
            aliases=aliases,
        )

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
