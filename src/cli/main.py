"""Main CLI entry point for vandamme-proxy."""

import typer
from rich.console import Console

# Import command modules
from src.cli.commands import config, health, server, test

app = typer.Typer(
    name="vdm",
    help="Vandamme Proxy CLI - Elegant management for your proxy server",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Add subcommands
app.add_typer(server.app, name="server", help="Server management")
app.add_typer(config.app, name="config", help="Configuration management")
app.add_typer(health.app, name="health", help="Health checks")
app.add_typer(test.app, name="test", help="Test commands")


@app.command()
def version() -> None:
    """Show version information."""
    from src import __version__

    console = Console()
    console.print(f"[bold cyan]vdm[/bold cyan] version [green]{__version__}[/green]")


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    config_file: str = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """Vandamme Proxy CLI."""
    if verbose:
        # Configure verbose logging
        import logging

        logging.basicConfig(level=logging.DEBUG)
    if config_file:
        # Load custom config file
        # TODO: Implement config file loading
        pass


if __name__ == "__main__":
    app()
