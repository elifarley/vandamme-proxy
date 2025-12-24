// Vandamme Dashboard - AG Grid Initialization
// This file initializes AG Grid with the custom renderers and helpers.
// Must be loaded after vdm-grid-renderers.js and vdm-grid-helpers.js.

// Show a toast notification by triggering a hidden Dash button
// The button click is bound to a Dash callback that shows a dbc.Toast
if (!window.vdmToast) {
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
}


// Attach a native AG Grid cellClicked listener once the grid API is ready.
// This avoids relying on dashGridOptions "function" plumbing.
// (That indirection doesn't reliably invoke handlers.)
if (!window.vdmAttachModelCellCopyListener) {
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
}

// Attempt to attach immediately for the models grid.
// (The dashboard also has a boot loop that waits for dash_ag_grid.getApi.)
if (window.vdmAttachModelCellCopyListener) {
    window.vdmAttachModelCellCopyListener('vdm-models-grid');
}

// dash-ag-grid expects functions under dashAgGridFunctions (kept for other formatters/comparators)
window.dashAgGridFunctions = window.dashAgGridFunctions || {};

// Helpers are resolved via dashAgGridFunctions when referenced by name in
// valueGetter / tooltipValueGetter / comparator declarations.
window.dashAgGridFunctions.vdmFormatDurationValue = window.vdmFormatDurationValue;
window.dashAgGridFunctions.vdmFormatDurationTooltip = window.vdmFormatDurationTooltip;

// Some dash-ag-grid versions also look under dashAgGridComponentFunctions for components.
window.dashAgGridComponentFunctions = window.dashAgGridComponentFunctions || {};

// Register our custom cell renderers.
// dash-ag-grid resolves string component names via these global maps.
// Use function declarations to avoid const redeclaration when script is loaded multiple times.
// Defer registration with requestAnimationFrame to ensure renderer functions are defined.
(function registerVdmRenderers() {
    // Use a flag to track if we've already scheduled registration
    if (window.__vdmRenderersRegistered) {
        return;
    }

    function doRegistration() {
        const vdmCellRenderers = {
            vdmModelPageLinkRenderer: window.vdmModelPageLinkRenderer,
            vdmModelIdWithIconRenderer: window.vdmModelIdWithIconRenderer,
            vdmProviderBadgeRenderer: window.vdmProviderBadgeRenderer,
            vdmFormattedNumberRenderer: window.vdmFormattedNumberRenderer,
            vdmQualifiedModelRenderer: window.vdmQualifiedModelRenderer,
            vdmRecencyDotRenderer: window.vdmRecencyDotRenderer,
        };

        let registeredCount = 0;
        for (const [name, fn] of Object.entries(vdmCellRenderers)) {
            if (typeof fn !== 'function') {
                // Renderer not yet available, retry later
                return false;
            }
            window.dashAgGridFunctions[name] = fn;
            window.dashAgGridComponentFunctions[name] = fn;

            // Expose as a global for debugging
            window['__' + name] = fn;
            registeredCount++;
        }

        if (registeredCount === Object.keys(vdmCellRenderers).length) {
            window.__vdmRenderersRegistered = true;
            console.info('[vdm] AG Grid renderers registered:', Object.keys(vdmCellRenderers));
            return true;
        }
        return false;
    }

    // Try immediate registration first
    if (doRegistration()) {
        return;
    }

    // Defer with requestAnimationFrame if renderers aren't ready yet
    // This handles the case where dash-ag-grid loads init before renderers
    requestAnimationFrame(function() {
        if (doRegistration()) {
            return;
        }
        // One more retry after a short delay
        setTimeout(function() {
            if (!doRegistration()) {
                console.warn('[vdm] Some renderers failed to register after retries');
            }
        }, 50);
    });
})();

console.info('[vdm] AG Grid init script loaded');

// --- Metrics polling UX helpers ---
// Provide a simple global "user is interacting" flag driven by pointer/focus.
// Dash can read this flag via a lightweight clientside callback.
(function initMetricsUserActiveTracking() {
    if (window.__vdmMetricsUserActiveInit) return;
    window.__vdmMetricsUserActiveInit = true;

    window.__vdm_metrics_user_active = false;
    let idleTimer = null;

    function setActiveTemporarily() {
        window.__vdm_metrics_user_active = true;
        if (idleTimer) {
            clearTimeout(idleTimer);
        }
        idleTimer = setTimeout(function() {
            window.__vdm_metrics_user_active = false;
        }, 1500);
    }

    function attach(containerId) {
        const el = document.getElementById(containerId);
        if (!el || el.__vdmActiveAttached) return;
        el.__vdmActiveAttached = true;

        el.addEventListener('pointermove', setActiveTemporarily, {passive: true});
        el.addEventListener('wheel', setActiveTemporarily, {passive: true});
        el.addEventListener('keydown', setActiveTemporarily, {passive: true});
        el.addEventListener('focusin', setActiveTemporarily, {passive: true});
    }

    // Retry attach because Dash may mount later.
    function boot() {
        attach('vdm-provider-breakdown');
        attach('vdm-model-breakdown');
    }

    boot();
    setTimeout(boot, 250);
    setTimeout(boot, 1000);
})();

window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.vdm_metrics = window.dash_clientside.vdm_metrics || {};

// Return the current value of the active flag.
// Used by dcc.Store polling (see Dash callback wiring).
window.dash_clientside.vdm_metrics.user_active = function(n) {
    return !!window.__vdm_metrics_user_active;
};
