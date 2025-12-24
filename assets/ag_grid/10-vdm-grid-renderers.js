// Vandamme Dashboard - AG Grid Cell Renderers
// This file contains the cell renderer functions for AG Grid components.
// Loaded before helpers and init scripts.

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

      /* Provider badge styling shared across the dashboard (AG Grid + non-grid).
         Keep this minimal: Bootstrap provides the color + pill shape. */
      .vdm-provider-badge {
        font-size: 11px;
        font-weight: 500;
        letter-spacing: 0.2px;
      }
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
            ''
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
            ''
        );
    }

    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
        return React.createElement(
            'span',
            {
                title: 'Only http(s) URLs allowed',
                style: { color: '#666', opacity: 0.3, fontSize: '16px' },
            },
            ''
        );
    }

    // Open in a new tab for better UX
    return React.createElement(
        'a',
        {
            href: parsed.toString(),
            target: '_blank',
            rel: 'noopener noreferrer',
            style: { textDecoration: 'none', color: '#666' },
            title: 'Open model page',
        },
        ''
    );
};


// Render a provider badge using Bootstrap's badge classes (DRY with dbc.Badge).
// Contract: Python row shaping must provide `provider_color` as a valid Bootstrap
// theme color name (e.g., "primary", "info", "danger", ...).
window.vdmProviderBadgeRenderer = function(params) {
    const provider = params && params.value ? String(params.value) : '';
    if (!provider) {
        return React.createElement('span', {}, '');
    }

    const color = (params.data && params.data.provider_color) || 'secondary';

    // Match the look of `dbc.Badge(..., pill=True, className="me-2")`.
    // We avoid hard-coded hex colors so the badge stays consistent with the
    // project's Bootstrap theme (incl. dark mode adjustments).
    return React.createElement(
        'span',
        {
            className: `badge bg-${color} rounded-pill me-2 vdm-provider-badge`,
        },
        provider
    );
};


// Format a number with thousand separators
window.vdmFormattedNumberRenderer = function(params) {
    const value = params && params.value;
    if (value == null) {
        return React.createElement('span', {}, '');
    }

    const num = Number(value);
    if (isNaN(num)) {
        return React.createElement('span', {}, '');
    }

    const formatted = num.toLocaleString('en-US');
    return React.createElement('span', {}, formatted);
};


// Render a qualified model id as: <provider badge> : <model id>
// Sorting/filtering should operate on the underlying string value (qualified_model).
window.vdmQualifiedModelRenderer = function(params) {
    const value = params && params.value ? String(params.value) : '';
    const data = (params && params.data) || {};

    if (!value) {
        return React.createElement('span', {}, '');
    }

    const provider = data.provider ? String(data.provider) : '';
    const model = data.model ? String(data.model) : '';

    if (!provider || !model) {
        // Fallback: render the raw value.
        return React.createElement('span', {}, value);
    }

    const badge = window.vdmProviderBadgeRenderer({
        value: provider,
        data: data,
    });

    return React.createElement(
        'span',
        { style: { display: 'inline-flex', alignItems: 'center', gap: '0px' } },
        badge,
        React.createElement('span', { style: { opacity: 0.85, marginRight: '6px' } }, ':'),
        React.createElement('span', {}, model)
    );
};


// Render a recency dot + the existing relative time string.
// Contract: row data must include `last_accessed_age_s` (seconds) and `last_accessed` (text).
window.vdmRecencyDotRenderer = function(params) {
    const data = (params && params.data) || {};
    const age = Number(data.last_accessed_age_s);
    const text = params && params.value ? String(params.value) : '';

    function clamp(x, lo, hi) {
        return Math.max(lo, Math.min(hi, x));
    }

    // Anchors (seconds -> rgb)
    const anchors = [
        [0,    [255, 0, 0]],       // red
        [5,    [255, 165, 0]],     // orange
        [20,   [255, 255, 0]],     // yellow
        [120,  [0, 255, 0]],       // green
        [600,  [255, 255, 255]],   // white
        [1800, [0, 128, 255]],     // blue
        [3600, [0, 0, 0]],         // black
    ];

    const t = clamp(isFinite(age) ? age : 3600, 0, 3600);

    let loT = anchors[0][0];
    let lo = anchors[0][1];
    let color = [0, 0, 0];

    for (let i = 1; i < anchors.length; i++) {
        const hiT = anchors[i][0];
        const hi = anchors[i][1];
        if (t <= hiT) {
            const span = Math.max(1e-9, hiT - loT);
            const u = (t - loT) / span;
            color = [
                Math.round(lo[0] + (hi[0] - lo[0]) * u),
                Math.round(lo[1] + (hi[1] - lo[1]) * u),
                Math.round(lo[2] + (hi[2] - lo[2]) * u),
            ];
            break;
        }
        loT = hiT;
        lo = hi;
    }

    const dot = React.createElement('span', {
        className: 'vdm-recency-dot',
        style: { backgroundColor: `rgb(${color[0]}, ${color[1]}, ${color[2]})` },
    });

    const iso = data.last_accessed_iso ? String(data.last_accessed_iso) : '';

    return React.createElement(
        'span',
        {
            style: { display: 'inline-flex', alignItems: 'center', gap: '6px', cursor: 'help' },
            title: iso || 'No timestamp available',
        },
        dot,
        React.createElement('span', {}, text)
    );
};
