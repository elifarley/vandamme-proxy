"""Runtime helpers for metrics ownership.

This module intentionally contains *only* wiring helpers (no import-time side
effects). It exists so API layers can retrieve the process-local RequestTracker
instance without importing an application module or relying on a global
singleton.

Invariants:
- The tracker is created once at app startup and stored on `app.state`.
- Endpoints access it via `request.app.state.request_tracker`.
"""

from __future__ import annotations

from fastapi import Request

from .tracker.tracker import RequestTracker


def get_request_tracker(request: Request) -> RequestTracker:
    """Return the RequestTracker instance owned by the FastAPI app."""

    tracker = getattr(request.app.state, "request_tracker", None)
    if tracker is None:
        raise RuntimeError("RequestTracker is not configured on app.state")
    if not isinstance(tracker, RequestTracker):
        raise TypeError("app.state.request_tracker is not a RequestTracker")
    return tracker
