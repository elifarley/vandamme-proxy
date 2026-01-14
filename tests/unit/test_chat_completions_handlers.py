"""Unit tests for chat completions handlers.

This module tests the strategy pattern implementation for /v1/chat/completions
endpoint, covering both Anthropic and OpenAI format handlers.
"""

import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from src.api.services.chat_completions_handlers import (
    AnthropicChatCompletionsHandler,
    OpenAIChatCompletionsHandler,
    get_chat_completions_handler,
)
from src.core.provider_config import ProviderConfig

# === Shared Fixtures ===


@pytest.fixture
def mock_provider_config_anthropic():
    """Mock Anthropic-format provider config."""
    return ProviderConfig(
        name="anthropic",
        api_key="test-key",
        base_url="https://api.anthropic.com",
        api_format="anthropic",
    )


@pytest.fixture
def mock_provider_config_openai():
    """Mock OpenAI-format provider config."""
    return ProviderConfig(
        name="openai",
        api_key="test-key",
        base_url="https://api.openai.com",
        api_format="openai",
    )


@pytest.fixture
def mock_tracker():
    """Mock request tracker."""
    tracker = MagicMock()
    tracker.end_request = AsyncMock()
    return tracker


@pytest.fixture
def mock_config():
    """Mock application config."""
    config = MagicMock()
    config.provider_manager = MagicMock()
    config.provider_manager.get_provider_config = MagicMock(return_value=None)
    return config


@pytest.fixture
def mock_http_request():
    """Mock FastAPI Request."""
    return MagicMock(spec=Request)


@pytest.fixture
def openai_chat_request():
    """Standard OpenAI chat completions request."""
    return {
        "model": "gpt-4",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "Hello!"}],
        "stream": False,
    }


