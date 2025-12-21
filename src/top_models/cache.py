from __future__ import annotations

# type: ignore
import datetime as dt
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.core.cache.disk import DiskCacheError, DiskJsonCache
from src.top_models.types import TopModel, TopModelPricing, TopModelsResult, TopModelsSourceName


class TopModelsCacheError(DiskCacheError):
    pass


def _parse_iso8601(ts: str) -> datetime:
    # Accept both Z and +00:00 formats
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def _to_iso8601_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _model_to_cache_dict(m: TopModel) -> dict[str, Any]:
    pricing: dict[str, Any] = {}
    if m.pricing.input_per_million is not None:
        pricing["input_per_million"] = m.pricing.input_per_million
    if m.pricing.output_per_million is not None:
        pricing["output_per_million"] = m.pricing.output_per_million

    return {
        "id": m.id,
        "name": m.name,
        "provider": m.provider,
        "sub_provider": m.sub_provider,
        "context_window": m.context_window,
        "capabilities": list(m.capabilities),
        "pricing": pricing,
    }


def _model_from_cache_dict(d: dict[str, Any]) -> TopModel | None:
    model_id = d.get("id")
    if not isinstance(model_id, str) or not model_id:
        return None

    name = d.get("name") if isinstance(d.get("name"), str) else None

    provider = d.get("provider") if isinstance(d.get("provider"), str) else None

    # Back-compat: older cache files stored the embedded provider under "provider".
    # New schema stores top-level provider under "provider" and embedded under "sub_provider".
    sub_provider = d.get("sub_provider") if isinstance(d.get("sub_provider"), str) else None
    if provider is None and sub_provider is not None:
        provider = "openrouter"
    if sub_provider is None and provider is not None and provider != "openrouter":
        sub_provider = provider
        provider = "openrouter"
    if provider is None:
        provider = "openrouter"

    context_window = d.get("context_window")
    if not isinstance(context_window, int):
        context_window = None

    caps = d.get("capabilities")
    capabilities: tuple[str, ...] = ()
    if isinstance(caps, list):
        capabilities = tuple(x for x in caps if isinstance(x, str))

    pricing_raw = d.get("pricing")
    pricing = TopModelPricing()
    if isinstance(pricing_raw, dict):
        ipm = pricing_raw.get("input_per_million")
        opm = pricing_raw.get("output_per_million")
        pricing = TopModelPricing(
            input_per_million=float(ipm) if isinstance(ipm, (int, float)) else None,
            output_per_million=float(opm) if isinstance(opm, (int, float)) else None,
        )

    return TopModel(
        id=model_id,
        name=name,
        provider=provider,
        sub_provider=sub_provider,
        context_window=context_window,
        capabilities=capabilities,
        pricing=pricing,
    )


class TopModelsDiskCache(DiskJsonCache):
    """Cache for top models recommendations.

    Migrates from legacy flat file to hierarchical structure.
    """

    def __init__(self, cache_dir: Path, ttl: timedelta, *, provider: str = "openrouter") -> None:
        super().__init__(
            cache_dir=cache_dir,
            ttl=ttl,
            schema_version=2,
            namespace="top-models",
        )
        self.provider = provider

    def _file_path(self) -> Path:
        """Path: top-models/{provider}/api.json"""
        return self.cache_dir / self.namespace / self.provider / "api.json"

    def _migrate_legacy_if_exists(self) -> TopModelsResult | None:
        """Migrate old top-models.json to new hierarchy and delete legacy."""
        legacy_path = self.cache_dir / "top-models.json"
        if legacy_path.exists():
            try:
                # Read from legacy location using old logic
                with legacy_path.open("r", encoding="utf-8") as f:
                    payload = json.load(f)

                # Validate legacy format
                if not isinstance(payload, dict) or payload.get("schema_version") not in (1, 2):
                    return None

                # Create result from legacy data
                source = payload.get("source", self.provider)
                last_updated_raw = payload.get("last_updated")
                if not isinstance(last_updated_raw, str):
                    return None

                try:
                    last_updated = _parse_iso8601(last_updated_raw)
                except Exception:
                    return None

                models_raw = payload.get("models", [])
                models: list[TopModel] = []
                for item in models_raw:
                    if not isinstance(item, dict):
                        continue
                    m = _model_from_cache_dict(item)
                    if m is not None:
                        models.append(m)

                aliases_raw = payload.get("aliases", {})
                aliases: dict[str, str] = {}
                if isinstance(aliases_raw, dict):
                    for k, v in aliases_raw.items():
                        if isinstance(k, str) and isinstance(v, str):
                            aliases[k] = v

                result = TopModelsResult(
                    source=source,
                    cached=True,
                    last_updated=last_updated,
                    models=tuple(models),
                    aliases=aliases,
                )

                # Write to new hierarchical location
                self.write_result(result)

                # Delete legacy file to avoid confusion
                legacy_path.unlink()
                return result
            except Exception as e:
                # Log but don't fail - let normal cache logic proceed
                import os

                if os.environ.get("PYTEST_CURRENT_TEST"):
                    pass  # Suppress logging in tests
                else:
                    import sys

                    print(
                        f"Warning: Failed to migrate legacy top-models cache: {e}", file=sys.stderr
                    )
        return None

    def read_if_fresh(self, expected_source: TopModelsSourceName) -> TopModelsResult | None:  # type: ignore[override]
        """Read from cache, checking legacy migration first."""
        # Try legacy migration first
        legacy_result = self._migrate_legacy_if_exists()
        if legacy_result:
            return legacy_result

        # Use base class cache read
        result = super().read_if_fresh()
        if result and hasattr(result, "source") and result.source == expected_source:  # type: ignore[assignment]
            return result  # type: ignore[return-value]
        return None

    def _serialize(self, result: TopModelsResult) -> dict[str, Any]:
        """Convert TopModelsResult to cache dict."""
        return {
            "source": result.source,
            "models": [_model_to_cache_dict(m) for m in result.models],
            "aliases": result.aliases,
        }

    def _deserialize(self, cache_data: dict[str, Any]) -> TopModelsResult:
        """Convert cache dict back to TopModelsResult."""
        source = cache_data.get("source")
        if not isinstance(source, str):
            raise TopModelsCacheError("Invalid source in cache")

        models_raw = cache_data.get("models", [])
        if not isinstance(models_raw, list):
            raise TopModelsCacheError("Invalid models in cache")

        models: list[TopModel] = []
        for item in models_raw:
            if isinstance(item, dict):
                m = _model_from_cache_dict(item)
                if m is not None:
                    models.append(m)

        aliases_raw = cache_data.get("aliases", {})
        aliases: dict[str, str] = {}
        if isinstance(aliases_raw, dict):
            for k, v in aliases_raw.items():
                if isinstance(k, str) and isinstance(v, str):
                    aliases[k] = v

        return TopModelsResult(
            source=source,  # type: ignore[arg-type]
            cached=True,
            last_updated=datetime.now(dt.timezone.utc),  # type: ignore[arg-type]
            models=tuple(models),
            aliases=aliases,
        )

    def write_result(self, result: TopModelsResult) -> None:
        """Write TopModelsResult to cache using base class write."""
        # Call base class write with the TopModelsResult
        super().write(result)

    def _write_legacy(
        self,
        source: TopModelsSourceName,
        last_updated: datetime,
        models: tuple[TopModel, ...],
        aliases: dict[str, str],
    ) -> None:
        """Legacy write method - create result and use write_result."""
        result = TopModelsResult(
            source=source,
            cached=False,
            last_updated=last_updated,
            models=models,
            aliases=aliases,
        )
        self.write_result(result)
