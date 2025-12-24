"""Unit tests for API endpoints with RESPX mocking.

Elegant HTTP-layer mocking for fast, reliable tests without external dependencies.
Converted from integration tests to use RESPX fixtures.
"""

import json

import httpx
import pytest

# Environment setup handled by conftest.py fixture
# This ensures consistent environment across all unit tests
# Import TestClient but NOT app - app will be imported in each test
# after the fixture has set up the environment
from fastapi.testclient import TestClient

from tests.config import TEST_HEADERS
from tests.fixtures.anthropic_tool_stream import anthropic_tool_use_stream_events


def _last_openai_chat_completion_request_json(mock_openai_api) -> dict:
    route = mock_openai_api.routes["POST", "https://api.openai.com/v1/chat/completions"]
    assert route.calls, "Expected at least one upstream OpenAI call"
    request = route.calls[-1].request
    return request.json()


def _last_anthropic_messages_request_json(mock_anthropic_api) -> dict:
    # respx stores routes keyed by (method, url) but url is normalized.
    route = mock_anthropic_api.routes["POST", "https://api.anthropic.com/v1/messages"]
    assert route.calls, "Expected at least one upstream Anthropic call"
    request = route.calls[-1].request
    return request.json()


def _assert_anthropic_messages_called(mock_anthropic_api) -> None:
    assert any(
        str(call.request.url) == "https://api.anthropic.com/v1/messages"
        for route in mock_anthropic_api.routes
        for call in route.calls
    ), "Expected upstream POST https://api.anthropic.com/v1/messages"


def _last_anthropic_messages_request_json_fallback(mock_anthropic_api) -> dict:
    for route in mock_anthropic_api.routes:
        for call in reversed(route.calls):
            if str(call.request.url) == "https://api.anthropic.com/v1/messages":
                content = call.request.content
                assert content is not None
                return json.loads(content.decode("utf-8"))
    raise AssertionError("Expected at least one upstream Anthropic call")


@pytest.mark.unit
def test_basic_chat_mocked(mock_openai_api, openai_chat_completion):
    """Test basic chat completion via Claude-format /v1/messages."""
    # Import app after fixture setup to get fresh config
    from src.main import app

    # Mock OpenAI endpoint
    mock_openai_api.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=openai_chat_completion)
    )

    # Test our proxy endpoint
    with TestClient(app) as client:
        response = client.post(
            "/v1/messages",
            json={
                "model": "openai:gpt-4",  # Use explicit provider to avoid alias conflicts
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers=TEST_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["content"][0]["text"] == "Hello! How can I help you today?"
    assert data["role"] == "assistant"


@pytest.mark.unit
def test_openai_chat_completions_passthrough_mocked(mock_openai_api, openai_chat_completion):
    """Test OpenAI-compatible /v1/chat/completions passthrough (non-streaming)."""
    from src.main import app

    mock_openai_api.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=openai_chat_completion)
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "openai:gpt-4",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 100,
            },
            headers=TEST_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "chat.completion"
        assert data["choices"][0]["message"]["content"] == "Hello! How can I help you today?"
        assert data["choices"][0]["message"]["role"] == "assistant"

        # Metrics should include this request under the resolved target model.
        totals = client.get("/metrics/running-totals", headers=TEST_HEADERS)
        assert totals.status_code == 200
        assert "providers:" in totals.text
        assert "openai:" in totals.text
        assert "gpt-4" in totals.text
        assert "total_requests:" in totals.text
        assert "total_requests: 1" in totals.text


