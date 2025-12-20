"""Server management commands for the vdm CLI."""

from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from src.core.config import config

app = typer.Typer(help="Server management")


@app.command()
def start(
    host: str = typer.Option(None, "--host", help="Override host"),
    port: int = typer.Option(None, "--port", help="Override port"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
    daemon: bool = typer.Option(False, "--daemon", help="Run in background"),
    pid_file: str = typer.Option(str(Path.home() / ".vdm.pid"), "--pid-file", help="PID file path"),
    systemd: bool = typer.Option(
        False, "--systemd", help="Send logs to systemd journal instead of console"
    ),
) -> None:
    """Start the proxy server."""
    # Configure logging FIRST before any console output
    from src.core.logging.configuration import configure_root_logging

    # Override config if provided
    server_host = host or config.host
    server_port = port or config.port

    # When using systemd, configure logging immediately and suppress all console output
    console = None  # Initialize console to None
    if systemd:
        configure_root_logging(use_systemd=True)
        # No console output when using systemd - everything goes to syslog
    else:
        configure_root_logging(use_systemd=False)
        console = Console()

        # Show configuration only when not using systemd
        table = Table(title="Vandamme Proxy Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Server URL", f"http://{server_host}:{server_port}")
        table.add_row("Default Provider", config.default_provider)
        table.add_row(f"{config.default_provider.title()} Base URL", config.base_url)
        table.add_row(f"{config.default_provider.title()} API Key", config.api_key_hash)

        console.print(table)

        # Show provider summary
        config.provider_manager.print_provider_summary()

        # Show common model mappings
        if config.alias_manager:
            config.alias_manager.print_common_model_mappings(config.default_provider)

    if daemon:
        _start_daemon(server_host, server_port, pid_file)
    else:
        _start_server(server_host, server_port, reload)


@app.command()
def stop() -> None:
    """Stop the proxy server."""
    console = Console()
    console.print("[yellow]Stop command not yet implemented[/yellow]")
    # TODO: Implement server stop functionality


@app.command()
def restart() -> None:
    """Restart the proxy server."""
    console = Console()
    console.print("[yellow]Restart command not yet implemented[/yellow]")
    # TODO: Implement server restart functionality


@app.command()
def status() -> None:
    """Check proxy server status."""
    console = Console()
    console.print("[yellow]Status command not yet implemented[/yellow]")
    # TODO: Implement server status checking


def _start_daemon(host: str, port: int, pid_file: str) -> None:
    """Start the server in daemon mode."""
    console = Console()
    console.print("[yellow]Daemon mode not yet implemented[/yellow]")
    # TODO: Implement daemon mode with proper PID file handling


def _start_server(host: str, port: int, reload: bool) -> None:
    """Start the uvicorn server."""
    # Disable uvicorn's default logging since we configure it ourselves
    uvicorn.run(
        "src.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="warning",  # Only show warnings/errors from uvicorn itself
        access_log=False,  # Disable access logs - we handle them ourselves
    )
