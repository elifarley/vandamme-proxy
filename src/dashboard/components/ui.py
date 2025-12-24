from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import dash_ag_grid as dag  # type: ignore[import-untyped]
import dash_bootstrap_components as dbc  # type: ignore[import-untyped]
from dash import html


def format_model_created_timestamp(timestamp: int | float | None) -> str | None:
    """Safely format model creation timestamp to ISO format.

    Handles large timestamps that might cause 'year out of range' errors.
    """
    if not timestamp:
        return None

    try:
        # Convert milliseconds to seconds if needed
        ts = timestamp / 1000 if timestamp > 1e12 else timestamp

        # Validate timestamp range (year 1 to 9999)
        if not (-62135596800 <= ts <= 253402300799):
            return None

        return datetime.fromtimestamp(ts).isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def monospace(text: Any) -> html.Span:
    """Apply monospace font to text or span with style preservation."""
    if isinstance(text, html.Span):
        # If it's already a Span, just add the font family to existing style
        existing_style = getattr(text, "style", None) or {}
        existing_style = existing_style.copy() if isinstance(existing_style, dict) else {}

        existing_style["fontFamily"] = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas"
        existing_class = getattr(text, "className", None)
        return html.Span(text.children, style=existing_style, className=existing_class)
    else:
        # Original behavior for non-Span values
        return html.Span(
            str(text), style={"fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas"}
        )


def status_badge(*, status: str) -> dbc.Badge:
    s = (status or "unknown").lower()
    if s == "healthy":
        color = "success"
    elif s == "degraded":
        color = "warning"
    elif s in {"failed", "down", "error"}:
        color = "danger"
    else:
        color = "secondary"

    return dbc.Badge(status.upper(), color=color, pill=True)


def kpi_card(*, title: str, value: Any, subtitle: str | None = None) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(title, className="text-muted small"),
                html.Div(monospace(value), className="h3 mb-0"),
                html.Div(subtitle, className="text-muted small") if subtitle else None,
            ]
        ),
        className="h-100",
    )


def format_duration(ms: float) -> str:
    """Convert milliseconds to a human-friendly duration.

    Notes:
    - This is used for per-request averages *and* aggregated totals.
    - For totals we want values like "1h 02m" rather than large second counts.
    """
    if ms == 0:
        return "0s"

    if ms < 1000:
        return "<1s"

    total_seconds = int(ms / 1000)
    if total_seconds < 60:
        return f"{total_seconds}s"

    total_minutes = total_seconds // 60
    if total_minutes < 60:
        seconds = total_seconds % 60
        return f"{total_minutes}m {seconds:02d}s" if seconds else f"{total_minutes}m"

    total_hours = total_minutes // 60
    minutes = total_minutes % 60
    if total_hours < 24:
        return f"{total_hours}h {minutes:02d}m" if minutes else f"{total_hours}h"

    days = total_hours // 24
    hours = total_hours % 24
    return f"{days}d {hours:02d}h" if hours else f"{days}d"


def format_timestamp(iso_string: str | None) -> str:
    """Convert ISO timestamp to relative time format with enhanced parsing."""
    if not iso_string:
        return "N/A"

    try:
        # Handle various ISO timestamp formats
        # Format with Z suffix
        if iso_string.endswith("Z"):
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        # Format with timezone offset
        elif "+" in iso_string[-6:] or "-" in iso_string[-6:]:
            dt = datetime.fromisoformat(iso_string)
        # Format without timezone info (assume local time)
        else:
            # Parse naive datetime and treat it as local time
            dt = datetime.fromisoformat(iso_string)
            now = datetime.now()
            # Compare naive datetimes in local time
            diff = now - dt

            # Handle future timestamps (clock skew)
            if diff.total_seconds() < 0:
                return "Just now"

            # Format as relative time
            if diff.total_seconds() < 60:
                return f"{int(diff.total_seconds())}s ago"
            elif diff.total_seconds() < 3600:
                return f"{int(diff.total_seconds() / 60)}m ago"
            elif diff.total_seconds() < 86400:
                return f"{int(diff.total_seconds() / 3600)}h ago"
            else:
                return f"{int(diff.total_seconds() / 86400)}d ago"

        # For timezone-aware timestamps, use UTC comparison
        now = datetime.now(timezone.utc)
        diff = now - dt

        # Handle future timestamps (clock skew)
        if diff.total_seconds() < 0:
            return "Just now"

        # Format as relative time
        if diff.total_seconds() < 60:
            return f"{int(diff.total_seconds())}s ago"
        elif diff.total_seconds() < 3600:
            return f"{int(diff.total_seconds() / 60)}m ago"
        elif diff.total_seconds() < 86400:
            return f"{int(diff.total_seconds() / 3600)}h ago"
        else:
            return f"{int(diff.total_seconds() / 86400)}d ago"
    except (ValueError, TypeError, AttributeError):
        return "Unknown"


