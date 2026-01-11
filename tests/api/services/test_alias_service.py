"""Tests for AliasService."""

import warnings
from unittest.mock import MagicMock

import pytest

from src.api.services.alias_service import (
    AliasService,
)
from src.core.constants import Constants


@pytest.mark.unit
def test_get_active_aliases_with_providers(mock_alias_manager, mock_provider_manager):
    """Test get_active_aliases returns filtered aliases."""
    mock_alias_manager.get_all_aliases.return_value = {
        "openai": {"haiku": "gpt-4o-mini"},
        "poe": {"sonnet": "glm-4.6"},
        "anthropic": {"opus": "claude-3-opus-20240229"},
    }
    mock_provider_manager.list_providers.return_value = {
        "openai": MagicMock(),
        "poe": MagicMock(),
    }

    service = AliasService(mock_alias_manager, mock_provider_manager)
    result = service.get_active_aliases()

    assert result == {
        "openai": {"haiku": "gpt-4o-mini"},
        "poe": {"sonnet": "glm-4.6"},
    }
    # anthropic excluded - not in active providers
    assert "anthropic" not in result


@pytest.mark.unit
def test_get_active_aliases_empty_providers(mock_alias_manager, mock_provider_manager):
    """Test get_active_aliases returns empty dict when no providers active."""
    mock_alias_manager.get_all_aliases.return_value = {
        "openai": {"haiku": "gpt-4o-mini"},
    }
    mock_provider_manager.list_providers.return_value = {}

    service = AliasService(mock_alias_manager, mock_provider_manager)
    result = service.get_active_aliases()

    assert result == {}


@pytest.mark.unit
def test_get_active_aliases_provider_manager_error(mock_alias_manager, mock_provider_manager):
    """Test get_active_aliases returns empty dict on ProviderManager error.

    Note: The new implementation only catches AttributeError explicitly.
    RuntimeError should propagate.
    """
    mock_provider_manager.list_providers.side_effect = RuntimeError("Not initialized")

    service = AliasService(mock_alias_manager, mock_provider_manager)

    with pytest.raises(RuntimeError, match="Not initialized"):
        service.get_active_aliases()


@pytest.mark.unit
def test_get_active_aliases_provider_manager_attribute_error(
    mock_alias_manager, mock_provider_manager
):
    """Test get_active_aliases returns empty dict when ProviderManager not initialized."""
    mock_provider_manager.list_providers.side_effect = AttributeError("Not initialized")

    service = AliasService(mock_alias_manager, mock_provider_manager)
    result = service.get_active_aliases()

    assert result == {}


@pytest.mark.unit
def test_get_active_aliases_all_providers_active(mock_alias_manager, mock_provider_manager):
    """Test get_active_aliases returns all aliases when all providers are active."""
    mock_alias_manager.get_all_aliases.return_value = {
        "openai": {"haiku": "gpt-4o-mini"},
        "poe": {"sonnet": "glm-4.6"},
    }
    mock_provider_manager.list_providers.return_value = {
        "openai": MagicMock(),
        "poe": MagicMock(),
    }

    service = AliasService(mock_alias_manager, mock_provider_manager)
    result = service.get_active_aliases()

    assert result == {
        "openai": {"haiku": "gpt-4o-mini"},
        "poe": {"sonnet": "glm-4.6"},
    }


@pytest.mark.unit
def test_get_active_aliases_filters_empty_provider_names(mock_alias_manager, mock_provider_manager):
    """Test get_active_aliases filters out empty provider names."""
    mock_alias_manager.get_all_aliases.return_value = {
        "openai": {"haiku": "gpt-4o-mini"},
        "": {"should_be_ignored": "model"},
    }
    mock_provider_manager.list_providers.return_value = {
        "openai": MagicMock(),
        "": MagicMock(),
    }

    service = AliasService(mock_alias_manager, mock_provider_manager)
    result = service.get_active_aliases()

    assert result == {
        "openai": {"haiku": "gpt-4o-mini"},
    }
    assert "" not in result


@pytest.mark.unit
def test_get_active_aliases_result_success(mock_alias_manager, mock_provider_manager):
    """Test get_active_aliases_result returns success result."""
    mock_alias_manager.get_all_aliases.return_value = {
        "openai": {"haiku": "gpt-4o-mini"},
        "poe": {"sonnet": "glm-4.6"},
    }
    mock_provider_manager.list_providers.return_value = {
        "openai": MagicMock(),
        "poe": MagicMock(),
    }

    service = AliasService(mock_alias_manager, mock_provider_manager)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = service.get_active_aliases_result()

        # Verify deprecation warning was raised
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "deprecated" in str(w[0].message).lower()

    assert result.is_success is True
    assert result.error_message is None
    assert result.provider_count == 2
    assert result.alias_count == 2
    # Verify aliases is a tuple of tuples
    assert isinstance(result.aliases, tuple)
    # Convert back to dict for easier comparison
    aliases_dict = {provider: dict(alias_items) for provider, alias_items in result.aliases}
    assert aliases_dict == {
        "openai": {"haiku": "gpt-4o-mini"},
        "poe": {"sonnet": "glm-4.6"},
    }


