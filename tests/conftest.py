"""Shared pytest configuration and fixtures for Vandamme Proxy tests."""

import os
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv

# Load test environment variables
load_dotenv(".env.test")

# Import HTTP mocking fixtures from fixtures module
pytest_plugins = ["tests.fixtures.mock_http"]


@pytest.fixture
def mock_openai_api_key():
    """Mock OpenAI API key for testing."""
    os.environ["OPENAI_API_KEY"] = "test-openai-key"
    yield
    os.environ.pop("OPENAI_API_KEY", None)


@pytest.fixture
def mock_anthropic_api_key():
    """Mock Anthropic API key for testing."""
    os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"
    yield
    os.environ.pop("ANTHROPIC_API_KEY", None)


@pytest.fixture
def mock_config():
    """Mock configuration with test values."""
    config = MagicMock()
    config.provider_manager = MagicMock()
    config.anthropic_api_key = None
    config.default_provider = "openai"
    config.openai_api_key = "test-key"
    config.openai_base_url = "https://api.openai.com/v1"
    config.log_level = "DEBUG"
    config.max_tokens_limit = 4096
    config.min_tokens_limit = 100
    config.request_timeout = 90
    config.max_retries = 2
    return config


@pytest.fixture
def mock_provider_config():
    """Mock provider configuration."""
    provider_config = MagicMock()
    provider_config.name = "test-provider"
    provider_config.api_key = "test-api-key"
    provider_config.base_url = "https://api.test.com/v1"
    provider_config.api_format = "openai"
    provider_config.api_version = None
    return provider_config


@pytest.fixture(scope="session")
def integration_test_port():
    """Port for integration tests (matching development server)."""
    return int(os.environ.get("VDM_TEST_PORT", "8082"))


@pytest.fixture
def base_url(integration_test_port):
    """Base URL for integration tests."""
    return f"http://localhost:{integration_test_port}"


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: marks tests as unit tests (fast, no external deps)")
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (requires services)"
    )
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end tests (requires valid API keys)"
    )


def pytest_collection_modifyitems(config, items):
    """Add markers to tests based on their location."""
    for item in items:
        # Add unit marker to tests in unit/ directory
        if "tests/unit/" in str(item.fspath):
            item.add_marker(pytest.mark.unit)

        # Add integration marker to tests in integration/ directory
        elif "tests/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        # Legacy handling for tests in root tests/ directory
        elif "tests/" in str(item.fspath):
            # Assume they're unit tests if they use TestClient
            if "TestClient" in item.function.__code__.co_names:
                item.add_marker(pytest.mark.unit)
            # Otherwise mark as integration
            else:
                item.add_marker(pytest.mark.integration)
