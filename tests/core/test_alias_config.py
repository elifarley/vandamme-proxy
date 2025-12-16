"""Unit tests for the AliasConfigLoader component."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.alias_config import AliasConfigLoader


@pytest.mark.unit
class TestAliasConfigLoader:
    """Test cases for AliasConfigLoader functionality."""

    def test_load_config_with_default_file(self):
        """Test loading default configuration from package root."""
        loader = AliasConfigLoader()

        # Clear any existing config to force reload from package defaults
        loader._config_cache = None

        # Temporarily move existing config files to test clean loading
        # Skip package defaults (last path) as those should always be available
        import shutil

        existing_files = []
        for path in loader._config_paths[:-1]:  # Skip package defaults
            if path.exists():
                temp_path = path.with_suffix(".toml.bak")
                shutil.move(str(path), str(temp_path))
                existing_files.append((path, temp_path))

        try:
            config = loader.load_config(force_reload=True)

            # Should load from the package defaults
            assert "providers" in config
            assert "poe" in config["providers"]
            assert "aliases" in config["providers"]["poe"]
            assert "haiku" in config["providers"]["poe"]["aliases"]
            assert "sonnet" in config["providers"]["poe"]["aliases"]
            assert "opus" in config["providers"]["poe"]["aliases"]
            assert config["providers"]["poe"]["aliases"]["haiku"] == "gpt-5.1-mini"
            assert config["providers"]["poe"]["aliases"]["sonnet"] == "glm-4.6"
            assert config["providers"]["poe"]["aliases"]["opus"] == "gpt-5.2"
        finally:
            # Restore original files
            for original_path, temp_path in existing_files:
                if temp_path.exists():
                    shutil.move(str(temp_path), str(original_path))

    def test_load_config_hierarchy(self):
        """Test that configuration hierarchy works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create user config
            user_config_dir = Path(tmpdir) / ".config" / "vandamme-proxy"
            user_config_dir.mkdir(parents=True)
            user_config = user_config_dir / "vandamme-config.toml"
            user_config.write_text(
                """
[poe]
base-url = "https://user-poe.com"
[poe.aliases]
haiku = "user-haiku-override"
new_alias = "user-new-model"
"""
            )

            # Create local config
            local_config = Path(tmpdir) / "vandamme-config.toml"
            local_config.write_text(
                """
[poe]
base-url = "https://local-poe.com"
timeout = 60
[poe.aliases]
haiku = "local-haiku-override"
sonnet = "local-sonnet-override"
another_new = "local-new-model"
"""
            )

            with (
                patch("src.core.alias_config.Path.home", return_value=Path(tmpdir)),
                patch("src.core.alias_config.Path.cwd", return_value=Path(tmpdir)),
            ):
                loader = AliasConfigLoader()

                # Mock the package root to use our test directory
                package_root = Path(tmpdir)
                # Create default config in the test directory
                default_config = package_root / "defaults.toml"
                default_config.write_text(
                    """
[poe]
base-url = "https://default-poe.com"
[poe.aliases]
haiku = "default-haiku"
sonnet = "default-sonnet"
opus = "default-opus"
"""
                )

                # Update the config path to use our test directory
                loader._config_paths[2] = default_config

                config = loader.load_config()

                # Local config should have highest priority
                assert config["providers"]["poe"]["aliases"]["haiku"] == "local-haiku-override"
                assert config["providers"]["poe"]["aliases"]["sonnet"] == "local-sonnet-override"

                # User config should be used for missing local values
                assert config["providers"]["poe"]["aliases"]["new_alias"] == "user-new-model"

                # Local config should be used for new values
                assert config["providers"]["poe"]["aliases"]["another_new"] == "local-new-model"

                # Default config should be used for missing values
                assert config["providers"]["poe"]["aliases"]["opus"] == "default-opus"

                # Check provider config hierarchy
                assert (
                    config["providers"]["poe"]["base-url"] == "https://local-poe.com"
                )  # Local overrides
                assert config["providers"]["poe"]["timeout"] == 60  # Local override

    def test_get_fallback_alias(self):
        """Test getting a specific fallback alias."""
        loader = AliasConfigLoader()

        # Test existing alias
        assert loader.get_fallback_alias("poe", "haiku") == "gpt-5.1-mini"

        # Test non-existing alias
        assert loader.get_fallback_alias("poe", "nonexistent") is None

        # Test non-existing provider
        assert loader.get_fallback_alias("nonexistent", "haiku") is None

    def test_has_provider_defaults(self):
        """Test checking if provider has defaults."""
        loader = AliasConfigLoader()

        # Test existing provider
        assert loader.has_provider_defaults("poe") is True

        # Test non-existing provider
        assert loader.has_provider_defaults("nonexistent") is False

    def test_config_caching(self):
        """Test that configuration is cached."""
        loader = AliasConfigLoader()

        # First load should read from file
        config1 = loader.load_config()

        # Second load should use cache
        config2 = loader.load_config()

        assert config1 is config2  # Should be the same object (cached)

        # Force reload should read again
        config3 = loader.load_config(force_reload=True)
        assert config1 is not config3  # Should be a new object

    def test_missing_toml_library(self):
        """Test graceful degradation when tomli is not available."""
        with patch("src.core.alias_config.tomli", None):
            loader = AliasConfigLoader()
            config = loader.load_config()

            # Should return empty provider and defaults configs when tomli is not available
            assert config == {"providers": {}, "defaults": {}}

    def test_invalid_toml_file(self):
        """Test handling of invalid TOML files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create invalid TOML file
            invalid_config = Path(tmpdir) / "vandamme-config.toml"
            invalid_config.write_text("invalid toml content !!!")

            with patch("src.core.alias_config.Path.cwd", return_value=Path(tmpdir)):
                loader = AliasConfigLoader()
                # Should not crash, just skip the invalid file
                config = loader.load_config()
                # Should still load from package defaults
                assert "providers" in config
                assert "poe" in config["providers"]

    def test_missing_aliases_section(self):
        """Test handling of TOML files without aliases section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create TOML file without aliases section
            config_without_aliases = Path(tmpdir) / "vandamme-config.toml"
            config_without_aliases.write_text(
                """
[other_section]
some_key = "some_value"
"""
            )

            with patch("src.core.alias_config.Path.cwd", return_value=Path(tmpdir)):
                loader = AliasConfigLoader()
                config = loader.load_config()

                # Should load from package defaults since local file has no aliases
                assert "providers" in config
                assert "poe" in config["providers"]
                assert "aliases" in config["providers"]["poe"]
                assert "haiku" in config["providers"]["poe"]["aliases"]

    def test_malformed_aliases_section(self):
        """Test handling of malformed aliases section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create TOML file with malformed aliases
            malformed_config = Path(tmpdir) / "vandamme-config.toml"
            malformed_config.write_text(
                """
[poe.aliases]
haiku = ["not", "a", "string"]
"""
            )

            with patch("src.core.alias_config.Path.cwd", return_value=Path(tmpdir)):
                loader = AliasConfigLoader()
                config = loader.load_config()

                # Should load from package defaults since local config is malformed
                assert "providers" in config
                assert "poe" in config["providers"]
                assert (
                    config["providers"]["poe"]["aliases"]["haiku"] == "gpt-5.1-mini"
                )

    def test_case_insensitive_alias_names(self):
        """Test that alias names are converted to lowercase."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create config with mixed case alias names
            config_file = Path(tmpdir) / "vandamme-config.toml"
            config_file.write_text(
                """
[poe.aliases]
HAIKU = "haiku-model"
SONNET = "sonnet-model"
"""
            )

            with patch("src.core.alias_config.Path.cwd", return_value=Path(tmpdir)):
                loader = AliasConfigLoader()
                config = loader.load_config()

                # Alias names should be lowercase
                assert "haiku" in config["providers"]["poe"]["aliases"]
                assert "sonnet" in config["providers"]["poe"]["aliases"]
                assert "HAIKU" not in config["providers"]["poe"]["aliases"]
                assert "SONNET" not in config["providers"]["poe"]["aliases"]
