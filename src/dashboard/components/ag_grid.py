"""AG-Grid component for the dashboard with dark theme support."""

from typing import Any

import dash_ag_grid as dag  # type: ignore[import-untyped]

from src.dashboard.ag_grid.transformers import (
    logs_errors_row_data,
    logs_traces_row_data,
    models_row_data,
    top_models_row_data,
)


def top_models_ag_grid(
    models: list[dict[str, Any]],
    *,
    grid_id: str = "vdm-top-models-grid",
) -> dag.AgGrid:
    """Create an AG-Grid table for Top Models.

    Expects rows shaped like the `/top-models` API output items.
    """
    column_defs = [
        {
            "headerName": "Provider",
            "field": "provider",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 130,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Sub-provider",
            "field": "sub_provider",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 160,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Model ID",
            "field": "id",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 2,
            "minWidth": 260,
            "cellStyle": {"cursor": "copy"},
        },
        {
            "headerName": "Name",
            "field": "name",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 1,
            "minWidth": 160,
        },
        {
            "headerName": "Context",
            "field": "context_window",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Avg $/M",
            "field": "avg_per_million",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Caps",
            "field": "capabilities",
            "sortable": False,
            "filter": True,
            "resizable": True,
            "flex": 1,
            "minWidth": 220,
        },
    ]

    row_data = top_models_row_data(models)

    custom_css = {
        "height": "70vh",
        "width": "100%",
        "minHeight": "500px",
    }

    return dag.AgGrid(
        id=grid_id,
        className="ag-theme-alpine-dark",
        style=custom_css,
        columnDefs=column_defs,
        rowData=row_data,
        defaultColDef={
            "sortable": True,
            "resizable": True,
            "filter": True,
        },
        dashGridOptions={
            "animateRows": True,
            "rowSelection": {"mode": "multiRow"},
            "suppressDragLeaveHidesColumns": True,
            "pagination": True,
            "paginationPageSize": 50,
            "paginationPageSizeSelector": [25, 50, 100, 200],
            "domLayout": "normal",
            "suppressContextMenu": False,
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
            "localeText": {
                "page": "Page",
                "to": "to",
                "of": "of",
                "first": "First",
                "last": "Last",
                "next": "Next",
                "previous": "Previous",
                "loadingOoo": "Loading...",
                "noRowsToShow": "No models found",
                "filterOoo": "Filter...",
            },
        },
        dangerously_allow_code=True,
    )


# --- Models AG Grid ---


def models_ag_grid(
    models: list[dict[str, Any]],
    grid_id: str = "vdm-models-grid",
) -> dag.AgGrid:
    """Create an AG-Grid table for models with dark theme and advanced features.

    Args:
        models: List of model dictionaries
        grid_id: Unique ID for the grid component

    Returns:
        AG-Grid component with models data
    """
    row_data = models_row_data(models)

    # Define column definitions with new order: Created → Actions → Model ID → metadata
    column_defs = [
        {
            "headerName": "Created",
            "field": "created_iso",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 120,  # Fixed width for yyyy-mm-dd format (plus padding)
            "suppressSizeToFit": True,
            "suppressMovable": False,
            "sort": "desc",  # Default sort by creation date (newest first)
            "tooltipField": "created_relative",
            "comparator": {"function": "vdmDateComparator"},
        },
        {
            "headerName": "Actions",
            "field": "actions",
            "sortable": False,
            "filter": False,
            "resizable": False,
            "width": 80,  # Fixed width for emoji icon with padding
            "suppressSizeToFit": True,
            "suppressMovable": True,
            "cellRenderer": "vdmModelPageLinkRenderer",
        },
        {
            "headerName": "Sub-Provider",
            "field": "owned_by",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 1,
            "minWidth": 140,
        },
        {
            "headerName": "Model ID",
            "field": "id",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 2,
            "minWidth": 220,
            "suppressMovable": False,
            "cellStyle": {"cursor": "copy"},
            "tooltipField": "description_full",
            "cellRenderer": "vdmModelIdWithIconRenderer",
        },
        {
            "headerName": "Modality",
            "field": "architecture_modality",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 1,
            "minWidth": 170,
        },
        {
            "headerName": "Context",
            "field": "context_length",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Max out",
            "field": "max_output_tokens",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "$/M in",
            "field": "pricing_prompt_per_million",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 100,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "$/M out",
            "field": "pricing_completion_per_million",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 100,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Description",
            "field": "description_preview",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 3,
            "minWidth": 360,
            "tooltipField": "description_full",
        },
    ]

    # Custom CSS for dark theme
    # NOTE: Using a viewport-based height avoids the common "100% of an auto-height parent"
    # trap where AG-Grid renders but no rows are visible.
    custom_css = {
        "height": "70vh",
        "width": "100%",
        "minHeight": "500px",
    }

    # Create the AG-Grid component with proper parameter names
    return dag.AgGrid(
        id=grid_id,
        className="ag-theme-alpine-dark",
        style=custom_css,
        columnDefs=column_defs,
        rowData=row_data,
        defaultColDef={
            "sortable": True,
            "resizable": True,
            "filter": True,
        },
        dashGridOptions={
            "animateRows": True,
            # Community-friendly multi-row selection (AG Grid v32+ object form)
            # Enable click-selection (AG Grid v32.2+).
            "rowSelection": {"mode": "multiRow", "enableClickSelection": True},
            "suppressDragLeaveHidesColumns": True,
            "pagination": True,
            "paginationPageSize": 50,
            "paginationPageSizeSelector": [25, 50, 100, 200],
            "domLayout": "normal",
            "suppressContextMenu": False,
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
            "localeText": {
                "page": "Page",
                "to": "to",
                "of": "of",
                "first": "First",
                "last": "Last",
                "next": "Next",
                "previous": "Previous",
                "loadingOoo": "Loading...",
                "noRowsToShow": "No models found",
                "filterOoo": "Filter...",
            },
        },
        dangerously_allow_code=True,
    )


