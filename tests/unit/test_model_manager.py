"""
Unit tests for the ModelManager component.
"""

import os
from unittest.mock import Mock, patch

import pytest

from src.core.model_manager import ModelManager


@pytest.mark.unit
class TestModelManager:
    """Test cases for ModelManager functionality."""

    @pytest.fixture(autouse=True)
    def clean_env_before_each_test(self):
        """Clean environment variables before each test."""
        # Store original environment
        original_env = os.environ.copy()

        # Clear all alias variables for clean test
        for key in list(os.environ.keys()):
            if "_ALIAS_" in key:
                os.environ.pop(key, None)

        yield

        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)

    @pytest.fixture
    def mock_config(self):
        """Create a mock config with provider manager and alias manager."""
        mock_provider_manager = Mock()
        mock_provider_manager.default_provider = "poe"
        mock_provider_manager.parse_model_name.side_effect = lambda model: (
            (model.split(":", 1)[0], model.split(":", 1)[1]) if ":" in model else ("poe", model)
        )

        mock_alias_manager = Mock()
        mock_alias_manager.has_aliases.return_value = True
        mock_alias_manager.get_alias_count.return_value = 3

        mock_config = Mock()
        mock_config.provider_manager = mock_provider_manager
        mock_config.alias_manager = mock_alias_manager

        return mock_config

    def test_resolve_model_with_default_provider_alias(self, mock_config):
        """Test that model without provider prefix uses default provider for alias resolution."""
        # Mock alias manager to return provider-scoped alias
        mock_config.alias_manager.resolve_alias.return_value = "poe:grok-4.1-fast"

        model_manager = ModelManager(mock_config)

        # Test model without provider prefix
        provider, actual_model = model_manager.resolve_model("haiku")

        # Should call resolve_alias with default provider
        mock_config.alias_manager.resolve_alias.assert_called_once_with("haiku", provider="poe")
        mock_config.provider_manager.parse_model_name.assert_called_once_with("poe:grok-4.1-fast")

        assert provider == "poe"
        assert actual_model == "grok-4.1-fast"

    def test_resolve_model_with_explicit_provider_prefix(self, mock_config):
        """Test that model with explicit provider prefix uses cross-provider alias resolution."""
        # Mock alias manager to return provider-scoped alias
        mock_config.alias_manager.resolve_alias.return_value = "openai:gpt-4o-mini"

        model_manager = ModelManager(mock_config)

        # Test model with explicit provider prefix
        provider, actual_model = model_manager.resolve_model("openai:haiku")

        # Should call resolve_alias without provider parameter (for cross-provider search)
        mock_config.alias_manager.resolve_alias.assert_called_once_with("openai:haiku")
        mock_config.provider_manager.parse_model_name.assert_called_once_with("openai:gpt-4o-mini")

        assert provider == "openai"
        assert actual_model == "gpt-4o-mini"

    def test_resolve_model_no_alias_match(self, mock_config):
        """Test behavior when no alias match is found."""
        # Mock alias manager to return None (no match)
        mock_config.alias_manager.resolve_alias.return_value = None

        model_manager = ModelManager(mock_config)

        # Test model without provider prefix
        provider, actual_model = model_manager.resolve_model("unknown-model")

        # Should call resolve_alias with default provider
        mock_config.alias_manager.resolve_alias.assert_called_once_with(
            "unknown-model", provider="poe"
        )
        mock_config.provider_manager.parse_model_name.assert_called_once_with("unknown-model")

        assert provider == "poe"
        assert actual_model == "unknown-model"

    def test_resolve_model_no_alias_manager(self, mock_config):
        """Test behavior when alias manager is not available."""
        mock_config.alias_manager = None

        model_manager = ModelManager(mock_config)

        # Test model resolution
        provider, actual_model = model_manager.resolve_model("haiku")

        # Should directly parse model name
        mock_config.provider_manager.parse_model_name.assert_called_once_with("haiku")

        assert provider == "poe"
        assert actual_model == "haiku"

    def test_resolve_model_no_aliases_configured(self, mock_config):
        """Test behavior when no aliases are configured."""
        mock_config.alias_manager.has_aliases.return_value = False

        model_manager = ModelManager(mock_config)

        # Test model resolution
        provider, actual_model = model_manager.resolve_model("haiku")

        # Should directly parse model name without calling resolve_alias
        mock_config.alias_manager.resolve_alias.assert_not_called()
        mock_config.provider_manager.parse_model_name.assert_called_once_with("haiku")

        assert provider == "poe"
        assert actual_model == "haiku"

    def test_resolve_model_different_default_provider(self, mock_config):
        """Test with a different default provider."""
        mock_config.provider_manager.default_provider = "openai"
        mock_config.alias_manager.resolve_alias.return_value = "openai:gpt-4o-mini"

        model_manager = ModelManager(mock_config)

        # Test model without provider prefix
        provider, actual_model = model_manager.resolve_model("fast")

        # Should call resolve_alias with new default provider
        mock_config.alias_manager.resolve_alias.assert_called_once_with("fast", provider="openai")
        mock_config.provider_manager.parse_model_name.assert_called_once_with("openai:gpt-4o-mini")

        assert provider == "openai"
        assert actual_model == "gpt-4o-mini"

    def test_resolve_model_case_insensitive_provider_prefix(self, mock_config):
        """Test that provider prefix in model name is case insensitive."""
        # Mock alias manager to return provider-scoped alias
        mock_config.alias_manager.resolve_alias.return_value = "OPENAI:gpt-4o-mini"

        model_manager = ModelManager(mock_config)

        # Test model with uppercase provider prefix
        provider, actual_model = model_manager.resolve_model("OPENAI:haiku")

        # Should call resolve_alias without provider parameter (cross-provider search)
        mock_config.alias_manager.resolve_alias.assert_called_once_with("OPENAI:haiku")
        mock_config.provider_manager.parse_model_name.assert_called_once_with("OPENAI:gpt-4o-mini")

        # parse_model_name should handle case normalization
        assert provider.lower() == "openai"
        assert actual_model == "gpt-4o-mini"

    @patch.dict(os.environ, {"POE_ALIAS_HAIKU": "grok-4.1-fast"})
    def test_resolve_model_integration_with_real_alias_manager(self):
        """Integration test with real AliasManager and mocked ProviderManager."""
        from src.core.alias_manager import AliasManager

        # Mock provider manager
        with patch("src.core.provider_manager.ProviderManager") as mock_provider_manager_class:
            mock_provider_manager = mock_provider_manager_class.return_value
            mock_provider_manager.default_provider = "poe"
            mock_provider_manager._configs = {"poe": {}}
            mock_provider_manager.parse_model_name.side_effect = lambda model: (
                (model.split(":", 1)[0], model.split(":", 1)[1]) if ":" in model else ("poe", model)
            )

            # Create real config with real alias manager
            mock_config = Mock()
            mock_config.provider_manager = mock_provider_manager
            mock_config.alias_manager = AliasManager()

            model_manager = ModelManager(mock_config)

            # Test model without provider prefix (should use default provider)
            provider, actual_model = model_manager.resolve_model("haiku")

            # Should resolve to poe's alias
            assert provider == "poe"
            assert actual_model == "grok-4.1-fast"

    def test_resolve_model_logging_behavior(self, mock_config, caplog):
        """Test that appropriate log messages are generated."""
        mock_config.alias_manager.resolve_alias.return_value = "poe:grok-4.1-fast"
        mock_config.alias_manager.has_aliases.return_value = True
        mock_config.alias_manager.get_alias_count.return_value = 1

        with caplog.at_level("DEBUG"):
            model_manager = ModelManager(mock_config)
            provider, actual_model = model_manager.resolve_model("haiku")

            # Check that debug logs are generated
            assert any(
                "Starting model resolution for: 'haiku'" in record.message
                for record in caplog.records
            )
            assert any(
                "Resolving alias 'haiku' with provider scope 'poe'" in record.message
                for record in caplog.records
            )
            assert any(
                "Alias resolved: 'haiku' -> 'poe:grok-4.1-fast'" in record.message
                for record in caplog.records
            )
            assert any(
                "Parsed provider: 'poe', actual model: 'grok-4.1-fast'" in record.message
                for record in caplog.records
            )

    @patch.dict(os.environ, {"XPOE_ALIAS_HAIKU": "zai:haiku"})
    def test_cross_provider_alias_via_model_manager(self):
        """Test cross-provider alias through full ModelManager flow."""
        from src.core.alias_manager import AliasManager

        # Mock provider manager
        with patch("src.core.provider_manager.ProviderManager") as mock_provider_manager_class:
            mock_provider_manager = mock_provider_manager_class.return_value
            mock_provider_manager.default_provider = "xpoe"
            mock_provider_manager._configs = {"xpoe": {}}
            mock_provider_manager.parse_model_name.side_effect = lambda model: (
                (model.split(":", 1)[0], model.split(":", 1)[1])
                if ":" in model
                else ("xpoe", model)
            )

            # Create real config with real alias manager
            mock_config = Mock()
            mock_config.provider_manager = mock_provider_manager
            mock_config.alias_manager = AliasManager()

            model_manager = ModelManager(mock_config)

            # Request "haiku" with default provider "xpoe"
            # Where xpoe.aliases.haiku = "zai:haiku"
            # Should resolve to provider="zai", model="haiku" (not "xpoe:zai:haiku")
            provider, actual_model = model_manager.resolve_model("haiku")

            # The cross-provider alias "zai:haiku" should be parsed correctly
            assert provider == "zai"
            assert actual_model == "haiku"