def test_openrouter_prefixed_alias_records_target_model_in_metrics(
    mock_openai_api, openai_chat_completion, monkeypatch
):
    """Regression: requests like model='openrouter:cheap' must record the target model.

    Underlying bug: provider-prefixed aliases can leak into metrics and appear as model rows.
    This test enforces that the recorded model name is the resolved target.
    """

    # Ensure a deterministic openrouter alias in this test.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("OPENROUTER_API_FORMAT", "openai")
    monkeypatch.setenv("OPENROUTER_ALIAS_CHEAP", "minimax/minimax-m2")

    from src.main import app

    # OpenRouter is OpenAI-compatible, but uses a different base URL. In unit tests,
    # the provider base URL may vary; match any upstream call to /chat/completions.
    mock_openai_api.post(url__regex=r".*/chat/completions$").mock(
        return_value=httpx.Response(200, json=openai_chat_completion)
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "openrouter:cheap",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 100,
            },
            headers=TEST_HEADERS,
        )

        assert response.status_code == 200

        totals = client.get("/metrics/running-totals", headers=TEST_HEADERS)
        assert totals.status_code == 200
        assert "providers:" in totals.text
        assert "openrouter:" in totals.text
        assert "minimax/minimax-m2" in totals.text
        assert "openrouter:cheap" not in totals.text
        assert "total_requests: 1" in totals.text


@pytest.mark.unit
def test_openai_chat_completions_anthropic_translation_non_stream(
    mock_anthropic_api, anthropic_message_response
):
    """OpenAI /v1/chat/completions -> Anthropic provider -> OpenAI response."""
    from src.main import app

    # The OpenAI endpoint accepts the same proxy auth headers as the Claude endpoint.
    # We keep using TEST_HEADERS here for consistency.

    mock_anthropic_api.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json=anthropic_message_response)
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic:claude-3-5-sonnet-20241022",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 100,
            },
            headers=TEST_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["choices"][0]["message"]["content"] == "Hello! How can I help you today?"

    _assert_anthropic_messages_called(mock_anthropic_api)
    upstream = _last_anthropic_messages_request_json_fallback(mock_anthropic_api)
    assert upstream["model"] == "claude-3-5-sonnet-20241022"
    assert upstream["messages"][0]["role"] == "user"
    assert upstream["messages"][0]["content"][0]["type"] == "text"


@pytest.mark.unit
def test_openai_chat_completions_anthropic_translation_stream(
    mock_anthropic_api, anthropic_streaming_events
):
    """OpenAI /v1/chat/completions (stream) -> Anthropic SSE -> OpenAI SSE."""
    from src.main import app

    # Return an Anthropic SSE stream body
    stream_body = b"".join(anthropic_streaming_events)
    mock_anthropic_api.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, content=stream_body)
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic:claude-3-5-sonnet-20241022",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 10,
                "stream": True,
            },
            headers=TEST_HEADERS,
        )

        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("text/event-stream")

        body = b"".join(response.iter_bytes())

    # Expect OpenAI-style chunks and termination
    assert b"chat.completion.chunk" in body
    assert b"data: [DONE]" in body


@pytest.mark.unit
def test_openai_chat_completions_anthropic_translation_stream_tool_calls(
    mock_anthropic_api,
):
    """Anthropic tool_use streaming -> OpenAI tool_calls streaming."""
    from src.main import app

    stream_body = b"".join(anthropic_tool_use_stream_events())
    mock_anthropic_api.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, content=stream_body)
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic:claude-3-5-sonnet-20241022",
                "messages": [{"role": "user", "content": "Compute 2+2"}],
                "max_tokens": 10,
                "stream": True,
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "description": "Perform basic arithmetic",
                            "parameters": {
                                "type": "object",
                                "properties": {"expression": {"type": "string"}},
                                "required": ["expression"],
                            },
                        },
                    }
                ],
            },
            headers=TEST_HEADERS,
        )

        assert response.status_code == 200
        body = b"".join(response.iter_bytes())

    assert b"tool_calls" in body
    assert b'"name": "calculator"' in body
    assert b"data: [DONE]" in body


