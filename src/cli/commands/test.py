"""Test commands for the vdm CLI."""

import sys

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.core.config import Config

app = typer.Typer(help="Test commands")


@app.command()
def connection() -> None:
    """Test API connectivity."""
    console = Console()
    cfg = Config()

    console.print("[bold cyan]Testing API Connectivity[/bold cyan]")
    console.print()

    # Test configuration
    try:
        if not cfg.openai_api_key:
            provider_upper = cfg.default_provider.upper()
            console.print(f"[red]❌ {provider_upper}_API_KEY not configured[/red]")
            sys.exit(1)

        console.print(f"✅ API Key configured: {cfg.api_key_hash}")
        console.print(f"✅ Default Provider: {cfg.default_provider}")
        console.print(f"✅ Base URL: {cfg.base_url}")

        console.print()
        console.print(
            Panel(
                "To run a full connectivity test, use: [cyan]vdm health upstream[/cyan]",
                title="Next Steps",
                expand=False,
            )
        )

    except Exception as e:
        console.print(f"[red]❌ Configuration test failed: {str(e)}[/red]")
        sys.exit(1)


@app.command()
def providers() -> None:
    """List all configured providers."""
    console = Console()
    cfg = Config()

    console.print("[bold cyan]Provider Status[/bold cyan]")
    console.print()

    # Load providers
    try:
        cfg.provider_manager.load_provider_configs()
        load_results = cfg.provider_manager.get_load_results()

        if not load_results:
            console.print("[yellow]No providers configured[/yellow]")
            console.print()
            console.print(
                Panel(
                    "Configure providers by setting {PROVIDER}_API_KEY environment variables.\n"
                    "For OpenAI and Poe, BASE_URL is optional (defaults will be used).",
                    title="Provider Configuration",
                    expand=False,
                )
            )
            return

        table = Table(title="Provider Configuration")
        table.add_column("Provider", style="cyan")
        table.add_column("API Key", style="green")
        table.add_column("Base URL", style="blue")
        table.add_column("Status", style="yellow")
        table.add_column("Default", style="magenta")

        success_count = 0
        for result in load_results:
            if result.status == "success":
                status = "[green]✓ Ready[/green]"
                success_count += 1
            else:  # partial
                status = f"[yellow]⚠️ {result.message}[/yellow]"

            is_default = "✓" if result.name == cfg.provider_manager.default_provider else ""
            table.add_row(
                result.name,
                f"[dim]{result.api_key_hash}[/dim]",
                result.base_url or "[dim]N/A[/dim]",
                status,
                is_default,
            )

        console.print(table)
        console.print()

        # Show summary
        provider_text = "providers" if success_count != 1 else "provider"
        console.print(
            f"[bold green]{success_count}[/bold green] {provider_text} ready for requests"
        )
        console.print()

        # Show default provider
        console.print(f"Default Provider: [bold]{cfg.provider_manager.default_provider}[/bold]")
        console.print()

        # Show examples
        default_provider = cfg.provider_manager.default_provider
        console.print(
            Panel(
                f"Use providers with model prefixes:\n"
                f"• [cyan]openrouter:gpt-4o[/cyan] → Uses OpenRouter\n"
                f"• [cyan]poe:gemini-3-pro[/cyan] → Uses Poe\n"
                f"• [cyan]claude-3-5-sonnet[/cyan] → Uses default provider ({default_provider})",
                title="Usage Examples",
                expand=False,
            )
        )

    except Exception as e:
        console.print(f"[red]❌ Error loading providers: {str(e)}[/red]")
        sys.exit(1)
