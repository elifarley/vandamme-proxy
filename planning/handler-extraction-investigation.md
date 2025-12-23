# Handler Extraction Investigation

## Problem Summary

Attempted to extract the `/v1/messages` and `/v1/chat/completions` handlers from `src/api/endpoints.py` into separate handler modules (`src/api/handlers/messages.py` and `src/api/handlers/chat_completions.py`). Despite nearly identical implementations and passing unit tests, the extracted handlers cause **Claude Code to fail silently** — the client clears the screen and acts as if nothing happened.

**Current working state**: Commit `e2294d8` uses the legacy functions from `src/api/endpoints.py` through `src/api/routers/v1.py`, which works correctly.

## Timeline of Attempts

### Attempt 1: Original Handler Extraction (commit `6be84af` - tagged `anthropic-passthru-broken`)
- Created `src/api/routers/v1.py` and `src/api/handlers/{messages,chat_completions}.py`
- Handlers imported `validate_api_key` from `src.api.dependencies.py`
- Legacy endpoints remained in `src/api/endpoints.py`
- **Result**: Silent failure for Claude Code

### Attempt 2: Fixed `validate_api_key` Import
- Changed handlers to import `validate_api_key` from `src.api.endpoints` (same as legacy)
- Ensured both used the exact same function object
- **Result**: Still failed

### Attempt 3: Removed Keyword-Only Arguments
- Removed `*,` from handler signatures (was causing `co_kwonlyargcount=3, co_argcount=0`)
- Made signatures match legacy: `co_argcount=3, co_kwonlyargcount=0`
- **Result**: Still failed

### Attempt 4: Removed Wrapper Functions
- Changed `messages_route` from a wrapper that called `handle_messages` to a direct alias: `messages_route = handle_messages`
- Added `Depends(validate_api_key)` directly to `handle_messages` signature
- **Result**: Still failed

### Attempt 5: Used Legacy Functions Through v1 Router (commit `2038e01`)
- `src/api/routers/v1.py` imports and registers `create_message` and `chat_completions` directly from `src/api.endpoints`
- No handler modules involved
- **Result**: **Works correctly**

### Attempt 6: Cleaned Up (commit `e2294d8` - current)
- Removed unused handler modules
- Simplified v1 router
- **Result**: Works correctly

## Root Cause Analysis

### What We Know Works
- `src/api/endpoints.py:create_message` and `chat_completions` — work when called directly
- `src/main.py` → `src/api.routers.v1:router` → legacy functions — works
- All unit tests pass for both implementations

### What We Know Doesn't Work
- Functions with nearly identical code defined in `src/api/handlers/*.py`
- Even when copying the exact same logic, imports, and signatures
- Even with the same `validate_api_key` function

### Key Differences Between Working and Failing Implementations

| Aspect | Working (legacy) | Failing (handlers) |
|--------|------------------|---------------------|
| Module | `src.api.endpoints` | `src.api.handlers.messages` |
| `co_argcount` | 3 | 3 (fixed in attempt 3) |
| `co_kwonlyargcount` | 0 | 0 (fixed in attempt 3) |
| `validate_api_key` | Defined inline in same module | Imported from `src.api.endpoints` |
| `count_tool_calls` | Defined inline | Imported from `src.api.handlers_common` |
| `_is_error_response` | Defined inline | Imported from `src.api.handlers_common` |
| Import chain | Shorter | Longer (depends on handlers_common) |

### Hypotheses

1. **Module Import Order Side Effects**
   - The `src.api.handlers` package or its imports may trigger some state change
   - FastAPI's dependency injection may behave differently based on module-level initialization
   - The `handlers_common` module might have an issue

2. **FastAPI Dependency Resolution**
   - FastAPI may cache or resolve dependencies differently based on the defining module
   - The `Depends(validate_api_key)` might resolve differently when the function is in a different module
   - Import-time decorator evaluation might differ

3. **Closure/Global Namespace Differences**
   - The handler functions close over different global namespaces
   - Even with the same imports, the actual global dict might differ subtly
   - Python's function attribute lookup might behave differently

