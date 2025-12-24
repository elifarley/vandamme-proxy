from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import yaml

logger = logging.getLogger(__name__)

# PyYAML is untyped; we rely on types-PyYAML in dev.


class DashboardConfigProtocol(Protocol):
    api_base_url: str


@dataclass(frozen=True)
class DashboardConfig(DashboardConfigProtocol):
    api_base_url: str = "http://localhost:8082"


class DashboardDataError(RuntimeError):
    pass


def _log_and_raise(msg: str, url: str, exc: Exception) -> None:
    logger.debug("%s (url=%s) - %s", msg, url, exc)
    raise DashboardDataError(f"{msg} from {url}: {exc}") from exc


async def fetch_health(*, cfg: DashboardConfigProtocol) -> dict[str, Any]:
    url = f"{cfg.api_base_url}/health"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    try:
        data = yaml.safe_load(resp.text)
    except Exception as e:  # noqa: BLE001
        _log_and_raise("Failed to parse YAML", url, e)

    if not isinstance(data, dict):
        raise DashboardDataError(f"Unexpected /health YAML shape from {url}: {type(data)}")
    return data


async def fetch_test_connection(*, cfg: DashboardConfigProtocol) -> dict[str, Any]:
    url = f"{cfg.api_base_url}/test-connection"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
    # Endpoint returns JSON both on success and failure; preserve status.
    try:
        payload = resp.json()
    except Exception as e:  # noqa: BLE001
        _log_and_raise("Failed to parse JSON", url, e)

    if not isinstance(payload, dict):
        raise DashboardDataError(
            f"Unexpected /test-connection JSON shape from {url}: {type(payload)}"
        )

    payload["_http_status"] = resp.status_code
    return payload


async def fetch_running_totals(
    *,
    cfg: DashboardConfigProtocol,
    provider: str | None = None,
    model: str | None = None,
    include_active: bool = True,
) -> dict[str, Any]:
    url = f"{cfg.api_base_url}/metrics/running-totals"
    params: dict[str, str] = {}
    if provider:
        params["provider"] = provider
    if model:
        params["model"] = model
    if not include_active:
        params["include_active"] = "false"

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()

    try:
        data = yaml.safe_load(resp.text)
    except Exception as e:  # noqa: BLE001
        _log_and_raise("Failed to parse YAML", url, e)

    if not isinstance(data, dict):
        raise DashboardDataError(
            f"Unexpected /metrics/running-totals YAML shape from {url}: {type(data)}"
        )
    return data


async def fetch_active_requests(*, cfg: DashboardConfigProtocol) -> dict[str, Any]:
    url = f"{cfg.api_base_url}/metrics/active-requests"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    try:
        payload = resp.json()
    except Exception as e:  # noqa: BLE001
        _log_and_raise("Failed to parse JSON", url, e)

    if not isinstance(payload, dict):
        raise DashboardDataError(
            f"Unexpected /metrics/active-requests JSON shape from {url}: {type(payload)}"
        )
    return payload


