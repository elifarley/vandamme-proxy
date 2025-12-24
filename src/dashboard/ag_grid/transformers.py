from __future__ import annotations

import os
import urllib.parse
from typing import Any

from src.core.alias_config import AliasConfigLoader
from src.dashboard.components.ui import (
    format_duration,
    format_model_created_timestamp,
    format_timestamp,
    timestamp_age_seconds,
    timestamp_epoch_ms,
)

# Module-level cache for provider configs
_alias_config_loader = None


def provider_badge_color(provider_name: str) -> str:
    key = (provider_name or "").lower()
    fixed_colors = {
        "openai": "primary",
        "openrouter": "info",
        "anthropic": "danger",
        "poe": "success",
    }
    return fixed_colors.get(key, "secondary")


def _format_log_time(ts: object) -> tuple[str, str | None, str | None]:
    time_iso = None
    time_relative = None
    time_formatted = ""

    if isinstance(ts, (int, float)):
        try:
            from datetime import datetime

            dt = datetime.fromtimestamp(float(ts))
            time_iso = dt.isoformat()
            time_relative = format_timestamp(time_iso)
            time_formatted = dt.strftime("%H:%M:%S")
        except Exception:  # noqa: BLE001
            time_formatted = ""

    return time_formatted, time_relative, time_iso