def _parse_iso_datetime(iso_string: str | None) -> datetime | None:
    if not iso_string:
        return None

    try:
        if iso_string.endswith("Z"):
            return datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        if "+" in iso_string[-6:] or "-" in iso_string[-6:]:
            return datetime.fromisoformat(iso_string)
        # Naive datetime: treat as local time
        return datetime.fromisoformat(iso_string)
    except (ValueError, TypeError, AttributeError):
        return None


def timestamp_age_seconds(iso_string: str | None) -> float | None:
    """Return age in seconds for an ISO timestamp.

    This is the shared primitive used by the Metrics recency indicator.
    """
    dt = _parse_iso_datetime(iso_string)
    if not dt:
        return None

    diff = datetime.now() - dt if dt.tzinfo is None else datetime.now(timezone.utc) - dt

    # Future timestamps (clock skew) count as "just now".
    return max(0.0, float(diff.total_seconds()))


def timestamp_epoch_ms(iso_string: str | None) -> int | None:
    """Return epoch milliseconds for an ISO timestamp.

    Used for low-overhead client-side recency updates (no ISO parsing in JS loops).
    """
    dt = _parse_iso_datetime(iso_string)
    if not dt:
        return None

    if dt.tzinfo is None:
        # Naive timestamps are interpreted as *local time*.
        # This must match `format_timestamp` semantics to keep the recency ticker correct.
        local_tz = datetime.now().astimezone().tzinfo
        dt = dt.replace(tzinfo=local_tz)

    return int(dt.timestamp() * 1000)


def recency_color_hex(age_seconds: float) -> str:
    """Map age in seconds to a continuous gradient color.

    Anchors:
    - red (<1s), orange, yellow, green, white, blue, black (>=1h)

    We interpolate linearly between anchor colors across [0s..3600s].
    """

    # Clamp to [0..3600]
    t = max(0.0, min(float(age_seconds), 3600.0))

    anchors = [
        (0.0, (255, 0, 0)),  # red
        (5.0, (255, 165, 0)),  # orange
        (20.0, (255, 255, 0)),  # yellow
        (120.0, (0, 255, 0)),  # green
        (600.0, (255, 255, 255)),  # white
        (1800.0, (0, 128, 255)),  # blue
        (3600.0, (0, 0, 0)),  # black
    ]

    lo_t, lo_rgb = anchors[0]
    for hi_t, hi_rgb in anchors[1:]:
        if t <= hi_t:
            span = max(1e-9, hi_t - lo_t)
            u = (t - lo_t) / span
            r = int(round(lo_rgb[0] + (hi_rgb[0] - lo_rgb[0]) * u))
            g = int(round(lo_rgb[1] + (hi_rgb[1] - lo_rgb[1]) * u))
            b = int(round(lo_rgb[2] + (hi_rgb[2] - lo_rgb[2]) * u))
            return f"#{r:02x}{g:02x}{b:02x}"
        lo_t, lo_rgb = hi_t, hi_rgb

    return "#000000"


def recency_dot(iso_string: str | None) -> html.Span:
    # Used for simple (non-ticking) cases.
    age = timestamp_age_seconds(iso_string)
    color = recency_color_hex(age if age is not None else 3600.0)
    return html.Span(
        "",
        className="vdm-recency-dot",
        style={"backgroundColor": color},
        title=iso_string or "No timestamp available",
    )


def recency_dot_with_data_attrs(iso_string: str | None) -> html.Span:
    """Recency dot that exposes epoch+age so JS can update it without server refresh."""
    epoch_ms = timestamp_epoch_ms(iso_string) or 0
    age_at_render = timestamp_age_seconds(iso_string) or 3600.0
    return html.Span(
        "",
        className="vdm-recency-dot",
        style={
            "backgroundColor": recency_color_hex(age_at_render),
            "--vdm-recency-epoch-ms": str(epoch_ms),
            "--vdm-recency-age-at-render": str(age_at_render),
        },
        title=iso_string or "No timestamp available",
    )


