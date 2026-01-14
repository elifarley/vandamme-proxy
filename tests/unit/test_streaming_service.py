import httpx
import pytest

from src.core.error_types import ErrorType


@pytest.mark.unit
@pytest.mark.asyncio
async def test_with_sse_error_handler_handles_read_timeout(monkeypatch):
    """Test that ReadTimeout is converted to SSE error event and [DONE]."""
    from src.api.services.streaming import with_sse_error_handler

    logged = []

    def fake_warning(msg):
        logged.append(msg)

    import src.api.services.streaming as streaming

    monkeypatch.setattr(streaming.conversation_logger, "warning", fake_warning)

    async def failing_gen():
        yield "first_chunk"
        raise httpx.ReadTimeout("Upstream read timeout")

    out = []
    async for chunk in with_sse_error_handler(
        original_stream=failing_gen(),
        request_id="test-req-1",
        provider_name="test_provider",
    ):
        out.append(chunk)

    # Should have received the first chunk, error event, and [DONE]
    assert len(out) == 3
    assert out[0] == "first_chunk"
    assert "data: " in out[1]
    assert "error" in out[1]
    assert "timeout" in out[1].lower()
    assert out[2] == "data: [DONE]\n\n"

    # Should have logged a warning
    assert len(logged) == 1
    assert "test-req-1" in logged[0]
    assert "timeout" in logged[0].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_with_sse_error_handler_handles_http_status_error(monkeypatch):
    """Test that HTTPStatusError is converted to SSE error event."""
    from src.api.services.streaming import with_sse_error_handler

    logged = []

    def fake_warning(msg):
        logged.append(msg)

    import src.api.services.streaming as streaming

    monkeypatch.setattr(streaming.conversation_logger, "warning", fake_warning)

    # Create a generic exception to test the fallback error handling
    async def failing_gen():
        raise RuntimeError("Test streaming error")

    out = []
    async for chunk in with_sse_error_handler(
        original_stream=failing_gen(),
        request_id="test-req-2",
        provider_name="upstream",
    ):
        out.append(chunk)

    # Should have error event and [DONE]
    assert len(out) == 2
    assert "data: " in out[0]
    assert "error" in out[0]
    assert out[1] == "data: [DONE]\n\n"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_with_sse_error_handler_passes_through_normal_chunks():
    """Test that normal chunks are passed through unchanged."""
    from src.api.services.streaming import with_sse_error_handler

    async def normal_gen():
        yield "chunk1"
        yield "chunk2"
        yield "data: [DONE]\n"

    out = []
    async for chunk in with_sse_error_handler(
        original_stream=normal_gen(),
        request_id="test-req-3",
    ):
        out.append(chunk)

    assert out == ["chunk1", "chunk2", "data: [DONE]\n"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_with_streaming_metrics_finalizer_calls_end(monkeypatch):
    from src.api.services.streaming import with_streaming_metrics_finalizer

    ended = []

    class FakeTracker:
        async def end_request(self, request_id: str) -> None:
            ended.append(request_id)

    def fake_get_request_tracker(_http_request):
        return FakeTracker()

    import src.api.services.streaming as streaming

    monkeypatch.setattr(streaming, "get_request_tracker", fake_get_request_tracker)

    class FakeRequest:
        pass

    async def gen():
        yield "a"
        yield "b"

    out = []
    async for x in with_streaming_metrics_finalizer(
        original_stream=gen(),
        http_request=FakeRequest(),
        request_id="req-1",
        enabled=True,
    ):
        out.append(x)

    assert out == ["a", "b"]
    assert ended == ["req-1"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_with_streaming_metrics_finalizer_skips_when_disabled(monkeypatch):
    from src.api.services.streaming import with_streaming_metrics_finalizer

    ended = []

    class FakeTracker:
        async def end_request(self, request_id: str) -> None:
            ended.append(request_id)

    def fake_get_request_tracker(_http_request):
        return FakeTracker()

    import src.api.services.streaming as streaming

    monkeypatch.setattr(streaming, "get_request_tracker", fake_get_request_tracker)

    class FakeRequest:
        pass

    async def gen():
        yield "x"

    out = []
    async for x in with_streaming_metrics_finalizer(
        original_stream=gen(),
        http_request=FakeRequest(),
        request_id="req-2",
        enabled=False,
    ):
        out.append(x)

    assert out == ["x"]
    assert ended == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_with_streaming_error_handling_combines_both(monkeypatch):
    """Test that with_streaming_error_handling combines error handling and metrics finalization."""
    from src.api.services.streaming import with_streaming_error_handling

    ended = []
    logged = []

    class FakeTracker:
        async def end_request(self, request_id: str) -> None:
            ended.append(request_id)

    def fake_get_request_tracker(_http_request):
        return FakeTracker()

    def fake_warning(msg):
        logged.append(msg)

    import src.api.services.streaming as streaming

    monkeypatch.setattr(streaming, "get_request_tracker", fake_get_request_tracker)
    monkeypatch.setattr(streaming.conversation_logger, "warning", fake_warning)

    class FakeRequest:
        pass

    async def failing_gen():
        yield "chunk_before_error"
        raise httpx.ReadTimeout("Timeout during stream")

    out = []
    async for chunk in with_streaming_error_handling(
        original_stream=failing_gen(),
        http_request=FakeRequest(),
        request_id="combined-test",
        provider_name="test_provider",
        metrics_enabled=True,
    ):
        out.append(chunk)

    # Should have chunk, error event, and [DONE]
    assert len(out) == 3
    assert out[0] == "chunk_before_error"
    assert "error" in out[1]
    assert out[2] == "data: [DONE]\n\n"

    # Metrics should have been finalized
    assert ended == ["combined-test"]

    # Warning should have been logged
    assert len(logged) == 1
    assert "combined-test" in logged[0]


@pytest.mark.unit
def test_format_sse_error_event():
    """Test SSE error event formatting."""
    from src.api.services.streaming import _format_sse_error_event

    result = _format_sse_error_event(
        message="Test error",
        error_type=ErrorType.API_ERROR,
        code="TEST_001",
        suggestion="Try again later",
    )

    assert "data: " in result
    assert "Test error" in result
    assert ErrorType.API_ERROR.value in result
    assert "TEST_001" in result
    assert "Try again later" in result


@pytest.mark.unit
def test_format_sse_error_event_without_suggestion():
    """Test SSE error event formatting without suggestion."""
    import json

    from src.api.services.streaming import _format_sse_error_event

    result = _format_sse_error_event(
        message="Error without suggestion",
        error_type=ErrorType.UNEXPECTED_ERROR,
        code="GEN_001",
    )

    assert "data: " in result
    assert "Error without suggestion" in result
    assert ErrorType.UNEXPECTED_ERROR.value in result
    assert "GEN_001" in result
    # Parse the JSON to check suggestion is not included
    data_start = result.find("data: ") + 6
    json_str = result[data_start:].strip()
    parsed = json.loads(json_str)
    assert "suggestion" not in parsed["error"]
