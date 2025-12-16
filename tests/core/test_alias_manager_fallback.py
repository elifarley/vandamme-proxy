"""Unit tests for AliasManager fallback functionality."""

import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.alias_manager import AliasManager


@pytest.mark.unit
class TestAliasManagerFallback:
    """Test cases for AliasManager fallback functionality."""

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

    def test_fallback_aliases_loaded_by_default(self):
        """Test that fallback aliases are loaded when no environment variables are set."""
        with patch("src.core.provider_manager.ProviderManager") as mock_provider_manager:
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}

            alias_manager = AliasManager()

            # Should have fallback aliases from config
            aliases = alias_manager.get_all_aliases()
            assert "poe" in aliases
            assert "haiku" in aliases["poe"]
            assert "sonnet" in aliases["poe"]
            assert "opus" in aliases["poe"]
            assert aliases["poe"]["haiku"] == "gpt-5.1-mini"
            assert aliases["poe"]["sonnet"] == "glm-4.6"
            assert aliases["poe"]["opus"] == "gpt-5.2"

    def test_environment_aliases_override_fallbacks(self):
        """Test that environment variable aliases override fallback aliases."""
        with (
            patch.dict(
                os.environ,
                {
                    "POE_API_KEY": "test",
                    "POE_ALIAS_HAIKU": "custom-haiku-model",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}

            alias_manager = AliasManager()

            # Should use environment variable value, not fallback
            aliases = alias_manager.get_all_aliases()
            assert aliases["poe"]["haiku"] == "custom-haiku-model"

            # Other fallbacks should still be applied
            assert aliases["poe"]["sonnet"] == "glm-4.6"
            assert aliases["poe"]["opus"] == "gpt-5.2"

    def test_fallback_resolution(self):
        """Test that fallback aliases are resolved correctly."""
        with patch("src.core.provider_manager.ProviderManager") as mock_provider_manager:
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}

            alias_manager = AliasManager()

            # Test resolving fallback aliases
            assert alias_manager.resolve_alias("haiku") == "poe:gpt-5.1-mini"
            assert alias_manager.resolve_alias("sonnet") == "poe:glm-4.6"
            assert alias_manager.resolve_alias("opus") == "poe:gpt-5.2"

            # Test case insensitive matching
            assert alias_manager.resolve_alias("HAIKU") == "poe:gpt-5.1-mini"
            assert alias_manager.resolve_alias("Sonnet") == "poe:glm-4.6"

            # Test substring matching
            assert alias_manager.resolve_alias("my-haiku-model") == "poe:gpt-5.1-mini"

    def test_no_fallbacks_for_unconfigured_providers(self):
        """Test that fallbacks are not applied to providers without defaults."""
        with patch("src.core.provider_manager.ProviderManager") as mock_provider_manager:
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"newprovider": {}}  # Provider without fallback defaults

            alias_manager = AliasManager()

            # Should not have any aliases for unconfigured provider
            aliases = alias_manager.get_all_aliases()
            assert "newprovider" not in aliases

    def test_explicit_vs_explicit_aliases_methods(self):
        """Test the difference between get_all_aliases and get_explicit_aliases."""
        with (
            patch.dict(
                os.environ,
                {
                    "POE_API_KEY": "test",
                    "POE_ALIAS_HAIKU": "custom-haiku-model",
                },
            ),
            patch("src.core.provider_manager.ProviderManager") as mock_provider_manager,
        ):
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}

            alias_manager = AliasManager()

            # get_all_aliases should include both explicit and fallback aliases
            all_aliases = alias_manager.get_all_aliases()
            assert "haiku" in all_aliases["poe"]  # explicit
            assert "sonnet" in all_aliases["poe"]  # fallback
            assert "opus" in all_aliases["poe"]  # fallback

            # get_explicit_aliases should only include explicit aliases
            explicit_aliases = alias_manager.get_explicit_aliases()
            assert "haiku" in explicit_aliases["poe"]  # explicit
            assert "sonnet" not in explicit_aliases["poe"]  # fallback
            assert "opus" not in explicit_aliases["poe"]  # fallback

    def test_fallback_loading_error_handling(self):
        """Test graceful handling when fallback loading fails."""

        # Temporarily move the defaults file to simulate loading error
        defaults_path = Path(__file__).parent.parent.parent / "src" / "config" / "defaults.toml"
        temp_path = defaults_path.with_suffix(".toml.bak")

        try:
            # Move the file temporarily
            if defaults_path.exists():
                shutil.move(str(defaults_path), str(temp_path))

            # Clear the config cache to force reload
            from src.core.alias_config import AliasConfigLoader

            AliasConfigLoader.reset_cache()

            alias_manager = AliasManager()

            # Should still work, just without fallbacks
            aliases = alias_manager.get_all_aliases()
            # With no fallbacks, we get empty aliases
            assert aliases == {}

        finally:
            # Restore the file
            if temp_path.exists():
                shutil.move(str(temp_path), str(defaults_path))

    def test_has_aliases_with_fallbacks(self):
        """Test that has_aliases() returns True when only fallbacks exist."""
        with patch("src.core.provider_manager.ProviderManager") as mock_provider_manager:
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}

            alias_manager = AliasManager()

            # Should return True even with only fallback aliases
            assert alias_manager.has_aliases() is True

            # Should count fallback aliases
            assert alias_manager.get_alias_count() == 3  # haiku, sonnet, opus

    def test_fallback_summary_display(self):
        """Test that fallback aliases are shown in summary display."""
        with patch("src.core.provider_manager.ProviderManager") as mock_provider_manager:
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"poe": {}}

            # Capture print output
            with patch("builtins.print") as mock_print:
                alias_manager = AliasManager()
                # Call _print_alias_summary to test output
                alias_manager._print_alias_summary()

                # Check that fallbacks are mentioned in output
                print_calls = [str(call) for call in mock_print.call_args_list]
                output_text = " ".join(print_calls)
                assert "3 fallback" in output_text or "fallback defaults" in output_text
                assert "haiku" in output_text
                assert "gpt-5.1-mini" in output_text

    def test_provider_validation_applies_to_fallbacks(self):
        """Test that fallback aliases are only loaded for configured providers."""
        with patch("src.core.provider_manager.ProviderManager") as mock_provider_manager:
            # Only configure openai provider
            mock_pm = mock_provider_manager.return_value
            mock_pm._configs = {"openai": {}}

            alias_manager = AliasManager()

            # Should not load poe fallbacks since poe is not configured
            aliases = alias_manager.get_all_aliases()
            assert "poe" not in aliases
