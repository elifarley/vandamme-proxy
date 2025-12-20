"""Duration helpers for metrics rollups."""

from __future__ import annotations


def finalize_average_duration(totals: dict[str, float | int]) -> None:
    """Compute `average_duration_ms` from `total_duration_ms` and delete the latter."""

    requests = int(totals.get("requests", 0) or 0)
    if requests > 0:
        totals["average_duration_ms"] = int(round(float(totals["total_duration_ms"]) / requests))
    else:
        totals["average_duration_ms"] = 0

    # The YAML schema expects average, not total duration.
    del totals["total_duration_ms"]


def finalize_split(split: dict[str, dict[str, float | int]]) -> None:
    for section in ("total", "streaming", "non_streaming"):
        finalize_average_duration(split[section])
