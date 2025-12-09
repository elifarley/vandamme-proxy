"""Test commands for the vdm CLI."""

import sys
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from src.core.config import config

app = typer.Typer(help="Test commands")


@app.command()
def connection() -> None:
    """Test API connectivity."""
    console = Console()

    console.print("[bold cyan]Testing API Connectivity[/bold cyan]")
    console.print()

    # Test configuration
    try:
        if not config.openai_api_key:
            console.print("[red]❌ OPENAI_API_KEY not configured[/red]")
            sys.exit(1)

        console.print(f"✅ API Key configured: {config.openai_api_key_hash}")
        console.print(f"✅ Base URL: {config.openai_base_url}")
        console.print(f"✅ Big Model: {config.big_model}")
        console.print(f"✅ Middle Model: {config.middle_model}")
        console.print(f"✅ Small Model: {config.small_model}")

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
def models() -> None:
    """Test model mappings."""
    console = Console()

    console.print("[bold cyan]Testing Model Mappings[/bold cyan]")
    console.print()

    # Define test mappings
    test_models = [
        ("claude-3-haiku", config.small_model),
        ("claude-3-5-haiku", config.small_model),
        ("claude-3-sonnet", config.middle_model),
        ("claude-3-5-sonnet", config.middle_model),
        ("claude-3-opus", config.big_model),
    ]

    table = Table(title="Model Mappings")
    table.add_column("Claude Model", style="cyan")
    table.add_column("Maps To", style="green")
    table.add_column("Type", style="yellow")

    for claude_model, openai_model in test_models:
        model_type = (
            "Small"
            if "haiku" in claude_model.lower()
            else "Middle"
            if "sonnet" in claude_model.lower()
            else "Big"
        )
        table.add_row(claude_model, openai_model, model_type)

    console.print(table)

    console.print()
    console.print(
        Panel(
            "These mappings are applied automatically when requests are processed.",
            title="Model Mapping Information",
            expand=False,
        )
    )