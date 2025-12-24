# CLAUDE.md — `src/dashboard/pages`

This package defines **Dash page layouts**.

The goal: pages should be **pure composition** (structure, IDs, layout) and remain boring to change.
All behavior and data work must live elsewhere.

---

## 0) One-sentence rule

**Pages declare what exists; they do not decide what it means.**

---

## 1) Responsibilities (HARD rules)

### ✅ Pages MAY do

- Declare layout: `dbc.Container`, `dbc.Row/Col`, `dbc.Card`, headers, footers.
- Declare client-side state containers: `dcc.Store`, `dcc.Interval`, `dcc.Location`.
- Declare **component IDs** (the contract used by `src/dashboard/callbacks/*`).
- Choose spacing/breakpoints and visual hierarchy.

### ❌ Pages MUST NOT do

- Fetch data, call HTTP endpoints, or read the filesystem.
- Parse / normalize API payloads.
- Contain business logic (token math, error rate computations, provider/model rollups).
- Build AG Grid columnDefs/rowData shaping.

**Expected flow**

```
pages/* (layout) → callbacks/* (wiring) → services/* (view composition)
→ data_sources.py (HTTP) → normalize.py / ag_grid/transformers.py (shaping)
```

---

## 2) ID contracts (HARD rules)

- IDs in `pages/*` are public contracts for `callbacks/*`. Treat them like API.
- Prefer stable, explicit IDs.
- If you must rename an ID, do it holistically (layout + callbacks + services) in one change.

### Naming conventions

- Page-scoped: `vdm-<page>-<thing>` (e.g. `vdm-metrics-refresh`).
- Shared/global: `vdm-<thing>` only if truly global (e.g. `vdm-global-error`).

---

## 3) DRY directives for tables/grids

### 3.1 AG Grid: reuse the shared ecosystem

If a page needs a grid/table:

- ✅ Use a thin builder in `src/dashboard/components/ag_grid.py`.
- ✅ Shape rowData in `src/dashboard/ag_grid/transformers.py`.
- ✅ Use the shared factory `src/dashboard/ag_grid/factories.py:build_ag_grid`.
- ✅ Reuse JS assets under `assets/ag_grid/*`.

- ❌ Don’t inline new AG Grid configuration in `pages/*`.
- ❌ Don’t invent a new renderer registration mechanism.

### 3.2 No “blink” regressions

AG Grid renderers must be registered via the guarded init pattern in:
- `assets/ag_grid/30-vdm-grid-init.js`

If you add a new renderer:
- ✅ register it there
- ✅ make it idempotent
- ✅ ensure it fails gracefully when dependencies aren’t loaded yet

### 3.3 Avoid DOM fights

Dash + AG Grid may re-render cells. Manual DOM mutation inside a cell can be overwritten.

- ✅ If something must update frequently, implement it as:
  - a renderer that derives from stable rowData, and/or
  - an intentional client-side ticker that operates on stable hooks (class names / data attrs) and is resilient to re-renders.
- ❌ Don’t patch cell DOM ad-hoc.

---

## 4) UX principles for dashboard pages

- Prefer in-place interaction (sorting/filtering in-grid) over separate filter forms.
- Put the primary triage signal first (often **recency** / “Last”).
- Default polling must not cause jitter:
  - pause while the user interacts
  - pause while the tab is hidden
- Reduce vertical footprint with intentional pagination defaults.

---

## 5) Golden patterns (Rules + examples)

### Pattern A: “Layout-only page”

**Do (in `pages/*`)**

```py
# pages/foo.py
return dbc.Container(
  [
    dbc.Row([...]),
    dbc.Row([dbc.Col(dbc.Spinner(id="vdm-foo-grid"), md=12)]),
    dcc.Interval(id="vdm-foo-poll", interval=5000, n_intervals=0),
  ],
  fluid=True,
)
```

**Don’t (in `pages/*`)**

```py
# ❌ don’t fetch data or compute metrics here
payload = httpx.get(...)
rows = expensive_transform(payload)
```

### Pattern B: “Manual refresh affordance”

If polling exists, users still benefit from an explicit refresh button.

- Add a button in the toolbar: `id="vdm-<page>-refresh"`.
- Wire it as an additional `Input` to the page refresh callback.

### Pattern C: “Recency UI”

If you show a relative time (“5s ago”), keep it accurate and low-overhead:

- Prefer shipping `epoch_ms` once (server) and compute age in the browser.
- Throttle:
  - dot color ~10fps
  - text ~1fps
- Pause when tab is hidden (`document.visibilityState === 'hidden'`).
- Use **one** tooltip mechanism (native `title` OR AG Grid tooltipField, not both).

---

## 6) Testing expectations

### Required

- `make pre-commit`
- `make test`

### Manual smoke checklist

- Open the page, check console for errors.
- Verify AG Grid renderers appear without “blink”.
- Verify tooltips are not duplicated.
- Verify polling/refresh ergonomics and that live UI tickers pause when the tab is hidden.