async def fetch_models(
    *, cfg: DashboardConfigProtocol, provider: str | None = None
) -> dict[str, Any]:
    """Fetch available models from the API"""
    url = f"{cfg.api_base_url}/v1/models"
    params: dict[str, str] = {"format": "openai"}
    headers: dict[str, str] = {}
    if provider:
        params["provider"] = provider
        headers["provider"] = provider

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params, headers=headers)

    if resp.status_code != 200:
        raise DashboardDataError(f"Failed to fetch models from {url}: HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        _log_and_raise("Failed to parse JSON", url, e)

    if isinstance(data, dict):
        list_data = data.get("data")
        if isinstance(list_data, list):
            return data

        alt_list = data.get("models")
        if isinstance(alt_list, list):
            message_parts = [
                "dashboard.models: /v1/models returned dict with 'models' key",
                "instead of 'data'; wrapping",
            ]
            logger.warning(
                " ".join(message_parts),
                extra={"provider": provider or "", "count": len(alt_list)},
            )
            return {"object": "list", "data": alt_list}

        raise DashboardDataError(
            f"Unexpected /v1/models JSON shape from {url}: missing 'data' list"
        )

    if isinstance(data, list):
        logger.warning(
            "dashboard.models: /v1/models returned bare list; wrapping",
            extra={"provider": provider or "", "count": len(data)},
        )
        return {"object": "list", "data": data}

    raise DashboardDataError(f"Unexpected /v1/models JSON shape from {url}: {type(data)}")


async def fetch_aliases(*, cfg: DashboardConfigProtocol) -> dict[str, Any]:
    """Fetch model aliases from the API"""
    url = f"{cfg.api_base_url}/v1/aliases"

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)

    if resp.status_code != 200:
        raise DashboardDataError(f"Failed to fetch aliases from {url}: HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        _log_and_raise("Failed to parse JSON", url, e)

    if not isinstance(data, dict):
        raise DashboardDataError(f"Unexpected /v1/aliases JSON shape from {url}: {type(data)}")
    return data


async def fetch_logs(
    *,
    cfg: DashboardConfigProtocol,
    limit_errors: int = 100,
    limit_traces: int = 200,
) -> dict[str, Any]:
    url = f"{cfg.api_base_url}/metrics/logs"
    params: dict[str, int] = {
        "limit_errors": limit_errors,
        "limit_traces": limit_traces,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)

    if resp.status_code != 200:
        raise DashboardDataError(f"Failed to fetch logs from {url}: HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        _log_and_raise("Failed to parse JSON", url, e)

    if not isinstance(data, dict):
        raise DashboardDataError(f"Unexpected /metrics/logs JSON shape from {url}: {type(data)}")

    return data


async def fetch_top_models(
    *,
    cfg: DashboardConfigProtocol,
    limit: int = 10,
    refresh: bool = False,
    provider: str | None = None,
) -> dict[str, Any]:
    """Fetch top models from the proxy metadata endpoint."""
    url = f"{cfg.api_base_url}/top-models"
    params: dict[str, str | int | bool] = {"limit": limit, "refresh": refresh}
    if provider:
        params["provider"] = provider

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)

    if resp.status_code != 200:
        raise DashboardDataError(f"Failed to fetch top models from {url}: HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        _log_and_raise("Failed to parse JSON", url, e)

    if not isinstance(data, dict):
        raise DashboardDataError(f"Unexpected /top-models JSON shape from {url}: {type(data)}")

    if not isinstance(data.get("models"), list):
        raise DashboardDataError(
            f"Unexpected /top-models JSON shape from {url}: missing 'models' list"
        )

    return data


def filter_top_models(
    models: list[dict[str, Any]],
    *,
    provider: str | None,
    query: str,
) -> list[dict[str, Any]]:
    """Client-side filtering for the dashboard Top Models page."""
    p = (provider or "").strip().lower()
    q = (query or "").strip().lower()

    out: list[dict[str, Any]] = []
    for m in models:
        if p and str(m.get("sub_provider", "")).lower() != p:
            continue

        if q:
            hay = " ".join(
                [
                    str(m.get("id", "")),
                    str(m.get("name", "")),
                ]
            ).lower()
            if q not in hay:
                continue

        out.append(m)

    return out


def top_models_provider_options(payload: dict[str, Any]) -> list[dict[str, str]]:
    sub_providers = payload.get("sub_providers")
    if not isinstance(sub_providers, list):
        sub_providers = []

    opts: list[dict[str, str]] = [{"label": "All", "value": ""}]
    for p in sub_providers:
        if isinstance(p, str) and p:
            opts.append({"label": p, "value": p})

    return opts


def top_models_limit_options() -> list[dict[str, Any]]:
    return [
        {"label": "5", "value": 5},
        {"label": "10", "value": 10},
        {"label": "20", "value": 20},
        {"label": "50", "value": 50},
    ]


def top_models_source_label(payload: dict[str, Any]) -> str:
    return "cache" if payload.get("cached") else "live"


def top_models_meta_rows(payload: dict[str, Any]) -> list[tuple[str, str]]:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        meta = {}

    rows: list[tuple[str, str]] = []
    ttl = meta.get("cache_ttl_seconds")
    if isinstance(ttl, int):
        rows.append(("cache_ttl_seconds", str(ttl)))

    excluded = meta.get("excluded_rules")
    if isinstance(excluded, list):
        excluded_s = ", ".join(x for x in excluded if isinstance(x, str))
        if excluded_s:
            rows.append(("excluded_rules", excluded_s))

    cache_file = meta.get("cache_file")
    if isinstance(cache_file, str) and cache_file:
        rows.append(("cache_file", cache_file))

    return rows


def top_models_suggested_aliases(payload: dict[str, Any]) -> dict[str, str]:
    raw = payload.get("suggested_aliases")
    if not isinstance(raw, dict):
        return {}

    out: dict[str, str] = {}
    for k, v in raw.items():
        if isinstance(k, str) and isinstance(v, str):
            out[k] = v
    return out


# NOTE: dashboard layout helpers live in src/dashboard/pages/ (package).
# data_sources.py should remain a pure fetch/transform layer.


async def fetch_all_providers(*, cfg: DashboardConfigProtocol) -> list[str]:
    """Extract list of all providers from health endpoint"""
    health_data = await fetch_health(cfg=cfg)
    providers = health_data.get("providers", [])

    # Handle both dict (old format) and list (new format) for resilience
    if isinstance(providers, dict):
        return list(providers.keys())

    if isinstance(providers, list):
        return [p for p in providers if isinstance(p, str)]

    return []
