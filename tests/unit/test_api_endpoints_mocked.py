"""Unit tests for API endpoints with RESPX mocking.

Elegant HTTP-layer mocking for fast, reliable tests without external dependencies.
Converted from integration tests to use RESPX fixtures.
"""

import httpx
import os
import pytest
from tests.config import TEST_HEADERS
from tests.fixtures.mock_http import (
    openai_chat_completion,
    openai_chat_completion_with_tool,
    openai_streaming_chunks,
)

# Set test environment BEFORE importing any src modules
# This ensures clean test state without external dependencies
os.environ["OPENAI_API_KEY"] = "test-openai-key"
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"  # Must match TEST_HEADERS
os.environ["POE_API_KEY"] = "test-poe-key"
os.environ["GLM_API_KEY"] = "test-glm-key"
os.environ["VDM_DEFAULT_PROVIDER"] = "openai"

# Clear any aliases to ensure clean test environment
for key in list(os.environ.keys()):
    if key.startswith("VDM_ALIAS_"):
        os.environ.pop(key, None)

# Now it's safe to import app modules
from fastapi.testclient import TestClient
from src.main import app


@pytest.mark.unit
def test_basic_chat_mocked(mock_openai_api, openai_chat_completion):
    """Test basic chat completion with mocked OpenAI API."""
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
                "messages": [{"role": "user", "content": "Hello"}]
            },
            headers=TEST_HEADERS
        )

    assert response.status_code == 200
    data = response.json()
    assert data["content"][0]["text"] == "Hello! How can I help you today?"
    assert data["role"] == "assistant"


@pytest.mark.unit
def test_function_calling_mocked(mock_openai_api, openai_chat_completion_with_tool):
    """Test function calling with mocked OpenAI API."""
    # API key is already set by setup_test_env fixture

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
            headers=TEST_HEADERS
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
    # API key is already set by setup_test_env fixture

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
            headers=TEST_HEADERS
        )

    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert len(data["content"]) > 0


@pytest.mark.unit
def test_multimodal_mocked(mock_openai_api, openai_chat_completion):
    """Test multimodal input (text + image) with mocked API."""
    # API key is already set by setup_test_env fixture

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
            headers=TEST_HEADERS
        )

    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert len(data["content"]) > 0


@pytest.mark.unit
def test_conversation_with_tool_use_mocked(mock_openai_api, openai_chat_completion, openai_chat_completion_with_tool):
    """Test a complete conversation with tool use and results."""
    # API key is already set by setup_test_env fixture

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
            headers=TEST_HEADERS
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
            headers=TEST_HEADERS
        )

        assert response2.status_code == 200
        result2 = response2.json()
        assert "content" in result2


@pytest.mark.unit
def test_token_counting_mocked():
    """Test token counting endpoint - no external API call needed."""
    # API key is already set by setup_test_env fixture

    with TestClient(app) as client:
        response = client.post(
            "/v1/messages/count_tokens",
            json={
                "model": "openai:gpt-4",  # Use explicit provider to avoid alias conflicts
                "messages": [
                    {"role": "user", "content": "This is a test message for token counting."}
                ],
            },
            headers=TEST_HEADERS
        )

    assert response.status_code == 200
    data = response.json()
    # Token counting endpoint returns just {"input_tokens": N} without usage wrapper
    assert "input_tokens" in data
    assert data["input_tokens"] > 0


@pytest.mark.skip(reason="Anthropic passthrough test requires actual Anthropic provider configuration")
def test_anthropic_passthrough_mocked(mock_anthropic_api, anthropic_message_response):
    """Test Anthropic API passthrough format with mocked API."""
    # Skipping this test for now as it requires complex provider setup
    # The test environment uses OpenAI provider by default
    pass

    # Cleanup handled by setup_test_env fixture