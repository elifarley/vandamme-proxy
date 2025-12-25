import pytest

from src.core.metrics import RequestMetrics, create_request_tracker


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recent_traces_and_errors_buffers_capture_completed_requests():
    request_tracker = create_request_tracker(summary_interval=999999)

    await request_tracker.start_request("r1", claude_model="openai:gpt-4o", is_streaming=False)
    await request_tracker.end_request(
        "r1",
        provider="openai",
        openai_model="gpt-4o",
        input_tokens=10,
        output_tokens=20,
    )

    # Regression: metrics should be keyed by the resolved target model (canonical),
    # never by a provider-prefixed alias like "openai:fast".
    await request_tracker.start_request("r_alias", claude_model="openai:fast", is_streaming=False)
    await request_tracker.end_request(
        "r_alias",
        provider="openai",
        openai_model="gpt-4o-mini",
        input_tokens=1,
        output_tokens=1,
    )

    # Extra regression: if a provider-prefixed alias leaks into openai_model on completion,
    # aggregation must not treat it as a nested provider/model.
    await request_tracker.start_request(
        "r_bad_model",
        claude_model="openrouter:cheap",
        is_streaming=False,
        provider="openrouter",
        resolved_model="minimax/minimax-m2",
    )
    await request_tracker.end_request(
        "r_bad_model",
        provider="openrouter",
        openai_model="minimax/minimax-m2",  # Should be the resolved model, not "openrouter:cheap"
        input_tokens=1,
        output_tokens=1,
    )

    # The resolved model name is used as-is (may contain colons legitimately).
    # No defensive stripping happens since openai_model should always be resolved.

    data = await request_tracker.get_running_totals_hierarchical(include_active=False)

    openai_provider = data["providers"]["openai"]
    assert "openai:fast" not in openai_provider["models"]
    assert "fast" not in openai_provider["models"]
    assert "gpt-4o-mini" in openai_provider["models"]
    assert openai_provider["models"]["gpt-4o-mini"]["total"]["requests"] >= 1

    openrouter_provider = data["providers"]["openrouter"]
    assert "openrouter:cheap" not in openrouter_provider["models"]
    assert "minimax/minimax-m2" in openrouter_provider["models"]
    assert openrouter_provider["models"]["minimax/minimax-m2"]["total"]["requests"] >= 1

    # Active requests snapshot should include in-flight requests only.
    active = await request_tracker.get_active_requests_snapshot()
    assert active == []

    await request_tracker.start_request("r2", claude_model="openai:gpt-4o", is_streaming=True)
    await request_tracker.end_request(
        "r2",
        provider="openai",
        openai_model="gpt-4o",
        input_tokens=1,
        output_tokens=2,
        error="boom",
        error_type="UpstreamError",
    )

    traces = await request_tracker.get_recent_traces(limit=10)
    errors = await request_tracker.get_recent_errors(limit=10)

    assert len(traces) >= 2
    assert traces[0]["request_id"] == "r2"
    assert traces[0]["status"] == "error"

    assert len(errors) == 1
    assert errors[0]["request_id"] == "r2"
    assert errors[0]["error_type"] == "UpstreamError"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_running_totals_hierarchical_includes_rollup_models_and_streaming_split():
    """Ensure running totals output is unambiguous and schema-consistent.

    We only assert on the presence/shape of the data structure. End-to-end YAML assertions
    live in integration tests.
    """
    request_tracker = create_request_tracker(summary_interval=999999)

    # Simulate one completed request by directly constructing ProviderModelMetrics
    pm = request_tracker.summary_metrics.provider_model_metrics["openai:gpt-4o"]
    pm.total_requests = 2
    pm.total_input_tokens = 10
    pm.total_output_tokens = 20
    pm.total_cache_read_tokens = 1
    pm.total_cache_creation_tokens = 2
    pm.total_tool_uses = 3
    pm.total_tool_results = 4
    pm.total_tool_calls = 5
    pm.total_errors = 1
    pm.total_duration_ms = 100.0

    pm.streaming_requests = 1
    pm.streaming_input_tokens = 7
    pm.streaming_output_tokens = 14
    pm.streaming_cache_read_tokens = 1
    pm.streaming_cache_creation_tokens = 2
    pm.streaming_tool_uses = 1
    pm.streaming_tool_results = 2
    pm.streaming_tool_calls = 3
    pm.streaming_errors = 1
    pm.streaming_duration_ms = 60.0

    pm.non_streaming_requests = 1
    pm.non_streaming_input_tokens = 3
    pm.non_streaming_output_tokens = 6
    pm.non_streaming_cache_read_tokens = 0
    pm.non_streaming_cache_creation_tokens = 0
    pm.non_streaming_tool_uses = 2
    pm.non_streaming_tool_results = 2
    pm.non_streaming_tool_calls = 2
    pm.non_streaming_errors = 0
    pm.non_streaming_duration_ms = 40.0

    data = await request_tracker.get_running_totals_hierarchical()

    assert "providers" in data
    assert "openai" in data["providers"]

    provider = data["providers"]["openai"]
    assert "rollup" in provider
    assert "models" in provider

    rollup = provider["rollup"]
    assert set(rollup.keys()) == {"total", "streaming", "non_streaming"}

    for section in ("total", "streaming", "non_streaming"):
        totals = rollup[section]
        assert "requests" in totals
        assert "errors" in totals
        assert "input_tokens" in totals
        assert "output_tokens" in totals
        assert "cache_read_tokens" in totals
        assert "cache_creation_tokens" in totals
        assert "tool_uses" in totals
        assert "tool_results" in totals
        assert "tool_calls" in totals
        assert "average_duration_ms" in totals
        assert "total_duration_ms" in totals

    assert "gpt-4o" in provider["models"]

    model_entry = provider["models"]["gpt-4o"]
    assert set(model_entry.keys()) >= {"total", "streaming", "non_streaming"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_running_totals_active_request_contributes_to_rollup_and_model():
    request_tracker = create_request_tracker(summary_interval=999999)

    metrics = RequestMetrics(
        request_id="r1",
        start_time=0.0,
        claude_model="gpt-4o",
        is_streaming=True,
        provider="openai",
        input_tokens=11,
        output_tokens=22,
        cache_read_tokens=3,
        cache_creation_tokens=4,
        tool_use_count=1,
        tool_result_count=2,
        tool_call_count=3,
    )
    request_tracker.active_requests["r1"] = metrics

    data = await request_tracker.get_running_totals_hierarchical()
    provider = data["providers"]["openai"]

    assert provider["rollup"]["total"]["requests"] == 1
    assert provider["rollup"]["streaming"]["requests"] == 1
    assert provider["rollup"]["non_streaming"]["requests"] == 0

    model = provider["models"]["gpt-4o"]
    assert model["total"]["requests"] == 1
    assert model["streaming"]["requests"] == 1
    assert model["non_streaming"]["requests"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hierarchical_metrics_preserves_provider_for_models_with_colons():
    """Test that model names with multiple colons preserve the correct provider.

    Regression test for: https://github.com/user/vandamme-proxy/issues/XXX

    When a model name contains colons (e.g., OpenRouter models like
    "openrouter:anthropic/claude-3-5-sonnet:context-flash"), the hierarchical
    metrics should:
    1. Extract the provider from the first colon ("openrouter")
    2. Keep the full model name including any remaining colons
    3. NOT incorrectly reassign the provider from the model portion

    Bug was at tracker.py:298-299 where `provider, model = model.split(":", 1)`
    incorrectly reassigned the provider variable.
    """
    request_tracker = create_request_tracker(summary_interval=999999)

    # Simulate a request with a model name containing colons
    # The format is: provider:model_name:variant
    # Where "model_name:variant" is the actual model identifier
    await request_tracker.start_request(
        "r1",
        claude_model="openrouter:anthropic/claude-3-5-sonnet:context-flash",
        is_streaming=False,
    )
    await request_tracker.end_request(
        "r1",
        provider="openrouter",
        # Already resolved, no provider prefix. Model name contains colon legitimately.
        openai_model="anthropic/claude-3-5-sonnet:context-flash",
        input_tokens=100,
        output_tokens=200,
    )

    data = await request_tracker.get_running_totals_hierarchical(include_active=False)

    # The provider should be "openrouter", NOT "anthropic"
    assert "openrouter" in data["providers"]
    assert "anthropic" not in data["providers"]

    openrouter_provider = data["providers"]["openrouter"]
    assert "models" in openrouter_provider

    # The model name should preserve the colons (it's already resolved)
    expected_model = "anthropic/claude-3-5-sonnet:context-flash"
    assert expected_model in openrouter_provider["models"]
    assert openrouter_provider["models"][expected_model]["total"]["requests"] == 1

    # Verify the model is stored without the provider prefix (it's just the model name)
    assert (
        "openrouter:anthropic/claude-3-5-sonnet:context-flash" not in openrouter_provider["models"]
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_alias_target_with_colon_is_preserved_in_metrics():
    """Test that alias targets containing colons are preserved in metrics.

    Regression test for user scenario:
    - Alias "free" → "kwaipilot/kat-coder-pro:free"
    - The resolved model name should be stored as-is, not truncated.

    Bug was in SummaryMetrics.add_request where it stripped any prefix from openai_model,
    breaking legitimate model names that contain colons.
    """
    request_tracker = create_request_tracker(summary_interval=999999)

    # User requests model "openrouter:free" which is an alias
    # The alias resolves to "kwaipilot/kat-coder-pro:free"
    await request_tracker.start_request(
        "r1",
        claude_model="openrouter:free",
        is_streaming=False,
    )
    await request_tracker.end_request(
        "r1",
        provider="openrouter",
        openai_model="kwaipilot/kat-coder-pro:free",  # Resolved model from alias
        input_tokens=100,
        output_tokens=200,
    )

    data = await request_tracker.get_running_totals_hierarchical(include_active=False)

    # Should be under openrouter provider
    assert "openrouter" in data["providers"]
    openrouter_provider = data["providers"]["openrouter"]
    assert "models" in openrouter_provider

    # The full resolved model name should be preserved, including the colon
    expected_model = "kwaipilot/kat-coder-pro:free"
    assert expected_model in openrouter_provider["models"]
    assert openrouter_provider["models"][expected_model]["total"]["requests"] == 1

    # Should NOT be truncated to just "free"
    assert "free" not in openrouter_provider["models"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_active_requests_snapshot_preserves_colons_in_resolved_model():
    """Test that active requests snapshot preserves colons in resolved model names.

    Regression for Active Requests grid "resolved" column showing truncated names
    (e.g., "free" instead of "kwaipilot/kat-coder-pro:free").

    Bug was in get_active_requests_snapshot where resolved_model_stripped was
    created by splitting on ":" and taking the second part, breaking legitimate
    model names containing colons. The field has been removed - resolved_model
    is now used directly since it already contains the canonical model name.
    """
    request_tracker = create_request_tracker(summary_interval=999999)

    # Start an active request with a model name containing colons
    await request_tracker.start_request(
        "r1",
        claude_model="openrouter:free",  # User requests via alias
        is_streaming=True,
    )

    # Simulate that the alias resolved to a model with colons
    metrics = request_tracker.active_requests.get("r1")
    assert metrics is not None
    metrics.provider = "openrouter"
    metrics.openai_model = "kwaipilot/kat-coder-pro:free"  # Resolved model

    # Get the snapshot
    snapshot = await request_tracker.get_active_requests_snapshot()
    assert len(snapshot) == 1

    row = snapshot[0]

    # The resolved_model field should preserve the full model name
    assert row["resolved_model"] == "kwaipilot/kat-coder-pro:free"

    # The "model" field shows what the user requested (with provider prefix stripped)
    assert row["model"] == "free"
    assert row["requested_model"] == "openrouter:free"
    assert row["provider"] == "openrouter"

    # Clean up
    await request_tracker.end_request(
        "r1",
        provider="openrouter",
        openai_model="kwaipilot/kat-coder-pro:free",
        input_tokens=0,
        output_tokens=0,
    )