@pytest.mark.unit
def test_function_calling_mocked(mock_openai_api, openai_chat_completion_with_tool):
    """Test function calling with mocked OpenAI API."""
    # Import app after fixture setup to get fresh config
    from src.main import app

    # Mock endpoint with tool response
    mock_openai_api.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=openai_chat_completion_with_tool)
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/messages",
            json={
                "model": "openai:gpt-4",  # Use explicit provider to avoid alias conflicts
                "max_tokens": 200,
                "messages": [
                    {
                        "role": "user",
                        "content": "What's 2 + 2? Use as calculator tool.",
                    }
                ],
                "tools": [
                    {
                        "name": "calculator",
                        "description": "Perform basic arithmetic",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "expression": {
                                    "type": "string",
                                    "description": "Mathematical expression",
                                },
                            },
                            "required": ["expression"],
                        },
                    }
                ],
                "tool_choice": {"type": "auto"},
            },
            headers=TEST_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()
    assert "content" in data

    # Verify tool_use in response
    tool_use_found = False
    for content_block in data.get("content", []):
        if content_block.get("type") == "tool_use":
            tool_use_found = True
            assert "id" in content_block
            assert "name" in content_block
            assert content_block["name"] == "calculator"
            assert content_block["input"] == {"expression": "2 + 2"}

    assert tool_use_found, "Expected tool_use block in response"


@pytest.mark.unit
def test_with_system_message_mocked(mock_openai_api, openai_chat_completion):
    """Test with system message using mocked API."""
    # Import app after fixture setup to get fresh config
    from src.main import app

    # Mock endpoint
    mock_openai_api.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=openai_chat_completion)
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/messages",
            json={
                "model": "openai:gpt-4",  # Use explicit provider to avoid alias conflicts
                "max_tokens": 50,
                "system": (
                    "You are a helpful assistant that always ends responses with 'over and out'."
                ),
                "messages": [{"role": "user", "content": "Say hello"}],
            },
            headers=TEST_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert len(data["content"]) > 0


@pytest.mark.unit
def test_multimodal_mocked(mock_openai_api, openai_chat_completion):
    """Test multimodal input (text + image) with mocked API."""
    # Import app after fixture setup to get fresh config
    from src.main import app

    # Mock endpoint
    mock_openai_api.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=openai_chat_completion)
    )

    # Small 1x1 pixel red PNG (base64)
    sample_image = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/"
        "PchI7wAAAABJRU5ErkJggg=="
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/messages",
            json={
                "model": "openai:gpt-4",  # Use explicit provider to avoid alias conflicts
                "max_tokens": 50,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "What color is this image?"},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": sample_image,
                                },
                            },
                        ],
                    }
                ],
            },
            headers=TEST_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert len(data["content"]) > 0


@pytest.mark.unit
def test_conversation_with_tool_use_mocked(
    mock_openai_api, openai_chat_completion, openai_chat_completion_with_tool
):
    """Test a complete conversation with tool use and results."""
    # Import app after fixture setup to get fresh config
    from src.main import app

    # Mock first call (tool use) and second call (final response)
    route = mock_openai_api.post("/v1/chat/completions")
    route.side_effect = [
        httpx.Response(200, json=openai_chat_completion_with_tool),
        httpx.Response(200, json=openai_chat_completion),
    ]

    with TestClient(app) as client:
        # First message with tool call
        response1 = client.post(
            "/v1/messages",
            json={
                "model": "openai:gpt-4",  # Use explicit provider to avoid alias conflicts
                "max_tokens": 200,
                "messages": [{"role": "user", "content": "Calculate 25 * 4"}],
                "tools": [
                    {
                        "name": "calculator",
                        "description": "Perform arithmetic calculations",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "expression": {
                                    "type": "string",
                                    "description": "Mathematical expression to calculate",
                                }
                            },
                            "required": ["expression"],
                        },
                    }
                ],
            },
            headers=TEST_HEADERS,
        )

        assert response1.status_code == 200
        result1 = response1.json()

        # Should have tool_use in response
        tool_use_blocks = [
            block for block in result1.get("content", []) if block.get("type") == "tool_use"
        ]
        assert len(tool_use_blocks) > 0, "Expected tool_use block in response"

        # Simulate tool execution and send result
        tool_block = tool_use_blocks[0]

        response2 = client.post(
            "/v1/messages",
            json={
                "model": "openai:gpt-4",  # Use explicit provider to avoid alias conflicts
                "max_tokens": 50,
                "messages": [
                    {"role": "user", "content": "Calculate 25 * 4"},
                    {"role": "assistant", "content": result1["content"]},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_block["id"],
                                "content": "100",
                            }
                        ],
                    },
                ],
            },
            headers=TEST_HEADERS,
        )

        assert response2.status_code == 200
        result2 = response2.json()
        assert "content" in result2


