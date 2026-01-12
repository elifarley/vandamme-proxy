"""Unit tests for streaming converter cancellation handling and SSE error emission."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.conversion.response_converter import convert_openai_streaming_to_claude
from src.models.claude import ClaudeMessage, ClaudeMessagesRequest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancellation_emits_sse_error_and_skips_final_events() -> None:
    """When client disconnects mid-stream, SSE error is emitted and final events are skipped."""
    # Mock stream that yields one chunk before disconnection
    openai_lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": "Hello"}}]}) + "\n",
    ]

    async def _gen():
        for line in openai_lines:
            yield line

    original_request = ClaudeMessagesRequest(
        model="openai:gpt-4",
        max_tokens=10,
        messages=[ClaudeMessage(role="user", content="hi")],
    )

    # Mock cancellation checker that returns True (disconnected)
    mock_http_request = MagicMock()
    mock_http_request.is_disconnected = AsyncMock(return_value=True)

    mock_openai_client = MagicMock()
    mock_openai_client.cancel_request = MagicMock()

    mock_logger = MagicMock()

    # Fake metrics object
    metrics = MagicMock()
    metrics.error = None
    metrics.error_type = None

    # Patch get_request_tracker to return a mock tracker with async get_request
    mock_tracker = MagicMock()
    mock_tracker.get_request = AsyncMock(return_value=None)

    with patch("src.conversion.response_converter.get_request_tracker", return_value=mock_tracker):
        # Collect all emitted SSE events
        events = []
        async for chunk in convert_openai_streaming_to_claude(
            _gen(),
            original_request,
            logger=mock_logger,
            http_request=mock_http_request,
            openai_client=mock_openai_client,
            request_id="test-req-123",
            metrics=metrics,
        ):
            events.append(chunk)

    # Verify cancellation was detected
    mock_openai_client.cancel_request.assert_called_once_with("test-req-123")

    # Verify SSE error event was emitted
    error_events = [e for e in events if "event: error" in e]
    assert len(error_events) == 1, f"Expected exactly one error event, got {len(error_events)}"
    error_data = json.loads(error_events[0].split("data: ")[1].split("\n")[0])
    assert error_data["error"]["type"] == "cancelled"
    assert error_data["error"]["message"] == "Request was cancelled by client"

    # Verify metrics were updated
    assert metrics.error == "Request cancelled by client"
    assert metrics.error_type == "cancelled"

    # Verify final events were NOT sent (no message_stop)
    assert not any("message_stop" in e for e in events), (
        "Final events should be skipped on cancellation"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancellation_without_metrics() -> None:
    """Cancellation works correctly when metrics is None."""
    openai_lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": "Hello"}}]}) + "\n",
    ]

    async def _gen():
        for line in openai_lines:
            yield line

    original_request = ClaudeMessagesRequest(
        model="openai:gpt-4",
        max_tokens=10,
        messages=[ClaudeMessage(role="user", content="hi")],
    )

    mock_http_request = MagicMock()
    mock_http_request.is_disconnected = AsyncMock(return_value=True)

    mock_openai_client = MagicMock()
    mock_openai_client.cancel_request = MagicMock()

    mock_logger = MagicMock()

    mock_tracker = MagicMock()
    mock_tracker.get_request = AsyncMock(return_value=None)

    with patch("src.conversion.response_converter.get_request_tracker", return_value=mock_tracker):
        events = []
        async for chunk in convert_openai_streaming_to_claude(
            _gen(),
            original_request,
            logger=mock_logger,
            http_request=mock_http_request,
            openai_client=mock_openai_client,
            request_id="test-req-456",
            metrics=None,  # No metrics
        ):
            events.append(chunk)

    # Should still emit error and handle gracefully
    error_events = [e for e in events if "event: error" in e]
    assert len(error_events) == 1
    assert not any("message_stop" in e for e in events)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancellation_with_unknown_request_id() -> None:
    """When request_id is None, cancellation checker is not created, stream completes normally."""
    openai_lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": "Hello"}}]}) + "\n",
        "data: " + json.dumps({"choices": [{"finish_reason": "stop", "delta": {}}]}) + "\n",
        "data: [DONE]\n",
    ]

    async def _gen():
        for line in openai_lines:
            yield line

    original_request = ClaudeMessagesRequest(
        model="openai:gpt-4",
        max_tokens=10,
        messages=[ClaudeMessage(role="user", content="hi")],
    )

    mock_http_request = MagicMock()
    mock_http_request.is_disconnected = AsyncMock(return_value=True)

    mock_openai_client = MagicMock()

    mock_tracker = MagicMock()
    mock_tracker.get_request = AsyncMock(return_value=None)

    with patch("src.conversion.response_converter.get_request_tracker", return_value=mock_tracker):
        events = []
        async for chunk in convert_openai_streaming_to_claude(
            _gen(),
            original_request,
            logger=MagicMock(),  # Capture logger call
            http_request=mock_http_request,
            openai_client=mock_openai_client,
            request_id=None,  # No request ID - cancellation checker not created
            metrics=None,
        ):
            events.append(chunk)

    # No cancellation without request_id - stream completes normally
    assert not any("event: error" in e for e in events)
    # Final events should still be sent
    assert any("message_stop" in e for e in events)
    # cancel_request should NOT be called (no request_id)
    mock_openai_client.cancel_request.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_normal_completion_without_cancellation() -> None:
    """Normal stream completion sends final events (no cancellation)."""
    openai_lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": "Hello"}}]}) + "\n",
        "data: " + json.dumps({"choices": [{"finish_reason": "stop", "delta": {}}]}) + "\n",
        "data: [DONE]\n",
    ]

    async def _gen():
        for line in openai_lines:
            yield line

    original_request = ClaudeMessagesRequest(
        model="openai:gpt-4",
        max_tokens=10,
        messages=[ClaudeMessage(role="user", content="hi")],
    )

    mock_http_request = MagicMock()
    mock_http_request.is_disconnected = AsyncMock(return_value=False)

    mock_openai_client = MagicMock()

    mock_tracker = MagicMock()
    mock_tracker.get_request = AsyncMock(return_value=None)

    with patch("src.conversion.response_converter.get_request_tracker", return_value=mock_tracker):
        events = []
        async for chunk in convert_openai_streaming_to_claude(
            _gen(),
            original_request,
            logger=None,
            http_request=mock_http_request,
            openai_client=mock_openai_client,
            request_id="test-req-normal",
            metrics=None,
        ):
            events.append(chunk)

    # No error event for normal completion
    assert not any("event: error" in e for e in events)

    # Final events should be sent
    assert any("message_stop" in e for e in events), (
        "Final events should be sent on normal completion"
    )

    # cancel_request should NOT be called
    mock_openai_client.cancel_request.assert_not_called()
