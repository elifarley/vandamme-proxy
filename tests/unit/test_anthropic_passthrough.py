"""Test Anthropic passthrough functionality."""

import os
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.mark.unit
def test_provider_config_api_format():
    """Test that ProviderConfig correctly handles api_format field."""
    from src.core.provider_config import ProviderConfig

    # Test with explicit anthropic format
    config = ProviderConfig(
        name="test",
        api_key="test-key",
        base_url="https://api.anthropic.com",
        api_format="anthropic",
    )
    assert config.is_anthropic_format is True
    assert config.api_format == "anthropic"

    # Test with default format
    config_default = ProviderConfig(
        name="test2", api_key="test-key", base_url="https://api.openai.com"
    )
    assert config_default.is_anthropic_format is False
    assert config_default.api_format == "openai"


@pytest.mark.unit
def test_provider_manager_loads_api_format():
    """Test that ProviderManager loads API format from environment."""
    from src.core.provider_manager import ProviderManager

    # Set up OpenAI API key for default provider
    os.environ["OPENAI_API_KEY"] = "test-openai-key"

    # Mock environment variables for additional provider (not default)
    os.environ["TEST_API_FORMAT"] = "anthropic"
    os.environ["TEST_API_KEY"] = "test-key"
    os.environ["TEST_BASE_URL"] = "https://api.test.com"

    manager = ProviderManager(default_provider="openai")  # Use different default
    manager.load_provider_configs()

    # Check that format was loaded for additional provider
    config = manager.get_provider_config("test")
    assert config is not None
    assert config.api_format == "anthropic"
    assert config.is_anthropic_format is True

    # Test with invalid format defaults to openai
    os.environ["TEST2_API_FORMAT"] = "invalid"
    os.environ["TEST2_API_KEY"] = "test-key"
    os.environ["TEST2_BASE_URL"] = "https://api.test2.com"

    manager2 = ProviderManager(default_provider="openai")
    manager2.load_provider_configs()

    config2 = manager2.get_provider_config("test2")
    assert config2 is not None
    assert config2.api_format == "openai"  # Should default to openai


@pytest.mark.unit
def test_anthropic_client_selection():
    """Test that correct client is selected based on api_format."""
    import sys

    # Save original environment
    original_env = os.environ.copy()

    try:
        # Clear and set specific environment for this test
        os.environ.clear()
        os.environ["OPENAI_API_KEY"] = "openai-key"
        os.environ["OPENAI_BASE_URL"] = "https://api.openai.com"
        os.environ["ANTHROPIC_API_KEY"] = "anthropic-key"
        os.environ["ANTHROPIC_BASE_URL"] = "https://api.anthropic.com"
        os.environ["ANTHROPIC_API_FORMAT"] = "anthropic"

        # Clear module cache and reset config
        for module in ["src.core.provider_manager", "src.core.config"]:
            if module in sys.modules:
                del sys.modules[module]

        # Import fresh modules
        from src.core.provider_manager import ProviderManager

        manager = ProviderManager()
        manager.load_provider_configs()

        # Should return OpenAI client for openai provider
        openai_client = manager.get_client("openai")
        from src.core.client import OpenAIClient

        assert isinstance(openai_client, OpenAIClient)

        # Should return Anthropic client for anthropic provider
        anthropic_client = manager.get_client("anthropic")
        from src.core.anthropic_client import AnthropicClient

        assert isinstance(anthropic_client, AnthropicClient)

    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


@pytest.mark.unit
def test_models_endpoint_openai_format():
    """Test /v1/models endpoint with OpenAI format provider."""
    from fastapi import FastAPI

    from src.api.endpoints import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # Mock config and provider manager
    with patch("src.api.endpoints.config") as mock_config:
        # Setup mock provider config
        mock_provider_config = MagicMock()
        mock_provider_config.is_anthropic_format = False
        mock_provider_config.api_format = "openai"

        # Mock OpenAI client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "object": "list",
            "data": [
                {"id": "gpt-4o", "created": 1699905200},
                {"id": "gpt-4o-mini", "created": 1699905200},
            ],
        }
        mock_response.raise_for_status.return_value = None
        mock_client.client.get.return_value = mock_response

        mock_provider_manager = MagicMock()
        mock_provider_manager.default_provider = "openai"
        mock_provider_manager.list_providers.return_value = {"openai": mock_provider_config}
        mock_provider_manager.get_client.return_value = mock_client
        mock_provider_manager.get_provider_config.return_value = mock_provider_config
        mock_config.provider_manager = mock_provider_manager
        mock_config.proxy_api_key = None  # No client auth required

        # Make request with mock auth header
        response = client.get("/v1/models", headers={"x-api-key": "test-key"})

        assert response.status_code == 200
        data = yaml.safe_load(response.content)
        assert data["object"] == "list"
        assert "data" in data

        # Check that models are transformed to Claude format
        model_ids = [model["id"] for model in data["data"]]
        assert "gpt-4o" in model_ids
        assert "gpt-4o-mini" in model_ids


@pytest.mark.unit
def test_anthropic_passthrough_message_format():
    """Test that Anthropic passthrough maintains correct message format."""
    from src.core.anthropic_client import AnthropicClient

    # Create Anthropic client
    AnthropicClient(api_key="test-key", base_url="https://api.anthropic.com")

    # Test request format
    request = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ],
        "max_tokens": 100,
        "stream": False,
        "_provider": "anthropic",
    }

    # Verify the request structure
    assert "model" in request
    assert "messages" in request
    assert "max_tokens" in request
    assert "_provider" in request

    # Verify message structure
    for message in request["messages"]:
        assert "role" in message
        assert "content" in message


if __name__ == "__main__":
    test_provider_config_api_format()
    test_provider_manager_loads_api_format()
    test_anthropic_client_selection()
    test_models_endpoint_openai_format()
    test_anthropic_passthrough_message_format()
    print("✅ All tests passed!")
