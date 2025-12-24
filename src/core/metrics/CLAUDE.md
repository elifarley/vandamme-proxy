# src/core/metrics — Claude Code Guidance

This package implements **request/usage metrics** collection and aggregation for Vandamme Proxy.

## Goals
- **Correctness first**: metrics must not distort counts/durations.
- **Low overhead**: metrics should be cheap on the hot path.
- **Deterministic aggregation**: rollups should be stable and easy to reason about.

## Architecture (high level)
- `tracker/`
  - Captures per-request lifecycle events.
  - Produces per-request measurements (duration, tokens, tool calls, status).

- `calculations/`
  - Pure(ish) functions that aggregate per-request events into rollups.
  - Key files:
    - `calculations/hierarchical.py` — builds the provider→model hierarchy and final schema.
    - `calculations/accumulation.py` — defines accumulator keys (requests, errors, tokens, total_duration_ms, etc.).
    - `calculations/duration.py` — computes `average_duration_ms` from `total_duration_ms`.

- `models/`
  - Typed structures representing internal metrics payloads.

## Data contract (running totals)
The `/metrics/running-totals` output is hierarchical and includes:
- top-level totals (requests/errors/tokens/tool_calls)
- `total_duration_ms` and `average_duration_ms`
- `providers[provider].rollup.{total,streaming,non_streaming}`
- `providers[provider].models[model].{total,streaming,non_streaming}`

**Rule:** keep `total_duration_ms` as the sum of per-request durations (NOT wall time).

## Contribution patterns
### Adding a new metric field
1) Add the field to the accumulator template in `calculations/accumulation.py`.
2) Ensure per-request tracking populates the field in `tracker/`.
3) Thread it through hierarchical rollups in `calculations/hierarchical.py`.
4) If the field needs derived values (like averages), compute it in a dedicated calculation module.

### Be careful with time
- Use monotonic timing for per-request measurement where possible.
- Normalize output timestamps consistently.
- If a timestamp string is naive (no timezone), treat it as local time consistently across UI formatting.

## Testing
Use repo targets:
- `make pre-commit`
- `make test` (unit + integration)

When adding metrics:
- Add/extend unit tests around `calculations/*` and tracker behavior.
- Ensure schemas in integration tests still match expected keys.

## Do not
- Don’t add expensive per-request processing.
- Don’t duplicate aggregation logic in API handlers.
- Don’t change output schema casually (it is consumed by the dashboard normalizers/transformers).