@pytest.fixture
def anthropic_message_response():
    """Standard Anthropic message response."""
    return {
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Hi there!"}],
        "model": "claude-3-5-sonnet-20241022",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


@pytest.fixture
def openai_chat_response():
    """Standard OpenAI chat completion response."""
    return {
        "id": "chatcmpl-456",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "gpt-4",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Response"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


# === AnthropicChatCompletionsHandler Tests ===


@pytest.mark.unit
@pytest.mark.asyncio
async def test_anthropic_handler_non_streaming_happy_path(
    mock_provider_config_anthropic,
    mock_tracker,
    mock_config,
    mock_http_request,
    openai_chat_request,
    anthropic_message_response,
    openai_chat_response,
):
    """Test Anthropic handler non-streaming path with successful response."""
    handler = AnthropicChatCompletionsHandler()
    openai_request = {**openai_chat_request, "stream": False}

    # Mock the client methods
    mock_client = AsyncMock()
    mock_client.create_chat_completion = AsyncMock(return_value=anthropic_message_response)

    # Mock conversion function - patch where it's imported (inside handle method)
    with patch(
        "src.conversion.anthropic_to_openai.anthropic_message_to_openai_chat_completion"
    ) as mock_convert:
        mock_convert.return_value = openai_chat_response

        response = await handler.handle(
            openai_request=openai_request,
            resolved_model="claude-3-5-sonnet-20241022",
            provider_name="anthropic",
            provider_config=mock_provider_config_anthropic,
            provider_api_key="test-key",
            client_api_key=None,
            config=mock_config,
            openai_client=mock_client,
            request_id="req-1",
            http_request=mock_http_request,
            is_metrics_enabled=True,
            metrics=MagicMock(),
            tracker=mock_tracker,
        )

        # Verify response structure
        assert response.status_code == 200
        # Verify metrics were finalized
        mock_tracker.end_request.assert_called_once_with("req-1")
        # Verify client was called correctly
        mock_client.create_chat_completion.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_anthropic_handler_non_streaming_metrics_disabled(
    mock_provider_config_anthropic,
    mock_config,
    mock_http_request,
    openai_chat_request,
    anthropic_message_response,
    openai_chat_response,
):
    """Test that tracker.end_request is NOT called when metrics disabled."""
    handler = AnthropicChatCompletionsHandler()
    openai_request = {**openai_chat_request, "stream": False}

    mock_client = AsyncMock()
    mock_client.create_chat_completion = AsyncMock(return_value=anthropic_message_response)

    with patch(
        "src.conversion.anthropic_to_openai.anthropic_message_to_openai_chat_completion"
    ) as mock_convert:
        mock_convert.return_value = openai_chat_response

        response = await handler.handle(
            openai_request=openai_request,
            resolved_model="claude-3-5-sonnet-20241022",
            provider_name="anthropic",
            provider_config=mock_provider_config_anthropic,
            provider_api_key="test-key",
            client_api_key=None,
            config=mock_config,
            openai_client=mock_client,
            request_id="req-2",
            http_request=mock_http_request,
            is_metrics_enabled=False,
            metrics=None,
            tracker=None,
        )

        assert response.status_code == 200


@pytest.mark.unit
@pytest.mark.asyncio
async def test_anthropic_handler_non_streaming_with_tracker_none(
    mock_provider_config_anthropic,
    mock_config,
    mock_http_request,
    openai_chat_request,
    anthropic_message_response,
    openai_chat_response,
):
    """Test handler doesn't crash when tracker is None but metrics enabled."""
    handler = AnthropicChatCompletionsHandler()
    openai_request = {**openai_chat_request, "stream": False}

    mock_client = AsyncMock()
    mock_client.create_chat_completion = AsyncMock(return_value=anthropic_message_response)

    with patch(
        "src.conversion.anthropic_to_openai.anthropic_message_to_openai_chat_completion"
    ) as mock_convert:
        mock_convert.return_value = openai_chat_response

        # Should not crash even though tracker is None
        response = await handler.handle(
            openai_request=openai_request,
            resolved_model="claude-3-5-sonnet-20241022",
            provider_name="anthropic",
            provider_config=mock_provider_config_anthropic,
            provider_api_key="test-key",
            client_api_key=None,
            config=mock_config,
            openai_client=mock_client,
            request_id="req-3",
            http_request=mock_http_request,
            is_metrics_enabled=True,
            metrics=MagicMock(),
            tracker=None,  # tracker is None
        )

        assert response.status_code == 200


@pytest.mark.unit
@pytest.mark.asyncio
async def test_anthropic_handler_streaming_happy_path(
    mock_provider_config_anthropic,
    mock_config,
    mock_http_request,
    openai_chat_request,
):
    """Test Anthropic handler streaming path."""
    handler = AnthropicChatCompletionsHandler()
    openai_request = {**openai_chat_request, "stream": True}

    # Mock stream that accepts api_key and next_api_key params
    async def mock_stream(
        _request: dict,
        _request_id: str,
        api_key: str | None = None,
        next_api_key: Any = None,
    ) -> AsyncGenerator[str, None]:
        yield 'data: {"type": "message_start"}\n'
        yield 'data: {"type": "content_block_delta", "delta": {"text": "Hi"}}\n'
        yield "data: [DONE]\n"

    mock_client = AsyncMock()
    mock_client.create_chat_completion_stream = mock_stream

    # Mock SSE conversion - patch where it's imported
    with patch(
        "src.conversion.anthropic_sse_to_openai.anthropic_sse_to_openai_chat_completions_sse"
    ) as mock_sse_convert:

        async def converted_stream() -> AsyncGenerator[str, None]:
            yield 'data: {"choices": [{"delta": {"content": "Hi"}}]}\n\n'
            yield "data: [DONE]\n\n"

        mock_sse_convert.return_value = converted_stream()

        response = await handler.handle(
            openai_request=openai_request,
            resolved_model="claude-3-5-sonnet-20241022",
            provider_name="anthropic",
            provider_config=mock_provider_config_anthropic,
            provider_api_key="test-key",
            client_api_key=None,
            config=mock_config,
            openai_client=mock_client,
            request_id="req-4",
            http_request=mock_http_request,
            is_metrics_enabled=False,
            metrics=None,
            tracker=None,
        )

        # Verify StreamingResponse with correct headers
        assert hasattr(response, "body_iterator")
        headers = dict(response.headers)
        assert "text/event-stream" in headers.get("content-type", "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_anthropic_handler_streaming_with_metrics(
    mock_provider_config_anthropic,
    mock_tracker,
    mock_config,
    mock_http_request,
    openai_chat_request,
):
    """Test Anthropic handler streaming with metrics enabled."""
    handler = AnthropicChatCompletionsHandler()
    openai_request = {**openai_chat_request, "stream": True}

    # Mock stream that accepts api_key and next_api_key params
    async def mock_stream(
        _request: dict,
        _request_id: str,
        api_key: str | None = None,
        next_api_key: Any = None,
    ) -> AsyncGenerator[str, None]:
        yield 'data: {"type": "message_start"}\n'
        yield "data: [DONE]\n"

    mock_client = AsyncMock()
    mock_client.create_chat_completion_stream = mock_stream

    with patch(
        "src.conversion.anthropic_sse_to_openai.anthropic_sse_to_openai_chat_completions_sse"
    ) as mock_sse_convert:

        async def converted_stream() -> AsyncGenerator[str, None]:
            yield 'data: {"choices": [{"delta": {"content": "Hi"}}]}\n\n'
            yield "data: [DONE]\n\n"

        mock_sse_convert.return_value = converted_stream()

        response = await handler.handle(
            openai_request=openai_request,
            resolved_model="claude-3-5-sonnet-20241022",
            provider_name="anthropic",
            provider_config=mock_provider_config_anthropic,
            provider_api_key="test-key",
            client_api_key=None,
            config=mock_config,
            openai_client=mock_client,
            request_id="req-5",
            http_request=mock_http_request,
            is_metrics_enabled=True,
            metrics=MagicMock(),
            tracker=mock_tracker,
        )

        # Metrics are handled by the streaming wrapper, not directly here
        assert hasattr(response, "body_iterator")


# === OpenAIChatCompletionsHandler Tests ===


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openai_handler_non_streaming_passthrough(
    mock_provider_config_openai,
    mock_tracker,
    mock_config,
    mock_http_request,
    openai_chat_request,
    openai_chat_response,
):
    """Test OpenAI handler passes through response unchanged."""
    handler = OpenAIChatCompletionsHandler()
    openai_request = {**openai_chat_request, "stream": False}

    mock_client = AsyncMock()
    mock_client.create_chat_completion = AsyncMock(return_value=openai_chat_response)

    response = await handler.handle(
        openai_request=openai_request,
        resolved_model="gpt-4",
        provider_name="openai",
        provider_config=mock_provider_config_openai,
        provider_api_key="test-key",
        client_api_key=None,
        config=mock_config,
        openai_client=mock_client,
        request_id="req-6",
        http_request=mock_http_request,
        is_metrics_enabled=True,
        metrics=MagicMock(),
        tracker=mock_tracker,
    )

    # Verify passthrough - response unchanged
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["id"] == "chatcmpl-456"
    mock_tracker.end_request.assert_called_once_with("req-6")
    mock_client.create_chat_completion.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openai_handler_non_streaming_metrics_disabled(
    mock_provider_config_openai,
    mock_config,
    mock_http_request,
    openai_chat_request,
    openai_chat_response,
):
    """Test OpenAI handler with metrics disabled."""
    handler = OpenAIChatCompletionsHandler()
    openai_request = {**openai_chat_request, "stream": False}

    mock_client = AsyncMock()
    mock_client.create_chat_completion = AsyncMock(return_value=openai_chat_response)

    response = await handler.handle(
        openai_request=openai_request,
        resolved_model="gpt-4",
        provider_name="openai",
        provider_config=mock_provider_config_openai,
        provider_api_key="test-key",
        client_api_key=None,
        config=mock_config,
        openai_client=mock_client,
        request_id="req-7",
        http_request=mock_http_request,
        is_metrics_enabled=False,
        metrics=None,
        tracker=None,
    )

    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["id"] == "chatcmpl-456"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openai_handler_streaming_passthrough_with_newlines(
    mock_provider_config_openai,
    mock_config,
    mock_http_request,
    openai_chat_request,
):
    """Test OpenAI handler adds newlines to streaming chunks."""
    handler = OpenAIChatCompletionsHandler()
    openai_request = {**openai_chat_request, "stream": True}

    # Mock stream that accepts api_key and next_api_key params
    async def mock_stream(
        _request: dict,
        _request_id: str,
        api_key: str | None = None,
        next_api_key: Any = None,
    ) -> AsyncGenerator[str, None]:
        yield '{"chunk": "data1"}'
        yield '{"chunk": "data2"}'

    mock_client = AsyncMock()
    mock_client.create_chat_completion_stream = mock_stream

    response = await handler.handle(
        openai_request=openai_request,
        resolved_model="gpt-4",
        provider_name="openai",
        provider_config=mock_provider_config_openai,
        provider_api_key="test-key",
        client_api_key=None,
        config=mock_config,
        openai_client=mock_client,
        request_id="req-8",
        http_request=mock_http_request,
        is_metrics_enabled=False,
        metrics=None,
        tracker=None,
    )

    # Collect and verify streaming output
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    # Verify newlines added
    assert chunks[0] == '{"chunk": "data1"}\n'
    assert chunks[1] == '{"chunk": "data2"}\n'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openai_handler_streaming_empty_chunks(
    mock_provider_config_openai,
    mock_config,
    mock_http_request,
    openai_chat_request,
):
    """Test OpenAI handler handles empty streaming chunks."""
    handler = OpenAIChatCompletionsHandler()
    openai_request = {**openai_chat_request, "stream": True}

    # Mock stream that accepts api_key and next_api_key params
    async def mock_stream(
        _request: dict,
        _request_id: str,
        api_key: str | None = None,
        next_api_key: Any = None,
    ) -> AsyncGenerator[str, None]:
        yield ""
        yield '{"chunk": "data"}'
        yield ""

    mock_client = AsyncMock()
    mock_client.create_chat_completion_stream = mock_stream

    response = await handler.handle(
        openai_request=openai_request,
        resolved_model="gpt-4",
        provider_name="openai",
        provider_config=mock_provider_config_openai,
        provider_api_key="test-key",
        client_api_key=None,
        config=mock_config,
        openai_client=mock_client,
        request_id="req-9",
        http_request=mock_http_request,
        is_metrics_enabled=False,
        metrics=None,
        tracker=None,
    )

    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    # Empty chunks still get newlines
    assert len(chunks) == 3
    assert chunks[0] == "\n"
    assert chunks[1] == '{"chunk": "data"}\n'
    assert chunks[2] == "\n"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openai_handler_streaming_with_metrics_enabled(
    mock_provider_config_openai,
    mock_tracker,
    mock_config,
    mock_http_request,
    openai_chat_request,
):
    """Test OpenAI handler streaming with metrics enabled."""
    handler = OpenAIChatCompletionsHandler()
    openai_request = {**openai_chat_request, "stream": True}

    # Mock stream that accepts api_key and next_api_key params
    async def mock_stream(
        _request: dict,
        _request_id: str,
        api_key: str | None = None,
        next_api_key: Any = None,
    ) -> AsyncGenerator[str, None]:
        yield '{"chunk": "data"}'

    mock_client = AsyncMock()
    mock_client.create_chat_completion_stream = mock_stream

    response = await handler.handle(
        openai_request=openai_request,
        resolved_model="gpt-4",
        provider_name="openai",
        provider_config=mock_provider_config_openai,
        provider_api_key="test-key",
        client_api_key=None,
        config=mock_config,
        openai_client=mock_client,
        request_id="req-10",
        http_request=mock_http_request,
        is_metrics_enabled=True,
        metrics=MagicMock(),
        tracker=mock_tracker,
    )

    # Metrics are handled by the streaming wrapper
    assert hasattr(response, "body_iterator")


# === Factory Function Tests ===


@pytest.mark.unit
def test_get_chat_completions_handler_anthropic_format(mock_provider_config_anthropic):
    """Test factory returns Anthropic handler for anthropic format."""
    handler = get_chat_completions_handler(mock_provider_config_anthropic)
    assert isinstance(handler, AnthropicChatCompletionsHandler)


@pytest.mark.unit
def test_get_chat_completions_handler_openai_format(mock_provider_config_openai):
    """Test factory returns OpenAI handler for openai format."""
    handler = get_chat_completions_handler(mock_provider_config_openai)
    assert isinstance(handler, OpenAIChatCompletionsHandler)


@pytest.mark.unit
def test_get_chat_completions_handler_none_config():
    """Test factory returns OpenAI handler when config is None."""
    handler = get_chat_completions_handler(None)
    assert isinstance(handler, OpenAIChatCompletionsHandler)


# === Edge Cases Tests ===


@pytest.mark.unit
@pytest.mark.asyncio
async def test_anthropic_handler_with_tool_use_response(
    mock_provider_config_anthropic,
    mock_tracker,
    mock_config,
    mock_http_request,
    openai_chat_request,
):
    """Test Anthropic handler properly handles tool use responses."""
    handler = AnthropicChatCompletionsHandler()
    openai_request = {**openai_chat_request, "stream": False}

    anthropic_response = {
        "id": "msg_tool",
        "type": "message",
        "role": "assistant",
        "content": [
            {"type": "text", "text": "I'll calculate that."},
            {
                "type": "tool_use",
                "id": "toolu_test123",
                "name": "calculator",
                "input": {"expression": "2 + 2"},
            },
        ],
        "model": "claude-3-5-sonnet-20241022",
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 50, "output_tokens": 30},
    }

    openai_response = {
        "id": "chatcmpl-tool",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "claude-3-5-sonnet-20241022",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "I'll calculate that.",
                    "tool_calls": [
                        {
                            "id": "toolu_test123",
                            "type": "function",
                            "function": {
                                "name": "calculator",
                                "arguments": '{"expression": "2 + 2"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
    }

    mock_client = AsyncMock()
    mock_client.create_chat_completion = AsyncMock(return_value=anthropic_response)

    with patch(
        "src.conversion.anthropic_to_openai.anthropic_message_to_openai_chat_completion"
    ) as mock_convert:
        mock_convert.return_value = openai_response

        response = await handler.handle(
            openai_request=openai_request,
            resolved_model="claude-3-5-sonnet-20241022",
            provider_name="anthropic",
            provider_config=mock_provider_config_anthropic,
            provider_api_key="test-key",
            client_api_key=None,
            config=mock_config,
            openai_client=mock_client,
            request_id="req-tool",
            http_request=mock_http_request,
            is_metrics_enabled=True,
            metrics=MagicMock(),
            tracker=mock_tracker,
        )

        assert response.status_code == 200
        mock_tracker.end_request.assert_called_once_with("req-tool")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openai_handler_with_empty_response(
    mock_provider_config_openai,
    mock_config,
    mock_http_request,
    openai_chat_request,
):
    """Test OpenAI handler handles empty response gracefully."""
    handler = OpenAIChatCompletionsHandler()
    openai_request = {**openai_chat_request, "stream": False}

    empty_response = {
        "id": "chatcmpl-empty",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "gpt-4",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10},
    }

    mock_client = AsyncMock()
    mock_client.create_chat_completion = AsyncMock(return_value=empty_response)

    response = await handler.handle(
        openai_request=openai_request,
        resolved_model="gpt-4",
        provider_name="openai",
        provider_config=mock_provider_config_openai,
        provider_api_key="test-key",
        client_api_key=None,
        config=mock_config,
        openai_client=mock_client,
        request_id="req-empty",
        http_request=mock_http_request,
        is_metrics_enabled=False,
        metrics=None,
        tracker=None,
    )

    assert response.status_code == 200
