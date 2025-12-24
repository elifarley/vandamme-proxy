"""Shared pytest configuration and fixtures for Vandamme Proxy tests."""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Import HTTP mocking fixtures from fixtures module
pytest_plugins = ["tests.fixtures.mock_http"]

# Import test configuration constants


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
    config.proxy_api_key = None
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
        # Add unit marker to tests in unit/ and middleware/ directories
        if "tests/unit/" in str(item.fspath) or "tests/middleware/" in str(item.fspath):
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

    Strategy:
    1. Set minimal test environment variables
    2. Reset the global config singleton
    3. Clear module cache for affected modules
    4. Restore environment after test completes
    """
    import os

    # Store original environment
    original_env = os.environ.copy()

    # Store original sys.modules state for cleanup
    original_modules = set(sys.modules.keys())

    try:
        # Clear any existing test aliases (both old and new patterns)
        for key in list(os.environ.keys()):
            if "_ALIAS_" in key:
                os.environ.pop(key, None)

        # Set minimal test environment from centralized config
        from tests.config import DEFAULT_TEST_CONFIG, TEST_API_KEYS, TEST_ENDPOINTS

        test_env = {
            # Dummy provider keys for unit tests.
            # These are NOT used to make real network calls (RESPX intercepts HTTP);
            # they exist solely so provider configuration loads and request routing
            # code paths can be exercised offline.
            "OPENAI_API_KEY": TEST_API_KEYS["OPENAI"],
            "ANTHROPIC_API_KEY": TEST_API_KEYS["ANTHROPIC"],
            "ANTHROPIC_BASE_URL": TEST_ENDPOINTS["ANTHROPIC"],
            "ANTHROPIC_API_FORMAT": "anthropic",
            "POE_API_KEY": TEST_API_KEYS["POE"],
            "GLM_API_KEY": TEST_API_KEYS["GLM"],
            "KIMI_API_KEY": "test-kimi-key",
            "VDM_DEFAULT_PROVIDER": DEFAULT_TEST_CONFIG["DEFAULT_PROVIDER"],
            "LOG_LEVEL": DEFAULT_TEST_CONFIG["LOG_LEVEL"],
            "LOG_REQUEST_METRICS": "true",
            # Ensure top-models endpoints work deterministically in unit tests.
            "TOP_MODELS_SOURCE": "manual_rankings",
        }

        os.environ.update(test_env)

        # Clear module cache for modules that need fresh import
        modules_to_clear = [
            "src.core.config",
            "src.core.provider_manager",
            "src.core.provider_config",
            "src.core.client",
            "src.core.anthropic_client",
            "src.core.alias_manager",
            "src.core.alias_config",
            "src.core.model_manager",
            "src.api.endpoints",
            "src.main",
        ]

        for module_name in modules_to_clear:
            if module_name in sys.modules:
                del sys.modules[module_name]

        # Import and reset the config singleton
        import src.core.config

        src.core.config.Config.reset_singleton()

        # Reset ModelManager lazy singleton for test isolation
        try:
            from src.core.model_manager import reset_model_manager_singleton

            reset_model_manager_singleton()
        except Exception:
            # Best-effort: avoid breaking tests if import order changes
            pass

        # Reset the AliasConfigLoader cache for test isolation
        from src.core.alias_config import AliasConfigLoader

        AliasConfigLoader.reset_cache()

        # Force reload of modules that import config at module level
        # This ensures they get the new config instance after reset
        modules_to_reload = [
            "src.api.endpoints",
            "src.main",
        ]

        for module_name in modules_to_reload:
            if module_name in sys.modules:
                del sys.modules[module_name]

        # Import app modules after config reset to ensure they use the fresh config
        import src.main  # noqa: F401

        yield

    finally:
        # Restore original environment completely
        os.environ.clear()
        os.environ.update(original_env)

        # Clear any modules imported during test
        current_modules = set(sys.modules.keys())
        test_modules = current_modules - original_modules
        for module_name in test_modules:
            if module_name.startswith("src.") or module_name.startswith("tests."):
                sys.modules.pop(module_name, None)