def logs_errors_row_data(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    row_data: list[dict[str, Any]] = []

    for error in errors:
        if not isinstance(error, dict):
            continue

        ts = error.get("ts")
        time_formatted, time_relative, time_iso = _format_log_time(ts)

        provider = str(error.get("provider") or "")
        row_data.append(
            {
                "seq": error.get("seq"),
                "ts": ts,
                "time_formatted": time_formatted,
                "time_relative": time_relative,
                "time_iso": time_iso,
                "provider": provider,
                "provider_color": provider_badge_color(provider),
                "model": str(error.get("model") or ""),
                "error_type": str(error.get("error_type") or ""),
                "error": str(error.get("error") or ""),
                "request_id": str(error.get("request_id") or ""),
            }
        )

    return row_data


def logs_traces_row_data(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    row_data: list[dict[str, Any]] = []

    def format_number(value: int | float) -> str:
        if isinstance(value, (int, float)):
            return f"{int(value):,}"
        return "0"

    for trace in traces:
        if not isinstance(trace, dict):
            continue

        ts = trace.get("ts")
        time_formatted, time_relative, time_iso = _format_log_time(ts)

        provider = str(trace.get("provider") or "")

        duration_ms = trace.get("duration_ms", 0)
        if isinstance(duration_ms, (int, float)):
            duration_s = float(duration_ms) / 1000
            duration_formatted = f"{duration_s:.2f}s"
        else:
            duration_formatted = "0.00s"

        row_data.append(
            {
                "seq": trace.get("seq"),
                "ts": ts,
                "time_formatted": time_formatted,
                "time_relative": time_relative,
                "time_iso": time_iso,
                "provider": provider,
                "provider_color": provider_badge_color(provider),
                "model": str(trace.get("model") or ""),
                "status": str(trace.get("status") or ""),
                "duration_ms": duration_ms,
                "duration_formatted": duration_formatted,
                "input_tokens": format_number(trace.get("input_tokens") or 0),
                "output_tokens": format_number(trace.get("output_tokens") or 0),
                "cache_read_tokens": format_number(trace.get("cache_read_tokens") or 0),
                "cache_creation_tokens": format_number(trace.get("cache_creation_tokens") or 0),
                "tool_use_count": format_number(trace.get("tool_use_count") or 0),
                "input_tokens_raw": int(trace.get("input_tokens") or 0),
                "output_tokens_raw": int(trace.get("output_tokens") or 0),
                "cache_read_tokens_raw": int(trace.get("cache_read_tokens") or 0),
                "cache_creation_tokens_raw": int(trace.get("cache_creation_tokens") or 0),
                "request_id": str(trace.get("request_id") or ""),
                "is_streaming": bool(trace.get("is_streaming") or False),
            }
        )

    return row_data


def get_model_page_template(provider_name: str) -> str | None:
    """Get model page template URL for a provider.

    Priority: Environment variable > TOML config
    """
    global _alias_config_loader

    env_var = f"{provider_name.upper()}_MODEL_PAGE"
    env_value = os.environ.get(env_var)
    if env_value:
        return env_value

    if _alias_config_loader is None:
        _alias_config_loader = AliasConfigLoader()

    provider_config = _alias_config_loader.get_provider_config(provider_name)
    return provider_config.get("model-page")


def format_model_page_url(template: str, model_id: str, display_name: str) -> str:
    """Format model page URL by substituting template variables."""

    def _poe_slug(name: str) -> str:
        return urllib.parse.quote(name.replace(" ", "-"))

    quoted_id = urllib.parse.quote(model_id)
    quoted_display_name = urllib.parse.quote(display_name)

    if template.startswith("https://poe.com/"):
        quoted_display_name = _poe_slug(display_name)

    try:
        return template.format(id=quoted_id, display_name=quoted_display_name)
    except Exception:  # noqa: BLE001
        return template.format(id=quoted_id, display_name=quoted_id)


def _safe_http_url(value: object) -> str | None:
    """Return a safe http(s) URL string or None."""
    if not isinstance(value, str) or not value:
        return None

    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None

    return value


def _extract_model_icon_url(model: dict[str, Any]) -> str | None:
    """Extract a normalized model icon URL from a provider model payload."""
    metadata = model.get("metadata")
    if isinstance(metadata, dict):
        image = metadata.get("image")
        if isinstance(image, dict):
            url = _safe_http_url(image.get("url"))
            if url:
                return url

        url = _safe_http_url(metadata.get("image_url"))
        if url:
            return url

        url = _safe_http_url(image)
        if url:
            return url

        icon = metadata.get("icon")
        if isinstance(icon, dict):
            url = _safe_http_url(icon.get("url"))
            if url:
                return url

    return _safe_http_url(model.get("image_url"))


def top_models_row_data(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build AG-Grid rowData for the Top Models page."""

    row_data: list[dict[str, Any]] = []
    for m in models:
        pricing = m.get("pricing") if isinstance(m.get("pricing"), dict) else {}
        avg = pricing.get("average_per_million") if isinstance(pricing, dict) else None
        avg_s = f"{avg:.3f}" if isinstance(avg, (int, float)) else ""

        caps = m.get("capabilities")
        caps_s = ", ".join(c for c in caps if isinstance(c, str)) if isinstance(caps, list) else ""

        row_data.append(
            {
                "provider": m.get("provider") or "",
                "sub_provider": m.get("sub_provider") or "",
                "id": m.get("id") or "",
                "name": m.get("name") or "",
                "context_window": m.get("context_window") or "",
                "avg_per_million": avg_s,
                "capabilities": caps_s,
            }
        )

    return row_data


def metrics_providers_row_data(running_totals_yaml: dict[str, Any]) -> list[dict[str, Any]]:
    """Build AG-Grid rowData for the Metrics Providers grid."""

    from src.dashboard.normalize import provider_rows

    rows = provider_rows(running_totals_yaml)

    row_data: list[dict[str, Any]] = []
    for r in rows:
        provider = str(r.get("provider") or "")

        requests = int(r.get("requests") or 0)
        errors = int(r.get("errors") or 0)
        error_rate = float(r.get("error_rate") or 0.0)

        row_data.append(
            {
                "provider": provider,
                "provider_color": provider_badge_color(provider),
                "requests": requests,
                "errors": errors,
                "error_rate": error_rate,
                "error_rate_pct": f"{error_rate * 100:.2f}%",
                "input_tokens_raw": int(r.get("input_tokens") or 0),
                "output_tokens_raw": int(r.get("output_tokens") or 0),
                "cache_read_tokens_raw": int(r.get("cache_read_tokens") or 0),
                "cache_creation_tokens_raw": int(r.get("cache_creation_tokens") or 0),
                "tool_calls_raw": int(r.get("tool_calls") or 0),
                "average_duration_ms": float(r.get("average_duration_ms") or 0.0),
                "average_duration": format_duration(float(r.get("average_duration_ms") or 0.0)),
                "total_duration_ms_raw": float(r.get("total_duration_ms") or 0.0),
                "total_duration": format_duration(float(r.get("total_duration_ms") or 0.0)),
                "last_accessed": format_timestamp(r.get("last_accessed")) or "",
                "last_accessed_iso": r.get("last_accessed") or "",
                "last_accessed_epoch_ms": timestamp_epoch_ms(r.get("last_accessed")) or 0,
                "last_accessed_age_s": timestamp_age_seconds(r.get("last_accessed")) or 3600.0,
                # Remember the age at the time the row was built so the browser can
                # update smoothly without server refresh.
                "last_accessed_age_s_at_render": timestamp_age_seconds(r.get("last_accessed"))
                or 3600.0,
            }
        )

    return row_data


def metrics_active_requests_row_data(active_requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build AG-Grid rowData for the Metrics Active Requests grid.

    The API returns a snapshot from `RequestTracker.get_active_requests_snapshot()`.

    Responsibilities here:
    - Ensure provider badge fields are present (`provider_color`, `model`)
    - Provide `last_accessed_*` fields expected by `vdmRecencyDotRenderer`, mapped
      to request start time (`start_time`) so the dot reflects request age.

    Note: `start_time` is epoch seconds.
    """

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    row_data: list[dict[str, Any]] = []
    for r in active_requests:
        if not isinstance(r, dict):
            continue

        provider = str(r.get("provider") or "")
        model = str(r.get("model") or "")

        start_time_s = r.get("start_time")
        if isinstance(start_time_s, (int, float)):
            start_epoch_ms = float(start_time_s) * 1000.0
            start_iso = datetime.fromtimestamp(float(start_time_s), tz=timezone.utc).isoformat()
            age_s = now.timestamp() - float(start_time_s)
        else:
            start_epoch_ms = 0.0
            start_iso = ""
            age_s = 3600.0

        row_data.append(
            {
                **r,
                "provider": provider,
                "provider_color": provider_badge_color(provider),
                "model": model,
                # `vdmRecencyDotRenderer` contract:
                "last_accessed": "",
                "last_accessed_iso": start_iso,
                "last_accessed_epoch_ms": int(start_epoch_ms) if start_epoch_ms else 0,
                "last_accessed_age_s_at_render": float(age_s),
            }
        )

    return row_data


def metrics_models_row_data(running_totals_yaml: dict[str, Any]) -> list[dict[str, Any]]:
    """Build AG-Grid rowData for the Metrics Models grid across all providers."""

    from src.dashboard.normalize import model_rows_for_provider, provider_rows

    provs = provider_rows(running_totals_yaml)

    row_data: list[dict[str, Any]] = []
    for prov in provs:
        provider = str(prov.get("provider") or "")
        for mr in model_rows_for_provider(prov):
            model = str(mr.get("model") or "")
            requests = int(mr.get("requests") or 0)
            errors = int(mr.get("errors") or 0)
            error_rate = float(mr.get("error_rate") or 0.0)

            row_data.append(
                {
                    "provider": provider,
                    "provider_color": provider_badge_color(provider),
                    "model": model,
                    "qualified_model": f"{provider}:{model}",
                    "requests": requests,
                    "errors": errors,
                    "error_rate": error_rate,
                    "error_rate_pct": f"{error_rate * 100:.2f}%",
                    "input_tokens_raw": int(mr.get("input_tokens") or 0),
                    "output_tokens_raw": int(mr.get("output_tokens") or 0),
                    "cache_read_tokens_raw": int(mr.get("cache_read_tokens") or 0),
                    "cache_creation_tokens_raw": int(mr.get("cache_creation_tokens") or 0),
                    "tool_calls_raw": int(mr.get("tool_calls") or 0),
                    "average_duration_ms": float(mr.get("average_duration_ms") or 0.0),
                    "average_duration": format_duration(
                        float(mr.get("average_duration_ms") or 0.0)
                    ),
                    "total_duration_ms_raw": float(mr.get("total_duration_ms") or 0.0),
                    "total_duration": format_duration(float(mr.get("total_duration_ms") or 0.0)),
                    "last_accessed": format_timestamp(mr.get("last_accessed")) or "",
                    "last_accessed_iso": mr.get("last_accessed") or "",
                    "last_accessed_epoch_ms": timestamp_epoch_ms(mr.get("last_accessed")) or 0,
                    "last_accessed_age_s": timestamp_age_seconds(mr.get("last_accessed")) or 3600.0,
                    "last_accessed_age_s_at_render": timestamp_age_seconds(mr.get("last_accessed"))
                    or 3600.0,
                }
            )

    row_data.sort(
        key=lambda r: (r.get("requests", 0), r.get("provider", ""), r.get("model", "")),
        reverse=True,
    )
    return row_data


def models_row_data(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build AG-Grid rowData for the Models page."""

    row_data: list[dict[str, Any]] = []
    for model in models:
        created = model.get("created")
        created_value = 0 if created is None else created
        if created_value > 1e12:
            created_value = created_value / 1000

        created_iso = format_model_created_timestamp(created_value)
        created_relative = format_timestamp(created_iso)
        created_day = (created_iso or "")[:10]

        provider = model.get("provider", "multiple")
        model_id = model.get("id", "")
        display_name = model.get("display_name", model_id)

        architecture = model.get("architecture")
        architecture_modality = None
        if isinstance(architecture, dict):
            modality = architecture.get("modality")
            if isinstance(modality, str):
                architecture_modality = modality

        context_window = model.get("context_window")
        context_length = None
        max_output_tokens = None
        if isinstance(context_window, dict):
            cl = context_window.get("context_length")
            mot = context_window.get("max_output_tokens")
            context_length = cl if isinstance(cl, int) else None
            max_output_tokens = mot if isinstance(mot, int) else None

        if context_length is None:
            cl2 = model.get("context_length")
            context_length = cl2 if isinstance(cl2, int) else None
        if max_output_tokens is None:
            mot2 = model.get("max_output_tokens")
            max_output_tokens = mot2 if isinstance(mot2, int) else None

        pricing = model.get("pricing")
        prompt_per_million = None
        completion_per_million = None
        if isinstance(pricing, dict):
            prompt = pricing.get("prompt")
            completion = pricing.get("completion")

            try:
                prompt_per_million = (
                    f"{float(prompt) * 1_000_000:.2f}" if prompt is not None else None
                )
            except Exception:  # noqa: BLE001
                prompt_per_million = None

            try:
                completion_per_million = (
                    f"{float(completion) * 1_000_000:.2f}" if completion is not None else None
                )
            except Exception:  # noqa: BLE001
                completion_per_million = None

        model_page_url = None
        if model_id:
            template = get_model_page_template(provider)
            if template:
                model_page_url = format_model_page_url(template, model_id, display_name)

        description_full = model.get("description")
        description_text = description_full if isinstance(description_full, str) else None
        description_preview = None
        if description_text:
            preview = description_text[:40]
            description_preview = preview + "..." if len(description_text) > 40 else preview

        image_url = _extract_model_icon_url(model)

        row_data.append(
            {
                "id": model_id,
                "provider": provider,
                "created": int(created_value),
                "created_relative": created_relative or "Unknown",
                "created_iso": created_day,
                "model_page_url": model_page_url,
                "owned_by": model.get("owned_by"),
                "architecture_modality": architecture_modality,
                "context_length": context_length,
                "max_output_tokens": max_output_tokens,
                "pricing_prompt_per_million": prompt_per_million,
                "pricing_completion_per_million": completion_per_million,
                "description_preview": description_preview,
                "description_full": description_text,
                "model_icon_url": image_url,
            }
        )

    return row_data
