"""RESPX-based HTTP mocking fixtures for testing.

This module provides elegant, reusable fixtures for mocking HTTP API calls
to OpenAI and Anthropic-compatible endpoints using RESPX.
"""

import httpx
import pytest
import respx

# Import test configuration
from tests.config import TEST_API_KEYS, TEST_ENDPOINTS


# === OpenAI Response Fixtures ===


@pytest.fixture
def openai_chat_completion():
    """Standard OpenAI chat completion response."""
    return {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "gpt-4",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello! How can I help you today?",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 15,
            "total_tokens": 25,
        },
    }


@pytest.fixture
def openai_chat_completion_with_tool():
    """OpenAI chat completion with function calling."""
    return {
        "id": "chatcmpl-456",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "gpt-4",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
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
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 20,
            "total_tokens": 70,
        },
    }


@pytest.fixture
def openai_streaming_chunks():
    """OpenAI streaming response chunks."""
    return [
        b'data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"gpt-4","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}\n\n',
        b'data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"gpt-4","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}\n\n',
        b'data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"gpt-4","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}\n\n',
        b'data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"gpt-4","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n',
        b"data: [DONE]\n\n",
    ]


# === Anthropic Response Fixtures ===


@pytest.fixture
def anthropic_message_response():
    """Standard Anthropic message response."""
    return {
        "id": "msg_test123",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello! How can I help you today?"}],
        "model": "claude-3-5-sonnet-20241022",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 10,
            "output_tokens": 15,
        },
    }


@pytest.fixture
def anthropic_message_with_tool_use():
    """Anthropic message with tool use."""
    return {
        "id": "msg_test456",
        "type": "message",
        "role": "assistant",
        "content": [
            {"type": "text", "text": "I'll help you calculate that."},
            {
                "type": "tool_use",
                "id": "toolu_test123",
                "name": "calculator",
                "input": {"expression": "2 + 2"},
            },
        ],
        "model": "claude-3-5-sonnet-20241022",
        "stop_reason": "tool_use",
        "usage": {
            "input_tokens": 50,
            "output_tokens": 30,
        },
    }


@pytest.fixture
def anthropic_streaming_events():
    """Anthropic streaming SSE events."""
    return [
        b'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_test123","type":"message","role":"assistant","content":[],"model":"claude-3-5-sonnet-20241022","usage":{"input_tokens":10,"output_tokens":0}}}\n\n',
        b'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n',
        b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}\n\n',
        b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"!"}}\n\n',
        b'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
        b'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":15}}\n\n',
        b'event: message_stop\ndata: {"type":"message_stop"}\n\n',
    ]


# === RESPX Mock Fixtures ===


@pytest.fixture(scope="function")
def mock_openai_api():
    """Mock OpenAI API endpoints with strict network isolation.

    This fixture ensures NO real HTTP calls are made during testing.
    All endpoints must be explicitly mocked in tests.

    Example:
        def test_chat(mock_openai_api, openai_chat_completion):
            mock_openai_api.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, json=openai_chat_completion)
            )
    """
    # Use assert_all_mocked=True to guarantee no real network calls
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as respx_mock:
        # Mock common OpenAI endpoints
        respx_mock.get(f"{TEST_ENDPOINTS['OPENAI']}/v1/models").mock(
            return_value=httpx.Response(200, json={"object": "list", "data": []})
        )
        # Note: Tests must explicitly mock /v1/chat/completions
        # This prevents silent failures and ensures proper test coverage
        yield respx_mock


@pytest.fixture
def mock_anthropic_api():
    """Mock Anthropic API endpoints with strict network isolation.

    This fixture ensures NO real HTTP calls are made during testing.
    All endpoints must be explicitly mocked in tests.

    Example:
        def test_message(mock_anthropic_api, anthropic_message_response):
            mock_anthropic_api.post("https://api.anthropic.com/v1/messages").mock(
                return_value=httpx.Response(200, json=anthropic_message_response)
            )
    """
    # Use assert_all_mocked=True to guarantee no real network calls
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as respx_mock:
        # Note: Tests must explicitly mock all Anthropic endpoints
        # This prevents silent failures and ensures proper test coverage
        yield respx_mock


# === Helper Functions ===


def create_openai_error(status_code: int, error_type: str, message: str) -> dict:
    """Create an OpenAI-formatted error response.

    Args:
        status_code: HTTP status code
        error_type: Error type (e.g., "invalid_request_error", "rate_limit_error")
        message: Error message

    Returns:
        Dictionary with OpenAI error format
    """
    return {
        "error": {
            "message": message,
            "type": error_type,
            "code": None,
        }
    }


def create_anthropic_error(status_code: int, error_type: str, message: str) -> dict:
    """Create an Anthropic-formatted error response.

    Args:
        status_code: HTTP status code
        error_type: Error type (e.g., "invalid_request_error", "rate_limit_error")
        message: Error message

    Returns:
        Dictionary with Anthropic error format
    """
    return {
        "type": "error",
        "error": {
            "type": error_type,
            "message": message,
        },
    }


def create_streaming_response(chunks: list[bytes]) -> httpx.Response:
    """Create a streaming HTTP response from chunks.

    Args:
        chunks: List of byte chunks to stream

    Returns:
        httpx.Response configured for streaming
    """
    return httpx.Response(
        status_code=200,
        headers={"content-type": "text/event-stream"},
        content=b"".join(chunks),
    )
