"""Unit tests for ProviderConfig OAuth mode."""

import pytest

from src.core.provider_config import (
    OAUTH_SENTINEL,
    PASSTHROUGH_SENTINEL,
    AuthMode,
    ProviderConfig,
)


@pytest.mark.unit
class TestProviderConfigOAuth:
    """Test cases for ProviderConfig OAuth authentication mode."""

    def test_uses_oauth_property_with_oauth_mode(self):
        """Test uses_oauth property returns True for OAuth mode."""

        config = ProviderConfig(
            name="test_provider",
            api_key="",
            base_url="https://api.test.com/v1",
            auth_mode=AuthMode.OAUTH,
        )

        assert config.uses_oauth is True

    def test_uses_oauth_property_with_api_key_mode(self):
        """Test uses_oauth property returns False for API key mode."""

        config = ProviderConfig(
            name="test_provider",
            api_key="sk-test-key",
            base_url="https://api.test.com/v1",
            auth_mode=AuthMode.API_KEY,
        )

        assert config.uses_oauth is False

    def test_uses_oauth_property_with_passthrough_mode(self):
        """Test uses_oauth property returns False for passthrough mode."""

        config = ProviderConfig(
            name="test_provider",
            api_key=PASSTHROUGH_SENTINEL,
            base_url="https://api.test.com/v1",
            auth_mode=AuthMode.PASSTHROUGH,
        )

        assert config.uses_oauth is False

    def test_oauth_sentinel_detection_in_post_init(self):
        """Test that !OAUTH sentinel sets auth_mode to OAuth."""

        config = ProviderConfig(
            name="test_provider",
            api_key=OAUTH_SENTINEL,
            base_url="https://api.test.com/v1",
            auth_mode=AuthMode.API_KEY,  # Will be overridden by __post_init__
        )

        assert config.api_key == OAUTH_SENTINEL
        assert config.auth_mode == AuthMode.OAUTH
        assert config.uses_oauth is True

    def test_oauth_allows_empty_api_key(self):
        """Test that OAuth mode allows empty API key."""

        # Should not raise ValueError for OAuth mode
        config = ProviderConfig(
            name="test_provider",
            api_key="",
            base_url="https://api.test.com/v1",
            auth_mode=AuthMode.OAUTH,
        )

        assert config.api_key == ""
        assert config.auth_mode == AuthMode.OAUTH

    def test_api_key_mode_requires_api_key(self):
        """Test that API key mode requires non-empty API key."""

        with pytest.raises(ValueError) as exc_info:
            ProviderConfig(
                name="test_provider",
                api_key="",
                base_url="https://api.test.com/v1",
                auth_mode=AuthMode.API_KEY,
            )

        assert "API key is required" in str(exc_info.value)

    def test_passthrough_mode_requires_api_key(self):
        """Test that passthrough mode requires API key (the sentinel)."""

        with pytest.raises(ValueError) as exc_info:
            ProviderConfig(
                name="test_provider",
                api_key="",
                base_url="https://api.test.com/v1",
                auth_mode=AuthMode.PASSTHROUGH,
            )

        assert "API key is required" in str(exc_info.value)

    def test_oauth_sentinel_in_api_keys_raises_error(self):
        """Test that OAuth sentinel in api_keys list raises error."""

        with pytest.raises(ValueError) as exc_info:
            ProviderConfig(
                name="test_provider",
                api_key="sk-first-key",
                api_keys=["sk-first-key", OAUTH_SENTINEL],
                base_url="https://api.test.com/v1",
            )

        assert "mixed configuration" in str(exc_info.value)
        assert "!OAUTH" in str(exc_info.value)

    def test_passthrough_sentinel_in_api_keys_raises_error(self):
        """Test that passthrough sentinel in api_keys list raises error."""

        with pytest.raises(ValueError) as exc_info:
            ProviderConfig(
                name="test_provider",
                api_key="sk-first-key",
                api_keys=["sk-first-key", PASSTHROUGH_SENTINEL],
                base_url="https://api.test.com/v1",
            )

        assert "mixed configuration" in str(exc_info.value)
        assert "!PASSTHRU" in str(exc_info.value)

    def test_get_api_keys_returns_empty_string_for_oauth_mode(self):
        """Test that get_api_keys returns list with empty string for OAuth providers.

        OAuth providers use token-based auth, not static API keys.
        The get_api_keys() method will return the empty api_key as a single-element list.
        """

        config = ProviderConfig(
            name="test_provider",
            api_key="",
            base_url="https://api.test.com/v1",
            auth_mode=AuthMode.OAUTH,
        )

        # For OAuth mode with empty api_key, get_api_keys returns [""]
        # This is the current behavior - OAuth providers should use TokenManager
        # instead of get_api_keys()
        keys = config.get_api_keys()
        assert keys == [""]

    def test_oauth_config_with_all_fields(self):
        """Test creating a complete OAuth provider config."""

        config = ProviderConfig(
            name="chatgpt",
            api_key="",
            base_url="https://api.openai.com/v1",
            api_format="openai",
            auth_mode=AuthMode.OAUTH,
            timeout=120,
            max_retries=3,
            custom_headers={"X-Custom": "value"},
        )

        assert config.name == "chatgpt"
        assert config.api_key == ""
        assert config.base_url == "https://api.openai.com/v1"
        assert config.uses_oauth is True
        assert config.is_anthropic_format is False
        assert config.timeout == 120
        assert config.max_retries == 3
        assert config.custom_headers == {"X-Custom": "value"}

    def test_uses_passthrough_vs_uses_oauth_are_mutually_exclusive(self):
        """Test that uses_passthrough and uses_oauth are mutually exclusive."""

        oauth_config = ProviderConfig(
            name="oauth_provider",
            api_key="",
            base_url="https://api.test.com/v1",
            auth_mode=AuthMode.OAUTH,
        )

        passthrough_config = ProviderConfig(
            name="passthrough_provider",
            api_key=PASSTHROUGH_SENTINEL,
            base_url="https://api.test.com/v1",
            auth_mode=AuthMode.PASSTHROUGH,
        )

        assert oauth_config.uses_oauth is True
        assert oauth_config.uses_passthrough is False

        assert passthrough_config.uses_passthrough is True
        assert passthrough_config.uses_oauth is False

    def test_default_auth_mode_is_api_key(self):
        """Test that default auth_mode is API_KEY when not specified."""

        config = ProviderConfig(
            name="test_provider",
            api_key="sk-test",
            base_url="https://api.test.com/v1",
        )

        assert config.auth_mode == AuthMode.API_KEY
        assert config.uses_oauth is False
        assert config.uses_passthrough is False
