# Refactor plan: API endpoints + Dashboard + AG Grid (incremental, aggressive moves)

## Goals (as requested)
- Improve modularity, testability, maintainability, debuggability, correctness, and code elegance.
- Refactor incrementally across all three large areas:
  - `src/api/endpoints.py` (~1414 LOC)
  - `src/dashboard/app.py` (~1307 LOC) + `src/dashboard/pages.py` (~1208 LOC)
  - `src/dashboard/components/ag_grid.py` (~1564 LOC)
- Add **targeted unit tests** for extracted logic.
- Behavior changes are allowed, but we’ll keep the refactor **risk-controlled** by preserving the externally-visible contract for the API and dashboard routes unless we explicitly decide otherwise.

## Key observations (from exploration)
### 1) `src/api/endpoints.py`
- One file mixes:
  - provider/model resolution and passthrough vs conversion decisions
  - API key rotation (`_next_provider_key` defined in multiple branches)
  - streaming vs non-streaming orchestration
  - middleware integration
  - metrics + conversation logging
  - error normalization
- Duplication hotspots: provider context setup, SSE response headers/wrappers, middleware invocation patterns, and error handling.

### 2) Dashboard (`src/dashboard/app.py` + `src/dashboard/pages.py`)
- `app.py` contains most callbacks and repeats the pattern: fetch → try/except → `dbc.Alert` fallback.
- `pages.py` contains many large layout functions and duplicated table-building logic (e.g., provider/model breakdown tables).
- Natural seams: **services** (fetch + normalization), **view-models/presenters** (compose UI fragments), **components** (reusable cards/tables/layout helpers).

### 3) `src/dashboard/components/ag_grid.py`
- Mixes:
  - pure Python data transformers (row-data builders)
  - grid configuration (column defs, theme CSS, options)
  - a very large embedded JS string (`CELL_RENDERER_SCRIPTS`) doing DOM/window manipulation
- Easy wins: extract pure transformers + provider-color mapping; consolidate repeated grid factory options; externalize JS.

---

## Target structure (recommended)
Aggressive moves are OK. The objective is to shrink each “god file” into a thin orchestrator that wires together small, testable units.

### A) API
```
src/api/
  routers/                 # Thin FastAPI route declarations
    v1.py
  handlers/                # HTTP-facing orchestration only
    chat_completions.py
    messages.py
    models.py
    health.py
    aliases.py
    top_models.py
  services/                # Business logic (testable without FastAPI)
    provider_context.py
    key_rotation.py
    streaming.py
    middleware.py
    metrics.py
    errors.py
    models_cache.py
```

### B) Dashboard
```
src/dashboard/
  app.py                   # routing + callback wiring (thinned)
  pages/                   # page layout functions only
    overview.py
    metrics.py
    models.py
    top_models.py
    aliases.py
    logs.py
    token_counter.py
  services/                # fetch + normalize
    overview.py
    metrics.py
    models.py
    top_models.py
    aliases.py
    logs.py
    token_counter.py
  components/              # reusable UI fragments
    cards.py
    tables.py
    layout.py
  ag_grid/                 # AG Grid specific
    transformers.py
    factories.py
    scripts.py
    grids.py
```

---

## Execution plan (incremental steps)

### Step 0 — Add seams without changing behavior
**Goal:** Create new modules with functions that are initially called from existing code.
- No big rewrites yet; just extract + delegate.

### Step 1 — API: extract provider context + key rotation
**Files involved:**
- Modify: `src/api/endpoints.py`
- Add: `src/api/services/provider_context.py`, `src/api/services/key_rotation.py`

**What moves/extracts:**
- Centralize the repeated `_next_provider_key(exclude)` logic into a single function/class.
- Centralize provider/model resolution and passthrough validation into `ProviderContext`.

**Unit tests:**
- `tests/api/test_key_rotation.py`: verify rotation/exhaustion semantics.

