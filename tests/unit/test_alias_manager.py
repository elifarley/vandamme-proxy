"""
Unit tests for the AliasManager component.
"""

import os
from unittest.mock import patch

import pytest

from src.core.alias_manager import AliasManager


@pytest.mark.unit
class TestAliasManager:
    """Test cases for AliasManager functionality."""

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

            alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            assert len(aliases) == 3
            assert aliases["poe"]["haiku"] == "grok-4.1-fast-non-reasoning"
            assert aliases["openai"]["fast"] == "gpt-4o-mini"
            assert aliases["anthropic"]["chat"] == "claude-3-5-sonnet-20241022"

    def test_case_insensitive_storage(self):
        """Test that aliases are stored in lowercase."""
        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_ALIAS_FAST": "gpt-4o-mini",
                    "POE_ALIAS_HaIkU": "grok-4.1-fast-non-reasoning",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"openai": {}, "poe": {}}

            alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            assert "fast" in aliases["openai"]
            assert "haiku" in aliases["poe"]
            assert "FAST" not in aliases["openai"]
            assert "HaIkU" not in aliases["poe"]

    def test_resolve_exact_match(self):
        """Test resolving exact alias matches."""
        with (
            patch.dict(
                os.environ,
                {
                    "POE_ALIAS_HAIKU": "custom-haiku-model",  # Only set POE alias
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}

            alias_manager = AliasManager()

            # Exact match (now returns with provider prefix)
            assert alias_manager.resolve_alias("haiku") == "poe:custom-haiku-model"
            assert alias_manager.resolve_alias("HAIKU") == "poe:custom-haiku-model"

            # Test fallback when no exact alias is set
            # Remove environment variable to test fallback behavior
            with patch.dict(os.environ, {}, clear=True):
                alias_manager2 = AliasManager()
                # Should use fallback from defaults.toml
                assert alias_manager2.resolve_alias("haiku") == "poe:gpt-5.1-mini"

    def test_resolve_substring_match(self):
        """Test resolving substring matches."""
        with (
            patch.dict(
                os.environ,
                {
                    "POE_ALIAS_HAIKU": "grok-4.1-fast-non-reasoning",
                    "OPENAI_ALIAS_FAST": "gpt-4o-mini",
                    "ANTHROPIC_ALIAS_MY_ALIAS": "claude-3-sonnet",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
            patch("src.core.alias_config.AliasConfigLoader") as mock_config_loader,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}, "openai": {}, "anthropic": {}}

            # Mock empty fallbacks
            mock_loader_instance = mock_config_loader.return_value
            mock_loader_instance.load_config.return_value = {"providers": {}, "defaults": {}}

            alias_manager = AliasManager()

            # Substring matches (now return with provider prefix)
            assert (
                alias_manager.resolve_alias("my-haiku-model") == "poe:grok-4.1-fast-non-reasoning"
            )
            assert alias_manager.resolve_alias("fast-response") == "openai:gpt-4o-mini"
            assert alias_manager.resolve_alias("SUPER-FAST") == "openai:gpt-4o-mini"

            # Test underscore to hyphen normalization for substring matching
            assert alias_manager.resolve_alias("oh-my-alias-model") == "anthropic:claude-3-sonnet"
            assert alias_manager.resolve_alias("my-alias-is-great") == "anthropic:claude-3-sonnet"

    def test_resolve_longest_match_priority(self):
        """Test that longer matches have priority over shorter ones."""
        with (
            patch.dict(
                os.environ,
                {
                    "ANTHROPIC_ALIAS_CHAT": "claude-3-5-sonnet-20241022",
                    "POE_ALIAS_HAIKU": "grok-4.1-fast-non-reasoning",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"anthropic": {}, "poe": {}}

            alias_manager = AliasManager()

            # "chathai" contains both "chat" and "haiku" - should pick longer match "chat"
            assert alias_manager.resolve_alias("chathai") == "anthropic:claude-3-5-sonnet-20241022"

    def test_resolve_alphabetical_priority_on_tie(self):
        """Test alphabetical priority when matches have same length."""
        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_ALIAS_ABC": "gpt-4o",
                    "ANTHROPIC_ALIAS_XYZ": "claude-3",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"openai": {}, "anthropic": {}}

            alias_manager = AliasManager()

            # Both "abc" and "xyz" have same length, should pick alphabetically first by provider
            # then alias
            assert alias_manager.resolve_alias("abc-xyz") == "anthropic:claude-3"

    def test_no_match_returns_none(self):
        """Test that non-matching model names return None."""
        with (
            patch.dict(
                os.environ,
                {
                    "POE_ALIAS_HAIKU": "grok-4.1-fast-non-reasoning",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}

            alias_manager = AliasManager()

            assert alias_manager.resolve_alias("gpt-4") is None
            assert alias_manager.resolve_alias("unknown") is None
            assert alias_manager.resolve_alias("") is None

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
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"openai": {}, "poe": {}, "anthropic": {}}

            alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            # Should have 3 providers:
            # anthropic (with explicit), poe (with fallbacks), openai (empty)
            assert len(aliases) == 3
            assert aliases["anthropic"]["valid"] == "claude-3-5-sonnet-20241022"
            # Check that poe has fallback aliases
            assert "haiku" in aliases["poe"]
            assert "sonnet" in aliases["poe"]
            assert "opus" in aliases["poe"]

    def test_circular_reference_validation(self):
        """Test detection of circular alias references."""
        with (
            patch.dict(
                os.environ,
                {
                    "POE_ALIAS_SELF": "self",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}

            alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            assert "self" not in aliases.get("poe", {})

    def test_invalid_format_validation(self):
        """Test validation of alias target formats."""
        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_ALIAS_VALID": "gpt-4o",
                    "POE_ALIAS_VALID2": "claude-3-5-sonnet-20241022",
                    "ANTHROPIC_ALIAS_INVALID": "invalid@format",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"openai": {}, "poe": {}, "anthropic": {}}

            alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            assert "valid" in aliases["openai"]
            assert "valid2" in aliases["poe"]
            assert "invalid" not in aliases.get("anthropic", {})

    def test_has_aliases(self):
        """Test has_aliases method."""
        with (
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager_class,
            patch.dict(os.environ, {}, clear=True),
        ):
            mock_pm = mock_provider_manager_class.return_value

            # No providers configured
            mock_pm._configs = {}
            alias_manager = AliasManager()
            assert not alias_manager.has_aliases()

            # No aliases (provider configured but no aliases for it)
            mock_pm._configs = {"unknownprovider": {}}
            alias_manager = AliasManager()
            assert not alias_manager.has_aliases()

        # Create a new patch for the rest of the test
        with (
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager_class,
            patch.dict(os.environ, {"OPENAI_ALIAS_FAST": "gpt-4o-mini"}),
        ):
            mock_pm = mock_provider_manager_class.return_value
            mock_pm._configs = {"openai": {}}
            alias_manager = AliasManager()
            assert alias_manager.has_aliases()

        # With fallback aliases (poe has defaults)
        with (
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager_class,
            patch.dict(os.environ, {}, clear=True),
        ):
            mock_pm = mock_provider_manager_class.return_value
            mock_pm._configs = {"poe": {}}
            alias_manager = AliasManager()
            assert alias_manager.has_aliases()  # Should have fallback aliases

    def test_get_alias_count(self):
        """Test get_alias_count method."""
        with (
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager_class,
            patch.dict(os.environ, {}, clear=True),
        ):
            mock_pm = mock_provider_manager_class.return_value

            # No providers configured
            mock_pm._configs = {}
            alias_manager = AliasManager()
            assert alias_manager.get_alias_count() == 0

            # Provider without fallbacks
            mock_pm._configs = {"unknownprovider": {}}
            alias_manager = AliasManager()
            assert alias_manager.get_alias_count() == 0

        # Provider with fallbacks (poe has 3 fallbacks)
        with (
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager_class,
            patch.dict(os.environ, {}, clear=True),
        ):
            mock_pm = mock_provider_manager_class.return_value
            mock_pm._configs = {"poe": {}}
            alias_manager = AliasManager()
            assert alias_manager.get_alias_count() == 3  # haiku, sonnet, opus from fallback

        # Explicit aliases override fallbacks
        with (
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager_class,
            patch.dict(
                os.environ,
                {
                    "OPENAI_ALIAS_FAST": "gpt-4o-mini",
                    "POE_ALIAS_HAIKU": "custom-haiku",  # Override fallback
                },
            ),
        ):
            mock_pm = mock_provider_manager_class.return_value
            mock_pm._configs = {"openai": {}, "poe": {}}
            alias_manager = AliasManager()
            # Total aliases: 1 openai explicit + 3 fallbacks + 1 poe explicit + 2 fallbacks = 7
            assert alias_manager.get_alias_count() == 7

    def test_invalid_provider_skip(self):
        """Test that aliases for unknown providers are skipped."""
        with (
            patch.dict(
                os.environ,
                {
                    "UNKNOWN_PROVIDER_ALIAS_FAST": "gpt-4o-mini",
                    "POE_ALIAS_HAIKU": "grok-4.1-fast-non-reasoning",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}  # Only poe is configured

            alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            assert len(aliases) == 1
            assert "haiku" in aliases["poe"]
            assert "unknown_provider" not in aliases

    def test_underscore_hyphen_matching(self):
        """Test that aliases with underscores match both hyphens and underscores in model names."""
        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_ALIAS_MY_MODEL": "gpt-4o",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"openai": {}}

            alias_manager = AliasManager()

            # Should match hyphens in model name
            assert alias_manager.resolve_alias("oh-this-is-my-model-right") == "openai:gpt-4o"
            # Should also match underscores in model name
            assert alias_manager.resolve_alias("oh-this-is-my_model-right") == "openai:gpt-4o"
            # Case insensitive
            assert alias_manager.resolve_alias("OH-THIS-IS-MY-MODEL-RIGHT") == "openai:gpt-4o"

    def test_get_all_aliases_is_copy(self):
        """Test that get_all_aliases returns a copy, not the original dict."""
        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_ALIAS_FAST": "gpt-4o-mini",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"openai": {}}

            alias_manager = AliasManager()

            aliases1 = alias_manager.get_all_aliases()
            aliases2 = alias_manager.get_all_aliases()

            # Modifying one shouldn't affect the other
            aliases1["openai"]["new"] = "value"
            assert "new" not in aliases2.get("openai", {})
            assert alias_manager.get_alias_count() == 4  # 1 explicit + 3 fallbacks

    def test_none_and_empty_inputs(self):
        """Test handling of None and empty inputs."""
        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_ALIAS_TEST": "gpt-4o",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"openai": {}}

            alias_manager = AliasManager()

            assert alias_manager.resolve_alias(None) is None
            assert alias_manager.resolve_alias("") is None
            assert alias_manager.resolve_alias("test") == "openai:gpt-4o"

    def test_logging_behavior(self, caplog):
        """Test that appropriate log messages are generated."""
        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_ALIAS_VALID": "gpt-4o-mini",
                    "ANTHROPIC_ALIAS_INVALID": "invalid@format",
                    "POE_ALIAS_EMPTY": "",
                    "UNKNOWN_ALIAS_FAST": "gpt-4o",  # Should generate provider not found warning
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
            caplog.at_level("DEBUG"),
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {
                "openai": {},
                "anthropic": {},
                "poe": {},
            }  # All providers configured

            AliasManager()

            # Check that valid alias was logged
            assert any(
                "Loaded model alias: openai:valid -> gpt-4o-mini" in record.message
                for record in caplog.records
            )

            # Check that invalid alias was logged with warning
            assert any(
                "Invalid alias configuration for ANTHROPIC_ALIAS_INVALID=invalid@format"
                in record.message
                for record in caplog.records
            )

            # Check that empty alias was logged with warning
            assert any(
                "Empty alias value for POE_ALIAS_EMPTY" in record.message
                for record in caplog.records
            )

            # Check that unknown provider was logged with warning
            assert any(
                "Provider 'unknown' not found for alias UNKNOWN_ALIAS_FAST" in record.message
                for record in caplog.records
            )
