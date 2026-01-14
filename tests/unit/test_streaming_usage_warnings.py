"""Unit tests for streaming usage warning handling.

This module tests that usage parsing errors in streaming responses are:
1. Logged as warnings (not errors)
2. Tracked in metrics.error for visibility
3. Do NOT set metrics.error_type (to avoid counting as errors)
4. Do NOT break the stream (stream continues)
"""

from unittest.mock import MagicMock

import pytest

from src.conversion.response_converter import convert_openai_streaming_to_claude
from src.core.metrics.models.request import RequestMetrics
from src.models.claude import ClaudeMessage, ClaudeMessagesRequest

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def claude_request():
    """Standard Claude messages request."""
    return ClaudeMessagesRequest(
        model="gpt-4",
        max_tokens=100,
        messages=[ClaudeMessage(role="user", content="Hello")],
    )


@pytest.fixture
def mock_metrics():
    """Mock RequestMetrics object."""
    return RequestMetrics(
        request_id="test-123",
        start_time=1234567890.0,
        claude_model="gpt-4",
        is_streaming=True,
    )


# =============================================================================
# Usage Warning Tests
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_usage_malformed_data_stream_continues(claude_request):
    """Test that malformed usage data doesn't break the stream."""

    # Stream with malformed usage field (string instead of dict)
    async def mock_stream():
        yield 'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":" world"}}],"usage":"invalid_string"}\n\n'
        yield "data: [DONE]\n\n"

    result_chunks = []
    async for chunk in convert_openai_streaming_to_claude(
        mock_stream(),
        claude_request,
        MagicMock(),
        metrics=None,  # No metrics to verify stream works without them
    ):
        result_chunks.append(chunk)

    # Stream should continue and produce output
    body = "".join(result_chunks)
    assert "Hello" in body or "world" in body


@pytest.mark.unit
@pytest.mark.asyncio
async def test_usage_warning_recorded_in_metrics(claude_request, mock_metrics):
    """Test that usage warnings are recorded in metrics.error."""

    # Stream with malformed usage field
    async def mock_stream():
        yield 'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
        # Malformed usage: string instead of dict
        yield 'data: {"choices":[{"delta":{"content":" there"}}],"usage":"bad_data"}\n\n'
        yield "data: [DONE]\n\n"

    result_chunks = []
    async for chunk in convert_openai_streaming_to_claude(
        mock_stream(),
        claude_request,
        MagicMock(),
        metrics=mock_metrics,
    ):
        result_chunks.append(chunk)

    # Stream should complete
    body = "".join(result_chunks)
    assert "Hi" in body or "there" in body

    # Warning should be recorded in metrics.error
    assert mock_metrics.error is not None
    assert "Usage accounting error" in mock_metrics.error
    # error_type should NOT be set (so it doesn't count as error)
    assert mock_metrics.error_type is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_usage_warning_appends_to_existing_error(claude_request):
    """Test that usage warnings append to existing error field."""
    # Start with an existing error
    metrics = RequestMetrics(
        request_id="test-456",
        start_time=1234567890.0,
        claude_model="gpt-4",
        is_streaming=True,
        error="Previous error",
    )

    async def mock_stream():
        yield 'data: {"choices":[{"delta":{"content":"Test"}}]}\n\n'
        # Invalid: int not dict
        yield 'data: {"choices":[{"delta":{"content":"ing"}}],"usage":123}\n\n'
        yield "data: [DONE]\n\n"

    result_chunks = []
    async for chunk in convert_openai_streaming_to_claude(
        mock_stream(),
        claude_request,
        MagicMock(),
        metrics=metrics,
    ):
        result_chunks.append(chunk)

    # Both errors should be present
    assert metrics.error is not None
    assert "Previous error" in metrics.error
    assert "Usage accounting error" in metrics.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multiple_usage_warnings_aggregated(claude_request, mock_metrics):
    """Test that multiple usage warnings are aggregated."""

    async def mock_stream():
        yield 'data: {"choices":[{"delta":{"content":"A"}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"B"}}],"usage":"err1"}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"C"}}],"usage":"err2"}\n\n'
        yield "data: [DONE]\n\n"

    result_chunks = []
    async for chunk in convert_openai_streaming_to_claude(
        mock_stream(),
        claude_request,
        MagicMock(),
        metrics=mock_metrics,
    ):
        result_chunks.append(chunk)

    # Should have aggregated warnings
    assert mock_metrics.error is not None
    assert "Usage accounting error" in mock_metrics.error
    # Multiple chunks with errors are tracked (last one wins or appends)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_usage_missing_fields_stream_continues(claude_request):
    """Test that missing usage fields don't break the stream."""

    async def mock_stream():
        yield 'data: {"choices":[{"delta":{"content":"Response"}}]}\n\n'
        # Missing usage field entirely - should not cause issues
        yield 'data: {"choices":[{"delta":{"content":" complete"}}]}\n\n'
        yield "data: [DONE]\n\n"

    result_chunks = []
    async for chunk in convert_openai_streaming_to_claude(
        mock_stream(),
        claude_request,
        MagicMock(),
        metrics=None,
    ):
        result_chunks.append(chunk)

    body = "".join(result_chunks)
    assert "Response" in body or "complete" in body


