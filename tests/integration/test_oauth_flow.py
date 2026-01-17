"""Integration tests for OAuth flow."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.provider.client_factory import ClientFactory
from src.core.provider_config import AuthMode, ProviderConfig


@pytest.mark.integration
class TestOAuthFlow:
    """Integration tests for OAuth authentication flow."""

    def test_token_manager_creation_with_oauth_provider(self):
        """Test TokenManager is created with correct storage path for OAuth providers."""

        # Create an OAuth provider config
        config = ProviderConfig(
            name="chatgpt",
            api_key="",
            base_url="https://api.openai.com/v1",
            auth_mode=AuthMode.OAUTH,
        )

        # Mock TokenManager and FileSystemAuthStorage
        with (
            patch("src.core.provider.client_factory.TokenManager") as mock_token_mgr_class,
            patch("src.core.provider.client_factory.FileSystemAuthStorage") as mock_storage_class,
        ):
            mock_storage = MagicMock()
            mock_storage_class.return_value = mock_storage
            mock_token_mgr = MagicMock()
            mock_token_mgr_class.return_value = mock_token_mgr

            factory = ClientFactory()

            # This should create TokenManager with the correct storage path
            factory.get_or_create_client(config)

            # Verify FileSystemAuthStorage was created with correct path
            expected_path = Path.home() / ".vandamme" / "oauth" / "chatgpt"
            mock_storage_class.assert_called_once_with(base_path=expected_path)

            # Verify TokenManager was instantiated
            mock_token_mgr_class.assert_called_once()
            call_kwargs = mock_token_mgr_class.call_args[1]
            assert call_kwargs["storage"] == mock_storage
            assert call_kwargs["raise_on_refresh_failure"] is False

    def test_oauth_provider_uses_token_manager_in_client(self):
        """Test that OAuth providers pass TokenManager to client instances."""

        config = ProviderConfig(
            name="chatgpt",
            api_key="",
            base_url="https://api.openai.com/v1",
            auth_mode=AuthMode.OAUTH,
        )

        with (
            patch("src.core.provider.client_factory.TokenManager") as mock_token_mgr_class,
            patch("src.core.provider.client_factory.FileSystemAuthStorage"),
        ):
            mock_token_mgr = MagicMock()
            mock_token_mgr_class.return_value = mock_token_mgr

            factory = ClientFactory()
            client = factory.get_or_create_client(config)

            # Verify the client was created (OpenAI client for openai format)
            assert client is not None

            # For OAuth mode, the client should have _oauth_token_manager set
            # This is verified by checking that TokenManager was created
            mock_token_mgr_class.assert_called_once()

    def test_non_oauth_provider_skips_token_manager(self):
        """Test that non-OAuth providers don't create TokenManager."""

        config = ProviderConfig(
            name="openai",
            api_key="sk-test-key",
            base_url="https://api.openai.com/v1",
            auth_mode=AuthMode.API_KEY,
        )

        with patch("src.core.provider.client_factory.TokenManager") as mock_token_mgr_class:
            factory = ClientFactory()
            factory.get_or_create_client(config)

            # TokenManager should NOT be created for API_KEY mode
            mock_token_mgr_class.assert_not_called()

    def test_passthrough_provider_skips_token_manager(self):
        """Test that passthrough providers don't create TokenManager."""

        config = ProviderConfig(
            name="anthropic",
            api_key="!PASSTHRU",
            base_url="https://api.anthropic.com",
            auth_mode=AuthMode.PASSTHROUGH,
            api_format="anthropic",
        )

        with patch("src.core.provider.client_factory.TokenManager") as mock_token_mgr_class:
            factory = ClientFactory()
            factory.get_or_create_client(config)

            # TokenManager should NOT be created for passthrough mode
            mock_token_mgr_class.assert_not_called()

    def test_oauth_provider_with_anthropic_format(self):
        """Test OAuth provider with Anthropic API format."""

        config = ProviderConfig(
            name="anthropic-oauth",
            api_key="",
            base_url="https://api.anthropic.com",
            auth_mode=AuthMode.OAUTH,
            api_format="anthropic",
        )

        with (
            patch("src.core.provider.client_factory.TokenManager") as mock_token_mgr_class,
            patch("src.core.provider.client_factory.FileSystemAuthStorage"),
        ):
            mock_token_mgr = MagicMock()
            mock_token_mgr_class.return_value = mock_token_mgr

            factory = ClientFactory()
            client = factory.get_or_create_client(config)

            # Verify client was created
            assert client is not None

            # Verify storage path is provider-specific
            expected_path = Path.home() / ".vandamme" / "oauth" / "anthropic-oauth"

            from src.core.provider.client_factory import FileSystemAuthStorage

            FileSystemAuthStorage.assert_called_once_with(base_path=expected_path)

    def test_multiple_oauth_providers_have_separate_storage(self):
        """Test that multiple OAuth providers use separate storage paths."""

        providers = [
            ProviderConfig(
                name="chatgpt",
                api_key="",
                base_url="https://api.openai.com/v1",
                auth_mode=AuthMode.OAUTH,
            ),
            ProviderConfig(
                name="another-oauth-provider",
                api_key="",
                base_url="https://api.example.com/v1",
                auth_mode=AuthMode.OAUTH,
            ),
        ]

        with (
            patch("src.core.provider.client_factory.TokenManager"),
            patch("src.core.provider.client_factory.FileSystemAuthStorage") as mock_storage_class,
        ):
            factory = ClientFactory()

            expected_paths = [
                Path.home() / ".vandamme" / "oauth" / "chatgpt",
                Path.home() / ".vandamme" / "oauth" / "another-oauth-provider",
            ]

            for _i, config in enumerate(providers):
                factory.get_or_create_client(config)

            # Verify each provider got its own storage path
            assert mock_storage_class.call_count == 2

            actual_paths = [call.kwargs["base_path"] for call in mock_storage_class.call_args_list]

            for expected_path in expected_paths:
                assert expected_path in actual_paths

    def test_client_factory_caches_oauth_clients(self):
        """Test that OAuth clients are cached per provider."""

        config = ProviderConfig(
            name="chatgpt",
            api_key="",
            base_url="https://api.openai.com/v1",
            auth_mode=AuthMode.OAUTH,
        )

        with (
            patch("src.core.provider.client_factory.TokenManager") as mock_token_mgr_class,
            patch("src.core.provider.client_factory.FileSystemAuthStorage"),
        ):
            mock_token_mgr = MagicMock()
            mock_token_mgr_class.return_value = mock_token_mgr

            factory = ClientFactory()

            client1 = factory.get_or_create_client(config)
            client2 = factory.get_or_create_client(config)

            # Should return the same cached instance
            assert client1 is client2

            # TokenManager should only be created once
            assert mock_token_mgr_class.call_count == 1

    def test_oauth_provider_missing_token_manager_import(self):
        """Test error handling when TokenManager import fails."""

        config = ProviderConfig(
            name="chatgpt",
            api_key="",
            base_url="https://api.openai.com/v1",
            auth_mode=AuthMode.OAUTH,
        )

        # Simulate import error by making TokenManager None
        with (
            patch("src.core.provider.client_factory.TokenManager", None),
            patch("src.core.provider.client_factory.FileSystemAuthStorage", None),
        ):
            factory = ClientFactory()

            with pytest.raises(ImportError) as exc_info:
                factory.get_or_create_client(config)

            assert "oauth" in str(exc_info.value).lower()
