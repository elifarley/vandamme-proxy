"""Presenters for alias display in CLI."""

from rich.console import Console
from rich.table import Table

from src.api.services.alias_service import AliasSummary, ProviderAliasInfo

# Rich color codes for providers (moved from service layer)
PROVIDER_COLORS = {
    "openai": "[blue]",
    "anthropic": "[green]",
    "azure": "[yellow]",
    "poe": "[magenta]",
    "bedrock": "[cyan]",
    "vertex": "[white]",
    "gemini": "[red]",
}


class AliasSummaryPresenter:
    """Presenter for alias summary display.

    This class is responsible for converting structured alias data
    into human-readable output using the Rich library. It contains
    no business logic - only presentation logic.
    """

    def __init__(self, console: Console | None = None):
        """Initialize presenter with optional Rich console.

        Args:
            console: Rich Console instance. If None, creates a new one.
        """
        self.console = console or Console()

    def present_summary(self, summary: AliasSummary) -> None:
        """Display alias summary with color formatting.

        This reproduces the original print_alias_summary() output
        using Rich formatting instead of ANSI codes and print().

        Args:
            summary: AliasSummary dataclass with structured data.
        """
        if summary.total_aliases == 0:
            return

        # Print header
        self.console.print(
            f"\n✨ Model Aliases ({summary.total_aliases} configured across "
            f"{summary.total_providers} providers):"
        )

        if summary.total_fallbacks > 0:
            self.console.print(
                f"   📦 Includes {summary.total_fallbacks} fallback defaults from configuration"
            )

        # Print each provider's aliases
        for provider_info in summary.providers:
            self._present_provider_aliases(provider_info)

        # Print usage examples
        self._present_usage_examples(summary)

    def _present_provider_aliases(self, provider_info: ProviderAliasInfo) -> None:
        """Display aliases for a single provider.

        Args:
            provider_info: ProviderAliasInfo with provider's alias data.
        """
        provider = provider_info.provider
        color = PROVIDER_COLORS.get(provider.lower(), "")
        reset = "[/]" if color else ""

        # Provider header
        provider_display = f"{color}{provider}{reset}"
        provider_info_str = f"{provider_display} ({provider_info.alias_count} aliases"
        if provider_info.fallback_count > 0:
            provider_info_str += f", {provider_info.fallback_count} fallbacks"
        provider_info_str += "):"

        self.console.print(f"\n   {provider_info_str}")

        # Table header
        table = Table(show_header=False, box=None, pad_edge=False)
        table.add_column("Alias", width=20, style="dim")
        table.add_column("Target Model", width=40)
        table.add_column("Type", width=10)

        # Add rows
        for alias, target, alias_type in provider_info.aliases:
            # Truncate long model names
            model_display = target
            if len(model_display) > 38:
                model_display = model_display[:35] + "..."

            # Dim fallback types
            type_display = f"[dim]{alias_type}[/dim]" if alias_type == "fallback" else alias_type

            table.add_row(f"   {alias}", f"   {model_display}", f"   {type_display}")

        self.console.print(table)

    def _present_usage_examples(self, summary: AliasSummary) -> None:
        """Display usage examples at the bottom.

        Args:
            summary: AliasSummary with example data.
        """
        self.console.print("\n   💡 Use aliases in your requests:")

        if summary.providers:
            # Use default provider if available, otherwise first provider
            example_provider = (
                summary.default_provider
                if summary.default_provider
                and any(p.provider == summary.default_provider for p in summary.providers)
                else summary.providers[0].provider
            )

            # Find the provider's info
            provider_info = next(
                (p for p in summary.providers if p.provider == example_provider),
                summary.providers[0],
            )

            if provider_info.aliases:
                first_alias, first_target, first_type = provider_info.aliases[0]
                is_fallback = first_type == "fallback"

                self.console.print(
                    f"      Example: model='{first_alias}' → resolves to "
                    f"'{example_provider}:{first_target}'"
                )
                if is_fallback:
                    self.console.print("                (from configuration defaults)")

        self.console.print("      Substring matching: 'my-{alias}-model' matches alias '{alias}'")
        self.console.print(
            "      Configure <PROVIDER>_ALIAS_<NAME> environment variables to create aliases"
        )
        self.console.print("      Or override defaults in vandamme-config.toml")

    def present_summary_as_table(self, summary: AliasSummary) -> None:
        """Display alias summary as a Rich table (alternative format).

        Args:
            summary: AliasSummary with structured data.
        """
        if summary.total_aliases == 0:
            self.console.print("[dim]No aliases configured.[/dim]")
            return

        table = Table(title=f"Model Aliases ({summary.total_aliases} configured)")

        table.add_column("Provider", style="cyan")
        table.add_column("Alias", style="bold")
        table.add_column("Target Model")
        table.add_column("Type")

        for provider_info in summary.providers:
            color = PROVIDER_COLORS.get(provider_info.provider.lower(), "")
            reset = "[/]" if color else ""

            for alias, target, alias_type in provider_info.aliases:
                type_display = (
                    f"[dim]{alias_type}[/dim]" if alias_type == "fallback" else alias_type
                )
                table.add_row(
                    f"{color}{provider_info.provider}{reset}", alias, target, type_display
                )

        self.console.print(table)