# JavaScript functions for AG-Grid
# These will be injected into the app's HTML
CELL_RENDERER_SCRIPTS = """
console.info('[vdm] CELL_RENDERER_SCRIPTS loaded');

// ---- Row striping (all grids) ----
// Use AG Grid's built-in classes (`ag-row-even` / `ag-row-odd`) instead of custom
// rowClassRules so striping works without any grid-specific configuration.
(function ensureStripedRowsCss() {
    if (document.getElementById('vdm-striped-rows-css')) return;
    const style = document.createElement('style');
    style.id = 'vdm-striped-rows-css';
    style.textContent = `
      .ag-theme-alpine-dark .ag-row-even .ag-cell { background-color: rgba(255,255,255,0.06); }
      .ag-theme-alpine-dark .ag-row-odd  .ag-cell { background-color: rgba(0,0,0,0.00); }
    `;
    document.head.appendChild(style);
})();


// Render model id with optional icon.
// Contract: Python row shaping (`models_row_data`) must provide `model_icon_url`
// as either null/undefined or a safe http(s) URL string.
window.vdmModelIdWithIconRenderer = function(params) {
    const id = params && params.value ? String(params.value) : '';
    const url = params && params.data && params.data.model_icon_url;

    if (!url) {
        return React.createElement('span', null, id);
    }

    // Only allow http(s) URLs.
    let parsed;
    try {
        parsed = new URL(url);
    } catch (e) {
        return React.createElement('span', null, id);
    }
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
        return React.createElement('span', null, id);
    }

    // Compact size aligned with existing row height.
    const img = React.createElement('img', {
        src: parsed.toString(),
        alt: '',
        width: 16,
        height: 16,
        style: {
            width: '16px',
            height: '16px',
            borderRadius: '3px',
            marginRight: '6px',
            verticalAlign: 'text-bottom',
            objectFit: 'cover',
        },
    });

    return React.createElement(
        'span',
        { style: { display: 'inline-flex', alignItems: 'center' } },
        img,
        React.createElement('span', null, id)
    );
};

// Render model page link as React element (Dash uses React; DOM nodes cause React invariant #31)
window.vdmModelPageLinkRenderer = function(params) {
    const url = params && params.data && params.data.model_page_url;

    if (!url) {
        return React.createElement(
            'span',
            {
                title: 'No model page available',
                style: { color: '#666', opacity: 0.3, fontSize: '16px' },
            },
            '🔗'
        );
    }

    // Only allow http(s) URLs to avoid accidentally creating javascript: links
    let parsed;
    try {
        parsed = new URL(url);
    } catch (e) {
        return React.createElement(
            'span',
            {
                title: 'Invalid model page URL',
                style: { color: '#666', opacity: 0.3, fontSize: '16px' },
            },
            '🔗'
        );
    }

    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
        return React.createElement(
            'span',
            {
                title: 'Unsupported model page URL',
                style: { color: '#666', opacity: 0.3, fontSize: '16px' },
            },
            '🔗'
        );
    }

    return React.createElement(
        'a',
        {
            href: parsed.toString(),
            target: '_blank',
            rel: 'noopener noreferrer',
            title: 'Open model page in new tab',
            style: { color: '#61DAFB', textDecoration: 'none', fontSize: '16px' },
        },
        '🔗'
    );
};

// Renderer returns a React element, not an HTML string.

// For dash-ag-grid function registry compatibility
window.dashAgGridFunctions = window.dashAgGridFunctions || {};
window.dashAgGridComponentFunctions = window.dashAgGridComponentFunctions || {};

window.dashAgGridFunctions.vdmModelIdWithIconRenderer = window.vdmModelIdWithIconRenderer;
window.dashAgGridComponentFunctions.vdmModelIdWithIconRenderer = window.vdmModelIdWithIconRenderer;

window.dashAgGridFunctions.vdmModelPageLinkRenderer = window.vdmModelPageLinkRenderer;
window.dashAgGridComponentFunctions.vdmModelPageLinkRenderer = window.vdmModelPageLinkRenderer;
window.__vdmModelPageLinkRenderer = window.vdmModelPageLinkRenderer;

// Ensure AG Grid treats the returned string as HTML (set in columnDefs via suppressHtmlEscaping)
window.dashAgGridFunctions.vdmModelPageLinkRenderer.suppressHtmlEscaping = true;
window.dashAgGridComponentFunctions.vdmModelPageLinkRenderer.suppressHtmlEscaping = true;
window.__vdmModelPageLinkRenderer.suppressHtmlEscaping = true;

// Provide a componentFuncs map in case some builds look there
window.dashAgGridComponentFunctions = window.dashAgGridComponentFunctions || {};
window.dashAgGridComponentFunctions = {
    ...window.dashAgGridComponentFunctions,
    vdmModelIdWithIconRenderer: window.vdmModelIdWithIconRenderer,
    vdmModelPageLinkRenderer: window.vdmModelPageLinkRenderer,
};
window.dashAgGridFunctions = {
    ...window.dashAgGridFunctions,
    vdmModelIdWithIconRenderer: window.vdmModelIdWithIconRenderer,
    vdmModelPageLinkRenderer: window.vdmModelPageLinkRenderer,
};
window.__vdmModelPageLinkRenderer = window.vdmModelPageLinkRenderer;
window.dashAgGridFunctions.__vdmModelPageLinkRenderer = window.vdmModelPageLinkRenderer;
window.dashAgGridComponentFunctions.__vdmModelPageLinkRenderer = window.vdmModelPageLinkRenderer;
window.dashAgGridComponentFunctions.suppressHtmlEscaping = true;
window.dashAgGridFunctions.suppressHtmlEscaping = true;
window.__vdmModelPageLinkRenderer.suppressHtmlEscaping = true;

// Also expose as components map (some dash-ag-grid versions read componentFuncs/components)
window.dashAgGridFunctions.components = window.dashAgGridFunctions.components || {};
window.dashAgGridFunctions.components.vdmModelPageLinkRenderer = window.vdmModelPageLinkRenderer;
window.dashAgGridComponentFunctions.components = (
    window.dashAgGridComponentFunctions.components || {}
);
window.dashAgGridComponentFunctions.components.vdmModelPageLinkRenderer = (
    window.vdmModelPageLinkRenderer
);
window.dashAgGridComponentFunctions.components.__vdmModelPageLinkRenderer = (
    window.vdmModelPageLinkRenderer
);
window.dashAgGridFunctions.components.__vdmModelPageLinkRenderer = (
    window.vdmModelPageLinkRenderer
);

// Utility: make sure escapeHtml exists
window.escapeHtml = window.escapeHtml || function(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
};

// For dash-ag-grid function registry compatibility
window.dashAgGridFunctions = window.dashAgGridFunctions || {};
window.dashAgGridComponentFunctions = window.dashAgGridComponentFunctions || {};
window.dashAgGridFunctions.vdmModelPageLinkRenderer = window.vdmModelPageLinkRenderer;
window.dashAgGridComponentFunctions.vdmModelPageLinkRenderer = window.vdmModelPageLinkRenderer;
window.__vdmModelPageLinkRenderer = window.vdmModelPageLinkRenderer;
window.dashAgGridFunctions.components = window.dashAgGridFunctions.components || {};
window.dashAgGridFunctions.components.vdmModelPageLinkRenderer = window.vdmModelPageLinkRenderer;
window.dashAgGridComponentFunctions.components = (
    window.dashAgGridComponentFunctions.components || {}
);
window.dashAgGridComponentFunctions.components.vdmModelPageLinkRenderer = (
    window.vdmModelPageLinkRenderer
);
window.dashAgGridFunctions.suppressHtmlEscaping = true;
window.dashAgGridComponentFunctions.suppressHtmlEscaping = true;
window.__vdmModelPageLinkRenderer.suppressHtmlEscaping = true;
window.dashAgGridFunctions.vdmModelPageLinkRenderer.suppressHtmlEscaping = true;
window.dashAgGridComponentFunctions.vdmModelPageLinkRenderer.suppressHtmlEscaping = true;
window.dashAgGridFunctions.components.vdmModelPageLinkRenderer.suppressHtmlEscaping = true;
window.dashAgGridComponentFunctions.components.vdmModelPageLinkRenderer.suppressHtmlEscaping = true;
window.dashAgGridFunctions.components.__vdmModelPageLinkRenderer = (
    window.vdmModelPageLinkRenderer
);
window.dashAgGridComponentFunctions.components.__vdmModelPageLinkRenderer = (
    window.vdmModelPageLinkRenderer
);
window.dashAgGridFunctions.components.__vdmModelPageLinkRenderer.suppressHtmlEscaping = (
    true
);
window.dashAgGridComponentFunctions.components.__vdmModelPageLinkRenderer.suppressHtmlEscaping = (
    true
);
window.__vdmModelPageLinkRenderer.components = (
    window.__vdmModelPageLinkRenderer.components || {}
);
window.__vdmModelPageLinkRenderer.components.vdmModelPageLinkRenderer = (
    window.vdmModelPageLinkRenderer
);
window.__vdmModelPageLinkRenderer.components.__vdmModelPageLinkRenderer = (
    window.vdmModelPageLinkRenderer
);
window.__vdmModelPageLinkRenderer.components.__vdmModelPageLinkRenderer.suppressHtmlEscaping = (
    true
);
window.__vdmModelPageLinkRenderer.components.vdmModelPageLinkRenderer.suppressHtmlEscaping = true;
window.__vdmModelPageLinkRenderer.components = {
    ...window.__vdmModelPageLinkRenderer.components,
    vdmModelPageLinkRenderer: window.vdmModelPageLinkRenderer,
    __vdmModelPageLinkRenderer: window.vdmModelPageLinkRenderer,
};

// No-op return to avoid returning undefined
window.vdmModelPageLinkRenderer;


// Date comparator function for sorting by creation date
window.dateComparator = function(dateA, dateB) {
    if (dateA === null && dateB === null) {
        return 0;
    }
    if (dateA === null) {
        return -1;
    }
    if (dateB === null) {
        return 1;
    }
    return dateA - dateB;
};

// AG Grid comparator wrapper for the Created column to ensure numeric sort on raw created
window.vdmDateComparator = function(valueA, valueB, nodeA, nodeB) {
    const a = (nodeA && nodeA.data && nodeA.data.created) || 0;
    const b = (nodeB && nodeB.data && nodeB.data.created) || 0;
    return a - b;
};

// Format unix seconds as relative time (e.g. "2m ago")
window.formatRelativeTimestamp = function(unixSeconds) {
    if (!unixSeconds) {
        return 'Unknown';
    }

    const tsMs = unixSeconds * 1000;
    const diffMs = Date.now() - tsMs;

    // Future timestamps (clock skew)
    if (diffMs < 0) {
        return 'Just now';
    }

    const diffSec = Math.floor(diffMs / 1000);
    if (diffSec < 10) return 'Just now';
    if (diffSec < 60) return diffSec + 's ago';

    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return diffMin + 'm ago';

    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return diffHr + 'h ago';

    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return diffDay + 'd ago';

    // Fallback to a stable short date for older entries
    return new Date(tsMs).toLocaleDateString();
};

// Absolute timestamp for tooltips (local time)
window.formatAbsoluteTimestamp = function(unixSeconds) {
    if (!unixSeconds) {
        return '';
    }
    const tsMs = unixSeconds * 1000;
    const d = new Date(tsMs);

    // Match Python's isoformat-ish output used by the dashboard cards:
    // - local time
    // - explicit numeric timezone offset
    const pad = (n) => String(n).padStart(2, '0');

    const year = d.getFullYear();
    const month = pad(d.getMonth() + 1);
    const day = pad(d.getDate());
    const hour = pad(d.getHours());
    const minute = pad(d.getMinutes());
    const second = pad(d.getSeconds());

    const tzMin = -d.getTimezoneOffset();
    const sign = tzMin >= 0 ? '+' : '-';
    const tzAbs = Math.abs(tzMin);
    const tzH = pad(Math.floor(tzAbs / 60));
    const tzM = pad(tzAbs % 60);

    return `${year}-${month}-${day}T${hour}:${minute}:${second}${sign}${tzH}:${tzM}`;
};

// AG Grid formatter wrappers: AG Grid calls these with `params`
window.vdmFormatRelativeTimestamp = function(params) {
    const rel = params && params.data && params.data.created_relative;
    return rel || window.formatRelativeTimestamp(params && params.value);
};

window.vdmFormatRelativeFromRow = function(params) {
    const rel = params && params.data && params.data.created_relative;
    return rel || window.formatRelativeTimestamp(params && params.data && params.data.created);
};

window.vdmFormatAbsoluteTimestamp = function(params) {
    const iso = params && params.data && params.data.created_iso;
    return iso ? iso : window.formatAbsoluteTimestamp(params && params.value);
};

window.vdmDateComparator = function(dateA, dateB) {
    // Compare underlying numeric created values to keep sort stable.
    return (dateA || 0) - (dateB || 0);
};


// Render provider name as a Bootstrap badge
window.vdmProviderBadgeRenderer = function(params) {
    const provider = params && params.value ? String(params.value) : '';
    const color =
        params && params.data && params.data.provider_color
            ? String(params.data.provider_color)
            : 'secondary';

    if (!provider) {
        return React.createElement('span', null, '');
    }

    // Map color names to Bootstrap classes
    const colorMap = {
        'primary': 'bg-primary',
        'success': 'bg-success',
        'info': 'bg-info',
        'warning': 'bg-warning',
        'danger': 'bg-danger',
        'secondary': 'bg-secondary'
    };

    const badgeClass = colorMap[color] || 'bg-secondary';

    return React.createElement(
        'span',
        {
            className: `badge ${badgeClass} rounded-pill me-2`,
            style: { fontSize: '0.8em' }
        },
        provider
    );
};

// Register provider badge renderer
window.dashAgGridFunctions.vdmProviderBadgeRenderer = window.vdmProviderBadgeRenderer;
window.dashAgGridComponentFunctions.vdmProviderBadgeRenderer = window.vdmProviderBadgeRenderer;
window.__vdmProviderBadgeRenderer = window.vdmProviderBadgeRenderer;
window.dashAgGridFunctions.vdmProviderBadgeRenderer.suppressHtmlEscaping = true;
window.dashAgGridComponentFunctions.vdmProviderBadgeRenderer.suppressHtmlEscaping = true;
window.__vdmProviderBadgeRenderer.suppressHtmlEscaping = true;

// Render status as a badge
window.vdmStatusBadgeRenderer = function(params) {
    const status = params && params.value ? String(params.value).toLowerCase() : '';
    const color = status === 'error' ? 'bg-danger' : 'bg-success';

    return React.createElement(
        'span',
        {
            className: `badge ${color} rounded-pill`,
            style: { fontSize: '0.8em' }
        },
        status || 'unknown'
    );
};

// Register status badge renderer
window.dashAgGridFunctions.vdmStatusBadgeRenderer = window.vdmStatusBadgeRenderer;
window.dashAgGridComponentFunctions.vdmStatusBadgeRenderer = window.vdmStatusBadgeRenderer;
window.__vdmStatusBadgeRenderer = window.vdmStatusBadgeRenderer;
window.dashAgGridFunctions.vdmStatusBadgeRenderer.suppressHtmlEscaping = true;
window.dashAgGridComponentFunctions.vdmStatusBadgeRenderer.suppressHtmlEscaping = true;
window.__vdmStatusBadgeRenderer.suppressHtmlEscaping = true;

// Render formatted numbers with thousand separators
window.vdmFormattedNumberRenderer = function(params) {
    const value = params && params.value ? parseInt(params.value, 10) : 0;

    // Format with thousand separators
    const formatted = value.toLocaleString();

    return React.createElement(
        'span',
        {
            style: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas' }
        },
        formatted
    );
};

// Register formatted number renderer
window.dashAgGridFunctions.vdmFormattedNumberRenderer = window.vdmFormattedNumberRenderer;
window.dashAgGridComponentFunctions.vdmFormattedNumberRenderer = window.vdmFormattedNumberRenderer;
window.__vdmFormattedNumberRenderer = window.vdmFormattedNumberRenderer;
window.dashAgGridFunctions.vdmFormattedNumberRenderer.suppressHtmlEscaping = true;
window.dashAgGridComponentFunctions.vdmFormattedNumberRenderer.suppressHtmlEscaping = true;
window.__vdmFormattedNumberRenderer.suppressHtmlEscaping = true;

// Numeric comparator for proper sorting
window.vdmNumericComparator = function(valueA, valueB) {
    const a = parseFloat(valueA) || 0;
    const b = parseFloat(valueB) || 0;
    return a - b;
};

// Register numeric comparator
window.dashAgGridFunctions.vdmNumericComparator = window.vdmNumericComparator;
window.dashAgGridComponentFunctions.vdmNumericComparator = window.vdmNumericComparator;

// Copy selected model IDs to clipboard (newline-separated)
window.vdmCopySelectedModelIds = async function(gridId) {
    console.debug('[vdm][copy] invoking vdmCopySelectedModelIds', {gridId});

    console.debug('[vdm][copy] hook ready:', {
        hasDashAgGrid: !!window.dash_ag_grid,
        apiFn:
            window.dash_ag_grid &&
            window.dash_ag_grid.getApi &&
            window.dash_ag_grid.getApi(gridId),
    });
    try {
        // dash-ag-grid registers itself as window.dash_ag_grid.
        const dag = window.dash_ag_grid;
        if (!dag || !dag.getApi) {
            throw new Error('Grid API not ready');
        }

        // Ensure the specific grid instance is available.
        const api = dag.getApi(gridId);
        if (!api) {
            throw new Error('Grid not ready');
        }
        const selected = api.getSelectedRows ? api.getSelectedRows() : [];
        const ids = (selected || []).map(r => r.id).filter(Boolean);

        if (!ids.length) {
            return { ok: false, message: 'Nothing selected' };
        }

        await navigator.clipboard.writeText(ids.join('\\n'));
        return { ok: true, message: 'Copied ' + ids.length + ' model IDs' };
    } catch (e) {
        return { ok: false, message: 'Copy failed: ' + (e && e.message ? e.message : String(e)) };
    }
};

// Copy a single string to clipboard
window.vdmCopyText = async function(text) {
    const value = (text == null) ? '' : String(text);
    if (!value) {
        return { ok: false, message: 'Nothing to copy' };
    }

    // Prefer the async clipboard API when available.
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(value);
            return { ok: true, message: 'Copied' };
        }
    } catch (e) {
        // Fall through to execCommand below.
    }

    // Fallback for contexts where clipboard API is unavailable/blocked.
    try {
        const ta = document.createElement('textarea');
        ta.value = value;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.top = '-1000px';
        ta.style.left = '-1000px';
        document.body.appendChild(ta);
        ta.select();
        ta.setSelectionRange(0, ta.value.length);
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        return ok ? { ok: true, message: 'Copied' } : { ok: false, message: 'Copy failed' };
    } catch (e) {
        return { ok: false, message: 'Copy failed: ' + (e && e.message ? e.message : String(e)) };
    }
};

// Click-to-copy triggers a toast via a hidden Dash button.
// Clipboard copy is handled in the native AG Grid listener.

// Bridge from grid JS to the Dash toast renderer.
// Payload is stored on window.__vdm_last_toast_payload and a hidden trigger is clicked.
window.vdmToast = function(level, message, modelId) {
    try {
        window.__vdm_last_toast_payload = JSON.stringify({
            level: level || 'info',
            message: message || '',
            model_id: modelId,
        });
        const btn = document.getElementById('vdm-models-toast-trigger');
        if (btn) {
            btn.click();
        } else {
            console.debug('[vdm][toast] trigger not found');
        }
    } catch (e) {
        console.debug('[vdm][toast] failed', e);
    }
};



// Attach a native AG Grid cellClicked listener once the grid API is ready.
// This avoids relying on dashGridOptions "function" plumbing.
// (That indirection doesn't reliably invoke handlers.)
window.vdmAttachModelCellCopyListener = function(gridId) {
    try {
        const dag = window.dash_ag_grid;
        if (!dag || !dag.getApi) {
            return false;
        }
        const api = dag.getApi(gridId);
        if (!api) {
            return false;
        }

        // Idempotent attach (per grid instance).
        if (api.__vdmCopyListenerAttached) {
            return true;
        }
        api.__vdmCopyListenerAttached = true;
        console.log('[vdm][copy] attached model-id click listener', {gridId});

        api.addEventListener('cellClicked', async function(e) {
            try {
                if (!e || !e.colDef || e.colDef.field !== 'id') {
                    return;
                }
                const id = e.value;
                console.log('[vdm][copy] cellClicked', {id});

                // Copy here (this is the only path we have proven works reliably in your browser).
                const r = await window.vdmCopyText(String(id));
                if (r && r.ok) {
                    window.vdmToast('success', 'Copied model id: ' + String(id), id);
                } else {
                    window.vdmToast('warning', (r && r.message) ? r.message : 'Copy failed', id);
                }
            } catch (err) {
                console.log('[vdm][copy] cellClicked handler failed', err);
                window.vdmToast(
                    'warning',
                    'Copy failed: '
                        + (err && err.message ? err.message : String(err)),
                    null,
                );
            }
        });

        return true;
    } catch (_) {
        return false;
    }
};

// Attempt to attach immediately for the models grid.
// (The dashboard also has a boot loop that waits for dash_ag_grid.getApi.)
window.vdmAttachModelCellCopyListener('vdm-models-grid');

// dash-ag-grid expects functions under dashAgGridFunctions (kept for other formatters/comparators)
window.dashAgGridFunctions = window.dashAgGridFunctions || {};

// Some dash-ag-grid versions also look under dashAgGridComponentFunctions for components.
window.dashAgGridComponentFunctions = window.dashAgGridComponentFunctions || {};

// Register our custom cell renderer
window.dashAgGridFunctions.vdmModelPageLinkRenderer = window.vdmModelPageLinkRenderer;
window.dashAgGridComponentFunctions.vdmModelPageLinkRenderer = window.vdmModelPageLinkRenderer;

// Expose as a global for debugging
window.__vdmModelPageLinkRenderer = window.vdmModelPageLinkRenderer;

// Utility function to escape HTML
window.escapeHtml = function(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
};

"""


