"""src.core.metrics

Request metrics tracking.

Key ideas:
- Metrics are **application state**, not a global module singleton.
- The runtime owner is the FastAPI app (see `app.state.request_tracker`).
- Tests should prefer `create_request_tracker()` to avoid shared mutable state.

This package provides:
- data models for request metrics
- a tracker that aggregates metrics across requests
- pure helper functions for rollups and hierarchical reporting
"""

from __future__ import annotations

from .models.request import RequestMetrics
from .tracker.factory import create_request_tracker
from .tracker.tracker import RequestTracker

__all__ = ["RequestMetrics", "RequestTracker", "create_request_tracker"]
