"""Health check commands."""

import json
import sys

import httpx
import typer
from rich.console import Console
from rich.status import Status
from rich.table import Table

from src.core.config import config

app = typer.Typer(help="Health checks")


@app.command()
def server(
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
    host: str = typer.Option(None, "--host", help="Host to check"),
    port: int = typer.Option(None, "--port", help="Port to check"),
) -> None:
    """Check proxy server health."""
    console = Console()
    check_host = host or config.host
    check_port = port or config.port
    url = f"http://{check_host}:{check_port}/health"

    try:
        with Status("Checking proxy server health...", console=console):
            response = httpx.get(url, timeout=5.0)
            response.raise_for_status()
            data = response.json()

        if json_output:
            console.print(json.dumps(data, indent=2))
        else:
            table = Table(title="Server Health")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Status", "✅ Healthy")
            table.add_row("URL", url)
            table.add_row("Response Time", f"{response.elapsed.total_seconds():.3f}s")

            console.print(table)

    except httpx.ConnectError:
        msg = f"❌ Cannot connect to server at {url}"
        if json_output:
            console.print(json.dumps({"status": "error", "message": msg}, indent=2))
            sys.exit(1)
        else:
            console.print(f"[red]{msg}[/red]")
            sys.exit(1)
    except Exception as e:
        msg = f"❌ Health check failed: {str(e)}"
        if json_output:
            console.print(json.dumps({"status": "error", "message": msg}, indent=2))
            sys.exit(1)
        else:
            console.print(f"[red]{msg}[/red]")
            sys.exit(1)


@app.command()
def upstream(
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Check upstream API connectivity."""
    console = Console()

    with Status("Checking OpenAI API connectivity...", console=console):
        try:
            # Use existing client to test connectivity
            client = httpx.Client(
                base_url=config.base_url,
                headers={"Authorization": f"Bearer {config.openai_api_key}"},
                timeout=10.0,
            )

            # Simple health check by listing models
            response = client.get("/models")
            response.raise_for_status()

            if json_output:
                console.print(
                    json.dumps(
                        {
                            "status": "healthy",
                            "base_url": config.base_url,
                            "api_key": config.api_key_hash,
                        },
                        indent=2,
                    )
                )
            else:
                table = Table(title="Upstream API Health")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")

                table.add_row("Status", "✅ Connected")
                table.add_row("Base URL", config.base_url)
                table.add_row("API Key", config.api_key_hash)
                table.add_row("Response Time", f"{response.elapsed.total_seconds():.3f}s")

                console.print(table)

        except Exception as e:
            msg = f"❌ Upstream API check failed: {str(e)}"
            if json_output:
                console.print(
                    json.dumps(
                        {
                            "status": "error",
                            "message": msg,
                            "base_url": config.base_url,
                        },
                        indent=2,
                    )
                )
                sys.exit(1)
            else:
                console.print(f"[red]{msg}[/red]")
                sys.exit(1)