@pytest.mark.unit
@pytest.mark.asyncio
async def test_usage_null_value_stream_continues(claude_request, mock_metrics):
    """Test that null usage values are handled gracefully."""

    async def mock_stream():
        yield 'data: {"choices":[{"delta":{"content":"Test"}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"ing"}}],"usage":null}\n\n'
        yield "data: [DONE]\n\n"

    result_chunks = []
    async for chunk in convert_openai_streaming_to_claude(
        mock_stream(),
        claude_request,
        MagicMock(),
        metrics=mock_metrics,
    ):
        result_chunks.append(chunk)

    # Stream should complete successfully
    body = "".join(result_chunks)
    assert "Test" in body or "ing" in body


@pytest.mark.unit
@pytest.mark.asyncio
async def test_usage_valid_json_stream_works(claude_request, mock_metrics):
    """Test that valid usage data works correctly."""

    async def mock_stream():
        yield 'data: {"choices":[{"delta":{"content":"OK"}}]}\n\n'
        # Valid usage data (must be on single line for proper SSE parsing)
        yield (
            'data: {"choices":[{"finish_reason":"stop"}],'
            '"usage":{"prompt_tokens":10,"completion_tokens":5}}\n\n'
        )
        yield "data: [DONE]\n\n"

    result_chunks = []
    async for chunk in convert_openai_streaming_to_claude(
        mock_stream(),
        claude_request,
        MagicMock(),
        metrics=mock_metrics,
    ):
        result_chunks.append(chunk)

    # Should have no warnings
    # Note: metrics.error might still be None
    assert "OK" in "".join(result_chunks)

    # Token counts should be updated
    assert mock_metrics.input_tokens == 10 or mock_metrics.output_tokens == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversion_error_yields_sse_error(claude_request, mock_metrics):
    """Test that ConversionError is yielded as SSE error (not raised)."""

    async def mock_stream():
        yield 'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
        yield "data: invalid json\n\n"  # Will cause SSEParseError (ConversionError subclass)

    result_chunks = []
    async for chunk in convert_openai_streaming_to_claude(
        mock_stream(),
        claude_request,
        MagicMock(),
        metrics=mock_metrics,
    ):
        result_chunks.append(chunk)

    # Error should be yielded as SSE event, not raised
    body = "".join(result_chunks)
    assert "error" in body.lower()
    # Metrics should be updated with error
    assert mock_metrics.error is not None
    assert mock_metrics.error_type is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_usage_error_without_metrics(claude_request):
    """Test that usage errors don't crash when metrics is None."""

    async def mock_stream():
        yield 'data: {"choices":[{"delta":{"content":"Test"}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"ing"}}],"usage":"bad"}\n\n'
        yield "data: [DONE]\n\n"

    result_chunks = []
    # Should not raise even with metrics=None
    async for chunk in convert_openai_streaming_to_claude(
        mock_stream(),
        claude_request,
        MagicMock(),
        metrics=None,  # No metrics
    ):
        result_chunks.append(chunk)

    # Stream should complete
    assert "Test" in "".join(result_chunks) or "ing" in "".join(result_chunks)
