"""Start command for the vdm CLI."""

import os
import signal
import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
import uvicorn
from src.main import app as fastapi_app
from src.core.config import config

app = typer.Typer(help="Start the proxy server")


@app.command()
def start(
    host: str = typer.Option(None, "--host", help="Override host"),
    port: int = typer.Option(None, "--port", help="Override port"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
    daemon: bool = typer.Option(False, "--daemon", help="Run in background"),
    pid_file: str = typer.Option(
        str(Path.home() / ".vdm.pid"), "--pid-file", help="PID file path"
    ),
) -> None:
    """Start the proxy server."""
    console = Console()

    # Override config if provided
    server_host = host or config.host
    server_port = port or config.port

    # Show configuration
    table = Table(title="Vandamme Proxy Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Host", server_host)
    table.add_row("Port", str(server_port))
    table.add_row("OpenAI Base URL", config.openai_base_url)
    table.add_row("Big Model", config.big_model)
    table.add_row("Small Model", config.small_model)
    table.add_row("API Key", config.openai_api_key_hash)

    console.print(table)

    if daemon:
        _start_daemon(server_host, server_port, pid_file)
    else:
        _start_server(server_host, server_port, reload)


def _start_daemon(host: str, port: int, pid_file: str) -> None:
    """Start the server in daemon mode."""
    console = Console()
    console.print("[yellow]Daemon mode not yet implemented[/yellow]")
    # TODO: Implement daemon mode with proper PID file handling


def _start_server(host: str, port: int, reload: bool) -> None:
    """Start the uvicorn server."""
    uvicorn.run(
        "src.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=config.log_level.lower(),
    )