# --- Logs AG Grid Functions ---


def logs_errors_ag_grid(
    errors: list[dict[str, Any]],
    grid_id: str = "vdm-logs-errors-grid",
) -> dag.AgGrid:
    """Create an AG-Grid table for error logs with dark theme and provider badges.

    Args:
        errors: List of error log dictionaries
        grid_id: Unique ID for the grid component

    Returns:
        AG-Grid component with error logs data
    """
    row_data = logs_errors_row_data(errors)

    # Define column definitions for errors
    column_defs = [
        {
            "headerName": "Time",
            "field": "time_formatted",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 100,
            "suppressSizeToFit": True,
            "tooltipField": "time_relative",
            "sort": "desc",  # Default sort by time (newest first)
        },
        {
            "headerName": "Provider",
            "field": "provider",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 130,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmProviderBadgeRenderer",
        },
        {
            "headerName": "Model",
            "field": "model",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 1,
            "minWidth": 200,
            "cellStyle": {"fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas"},
        },
        {
            "headerName": "Error Type",
            "field": "error_type",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 160,
            "suppressSizeToFit": True,
        },
        {
            "headerName": "Error Message",
            "field": "error",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 3,
            "minWidth": 300,
            "cellStyle": {"fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas"},
            "tooltipField": "error",
        },
    ]

    # Custom CSS for dark theme
    custom_css = {
        "height": "70vh",
        "width": "100%",
        "minHeight": "500px",
    }

    return dag.AgGrid(
        id=grid_id,
        className="ag-theme-alpine-dark",
        style=custom_css,
        columnDefs=column_defs,
        rowData=row_data,
        defaultColDef={
            "sortable": True,
            "resizable": True,
            "filter": True,
        },
        dashGridOptions={
            "animateRows": True,
            "rowSelection": {"mode": "multiRow"},
            "suppressDragLeaveHidesColumns": True,
            "pagination": True,
            "paginationPageSize": 50,
            "paginationPageSizeSelector": [25, 50, 100, 200],
            "domLayout": "normal",
            "suppressContextMenu": False,
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
            "localeText": {
                "page": "Page",
                "to": "to",
                "of": "of",
                "first": "First",
                "last": "Last",
                "next": "Next",
                "previous": "Previous",
                "loadingOoo": "Loading...",
                "noRowsToShow": "No errors found",
                "filterOoo": "Filter...",
            },
        },
        dangerously_allow_code=True,
    )


