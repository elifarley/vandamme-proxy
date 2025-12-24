"""Reusable AG Grid option/CSS presets.

These are thin wrappers around `build_ag_grid(...)` inputs to keep per-grid
builders small and consistent.
"""

from __future__ import annotations

from typing import Any


def metrics_common_grid_options(*, row_height: int = 37) -> dict[str, Any]:
    # Mirrors existing metrics grids (providers/models/active requests).
    return {
        "rowHeight": row_height,
    }


def grid_css_compact(*, height_px: int) -> dict[str, str]:
    height = f"{height_px}px"
    return {
        "height": height,
        "minHeight": height,
        "width": "100%",
    }
