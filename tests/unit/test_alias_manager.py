"""
Unit tests for the AliasManager component.
"""

import os
from unittest.mock import patch

from src.core.alias_manager import AliasManager


class TestAliasManager:
    """Test cases for AliasManager functionality."""

    def test_load_aliases_from_env(self):
        """Test loading aliases from environment variables."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_FAST": "openai:gpt-4o-mini",
                "VDM_ALIAS_HAIKU": "poe:gpt-4o-mini",
                "VDM_ALIAS_CHAT": "anthropic:claude-3-5-sonnet-20241022",
                "OTHER_VAR": "should_be_ignored",
            },
        ):
            alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            assert len(aliases) == 3
            assert aliases["fast"] == "openai:gpt-4o-mini"
            assert aliases["haiku"] == "poe:gpt-4o-mini"
            assert aliases["chat"] == "anthropic:claude-3-5-sonnet-20241022"

    def test_case_insensitive_storage(self):
        """Test that aliases are stored in lowercase."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_FAST": "openai:gpt-4o-mini",
                "VDM_ALIAS_HaIkU": "poe:gpt-4o-mini",
            },
        ):
            alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            assert "fast" in aliases
            assert "haiku" in aliases
            assert "FAST" not in aliases
            assert "HaIkU" not in aliases

    def test_resolve_exact_match(self):
        """Test resolving exact alias matches."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_HAIKU": "poe:gpt-4o-mini",
                "VDM_ALIAS_MY_ALIAS": "openai:gpt-4o",
            },
        ):
            alias_manager = AliasManager()

            # Exact match
            assert alias_manager.resolve_alias("haiku") == "poe:gpt-4o-mini"
            assert alias_manager.resolve_alias("HAIKU") == "poe:gpt-4o-mini"

            # Test underscore to hyphen normalization for exact match
            assert alias_manager.resolve_alias("my-alias") == "openai:gpt-4o"
            assert alias_manager.resolve_alias("MY-ALIAS") == "openai:gpt-4o"

    def test_resolve_substring_match(self):
        """Test resolving substring matches."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_HAIKU": "poe:gpt-4o-mini",
                "VDM_ALIAS_FAST": "openai:gpt-4o-mini",
                "VDM_ALIAS_MY_ALIAS": "anthropic:claude-3-sonnet",
            },
        ):
            alias_manager = AliasManager()

            # Substring matches
            assert alias_manager.resolve_alias("my-haiku-model") == "poe:gpt-4o-mini"
            assert alias_manager.resolve_alias("fast-response") == "openai:gpt-4o-mini"
            assert alias_manager.resolve_alias("SUPER-FAST") == "openai:gpt-4o-mini"

            # Test underscore to hyphen normalization for substring matching
            assert alias_manager.resolve_alias("oh-my-alias-model") == "anthropic:claude-3-sonnet"
            assert alias_manager.resolve_alias("my-alias-is-great") == "anthropic:claude-3-sonnet"

    def test_resolve_longest_match_priority(self):
        """Test that longer matches have priority over shorter ones."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_CHAT": "anthropic:claude-3-5-sonnet-20241022",
                "VDM_ALIAS_HAIKU": "poe:gpt-4o-mini",
            },
        ):
            alias_manager = AliasManager()

            # "chathai" contains both "chat" and "haiku" - should pick longer match "chat"
            assert alias_manager.resolve_alias("chathai") == "anthropic:claude-3-5-sonnet-20241022"

    def test_resolve_alphabetical_priority_on_tie(self):
        """Test alphabetical priority when matches have same length."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_ABC": "openai:gpt-4o",
                "VDM_ALIAS_XYZ": "anthropic:claude-3",
            },
        ):
            alias_manager = AliasManager()

            # Both "abc" and "xyz" have same length, should pick alphabetically first
            assert alias_manager.resolve_alias("abc-xyz") == "openai:gpt-4o"

    def test_no_match_returns_none(self):
        """Test that non-matching model names return None."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_HAIKU": "poe:gpt-4o-mini",
            },
        ):
            alias_manager = AliasManager()

            assert alias_manager.resolve_alias("gpt-4") is None
            assert alias_manager.resolve_alias("unknown") is None
            assert alias_manager.resolve_alias("") is None

    def test_empty_alias_value_skip(self):
        """Test that empty alias values are skipped."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_EMPTY": "",
                "VDM_ALIAS_SPACES": "   ",
                "VDM_ALIAS_VALID": "openai:gpt-4o",
            },
        ):
            alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            assert len(aliases) == 1
            assert aliases["valid"] == "openai:gpt-4o"

    def test_circular_reference_validation(self):
        """Test detection of circular alias references."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_SELF": "self",
            },
        ):
            alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            assert "self" not in aliases

    def test_invalid_format_validation(self):
        """Test validation of alias target formats."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_VALID": "openai:gpt-4o",
                "VDM_ALIAS_VALID2": "claude-3-5-sonnet-20241022",
                "VDM_ALIAS_INVALID": "invalid@format",
            },
        ):
            alias_manager = AliasManager()

            aliases = alias_manager.get_all_aliases()
            assert "valid" in aliases
            assert "valid2" in aliases
            assert "invalid" not in aliases

    def test_has_aliases(self):
        """Test has_aliases method."""
        # No aliases
        with patch.dict(os.environ, {}, clear=True):
            alias_manager = AliasManager()
            assert not alias_manager.has_aliases()

        # With aliases
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_FAST": "openai:gpt-4o-mini",
            },
        ):
            alias_manager = AliasManager()
            assert alias_manager.has_aliases()

    def test_get_alias_count(self):
        """Test get_alias_count method."""
        with patch.dict(os.environ, {}, clear=True):
            alias_manager = AliasManager()
            assert alias_manager.get_alias_count() == 0

        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_FAST": "openai:gpt-4o-mini",
                "VDM_ALIAS_HAIKU": "poe:gpt-4o-mini",
            },
        ):
            alias_manager = AliasManager()
            assert alias_manager.get_alias_count() == 2

    def test_provider_prefix_handling(self):
        """Test that provider prefixes are preserved in alias values."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_OPENAI_FAST": "openai:gpt-4o-mini",
                "VDM_ALIAS_ANTHROPIC_FAST": "anthropic:claude-3-5-haiku-20241022",
                "VDM_ALIAS_PLAIN": "gpt-4",
            },
        ):
            alias_manager = AliasManager()

            # Underscore in alias should match hyphen in model name
            assert alias_manager.resolve_alias("openai-fast") == "openai:gpt-4o-mini"
            assert (
                alias_manager.resolve_alias("anthropic-fast")
                == "anthropic:claude-3-5-haiku-20241022"
            )
            assert alias_manager.resolve_alias("plain") == "gpt-4"

    def test_special_characters_in_model_names(self):
        """Test handling of special characters in model names."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_SPECIAL": "custom-provider/model-v1.2.3",
            },
        ):
            alias_manager = AliasManager()

            assert alias_manager.resolve_alias("special") == "custom-provider/model-v1.2.3"
            assert alias_manager.resolve_alias("my-special-model") == "custom-provider/model-v1.2.3"

    def test_underscore_hyphen_matching(self):
        """Test that aliases with underscores match both hyphens and underscores in model names."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_MY_MODEL": "openai:gpt-4o",
            },
        ):
            alias_manager = AliasManager()

            # Should match hyphens in model name
            assert alias_manager.resolve_alias("oh-this-is-my-model-right") == "openai:gpt-4o"
            # Should also match underscores in model name
            assert alias_manager.resolve_alias("oh-this-is-my_model-right") == "openai:gpt-4o"
            # Case insensitive
            assert alias_manager.resolve_alias("OH-THIS-IS-MY-MODEL-RIGHT") == "openai:gpt-4o"

    def test_get_all_aliases_is_copy(self):
        """Test that get_all_aliases returns a copy, not the original dict."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_FAST": "openai:gpt-4o-mini",
            },
        ):
            alias_manager = AliasManager()

            aliases1 = alias_manager.get_all_aliases()
            aliases2 = alias_manager.get_all_aliases()

            # Modifying one shouldn't affect the other
            aliases1["new"] = "value"
            assert "new" not in aliases2
            assert len(alias_manager.get_all_aliases()) == 1

    def test_none_and_empty_inputs(self):
        """Test handling of None and empty inputs."""
        with patch.dict(
            os.environ,
            {
                "VDM_ALIAS_TEST": "openai:gpt-4o",
            },
        ):
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
                    "VDM_ALIAS_VALID": "openai:gpt-4o-mini",
                    "VDM_ALIAS_INVALID": "invalid@format",
                    "VDM_ALIAS_EMPTY": "",
                },
            ),
            caplog.at_level("INFO"),
        ):
            AliasManager()

            # Check that valid alias was logged
            assert any(
                "Loaded model alias: valid -> openai:gpt-4o-mini" in record.message
                for record in caplog.records
            )

            # Check that invalid alias was logged with warning
            assert any(
                "Invalid alias configuration for VDM_ALIAS_INVALID=invalid@format" in record.message
                for record in caplog.records
            )

            # Check that empty alias was logged with warning
            assert any(
                "Empty alias value for VDM_ALIAS_EMPTY" in record.message
                for record in caplog.records
            )
