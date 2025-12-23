"""Unit tests for alias_manager module."""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.core.alias_manager import AliasManager


@pytest.mark.unit
class TestAliasManager:
    """Test cases for AliasManager."""

    def test_load_aliases_from_env(self):
        """Test loading aliases from environment variables."""
        with (
            patch.dict(
                os.environ,
                {
                    "POE_ALIAS_HAIKU": "grok-4.1-fast-non-reasoning",
                    "OPENAI_ALIAS_FAST": "gpt-4o-mini",
                    "ANTHROPIC_ALIAS_CHAT": "claude-3-5-sonnet-20241022",
                    "OTHER_VAR": "should_be_ignored",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            # Mock provider manager with available providers
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}, "openai": {}, "anthropic": {}}

            # Mock empty fallbacks to avoid interference
            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}

                alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            assert len(aliases) == 3
            assert aliases["poe"]["haiku"] == "grok-4.1-fast-non-reasoning"
            assert aliases["openai"]["fast"] == "gpt-4o-mini"
            assert aliases["anthropic"]["chat"] == "claude-3-5-sonnet-20241022"

    def test_case_insensitive_storage(self):
        """Test that aliases are stored in lowercase."""
        with (
            patch.dict(os.environ, {"OPENAI_ALIAS_TEST": "gpt-4"}),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"openai": {}}

            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            assert "test" in aliases["openai"]
            assert aliases["openai"]["test"] == "gpt-4"

    def test_resolve_exact_match(self):
        """Test resolving exact alias matches."""
        with (
            patch.dict(os.environ, {"POE_ALIAS_HAIKU": "grok-4.1-fast"}),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}

            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()

            assert alias_manager.resolve_alias("haiku") == "poe:grok-4.1-fast"
            assert alias_manager.resolve_alias("HAIKU") == "poe:grok-4.1-fast"

    def test_resolve_substring_match(self):
        """Test resolving substring alias matches."""
        with (
            patch.dict(os.environ, {"POE_ALIAS_HAIKU": "grok-4.1-fast"}),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}

            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()

            assert alias_manager.resolve_alias("my-haiku-model") == "poe:grok-4.1-fast"

    def test_resolve_longest_match_priority(self):
        """Test that longer matches take priority."""
        with (
            patch.dict(
                os.environ,
                {
                    "POE_ALIAS_HAIKU": "grok-4.1-fast",
                    "POE_ALIAS_HAIKUFAST": "grok-4.1-fast-non-reasoning",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}

            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()

            assert alias_manager.resolve_alias("haikufast") == "poe:grok-4.1-fast-non-reasoning"
            assert (
                alias_manager.resolve_alias("my-haikufast-model")
                == "poe:grok-4.1-fast-non-reasoning"
            )

    def test_resolve_alphabetical_priority_on_tie(self):
        """Test that alphabetical order breaks ties."""
        with (
            patch.dict(
                os.environ,
                {
                    "POE_ALIAS_BETA": "model-beta",
                    "POE_ALIAS_ALPHA": "model-alpha",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}

            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()

            # Both are exact matches based on variations; alphabetical alias name wins
            assert alias_manager.resolve_alias("alpha") == "poe:model-alpha"

    def test_empty_alias_value_skip(self):
        """Test that empty alias values are skipped."""
        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_ALIAS_EMPTY": "",
                    "POE_ALIAS_SPACES": "   ",
                    "ANTHROPIC_ALIAS_VALID": "claude-3-5-sonnet-20241022",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
            patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"openai": {}, "poe": {}, "anthropic": {}}

            # Mock empty fallbacks to avoid interference
            mock_loader_instance = mock_config_loader.return_value
            mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}

            alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            assert aliases == {"anthropic": {"valid": "claude-3-5-sonnet-20241022"}}

    def test_invalid_provider_skip(self):
        """Test that aliases for unknown providers are accepted (lazy validation)."""
        with (
            patch.dict(os.environ, {"UNKNOWN_ALIAS_X": "model"}),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"openai": {}}

            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()

            # With lazy validation, AliasManager accepts any provider alias.
            # Validation will occur downstream when the alias is actually used.
            assert alias_manager.get_all_aliases() == {"unknown": {"x": "model"}}

    def test_get_all_aliases_is_copy(self):
        """Test get_all_aliases returns a copy."""
        with (
            patch.dict(os.environ, {"OPENAI_ALIAS_FAST": "gpt-4o-mini"}),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"openai": {}}

            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            aliases["openai"]["fast"] = "mutated"
            assert alias_manager.get_all_aliases()["openai"]["fast"] == "gpt-4o-mini"

    def test_has_aliases(self):
        """Test has_aliases method."""
        with (
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager_class,
            patch.dict(os.environ, {}, clear=True),
        ):
            mock_pm = mock_provider_manager_class.return_value
            mock_pm.load_provider_configs.return_value = None

            # No providers configured
            mock_pm._configs = {}
            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()
            assert not alias_manager.has_aliases()

            # No aliases (provider configured but no aliases for it)
            mock_pm._configs = {"unknownprovider": {}}
            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()
            assert not alias_manager.has_aliases()

        # Explicit aliases
        with (
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager_class,
            patch.dict(os.environ, {"OPENAI_ALIAS_FAST": "gpt-4o-mini"}),
        ):
            mock_pm = mock_provider_manager_class.return_value
            mock_pm._configs = {"openai": {}}

            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()
            assert alias_manager.has_aliases()

        # With fallback aliases (poe has defaults)
        with patch("src.core.provider_manager.ProviderManager") as mock_provider_manager_class:
            mock_pm = mock_provider_manager_class.return_value
            mock_pm._configs = {"poe": {}}
            alias_manager = AliasManager()
            assert alias_manager.has_aliases()

    def test_get_alias_count(self):
        """Test get_alias_count method."""
        with (
            patch.dict(os.environ, {"POE_ALIAS_HAIKU": "grok-4.1-fast"}),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}

            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()

            assert alias_manager.get_alias_count() == 1

    def test_resolve_alias_provider_scope_with_fallbacks(self):
        """Test provider-scoped resolution works with fallback aliases."""
        with patch("src.core.provider_manager.ProviderManager") as mock_provider_manager:
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}
            alias_manager = AliasManager()

            assert alias_manager.resolve_alias("haiku", provider="poe") == "poe:gpt-5.1-mini"
            # Provider-scoped resolution uses fallback defaults for the scoped provider.
            assert alias_manager.resolve_alias("haiku", provider="openai") == "openai:gpt-5.1-mini"

    def test_literal_name_through_model_manager(self):
        """Test that literal names work correctly through ModelManager.resolve_model()."""
        with (
            patch.dict(os.environ, {"POE_ALIAS_HAIKU": "should-not-be-used"}),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
            patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm.load_provider_configs.return_value = None
            mock_pm._configs = {"poe": {}}
            mock_pm.default_provider = "poe"
            mock_pm.parse_model_name.return_value = ("poe", "my-literal-model")

            mock_loader_instance = mock_config_loader.return_value
            mock_loader_instance.get_defaults.return_value = {}
            mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
            mock_loader_instance.get_fallback_aliases.return_value = {}

            # Create a mock Config with mocked provider_manager
            mock_config = MagicMock()
            mock_config.provider_manager = mock_pm
            mock_config.alias_manager = None

            from src.core.model_manager import ModelManager

            model_manager = ModelManager(mock_config)
            provider, model = model_manager.resolve_model("!my-literal-model")

            # The literal model name passes through alias resolution unchanged,
            # then ProviderManager.parse_model_name is called on it
            mock_pm.parse_model_name.assert_called_with("!my-literal-model")
            assert provider == "poe"
            assert model == "my-literal-model"
