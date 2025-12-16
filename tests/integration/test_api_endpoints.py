"""Integration tests for API endpoints."""

import os

import httpx
import pytest
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get test port from environment or use default (matching development server)
TEST_PORT = int(os.environ.get("VDM_TEST_PORT", "8082"))
BASE_URL = f"http://localhost:{TEST_PORT}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_check():
    """Test health check endpoint."""
    import yaml

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")

        assert response.status_code == 200
        # Verify content type is YAML
        assert "text/yaml" in response.headers.get("content-type", "")
        # Verify it displays inline (not as attachment)
        content_disposition = response.headers.get("content-disposition", "")
        assert "inline" in content_disposition

        # Parse YAML response
        data = yaml.safe_load(response.text)
        assert "status" in data
        # Accept both "healthy" and "ok" status values for flexibility
        assert data["status"] in ["healthy", "ok", "degraded"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_models_endpoint():
    """Test /v1/models endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/v1/models")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_running_totals_endpoint():
    """Test GET /metrics/running-totals endpoint."""
    async with httpx.AsyncClient() as client:
        # Test without filters
        response = await client.get(f"{BASE_URL}/metrics/running-totals")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/yaml; charset=utf-8"

        yaml_content = response.text

        # If metrics are disabled, we get a different response
        if "Request metrics logging is disabled" in yaml_content:
            assert "Set LOG_REQUEST_METRICS=true to enable tracking" in yaml_content
        else:
            # Check for YAML structure elements
            assert "# Running Totals Report" in yaml_content
            assert "summary:" in yaml_content
            assert "total_requests:" in yaml_content
            assert "total_errors:" in yaml_content
            assert "total_input_tokens:" in yaml_content
            assert "total_output_tokens:" in yaml_content
            assert "active_requests:" in yaml_content
            assert "average_duration_ms:" in yaml_content

        # Test with provider filter
        response = await client.get(f"{BASE_URL}/metrics/running-totals?provider=poe")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/yaml; charset=utf-8"
        yaml_content = response.text

        if "Request metrics logging is disabled" not in yaml_content:
            assert "# Filter: provider=poe" in yaml_content

        # Test with model filter using wildcard
        response = await client.get(f"{BASE_URL}/metrics/running-totals?model=gpt*")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/yaml; charset=utf-8"
        yaml_content = response.text

        if "Request metrics logging is disabled" not in yaml_content:
            assert "# Filter: model=gpt*" in yaml_content

        # Test with both provider and model filter
        response = await client.get(f"{BASE_URL}/metrics/running-totals?provider=poe&model=claude*")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/yaml; charset=utf-8"
        yaml_content = response.text

        if "Request metrics logging is disabled" not in yaml_content:
            assert "# Filter: provider=poe & model=claude*" in yaml_content

        # Test case-insensitive matching
        response = await client.get(f"{BASE_URL}/metrics/running-totals?provider=POE")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/yaml; charset=utf-8"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_connection_test():
    """Test connection test endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/test-connection")

        assert response.status_code == 200
        data = response.json()
        # Check for success response structure
        assert "status" in data
        assert data["status"] == "success"
        assert "provider" in data
        assert "message" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_basic_chat():
    """Test basic chat completion with real API."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BASE_URL}/v1/messages",
            json={
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 20,
                "messages": [{"role": "user", "content": "Say 'Hello world'"}],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert len(data["content"]) > 0
        assert "role" in data
        assert data["role"] == "assistant"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_streaming_chat():
    """Test streaming chat completion with real API."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    async with (
        httpx.AsyncClient(timeout=30.0) as client,
        client.stream(
            "POST",
            f"{BASE_URL}/v1/messages",
            json={
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": 50,
                "messages": [{"role": "user", "content": "Count to 3"}],
                "stream": True,
            },
        ) as response,
    ):
        assert response.status_code == 200

        # Collect streamed events
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(line[6:])  # Remove "data: " prefix

        # Should have at least some events
        assert len(events) > 0

        # Check for event stream format
        assert any("message_start" in event for event in events)
        assert any("content_block_start" in event for event in events)
        assert any("content_block_stop" in event for event in events)
        assert any("message_stop" in event for event in events)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_function_calling():
    """Test function calling with real API."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BASE_URL}/v1/messages",
            json={
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 200,
                "messages": [
                    {
                        "role": "user",
                        "content": "What's 2 + 2? Use the calculator tool.",
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
        )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data

        # Should have tool_use in content
        tool_use_found = False
        for content_block in data.get("content", []):
            if content_block.get("type") == "tool_use":
                tool_use_found = True
                assert "id" in content_block
                assert "name" in content_block
                assert content_block["name"] == "calculator"

        assert tool_use_found, "Expected tool_use block in response"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_with_system_message():
    """Test with system message."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BASE_URL}/v1/messages",
            json={
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 50,
                "system": (
                    "You are a helpful assistant that always ends responses with 'over and out'."
                ),
                "messages": [{"role": "user", "content": "Say hello"}],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert len(data["content"]) > 0

        # Check that the response follows the system instruction
        content_text = data["content"][0].get("text", "").lower()
        assert "over and out" in content_text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multimodal():
    """Test multimodal input (text + image)."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Small 1x1 pixel red PNG
        sample_image = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/"
            "PchI7wAAAABJRU5ErkJggg=="
        )

        response = await client.post(
            f"{BASE_URL}/v1/messages",
            json={
                "model": "claude-3-5-sonnet-20241022",
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
        )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert len(data["content"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_conversation_with_tool_use():
    """Test a complete conversation with tool use and results."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # First message with tool call
        response1 = await client.post(
            f"{BASE_URL}/v1/messages",
            json={
                "model": "claude-3-5-sonnet-20241022",
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

        response2 = await client.post(
            f"{BASE_URL}/v1/messages",
            json={
                "model": "claude-3-5-sonnet-20241022",
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
        )

        assert response2.status_code == 200
        result2 = response2.json()
        assert "content" in result2

        # Should acknowledge the calculation result
        content_text = " ".join(
            block.get("text", "")
            for block in result2.get("content", [])
            if block.get("type") == "text"
        ).lower()
        assert "100" in content_text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_token_counting():
    """Test token counting endpoint."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BASE_URL}/v1/messages/count_tokens",
            json={
                "model": "claude-3-5-sonnet-20241022",
                "messages": [
                    {"role": "user", "content": "This is a test message for token counting."}
                ],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "input_tokens" in data
        assert data["input_tokens"] > 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_anthropic_passthrough():
    """Test Anthropic API passthrough format with real API."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    os.environ["ANTHROPIC_API_FORMAT"] = "anthropic"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BASE_URL}/v1/messages",
            json={
                "model": "anthropic:claude-3-5-sonnet-20241022",
                "max_tokens": 20,
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert "role" in data
        assert data["role"] == "assistant"
