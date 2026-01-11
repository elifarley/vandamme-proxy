"""Tests for alias presenter."""

from io import StringIO

import pytest
from rich.console import Console

from src.api.services.alias_service import AliasSummary, ProviderAliasInfo
from src.cli.presenters.aliases import AliasSummaryPresenter


@pytest.mark.unit
def test_presenter_empty_summary(capsys):
    """Test presenter does nothing when summary is empty."""
    console = Console(file=StringIO())
    summary = AliasSummary(
        total_aliases=0,
        total_providers=0,
        total_fallbacks=0,
        providers=[],
        default_provider=None,
    )

    presenter = AliasSummaryPresenter(console=console)
    presenter.present_summary(summary)

    # Nothing should be printed
    output = console.file.getvalue()
    assert "Model Aliases" not in output


@pytest.mark.unit
def test_presenter_with_aliases(capsys):
    """Test presenter displays formatted aliases."""
    console = Console(file=StringIO())
    summary = AliasSummary(
        total_aliases=2,
        total_providers=1,
        total_fallbacks=1,
        providers=[
            ProviderAliasInfo(
                provider="openai",
                alias_count=2,
                fallback_count=1,
                aliases=[
                    ("haiku", "gpt-4o-mini", "fallback"),
                    ("fast", "gpt-4o", "explicit"),
                ],
            )
        ],
        default_provider="openai",
    )

    presenter = AliasSummaryPresenter(console=console)
    presenter.present_summary(summary)

    output = console.file.getvalue()
    assert "Model Aliases" in output
    assert "2 configured" in output
    assert "openai" in output
    assert "haiku" in output
    assert "fast" in output


@pytest.mark.unit
def test_presenter_with_multiple_providers(capsys):
    """Test presenter handles multiple providers."""
    console = Console(file=StringIO())
    summary = AliasSummary(
        total_aliases=3,
        total_providers=2,
        total_fallbacks=0,
        providers=[
            ProviderAliasInfo(
                provider="openai",
                alias_count=2,
                fallback_count=0,
                aliases=[
                    ("fast", "gpt-4o", "explicit"),
                    ("haiku", "gpt-4o-mini", "explicit"),
                ],
            ),
            ProviderAliasInfo(
                provider="anthropic",
                alias_count=1,
                fallback_count=0,
                aliases=[("chat", "claude-3-5-sonnet", "explicit")],
            ),
        ],
        default_provider="openai",
    )

    presenter = AliasSummaryPresenter(console=console)
    presenter.present_summary(summary)

    output = console.file.getvalue()
    assert "3 configured" in output
    assert "openai" in output
    assert "anthropic" in output


@pytest.mark.unit
def test_presenter_table_format():
    """Test presenter table format."""
    console = Console(file=StringIO())
    summary = AliasSummary(
        total_aliases=2,
        total_providers=1,
        total_fallbacks=1,
        providers=[
            ProviderAliasInfo(
                provider="openai",
                alias_count=2,
                fallback_count=1,
                aliases=[
                    ("haiku", "gpt-4o-mini", "fallback"),
                    ("fast", "gpt-4o", "explicit"),
                ],
            )
        ],
        default_provider="openai",
    )

    presenter = AliasSummaryPresenter(console=console)
    presenter.present_summary_as_table(summary)

    output = console.file.getvalue()
    assert "openai" in output
    assert "haiku" in output
    assert "fast" in output
    assert "gpt-4o-mini" in output