def timestamp_with_hover(iso_string: str | None) -> html.Span:
    """Create a span with relative time display and absolute timestamp on hover."""
    relative_time = format_timestamp(iso_string)

    # Use the original iso_string for hover, or a default message
    hover_text = iso_string if iso_string else "No timestamp available"

    return html.Span(
        relative_time,
        title=hover_text,
        style={"cursor": "help", "textDecoration": "underline", "textDecorationStyle": "dotted"},
    )


def timestamp_with_recency_dot(
    iso_string: str | None,
    *,
    id_override: str | None = None,
) -> html.Span:
    """Render a recency dot + relative time text, with absolute timestamp on hover.

    This is used both in AG Grid cells and in KPI cards. We attach predictable
    DOM hooks so a lightweight client-side ticker can update the dot/text
    without any server refresh.

    `id_override` exists so specific places (e.g., the Overview "Last activity"
    KPI) can be targeted by client-side tickers without relying on brittle DOM
    traversal.
    """

    hover_text = iso_string if iso_string else "No timestamp available"
    dot = recency_dot_with_data_attrs(iso_string)
    text = html.Span(format_timestamp(iso_string), className="vdm-recency-text")

    return html.Span(
        [dot, text],
        className="vdm-recency-wrap",
        id=id_override,
        title=hover_text,
        style={
            "display": "inline-flex",
            "alignItems": "center",
            "gap": "6px",
            "cursor": "help",
            "textDecoration": "underline",
            "textDecorationStyle": "dotted",
        },
    )


def duration_color_class(ms: float) -> str:
    """Return CSS class for duration color coding."""
    if ms == 0:
        return "text-muted"
    elif ms < 500:
        return "text-success"
    elif ms < 2000:
        return "text-warning"
    else:
        return "text-danger"


def duration_cell(ms: float, show_raw: bool = True) -> html.Td:
    """Create a table cell with formatted duration and color coding."""
    if ms == 0:
        return html.Td(monospace("N/A"), className="text-muted")

    formatted = format_duration(ms)
    color_class = duration_color_class(ms)

    if show_raw:
        # Show both formatted and raw value
        return html.Td(
            html.Span(
                [
                    html.Span(formatted, className=color_class),
                    html.Span(f" ({ms:.0f}ms)", className="text-muted small ms-1"),
                ]
            )
        )
    else:
        return html.Td(html.Span(formatted, className=color_class))


def search_box(id: str, placeholder: str = "Search...", debounce: bool = True) -> dbc.Input:
    """Create a consistent search input with optional debouncing."""
    return dbc.Input(
        id=id,
        type="text",
        placeholder=placeholder,
        className="border-primary",
        debounce=debounce,
    )


def provider_badge(provider: str, color: str | None = None) -> dbc.Badge:
    """Create a styled provider badge.

    Rules:
    - Some well-known providers have fixed colors for consistent branding.
    - All other providers get a deterministic color derived from their name.
    """

    p = (provider or "").strip()
    key = p.lower()

    # Allow explicit override.
    if color:
        return dbc.Badge(p, color=color, pill=True, className="me-2")

    # Fixed colors for well-known providers.
    # NOTE: Colors must be valid Bootstrap theme colors.
    fixed: dict[str, str] = {
        # Blue-ish
        "openai": "primary",
        "openrouter": "info",
        # Anthropic uses danger now
        "anthropic": "danger",
        # Poe reuses success (green)
        "poe": "success",
    }

    fixed_color = fixed.get(key)
    if fixed_color:
        return dbc.Badge(p, color=fixed_color, pill=True, className="me-2")

    # Deterministic color for the rest.
    # We intentionally keep this simple (not cryptographic): sum of code points.
    palette: list[str] = [
        "primary",
        "success",
        "info",
        "warning",
        "danger",
        "secondary",
    ]
    idx = sum(ord(c) for c in key) % len(palette) if key else 0

    return dbc.Badge(p, color=palette[idx], pill=True, className="me-2")


