// Vandamme Dashboard - Active Requests recency/duration updates
//
// Goals:
// - Active Requests "Duration" column uses the shared vdmRecencyDotRenderer for the dot UI.
// - But the *text* should display request duration (e.g., "12s", "3m 04s"), not "Xs ago".
// - Update the duration text at a slow cadence (default 2s), configurable via UI.
//
// This is intentionally separate from the global recency ticker to avoid changing the
// semantics of "Last" columns across the rest of the dashboard.

(function initActiveRequestsDurationTicker() {
    if (window.__vdmActiveRequestsDurationTickerInit) return;
    window.__vdmActiveRequestsDurationTickerInit = true;

    const GRID_ID = 'vdm-metrics-active-requests-grid';
    const STORAGE_KEY = 'vdm.metrics.activeRequests.durationTickMs';
    const DEFAULT_TICK_MS = 2000;

    // Use performance.now() for smooth elapsed time, and anchor it to epoch.
    const epochOffsetMs = Date.now() - performance.now();

    function getTickMs() {
        // 1) Prefer explicit setting from UI control (stored on window)
        const ui = window.__vdm_active_requests_duration_tick_ms;
        if (Number.isFinite(ui) && ui >= 250) return ui;

        // 2) LocalStorage fallback
        try {
            const raw = window.localStorage ? localStorage.getItem(STORAGE_KEY) : null;
            const n = Number(raw);
            if (Number.isFinite(n) && n >= 250) return n;
        } catch (e) {
            // ignore
        }

        return DEFAULT_TICK_MS;
    }

    function updateGridDurations(nowEpochMs, root) {
        if (!root) return;
        // Only touch duration cells: we tag them with a dedicated class via columnDef.
        const wraps = root.querySelectorAll('.vdm-active-req-duration .vdm-recency-wrap');
        if (!wraps.length) return;

        for (const wrap of wraps) {
            const dot = wrap.querySelector('.vdm-recency-dot');
            const textEl = wrap.querySelector('.vdm-recency-text');
            if (!dot || !textEl) continue;

            const startTimeStr = dot.getAttribute('data-vdm-recency-epoch-ms') || '';
            const startTime = Number(startTimeStr);
            if (!Number.isFinite(startTime) || startTime <= 0) continue;

            // Active Requests stores request start as epoch-seconds, not ms.
            const startEpochMs = startTime < 1e12 ? (startTime * 1000) : startTime;
            const ms = Math.max(0, nowEpochMs - startEpochMs);
            if (typeof window.vdmFormatDurationValue !== 'function') continue;

            const nextText = window.vdmFormatDurationValue(ms);
            if (textEl.textContent !== nextText) {
                textEl.textContent = nextText;
            }
        }
    }

    let lastTickPerfMs = 0;

    function tick(nowPerfMs) {
        if (document.visibilityState === 'hidden') {
            requestAnimationFrame(tick);
            return;
        }

        const root = document.getElementById(GRID_ID);
        if (!root) {
            requestAnimationFrame(tick);
            return;
        }

        const tickMs = getTickMs();
        if ((nowPerfMs - lastTickPerfMs) < tickMs) {
            requestAnimationFrame(tick);
            return;
        }
        lastTickPerfMs = nowPerfMs;

        const nowEpochMs = epochOffsetMs + nowPerfMs;
        updateGridDurations(nowEpochMs, root);

        requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
})();