4. **Request/Response Processing Pipeline**
   - FastAPI's middleware chain might process routes differently based on module
   - The request might be routed to the wrong function
   - Response serialization might fail silently

## Investigation Steps Taken

### 1. Bytecode Comparison
```python
# Both functions have nearly identical bytecode structure
create_message.__code__.co_argcount == handle_messages.__code__.co_argcount  # True
```

### 2. Function Signature Comparison
```python
# Signatures match after removing keyword-only args
inspect.signature(create_message) == inspect.signature(handle_messages)  # Same structure
```

### 3. Dependency Object Comparison
```python
# Both use the same validate_api_key function object
messages_route_dep.dependency is create_message_dep.dependency  # True
```

### 4. Direct Function Call Testing
```python
# TestClient shows both work identically in test environment
# But real Claude Code client fails with handlers
```

## Possible Ways Forward

### Option A: Defer Handler Extraction (Recommended)
- **Pros**: Zero risk, working system remains stable
- **Cons**: Leaves `src/api/endpoints.py` monolithic
- **Action**: Continue with other refactors (dashboard, services), revisit handler extraction later with more debugging tools

### Option B: Binary Search the Implementation
- Copy the legacy function piece by piece into the handler:
  1. Start with exact copy, test
  2. Remove comments, test
  3. Change imports one at a time, test
  4. Move helper functions to separate modules, test
- **Pros**: Would identify the exact line that causes the failure
- **Cons**: Time-consuming, requires many test cycles with real Claude Code

### Option C: Runtime Debugging with Real Traffic
- Add detailed logging at every step of the request flow
- Use Python debugger to trace execution path with real Claude Code requests
- Compare execution traces between working and failing versions
- **Pros**: Would show exactly where execution diverges
- **Cons**: Requires reproducing with real Claude Code, may be noisy

### Option D: FastAPI Internals Investigation
- Inspect FastAPI's route registration and dependency resolution
- Check how `APIRoute` objects are created and stored
- Compare `router.routes` between working and failing versions
- **Pros**: Would reveal if there's a FastAPI-level difference
- **Cons**: Requires understanding FastAPI internals

### Option E: Minimized Reproduction Case
- Create a minimal FastAPI app with just the failing pattern
- Reduce to smallest possible example that still fails
- Report as FastAPI bug if it's a framework issue
- **Pros**: Would isolate whether it's our code or FastAPI
- **Cons**: May not reproduce if it's specific to our setup

### Option F: Accept the Monolith
- Keep `src/api/endpoints.py` as-is
- Focus refactoring efforts on other parts of the codebase
- Revisit handler extraction only if endpoints.py becomes unmanageable
- **Pros**: Pragmatic, zero risk
- **Cons**: Technical debt remains

## Current Recommendation

**Go with Option A (Defer Handler Extraction)** for now because:
1. The v1 router structure provides a clean separation point
2. All other refactoring goals can proceed independently
3. The risk of breaking the critical Anthropic API compatibility is too high
4. We have a working baseline (commit `e2294d8`) that can be returned to at any time

## Future Investigation Checklist

When revisiting this issue:
- [ ] Add request/response logging at FastAPI middleware level
- [ ] Use `pdb` or similar to trace real Claude Code requests
- [ ] Compare FastAPI `APIRoute` objects byte-by-byte
- [ ] Check if there's a module-level `__setattr__` or descriptor interference
- [ ] Test with isolated FastAPI app (minimal reproduction)
- [ ] Report findings to FastAPI project if it's a framework bug

## Files Referenced

- `src/api/endpoints.py` - Working implementations
- `src/api/routers/v1.py` - Router structure (working)
- `src/api/handlers/` - Failed extraction attempts (deleted)
- `tests/unit/test_api_router_registration.py` - Regression test for route registration
- `planning/major-refactor.md` - Original refactor plan

## Related Commits

- `6be84af` - Initial handler extraction (tagged `anthropic-passthru-broken`)
- `2038e01` - v1 router with legacy functions (working baseline)
- `e2294d8` - Cleaned up working state (current)
