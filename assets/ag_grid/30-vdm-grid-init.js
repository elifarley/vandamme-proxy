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
        attach('vdm-metrics-providers-grid');
        attach('vdm-metrics-models-grid');
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


// --- Metrics live recency updates ---
// Update dot color at ~10fps and relative text at ~1fps without server fetches.
(function initMetricsRecencyTicker() {
    if (window.__vdmMetricsRecencyTickerInit) return;
    window.__vdmMetricsRecencyTickerInit = true;

    const GRID_CONTAINER_IDS = ['vdm-metrics-providers-grid', 'vdm-metrics-models-grid', 'vdm-metrics-active-requests-grid'];
    const OVERVIEW_LAST_ACTIVITY_ID = 'vdm-overview-last-activity';
    const OVERVIEW_ANCHOR_ID = 'vdm-refresh-now';
    const OVERVIEW_FALLBACK_WRAP_SELECTOR = '.vdm-recency-wrap';
    const OVERVIEW_FALLBACK_SCOPE_SELECTOR = '#vdm-page';

    function getOverviewWrap() {
        const byId = document.getElementById(OVERVIEW_LAST_ACTIVITY_ID);
        if (byId) return byId;

        // Fallback for older Overview layouts: if we're on the Overview page and
        // there is exactly one recency wrap in the page, treat it as Last activity.
        if (!document.getElementById(OVERVIEW_ANCHOR_ID)) return null;
        const scope = document.querySelector(OVERVIEW_FALLBACK_SCOPE_SELECTOR) || document;
        const wraps = scope.querySelectorAll(OVERVIEW_FALLBACK_WRAP_SELECTOR);
        if (wraps.length === 1) return wraps[0];
        return null;
    }

    // Use performance.now() for smooth elapsed time, and anchor it to epoch.
    // This avoids calling Date.now() in hot loops.
    const epochOffsetMs = Date.now() - performance.now();

    let lastDotTickMs = 0;
    let lastTextTickMs = 0;

    function withinMetricsOrOverview() {
        // Run if Metrics grids exist or the Overview last-activity KPI exists.
        if (getOverviewWrap()) return true;
        return GRID_CONTAINER_IDS.some((id) => document.getElementById(id));
    }

    // Minimal run-time cost: only tick when there is at least one target wrap.
    function anyRecencyTargetsPresent() {
        if (getOverviewWrap()) return true;
        for (const containerId of GRID_CONTAINER_IDS) {
            const root = document.getElementById(containerId);
            if (!root) continue;
            if (root.querySelector('.vdm-recency-wrap')) return true;
        }
        return false;
    }

    function getEpochAndAge(dot) {
        const epochMsStr = dot.getAttribute('data-vdm-recency-epoch-ms')
            || dot.style.getPropertyValue('--vdm-recency-epoch-ms')
            || '';
        const ageAtRenderStr = dot.getAttribute('data-vdm-recency-age-at-render')
            || dot.style.getPropertyValue('--vdm-recency-age-at-render')
            || '3600';

        return {
            epochMs: Number(epochMsStr),
            ageAtRender: Number(ageAtRenderStr),
        };
    }

    function updateWrap(wrap, nowEpochMs, nowPerfMs, doDot, doText) {
        if (!wrap) return;
        const dot = wrap.querySelector('.vdm-recency-dot');
        if (!dot) return;

        const { epochMs, ageAtRender } = getEpochAndAge(dot);
        if (!isFinite(ageAtRender)) return;

        const ageSeconds = (isFinite(epochMs) && epochMs > 0)
            ? Math.max(0, (nowEpochMs - epochMs) / 1000)
            : ageAtRender + (nowPerfMs / 1000);

        if (doDot && typeof window.vdmRecencyColorRgb === 'function') {
            const rgb = window.vdmRecencyColorRgb(ageSeconds);
            const next = `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
            if (dot.style.backgroundColor !== next) {
                dot.style.backgroundColor = next;
            }
        }

        if (doText && typeof window.vdmRecencyText === 'function') {
            const textEl = wrap.querySelector('.vdm-recency-text');
            if (!textEl) return;

            // Active Requests Duration column is special: it reuses the recency dot
            // renderer for the dot UI, but the text is updated by a dedicated ticker
            // to show duration (no "ago").
            if (wrap.closest('.vdm-active-req-duration')) return;

            const nextText = window.vdmRecencyText(ageSeconds);
            if (textEl.textContent !== nextText) {
                textEl.textContent = nextText;
            }
        }
    }

    function updateMetricsTargets(nowEpochMs, nowPerfMs, doDot, doText) {
        for (const containerId of GRID_CONTAINER_IDS) {
            const root = document.getElementById(containerId);
            if (!root) continue;
            const wraps = root.querySelectorAll('.vdm-recency-wrap');
            for (const wrap of wraps) {
                updateWrap(wrap, nowEpochMs, nowPerfMs, doDot, doText);
            }
        }
    }

    function updateOverviewTarget(nowEpochMs, nowPerfMs, doDot, doText) {
        const overviewWrap = getOverviewWrap();
        if (overviewWrap) {
            updateWrap(overviewWrap, nowEpochMs, nowPerfMs, doDot, doText);
        }
    }

    function tick(nowPerfMs) {
        if (document.visibilityState === 'hidden') {
            // Avoid doing any work while the tab is hidden.
            requestAnimationFrame(tick);
            return;
        }

        if (!withinMetricsOrOverview()) {
            requestAnimationFrame(tick);
            return;
        }

        if (!anyRecencyTargetsPresent()) {
            requestAnimationFrame(tick);
            return;
        }

        // Fast path: if helpers aren't available, don't do work.
        if (typeof window.vdmRecencyColorRgb !== 'function' || typeof window.vdmRecencyText !== 'function') {
            requestAnimationFrame(tick);
            return;
        }

        // Compute epoch time once per tick.
        const nowEpochMs = epochOffsetMs + nowPerfMs;

        // Throttle dot updates (~10fps) and text updates (~1fps)
        const doDot = (nowPerfMs - lastDotTickMs) >= 100;
        const doText = (nowPerfMs - lastTextTickMs) >= 1000;

        if (!doDot && !doText) {
            requestAnimationFrame(tick);
            return;
        }

        if (doDot) lastDotTickMs = nowPerfMs;
        if (doText) lastTextTickMs = nowPerfMs;

        updateMetricsTargets(nowEpochMs, nowPerfMs, doDot, doText);
        updateOverviewTarget(nowEpochMs, nowPerfMs, doDot, doText);

        requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
})();
