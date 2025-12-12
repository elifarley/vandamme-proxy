"""Shared pytest configuration and fixtures for Vandamme Proxy tests."""

import os
import sys
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv

# Import HTTP mocking fixtures from fixtures module
pytest_plugins = ["tests.fixtures.mock_http"]

# Import test configuration constants
from tests.config import TEST_API_KEYS, TEST_ENDPOINTS, DEFAULT_TEST_CONFIG


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


@pytest.fixture(scope="function", autouse=True)
def setup_test_environment_for_unit_tests():
    """Setup test environment for unit tests with minimal provider configuration.

    This fixture runs before each test to ensure a clean environment.
    Unit tests should only need minimal provider setup since all HTTP calls are mocked.
    """
    import os
    import sys

    # Load basic test configuration (non-sensitive settings only)
    # Use dotenv_path to avoid loading from home directory .env file
    load_dotenv(dotenv_path=".env.test")

    # Store original values
    original_env = {}

    # Minimal test API keys - these are NOT real keys and will never be used
    # since RESPX mocks all HTTP requests
    test_api_keys = {
        "OPENAI_API_KEY": "test-openai-key-mocked",
        "ANTHROPIC_API_KEY": "test-anthropic-key-mocked",
        "POE_API_KEY": "test-poe-key-mocked",
        "GLM_API_KEY": "test-glm-key-mocked",
        "VDM_DEFAULT_PROVIDER": "openai",
    }

    try:
        # Store original values
        for key in test_api_keys:
            original_env[key] = os.environ.get(key)

        # Clear any existing test aliases
        for key in list(os.environ.keys()):
            if key.startswith("VDM_ALIAS_"):
                os.environ.pop(key, None)

        # Set minimal test environment
        os.environ.update(test_api_keys)

        # Force reimport of modules to pick up new environment
        modules_to_reload = [
            "src.core.config",
            "src.core.provider_manager",
            "src.core.client",
            "src.core.alias_manager",
            "src.core.model_manager",
            # Also reload the endpoints module since it imports config at module level
            "src.api.endpoints",
        ]

        for module_name in modules_to_reload:
            if module_name in sys.modules:
                del sys.modules[module_name]

        # Fresh import with new environment
        # This will create new instances with the updated environment
        import src.core.config

        # Reset the global config instance to pick up new environment
        # The config module creates a global `config` instance that we need to replace
        config_class = src.core.config.Config
        src.core.config.config = config_class()

        import src.api.endpoints
        import src.main

        yield

    finally:
        # Restore original values
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