@pytest.mark.unit
def test_get_active_aliases_result_no_providers(mock_alias_manager, mock_provider_manager):
    """Test get_active_aliases_result returns failure result when no providers."""
    mock_provider_manager.list_providers.return_value = {}

    service = AliasService(mock_alias_manager, mock_provider_manager)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = service.get_active_aliases_result()

        # Verify deprecation warning was raised
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)

    assert result.is_success is False
    assert result.error_message == "No active providers found"
    assert result.provider_count == 0
    assert result.alias_count == 0
    assert result.aliases == ()


@pytest.mark.unit
def test_get_alias_summary_no_aliases(mock_alias_manager, mock_provider_manager):
    """Test get_alias_summary returns empty summary when no aliases."""
    mock_alias_manager.get_all_aliases.return_value = {}
    mock_alias_manager.get_fallback_aliases.return_value = {}

    service = AliasService(mock_alias_manager, mock_provider_manager)
    summary = service.get_alias_summary()

    assert summary.total_aliases == 0
    assert summary.total_providers == 0
    assert summary.total_fallbacks == 0
    assert summary.providers == ()


@pytest.mark.unit
def test_get_alias_summary_with_aliases(mock_alias_manager, mock_provider_manager):
    """Test get_alias_summary returns structured summary data."""
    mock_alias_manager.get_all_aliases.return_value = {
        "openai": {"haiku": "gpt-4o-mini", "fast": "gpt-4o"},
    }
    mock_alias_manager.get_fallback_aliases.return_value = {
        "openai": {"haiku": "gpt-4o-mini"},
    }
    mock_provider_manager.list_providers.return_value = {
        "openai": MagicMock(),
    }

    service = AliasService(mock_alias_manager, mock_provider_manager)
    summary = service.get_alias_summary()

    assert summary.total_aliases == 2
    assert summary.total_providers == 1
    assert summary.total_fallbacks == 1
    assert len(summary.providers) == 1

    provider_info = summary.providers[0]
    assert provider_info.provider == "openai"
    assert provider_info.alias_count == 2
    assert provider_info.fallback_count == 1
    assert len(provider_info.aliases) == 2

    # Check alias structure: (alias, target, type)
    haiku_entry = next((a for a in provider_info.aliases if a[0] == "haiku"), None)
    assert haiku_entry is not None
    assert haiku_entry[1] == "gpt-4o-mini"
    assert haiku_entry[2] == Constants.ALIAS_TYPE_FALLBACK


@pytest.mark.unit
def test_get_alias_summary_uses_public_getter(mock_alias_manager, mock_provider_manager):
    """Test that get_alias_summary uses public get_fallback_aliases method."""
    mock_alias_manager.get_all_aliases.return_value = {
        "openai": {"haiku": "gpt-4o-mini"},
    }
    mock_alias_manager.get_fallback_aliases.return_value = {
        "openai": {"haiku": "gpt-4o-mini"},
    }
    mock_provider_manager.list_providers.return_value = {
        "openai": MagicMock(),
    }

    service = AliasService(mock_alias_manager, mock_provider_manager)
    summary = service.get_alias_summary()

    # Verify the public getter was called
    mock_alias_manager.get_fallback_aliases.assert_called_once()
    assert summary.total_fallbacks == 1


@pytest.fixture
def mock_alias_manager():
    """Mock AliasManager."""
    return MagicMock()


@pytest.fixture
def mock_provider_manager():
    """Mock ProviderManager."""
    return MagicMock()


@pytest.mark.unit
def test_get_active_aliases_result_propagates_exceptions(mock_alias_manager, mock_provider_manager):
    """Test get_active_aliases_result propagates unexpected exceptions."""
    mock_alias_manager.get_all_aliases.side_effect = RuntimeError("Database error")
    mock_provider_manager.list_providers.return_value = {"openai": MagicMock()}

    service = AliasService(mock_alias_manager, mock_provider_manager)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with pytest.raises(RuntimeError, match="Database error"):
            service.get_active_aliases_result()
        # Verify deprecation warning was raised before exception
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)


@pytest.mark.unit
def test_get_active_aliases_result_attribute_error(mock_alias_manager, mock_provider_manager):
    """Test get_active_aliases_result handles AttributeError gracefully."""
    mock_provider_manager.list_providers.side_effect = AttributeError("Not initialized")

    service = AliasService(mock_alias_manager, mock_provider_manager)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = service.get_active_aliases_result()

        # Verify deprecation warning was raised
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)

    assert result.is_success is False
    assert result.error_message == "No active providers found"
    assert result.aliases == ()
