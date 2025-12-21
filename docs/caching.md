# Caching System

Vandamme Proxy uses a small, explicit caching layer to reduce repeated upstream calls and to make the dashboard/CLI feel “instant” when data is already known.

This document is intentionally **both operator-facing and developer-facing**:
- **Operators**: where cache files live, how TTL works, and how to disable caching.
- **Developers**: architecture, cache key design, schema/versioning, and how to add new cached endpoints/providers.

---

## Goals (Why we cache)

1. **Performance**: avoid calling upstream endpoints (especially `/models`) on every request.
2. **Determinism**: cached payloads are persisted on disk, so the proxy can start “warm”.
3. **Extensibility**: support caching **multiple endpoints** across **multiple providers** without collisions.

Non-goals:
- This cache is **not** a distributed cache.
- This cache is **not** a general-purpose memoization framework.

---

## High-level Architecture

### Disk JSON cache base

The core abstraction is `DiskJsonCache`:
- File: `src/core/cache/disk.py`
- Responsibilities:
  - TTL freshness checks (`last_updated` timestamp)
  - Schema version validation (`schema_version`)
  - Atomic writes (`.json.tmp` → rename)
  - Small, explicit error handling (invalid/corrupt cache simply behaves like a cache miss)

This design keeps caching logic consistent across endpoints.

### Provider/endpoint hierarchy

All disk caches are organized as:

```
~/.cache/vandamme-proxy/
  <endpoint-namespace>/
    <provider-name>/
      <cache-file>.json
```

Why this structure?
- We expect to cache **multiple endpoints** (e.g., top-models, models, future metadata).
- We expect to talk to **multiple providers** (e.g., openrouter, poe, openai, custom).
- This prevents collisions and keeps cache inspection/debugging simple.

---

## Cache Locations and File Layout

### Top Models (proxy metadata)

Top-models caching persists the result fetched from the remote source (currently OpenRouter).

- Namespace: `top-models`
- Provider: `openrouter`
- File:

```
~/.cache/vandamme-proxy/top-models/openrouter/api.json
```

Implementation:
- `src/top_models/cache.py` (`TopModelsDiskCache`)

#### Legacy migration

Older versions used a single flat cache file:

```
~/.cache/vandamme-proxy/top-models.json
```

On next read, the cache layer will:
1. Detect the legacy file
2. Migrate its contents into the hierarchical path
3. Delete the legacy file (to avoid ambiguity)

### `/v1/models` (provider model listing)

The `/v1/models` endpoint can query upstream `/models`. Those results are cached per provider configuration.

- Namespace: `models`
- Provider: `<provider-name>` (e.g., `openai`, `openrouter`, `poe`)
- File pattern:

```
~/.cache/vandamme-proxy/models/<provider>/models-<fingerprint>.json
```

Implementation:
- `src/models/cache.py` (`ModelsDiskCache`)
- Integrated into `/v1/models` in `src/api/endpoints.py`

---

## Configuration (Operator-facing)

### Top Models cache

- `TOP_MODELS_CACHE_DIR` (default: `~/.cache/vandamme-proxy`)
- `TOP_MODELS_CACHE_TTL_DAYS` (default: `2`)

### Models cache

- `MODELS_CACHE_ENABLED` (default: `true`)
- `MODELS_CACHE_TTL_HOURS` (default: `1`)

Notes:
- The models cache uses the same base cache directory as `TOP_MODELS_CACHE_DIR` today.
- TTLs are intentionally different:
  - top-models changes less frequently (days)
  - `/models` can change more frequently (hours)

---

## Cache Key / Fingerprinting (Developer-facing)

### Why we need a fingerprint

For `/v1/models`, the returned model list can vary by:
- provider name
- base URL (custom endpoints)
- custom headers (some deployments inject extra upstream headers)

So, we generate a **deterministic fingerprint** and include it in the filename.

### Fingerprint inputs

For `ModelsDiskCache`, the fingerprint includes:
- `provider`
- `base_url`
- `custom_headers` (sorted)

This avoids collisions while keeping the file paths stable.

---

## Schema Versioning

Every cache file includes:
- `schema_version`: integer
- `last_updated`: ISO8601 UTC timestamp

The base cache reader treats mismatched schema versions as cache misses.

This makes cache format changes safe:
- update code
- bump schema version
- stale cache is ignored and naturally re-built

---

## Atomic Writes & Corruption Safety

All cache writes are done atomically:
1. Write JSON to a temporary path: `*.json.tmp`
2. Rename/replace the real cache file

If a crash occurs mid-write:
- the temp file may remain
- the real cache file is never partially written

This protects correctness while keeping the implementation minimal.

---

## Test Isolation

The caching layer is designed to keep tests deterministic:
- For unit/integration tests, disk caches can be bypassed by using a cache path containing `testserver`.

Why?
- Tests commonly mock upstream HTTP responses and expect the mocked payload to be used.
- Reading developer machine caches would introduce nondeterminism.

---

## How to Add Caching for a New Endpoint (Developer guide)

When adding caching for a new endpoint/provider, follow this approach:

1. **Create a new cache class** extending `DiskJsonCache`.
   - Choose a namespace name that matches the endpoint group (e.g., `metrics`, `providers`, `capabilities`).
2. **Define a stable path** using:
   - endpoint namespace
   - provider name
   - a filename that encodes the endpoint and a fingerprint of parameters
3. **Cache the raw upstream payload** when possible.
   - This reduces re-serialization bugs and makes cache files inspectable.
4. **Add tests** for:
   - cache hits/misses
   - schema mismatch behavior
   - TTL expiration
   - atomic write behavior

Suggested checklist:
- [ ] Cache directory and file naming is deterministic and collision-free
- [ ] TTL is configurable
- [ ] Schema version is explicit
- [ ] Tests do not depend on developer machine caches

---

## Troubleshooting

### “I’m not seeing cache files”

- Confirm the proxy has made at least one request to the cached endpoint.
- Ensure `MODELS_CACHE_ENABLED=true` (for `/v1/models`).
- Check the directory:
  - `TOP_MODELS_CACHE_DIR` (default: `~/.cache/vandamme-proxy`)

### “My cache seems stale”

- Reduce TTL (e.g., `MODELS_CACHE_TTL_HOURS=1`) or delete the specific cache file.
- If the schema changes, old caches are ignored automatically.

### “Different providers are interfering with each other”

They shouldn’t:
- cache paths are segregated by provider
- `/v1/models` is further segregated by fingerprinted provider configuration

If this occurs, it likely indicates:
- multiple providers are configured with the same name
- or a provider name is being normalized unexpectedly

---

## References

Key files:
- `src/core/cache/disk.py`
- `src/top_models/cache.py`
- `src/models/cache.py`
- `src/api/endpoints.py`