### Step 2 — API: extract streaming response builder
**Files involved:**
- Modify: `src/api/endpoints.py`
- Add: `src/api/services/streaming.py`

**What moves/extracts:**
- SSE headers construction and StreamingResponse setup.
- Ensure metric finalization happens on normal completion and on cancellation.

**Unit tests:**
- `tests/api/test_streaming_wrappers.py`: streaming generator wrapper ensures cleanup/finalize.

### Step 3 — API: split `endpoints.py` into routers + handlers
**Files involved:**
- Modify: `src/api/endpoints.py` (reduce to imports / router wiring or replace with `routers/v1.py`)
- Add: `src/api/routers/v1.py`, `src/api/handlers/messages.py`, `src/api/handlers/chat_completions.py`, etc.

**What changes:**
- Keep endpoint paths and request/response schemas the same.
- Handlers call services (provider_context/streaming/middleware/metrics/errors).

**Unit tests:**
- Focus on services, plus 1–2 integration tests hitting FastAPI route for `/v1/messages` and `/v1/chat/completions` using RESPX fixtures.

### Step 4 — AG Grid: extract pure transformers + grid factories
**Files involved:**
- Modify: `src/dashboard/components/ag_grid.py`
- Add: `src/dashboard/ag_grid/transformers.py`, `src/dashboard/ag_grid/factories.py`, `src/dashboard/ag_grid/grids.py`

**What moves/extracts (examples):**
- Pure functions from `ag_grid.py`:
  - `format_model_page_url`, `_safe_http_url`, `_extract_model_icon_url`, `models_row_data`
  - `logs_errors_row_data`, `logs_traces_row_data`
- Provider badge color mapping becomes a shared helper.
- Consolidate repeated grid options into factory functions.

**Unit tests:**
- `tests/dashboard/test_ag_grid_transformers.py`: data-driven tests for row-data output.

### Step 5 — AG Grid: externalize JS scripts
**Files involved:**
- Modify: `src/dashboard/components/ag_grid.py` or `src/dashboard/ag_grid/scripts.py`
- Add static asset or a dedicated module containing the JS string(s).

**What changes:**
- Move `CELL_RENDERER_SCRIPTS` out of the big component file.
- Expose a single `register_grid_helpers()` JS entrypoint (still embedded if Dash requires it), to reduce global `window.*` scatter.

**Unit tests:**
- Minimal (JS unit tests optional); main benefit is maintainability.

### Step 6 — Dashboard: split pages + introduce services
**Files involved:**
- Modify: `src/dashboard/app.py`, `src/dashboard/pages.py`
- Add: `src/dashboard/pages/*.py`, `src/dashboard/services/*.py`, `src/dashboard/components/*.py`

**What moves/extracts:**
- Move each layout function into its page module.
- Move fetch/normalize/error-handling patterns into services:
  - e.g., `services/models.py` returns already-normalized row data + “view state” (empty, disabled, error).
- Move duplicated table construction into components:
  - e.g., unify provider/model breakdown table builder currently duplicated in `pages.py`.

**Unit tests:**
- Services tested with mocked data sources; components tested as pure functions returning Dash components.

---

## Safety/validation checklist (throughout)
- Use existing Make targets to validate at each step:
  - `make lint`
  - `make type-check`
  - `make test-unit`
  - `make test` (periodically)
- Keep changes small per step: extract + delegate + tests; only then move files.

---

## Critical files (will be modified)
- `src/api/endpoints.py`
- `src/dashboard/app.py`
- `src/dashboard/pages.py`
- `src/dashboard/components/ag_grid.py`

## New files (planned)
- `src/api/services/{provider_context,key_rotation,streaming,errors,metrics,middleware}.py`
- `src/api/handlers/*.py`, `src/api/routers/v1.py`
- `src/dashboard/ag_grid/{transformers,factories,scripts,grids}.py`
- `src/dashboard/services/*.py`, `src/dashboard/pages/*.py`, `src/dashboard/components/*.py`
