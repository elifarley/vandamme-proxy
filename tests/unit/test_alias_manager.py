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
        with (
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
            patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}, "openai": {}}

            # Mock the config loader to provide fallback aliases without project overrides
            mock_loader_instance = mock_config_loader.return_value
            mock_loader_instance.load_config.return_value = {
                "providers": {
                    "poe": {
                        "aliases": {
                            "haiku": "gpt-5.1-mini",
                            "sonnet": "gpt-5.1-codex-mini",
                            "opus": "gpt-5.1-codex-max",
                        }
                    },
                    "openai": {
                        "aliases": {
                            "haiku": "gpt-5.1-mini",
                            "sonnet": "gpt-5.1-codex",
                            "opus": "gpt-5.2",
                        }
                    },
                },
                "defaults": {"default-provider": "openai"},
            }
            mock_loader_instance.get_defaults.return_value = {"default-provider": "openai"}

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

    def test_resolve_cross_provider_alias_no_double_prefix(self):
        """Test that cross-provider alias doesn't get double prefix."""
        with (
            patch.dict(
                os.environ,
                {
                    "XPOE_ALIAS_HAIKU": "zai:haiku",
                    # Need to add a zai alias so "zai" becomes a known provider
                    "ZAI_ALIAS_TEST": "test-model",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"xpoe": {}, "zai": {}}

            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()

            # Cross-provider alias target should be returned as-is (not "xpoe:zai:haiku")
            # since "zai" IS a known provider
            assert alias_manager.resolve_alias("haiku", provider="xpoe") == "zai:haiku"

    def test_resolve_bare_model_target_gets_prefix(self):
        """Test that bare model targets still get provider prefix."""
        with (
            patch.dict(os.environ, {"XPOE_ALIAS_HAIKU": "some-model"}),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"xpoe": {}}

            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()

            # Bare model target should get provider prefix added
            assert alias_manager.resolve_alias("haiku", provider="xpoe") == "xpoe:some-model"

    def test_alias_target_with_colon_gets_provider_prefix(self):
        """Test that model names with colons but no valid provider get prefixed."""
        with (
            patch.dict(
                os.environ,
                {"OPENROUTER_ALIAS_FREE": "kwaipilot/kat-coder-pro:free"},
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"openrouter": {}}

            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()

            # Model names with colons are NOT provider prefixes if the "provider" isn't known
            # Since "kwaipilot/kat-coder-pro" is not a known provider, add source provider prefix
            assert (
                alias_manager.resolve_alias("free", provider="openrouter")
                == "openrouter:kwaipilot/kat-coder-pro:free"
            )

    def test_cross_provider_alias_with_known_provider(self):
        """Test that cross-provider aliases with valid provider prefixes work correctly."""
        with (
            patch.dict(
                os.environ,
                {
                    "OPENROUTER_ALIAS_FAST": "openai:gpt-4o-mini",
                    # Need to add an openai alias so "openai" becomes a known provider
                    "OPENAI_ALIAS_TEST": "test-model",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"openrouter": {}, "openai": {}}

            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()

            # Since "openai" IS a known provider (has at least one alias), this is treated
            # as a cross-provider alias and returned as-is (not prefixed with "openrouter:")
            assert (
                alias_manager.resolve_alias("fast", provider="openrouter") == "openai:gpt-4o-mini"
            )

    def test_chained_alias_resolution_single_provider(self):
        """Test that chained aliases (fast -> sonnet -> gpt-4o-mini) resolve to final model."""
        with (
            patch.dict(
                os.environ,
                {
                    "POE_ALIAS_FAST": "sonnet",
                    "POE_ALIAS_SONNET": "gpt-4o-mini",
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

            # fast -> sonnet -> gpt-4o-mini should fully resolve to gpt-4o-mini
            assert alias_manager.resolve_alias("fast", provider="poe") == "poe:gpt-4o-mini"

    def test_chained_alias_resolution_cross_provider(self):
        """Test chained aliases with cross-provider references."""
        with (
            patch.dict(
                os.environ,
                {
                    "POE_ALIAS_FAST": "openai:sonnet",
                    "OPENAI_ALIAS_SONNET": "gpt-4o",
                    # Need at least one alias per provider to make them "known"
                    "POE_ALIAS_OTHER": "other-model",
                    "OPENAI_ALIAS_OTHER": "other-model",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}, "openai": {}}

            with patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader:
                mock_loader_instance = mock_config_loader.return_value
                mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}
                mock_loader_instance.get_defaults.return_value = {}
                alias_manager = AliasManager()

            # fast -> openai:sonnet -> gpt-4o should resolve to openai:gpt-4o
            assert alias_manager.resolve_alias("fast", provider="poe") == "openai:gpt-4o"

    def test_chained_alias_cycle_detection(self):
        """Test that circular alias references are detected and stopped."""
        with (
            patch.dict(
                os.environ,
                {
                    "POE_ALIAS_A": "b",
                    "POE_ALIAS_B": "c",
                    "POE_ALIAS_C": "a",  # Creates cycle: a -> b -> c -> a
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

            # Should detect cycle and stop - returns the value before cycle restarted
            # The exact value depends on where the cycle is detected, but it shouldn't hang
            result = alias_manager.resolve_alias("a", provider="poe")
            # After a->b->c, when c tries to resolve to 'a', we detect the cycle
            # The result should be one of the intermediate values (not hanging infinitely)
            assert result is not None
            assert ":" in result  # Should have provider prefix
            # The cycle should be detected, so we don't loop forever
            # Result could be "poe:c" (stopped at cycle detection) or similar