def models_table(
    models: list[dict[str, Any]],
    sort_field: str = "id",
    sort_desc: bool = False,
    show_provider: bool = True,
) -> dag.AgGrid:
    """Create an AG-Grid table for models with advanced features.

    This function now returns an AG-Grid component instead of a Bootstrap table.
    The sort_field and sort_desc parameters are kept for backward compatibility
    but AG-Grid handles sorting internally through column headers.
    """
    from src.dashboard.components.ag_grid import models_ag_grid

    # Return AG-Grid component - sorting is now handled by clicking column headers
    # Note: grid_id is also used for selection/copy callbacks.
    return models_ag_grid(models=models, grid_id="vdm-models-grid")


def model_details_modal() -> dbc.Modal:
    """Modal for displaying full model details in card format."""
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Model Details", className="text-white"), className="bg-dark"
            ),
            dbc.ModalBody(id="model-details-content", className="bg-dark text-white"),
            dbc.ModalFooter(
                dbc.Button("Close", id="close-model-modal", className="btn-secondary", n_clicks=0),
                className="bg-dark",
            ),
        ],
        id="model-details-modal",
        is_open=False,
        size="lg",
        className="modal-dark",
    )


def model_details_drawer() -> dbc.Offcanvas:
    """Right-side drawer for displaying model details.

    The models grid supports multi-select (for copy IDs). The drawer is intended to
    show details for the *focused* row (typically the first selected row).

    Callback outputs:
    - Body: #vdm-model-details-body
    - Open state: #vdm-model-details-drawer.is_open
    """
    return dbc.Offcanvas(
        [
            html.Div(id="vdm-model-details-header"),
            html.Div(id="vdm-model-details-body"),
            dbc.Button(
                "Close",
                id="vdm-model-details-close",
                color="secondary",
                outline=True,
                size="sm",
                className="mt-3",
                n_clicks=0,
            ),
        ],
        id="vdm-model-details-drawer",
        title="Model details",
        is_open=False,
        placement="end",
        backdrop=True,
        scrollable=True,
        className="bg-dark text-white",
        style={"width": "min(560px, 92vw)"},
    )


def model_card(model: dict[str, Any], show_provider: bool = False) -> dbc.Card:
    """Create a reusable model display card."""
    card_content = [
        dbc.CardHeader(html.Strong(model.get("id", "Unknown Model"))),
        dbc.CardBody(
            [
                html.P(model.get("display_name", ""), className="card-text text-muted mb-2"),
                html.Small(
                    [
                        html.Span("Created: ", className="text-muted"),
                        timestamp_with_hover(format_model_created_timestamp(model.get("created"))),
                    ]
                ),
            ]
        ),
    ]

    if show_provider and model.get("provider"):
        card_content[1].children.insert(0, provider_badge(model["provider"]))

    return dbc.Card(card_content, className="h-100")


def alias_table(aliases: dict[str, Any]) -> dbc.Table:
    """Create a styled table for displaying aliases."""
    rows = []

    for provider, provider_aliases in aliases.items():
        if not isinstance(provider_aliases, dict):
            continue

        for alias_name, maps_to in provider_aliases.items():
            rows.append(
                html.Tr(
                    [
                        html.Td([provider_badge(provider), alias_name]),
                        html.Td(monospace(maps_to)),
                    ]
                )
            )

    return dbc.Table(
        [html.Thead(html.Tr([html.Th("Alias"), html.Th("Maps To")]))] + [html.Tbody(rows)]
        if rows
        else [
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td(
                                "No aliases configured",
                                colSpan=2,
                                className="text-center text-muted",
                            )
                        ]
                    )
                ]
            )
        ],
        striped=True,
        borderless=True,
        size="sm",
        responsive=True,
        className="table-dark",
    )


def token_display(count: int, label: str = "Tokens") -> html.Div:
    """Create a large, prominent token count display."""
    return html.Div(
        [
            html.Div(count, className="display-4 text-primary"),
            html.Div(label, className="text-muted small"),
        ],
        className="text-center",
    )


def empty_state(message: str, icon: str = "📋") -> html.Div:
    """Create a consistent empty state message."""
    return html.Div(
        [
            html.Div(icon, className="display-1 text-muted mb-3"),
            html.H4(message, className="text-muted"),
        ],
        className="text-center py-5",
    )


def loading_state() -> dbc.Spinner:
    """Create a consistent loading spinner."""
    return dbc.Spinner(color="primary", size="sm", type="border")