def logs_traces_ag_grid(
    traces: list[dict[str, Any]],
    grid_id: str = "vdm-logs-traces-grid",
) -> dag.AgGrid:
    """Create an AG-Grid table for trace logs with dark theme and provider badges.

    Args:
        traces: List of trace log dictionaries
        grid_id: Unique ID for the grid component

    Returns:
        AG-Grid component with trace logs data
    """
    row_data = logs_traces_row_data(traces)

    # Define column definitions for traces
    column_defs = [
        {
            "headerName": "Time",
            "field": "time_formatted",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 100,
            "suppressSizeToFit": True,
            "tooltipField": "time_relative",
            "sort": "desc",  # Default sort by time (newest first)
        },
        {
            "headerName": "Provider",
            "field": "provider",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 130,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmProviderBadgeRenderer",
        },
        {
            "headerName": "Model",
            "field": "model",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "flex": 1,
            "minWidth": 200,
            "cellStyle": {"fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas"},
        },
        {
            "headerName": "Status",
            "field": "status",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 100,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmStatusBadgeRenderer",
        },
        {
            "headerName": "Duration",
            "field": "duration_formatted",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 100,
            "suppressSizeToFit": True,
            "tooltipField": "duration_ms",
            "comparator": {"function": "vdmNumericComparator"},
        },
        {
            "headerName": "In Tokens",
            "field": "input_tokens_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Out Tokens",
            "field": "output_tokens_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Cache Read",
            "field": "cache_read_tokens_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
        {
            "headerName": "Cache Create",
            "field": "cache_creation_tokens_raw",
            "sortable": True,
            "filter": True,
            "resizable": True,
            "width": 110,
            "suppressSizeToFit": True,
            "cellRenderer": "vdmFormattedNumberRenderer",
        },
    ]

    # Custom CSS for dark theme
    custom_css = {
        "height": "70vh",
        "width": "100%",
        "minHeight": "500px",
    }

    return dag.AgGrid(
        id=grid_id,
        className="ag-theme-alpine-dark",
        style=custom_css,
        columnDefs=column_defs,
        rowData=row_data,
        defaultColDef={
            "sortable": True,
            "resizable": True,
            "filter": True,
        },
        dashGridOptions={
            "animateRows": True,
            "rowSelection": {"mode": "multiRow"},
            "suppressDragLeaveHidesColumns": True,
            "pagination": True,
            "paginationPageSize": 50,
            "paginationPageSizeSelector": [25, 50, 100, 200],
            "domLayout": "normal",
            "suppressContextMenu": False,
            "enableCellTextSelection": True,
            "ensureDomOrder": True,
            "localeText": {
                "page": "Page",
                "to": "to",
                "of": "of",
                "first": "First",
                "last": "Last",
                "next": "Next",
                "previous": "Previous",
                "loadingOoo": "Loading...",
                "noRowsToShow": "No traces found",
                "filterOoo": "Filter...",
            },
        },
        dangerously_allow_code=True,
    )


def get_ag_grid_clientside_callback() -> dict[str, dict[str, str]]:
    """Return the clientside callback for AG-Grid cell renderers.

    Note: the keys must match the Dash component id(s) of the AgGrid instances.
    """
    return {
        "vdm-models-grid": {"javascript": CELL_RENDERER_SCRIPTS},
        "vdm-top-models-grid": {"javascript": CELL_RENDERER_SCRIPTS},
        "vdm-logs-errors-grid": {"javascript": CELL_RENDERER_SCRIPTS},
        "vdm-logs-traces-grid": {"javascript": CELL_RENDERER_SCRIPTS},
    }
