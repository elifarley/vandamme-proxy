from __future__ import annotations

import pytest


@pytest.mark.unit
def test_v1_routes_present() -> None:
    """Regression test: ensure v1 routes register (import-cycle detector).

    The broken split attempt (tagged `anthropic-passthru-broken`) likely failed via
    circular imports / partial initialization, which can silently break clients.

    This test forces route wiring to be import-safe and explicit.
    """

    from src.api.endpoints import router

    paths = {getattr(r, "path", None) for r in router.routes}

    assert "/v1/messages" in paths
    assert "/v1/chat/completions" in paths
    assert "/v1/models" in paths
    assert "/v1/messages/count_tokens" in paths
