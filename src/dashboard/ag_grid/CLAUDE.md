# src/dashboard/ag_grid — Claude Code Guidance

This directory is the **shared AG Grid subsystem** for the Dash dashboard.

## Goals
- **DRY**: prefer extending the shared grid stack rather than creating one-off grids.
- **No blink / no jitter**: preserve the existing renderer registration + stable IDs patterns.
- **Separation of concerns**:
  - **Factories** define consistent defaults.
  - **Transformers** shape API payloads into AG Grid `rowData`.
  - **Assets JS** implements renderers/UX helpers.

## Key modules & responsibilities
- `factories.py`
  - Owns shared `build_ag_grid(...)` defaults (theme, pagination, locale, gridOptions).
  - Any new grid should call `build_ag_grid` rather than instantiate `dag.AgGrid` directly.

- `transformers.py`
  - **Single source of truth** for `rowData` shaping.
  - Emit both:
    - **raw numeric fields** for sorting/filtering (`*_raw`, epoch ms, etc.)
    - **display fields** for renderers/valueGetters (formatted strings)
  - Prefer adding new transformer functions over embedding shaping logic in callbacks/pages.

- `scripts.py`
  - Keeps dash-ag-grid clientside callback wiring minimal (often empty strings) while assets JS does real work.

## Asset JS contract (anti-blink)
Renderer functions must be registered in the guarded init pipeline:
- `assets/ag_grid/10-vdm-grid-renderers.js` — renderers and shared CSS injection
- `assets/ag_grid/20-vdm-grid-helpers.js` — valueGetter/tooltip helpers
- `assets/ag_grid/30-vdm-grid-init.js` — **guarded registration** + optional lightweight tickers

**Rule:** if you add a new renderer (e.g., `vdmFooRenderer`), it must be:
1) defined on `window.*` in `10-vdm-grid-renderers.js`
2) registered in `30-vdm-grid-init.js` in the same guarded map as existing renderers

This avoids cells rendering blank ("blink") due to race conditions.

## Patterns to follow
### 1) Add a new grid
- Add a thin builder in `src/dashboard/components/ag_grid.py`:
  - define columnDefs
  - call transformer to get rowData
  - call `build_ag_grid(...)`

### 2) Sorting & formatting
- **Sorting correctness:** sort on raw values.
  - Prefer `field: "*_raw"` for numeric sorting.
  - Use `valueGetter` to format display.

### 3) Time fields
- Provide epoch ms (`*_epoch_ms`) once.
- Prefer client-side ticking only when it improves UX materially.
- If you tick, throttle and pause on `document.visibilityState === 'hidden'`.

## Testing
- Run repo-level targets (don’t run tools directly):
  - `make pre-commit`
  - `make test`

## Do not
- Don’t duplicate renderer registration logic in new files.
- Don’t add new polling loops unless strictly necessary.
- Don’t compute rowData in callbacks; put it in transformers.
