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

    data = await request_tracker.get_running_totals_hierarchical()
    openai_provider = data["providers"]["openai"]
    assert "openai:fast" not in openai_provider["models"]
    assert "fast" not in openai_provider["models"]
    assert "gpt-4o-mini" in openai_provider["models"]
    assert openai_provider["models"]["gpt-4o-mini"]["total"]["requests"] >= 1

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