@pytest.mark.unit
def test_kimi_tool_name_sanitization_outbound_and_inbound_non_streaming(mock_openai_api):
    """Kimi requires strict tool names; we sanitize outbound and restore inbound."""
    from src.main import app

    original_tool_name = "get weather"  # contains space, should be sanitized

    # Kimi uses its own base URL; the provider config is config-driven.
    # Mock exactly what the OpenAI client will call for kimi.
    mock_openai_api.post("https://api.kimi.com/coding/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-kimi-1",
                "object": "chat.completion",
                "created": 1677652288,
                "model": "kimi",
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
                                        "name": "get_weather",
                                        "arguments": '{"city": "NYC"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/messages",
            json={
                "model": "kimi:sonnet",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": "What is the weather in NYC?"}],
                "tools": [
                    {
                        "name": original_tool_name,
                        "description": "Get weather",
                        "input_schema": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    }
                ],
                "tool_choice": {"type": "tool", "name": original_tool_name},
            },
            headers=TEST_HEADERS,
        )

    assert response.status_code == 200

    import json as _json

    assert len(mock_openai_api.calls) > 0
    upstream_json = _json.loads(mock_openai_api.calls[-1].request.content)

    assert upstream_json["tools"][0]["function"]["name"] == "get_weather"
    assert upstream_json["tool_choice"]["function"]["name"] == "get_weather"

    data = response.json()
    tool_use_blocks = [b for b in data.get("content", []) if b.get("type") == "tool_use"]
    assert len(tool_use_blocks) == 1
    assert tool_use_blocks[0]["name"] == original_tool_name


@pytest.mark.unit
def test_kimi_tool_name_restoration_streaming(mock_openai_api, openai_streaming_tool_call_chunks):
    """Streaming tool_use name is restored back to the original tool name."""
    from src.main import app

    mock_openai_api.post("https://api.kimi.com/coding/v1/chat/completions").mock(
        return_value=httpx.Response(200, content=b"".join(openai_streaming_tool_call_chunks))
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/messages",
            json={
                "model": "kimi:sonnet",
                "max_tokens": 200,
                "stream": True,
                "messages": [{"role": "user", "content": "Weather?"}],
                "tools": [
                    {
                        "name": "get weather",
                        "description": "Get weather",
                        "input_schema": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    }
                ],
                "tool_choice": {"type": "auto"},
            },
            headers=TEST_HEADERS,
        )

    assert response.status_code == 200
    body = response.text
    assert '"type": "tool_use"' in body
    assert '"name": "get weather"' in body


@pytest.mark.unit
def test_token_counting_mocked():
    """Test token counting endpoint - no external API call needed."""
    # Import app after fixture setup to get fresh config
    from src.main import app

    with TestClient(app) as client:
        response = client.post(
            "/v1/messages/count_tokens",
            json={
                "model": "openai:gpt-4",  # Use explicit provider to avoid alias conflicts
                "messages": [
                    {"role": "user", "content": "This is a test message for token counting."}
                ],
            },
            headers=TEST_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()
    # Token counting endpoint returns just {"input_tokens": N} without usage wrapper
    assert "input_tokens" in data
    assert data["input_tokens"] > 0


@pytest.mark.skip(
    reason="Anthropic passthrough test requires actual Anthropic provider configuration"
)
def test_anthropic_passthrough_mocked(mock_anthropic_api, anthropic_message_response):
    """Test Anthropic API passthrough format with mocked API."""
    # Skipping this test for now as it requires complex provider setup
    # The test environment uses OpenAI provider by default
    pass

    # Cleanup handled by setup_test_env fixture
