"""Configuration management commands."""

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src.core.config import config

app = typer.Typer(help="Configuration management")


@app.command()
def show() -> None:
    """Display current configuration."""
    console = Console()

    table = Table(title="Current Configuration")
    table.add_column("Variable", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Source", style="yellow")

    # Add rows with masked secrets
    table.add_row(f"{config.default_provider.upper()}_API_KEY", config.api_key_hash, "Environment")
    table.add_row(
        "PROXY_API_KEY",
        "***" if config.proxy_api_key else "<not set>",
        "Environment",
    )
    table.add_row(
        f"{config.default_provider.upper()}_BASE_URL", config.base_url, "Environment/Default"
    )
    table.add_row("HOST", config.host, "Environment/Default")
    table.add_row("PORT", str(config.port), "Environment/Default")
    table.add_row("LOG_LEVEL", config.log_level, "Environment/Default")
    table.add_row("MIN_TOKENS_LIMIT", str(config.min_tokens_limit), "Environment/Default")
    table.add_row("MAX_TOKENS_LIMIT", str(config.max_tokens_limit), "Environment/Default")
    table.add_row("MAX_RETRIES", str(config.max_retries), "Environment/Default")
    table.add_row("REQUEST_TIMEOUT", str(config.request_timeout), "Environment/Default")

    console.print(table)


@app.command()
def validate() -> None:
    """Validate configuration."""
    console = Console()

    errors = []

    # Validate required settings
    if not config.openai_api_key:
        errors.append("❌ OPENAI_API_KEY is required")
    elif not config.validate_api_key():
        errors.append("❌ OPENAI_API_KEY format is invalid")

    if errors:
        console.print(Panel("\n".join(errors), title="Validation Errors", style="red"))
        sys.exit(1)
    else:
        console.print(
            Panel("✅ All configuration is valid!", title="Validation Success", style="green")
        )


@app.command()
def env() -> None:
    """Show required environment variables."""
    console = Console()

    console.print(
        Panel(
            """
[bold cyan]Required Environment Variables:[/bold cyan]
  OPENAI_API_KEY        - Your OpenAI API key (format: sk-...)

[bold yellow]Optional Environment Variables:[/bold yellow]
  PROXY_API_KEY    - Expected API key for client validation at the proxy
  OPENAI_BASE_URL      - OpenAI API base URL (default: https://api.openai.com/v1)
  AZURE_API_VERSION    - API version for Azure OpenAI
  HOST                - Server host (default: 0.0.0.0)
  PORT                - Server port (default: 8082)
  LOG_LEVEL           - Logging level: DEBUG/INFO/WARNING/ERROR (default: INFO)
  MIN_TOKENS_LIMIT    - Minimum tokens per request (default: 100)
  MAX_TOKENS_LIMIT    - Maximum tokens per request (default: 4096)
  MAX_RETRIES         - Maximum retry attempts (default: 2)
  REQUEST_TIMEOUT     - Request timeout in seconds (default: 90)

[bold green]Custom Headers:[/bold green]
  CUSTOM_HEADER_*     - Any env var starting with CUSTOM_HEADER_ will be
                        converted to a HTTP header (underscores -> hyphens)
                        Example: CUSTOM_HEADER_X_API_KEY=xyz becomes X-API-Key: xyz
      """,
            title="Environment Variables",
            width=100,
        )
    )


@app.command()
def setup() -> None:
    """Interactive configuration setup."""
    console = Console()

    env_path = Path(".env")

    if env_path.exists() and not Confirm.ask(".env file already exists. Overwrite?", default=False):
        console.print("[yellow]Setup cancelled[/yellow]")
        return

    console.print("[bold cyan]Vandamme Proxy Configuration Setup[/bold cyan]")
    console.print()

    # Get required values
    openai_key = Prompt.ask("OpenAI API Key", password=True)

    # Get optional values
    anthropic_key = Prompt.ask("Proxy API Key (optional)", default="", password=True)
    base_url = Prompt.ask("OpenAI Base URL", default="https://api.openai.com/v1")
    host = Prompt.ask("Server Host", default="0.0.0.0")
    port = Prompt.ask("Server Port", default="8082")

    # Write .env file
    with open(env_path, "w") as f:
        f.write("# Vandamme Proxy Configuration\n")
        f.write(f"OPENAI_API_KEY={openai_key}\n")
        if anthropic_key:
            f.write(f"PROXY_API_KEY={anthropic_key}\n")
        if base_url != "https://api.openai.com/v1":
            f.write(f"OPENAI_BASE_URL={base_url}\n")
        if host != "0.0.0.0":
            f.write(f"HOST={host}\n")
        if port != "8082":
            f.write(f"PORT={port}\n")

    console.print(f"\n[green]✅ Configuration saved to {env_path}[/green]")
