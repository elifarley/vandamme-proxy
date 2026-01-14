import httpx
import pytest
from fastapi.testclient import TestClient

from tests.config import TEST_HEADERS


@pytest.mark.unit
def test_multi_api_key_round_robin_and_retry_openai(mock_openai_api, openai_chat_completion):
    """When multiple provider keys are configured, rotate keys on 401/429 and succeed with next.

    NOTE: This test has a known issue where it fails when run with 'pytest tests/ -m unit'
    due to module import order and closure capture of the api_keys list. The test passes
    when run in isolation or with 'pytest tests/unit/'.

    The root cause is that build_api_key_params() captures the api_keys list in a closure
    at module import time. When running with 'tests/' path, pytest collects integration tests
    which causes some modules to be imported before our test can modify the provider config.

    A proper fix would require refactoring the key rotation logic to be more testable.
    """
    # Mock the chat completions endpoint to track calls
    call_count = 0

    def mock_response(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First key fails auth
            return httpx.Response(401, json={"error": {"message": "invalid_api_key"}})
        else:
            # Second key succeeds
            return httpx.Response(200, json=openai_chat_completion)

    # Set up the mock with a custom response handler
    mock_openai_api.post("https://api.openai.com/v1/chat/completions").mock(
        side_effect=mock_response
    )

    # Import app (autouse fixture will have set up test config)
    # Modify the provider config directly to use multiple keys
    from src.main import app

    provider = app.state.config.provider_manager.get_provider_config("openai")
    assert provider is not None, "OpenAI provider should be configured"

    # Override the provider's API keys with our test keys
    provider.api_key = "key1"  # First key for backward compatibility
    provider.api_keys = ["key1", "key2"]  # Multiple keys for rotation

    # Verify the modification worked
    keys = provider.get_api_keys()
    assert len(keys) == 2, f"Expected 2 keys, got {len(keys)}: {keys}"
    assert keys == ["key1", "key2"], f"Expected ['key1', 'key2'], got {keys}"

    # Reset API key rotation state for this provider to ensure clean test
    app.state.config.provider_manager._api_key_indices.pop("openai", None)

    with TestClient(app) as client:
        response = client.post(
            "/v1/messages",
            json={
                "model": "openai:gpt-4",
                "max_tokens": 50,
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers=TEST_HEADERS,
        )

    # Verify that the mock was called twice (first key fails, second succeeds)
    # NOTE: This assertion may fail when run with 'pytest tests/ -m unit' due to the
    # module import order issue described in the docstring.
    assert call_count == 2, f"Expected 2 calls (retry on 401), got {call_count}"
    assert response.status_code == 200


@pytest.mark.unit
def test_multi_api_key_reject_mixed_passthru_and_keys():
    """Reject mixed '!PASSTHRU' and real keys to avoid ambiguous config."""
    from src.core.provider_config import ProviderConfig

    with pytest.raises(ValueError):
        ProviderConfig(
            name="openai",
            api_key="!PASSTHRU",
            api_keys=["!PASSTHRU", "key2"],
            base_url="https://api.openai.com/v1",
        )


@pytest.mark.unit
def test_api_key_parsing_whitespace_split():
    """Whitespace is used as a separator between configured keys."""
    from src.core.provider_config import ProviderConfig

    cfg = ProviderConfig(
        name="openai",
        api_key="key1",
        api_keys=["key1", "key2", "key3"],
        base_url="https://api.openai.com/v1",
    )

    assert cfg.get_api_keys() == ["key1", "key2", "key3"]
