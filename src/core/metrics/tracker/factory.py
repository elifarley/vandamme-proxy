"""Factory for RequestTracker.

Why a factory:
- keeps tests isolated (fresh tracker per test)
- keeps app initialization explicit (FastAPI owns the instance)
"""

from __future__ import annotations

import os

from .tracker import RequestTracker


def create_request_tracker(*, summary_interval: int | None = None) -> RequestTracker:
    """Create a new RequestTracker instance.

    Args:
        summary_interval:
            Number of completed requests between summary log emissions.
            Defaults to env var LOG_SUMMARY_INTERVAL (or 100).

    Returns:
        A new RequestTracker.
    """

    if summary_interval is None:
        summary_interval = int(os.environ.get("LOG_SUMMARY_INTERVAL", "100"))

    return RequestTracker(summary_interval=summary_interval)
