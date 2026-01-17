"""OAuth authentication commands for Vandamme Proxy."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="OAuth authentication management")


@app.command()
def login(
    provider: str = typer.Argument(..., help="Provider name (e.g., 'chatgpt')"),
) -> None:
    """Authenticate with a provider using OAuth.

    This will open a browser window for you to complete the OAuth flow.
    After successful authentication, tokens will be stored securely.

    Example:
        vdm oauth login chatgpt
    """
    console = Console()

    # Validate provider name
    provider = provider.lower()
    if not provider:
        console.print("[red]Error: Provider name is required[/red]")
        raise typer.Exit(1) from None

    try:
        from src.core.oauth import (  # type: ignore[import-untyped]
            FileSystemAuthStorage,
            HttpxHttpClient,
            OAuthFlow,
        )

        # Create per-provider storage path: ~/.vandamme/oauth/{provider}/
        storage_path = Path.home() / ".vandamme" / "oauth" / provider
        storage_path.mkdir(parents=True, exist_ok=True)

        storage = FileSystemAuthStorage(base_path=storage_path)
        http_client = HttpxHttpClient()
        oauth = OAuthFlow(storage, http_client=http_client)

        console.print(f"[cyan]Starting OAuth flow for provider: {provider}[/cyan]")
        console.print("[yellow]A browser window will open for authentication...[/yellow]")

        success = oauth.authenticate()

        if success:
            # Get account info from stored tokens
            auth_data = storage.read_auth()
            if auth_data:
                console.print(
                    Panel(
                        f"[green]✅ Successfully authenticated![/green]\n\n"
                        f"Provider: {provider}\n"
                        f"Account ID: {auth_data.account_id}\n"
                        f"Token expires at: {auth_data.expires_at or 'Unknown'}",
                        title="OAuth Login Success",
                        border_style="green",
                    )
                )
            else:
                console.print("[green]✅ Authentication successful![/green]")
        else:
            console.print("[red]❌ Authentication failed or was cancelled[/red]")
            raise typer.Exit(1) from None

    except Exception as e:
        console.print(
            Panel(
                f"[red]An error occurred during OAuth authentication.[/red]\n\nError: {e}",
                title="Authentication Error",
                border_style="red",
            )
        )
        raise typer.Exit(1) from None


@app.command()
def status(
    provider: str = typer.Argument(..., help="Provider name (e.g., 'chatgpt')"),
) -> None:
    """Check OAuth authentication status for a provider.

    Example:
        vdm oauth status chatgpt
    """
    console = Console()

    # Validate provider name
    provider = provider.lower()
    if not provider:
        console.print("[red]Error: Provider name is required[/red]")
        raise typer.Exit(1) from None

    try:
        from src.core.oauth import (  # type: ignore[import-untyped]
            FileSystemAuthStorage,
            TokenManager,
        )

        # Create per-provider storage path: ~/.vandamme/oauth/{provider}/
        storage_path = Path.home() / ".vandamme" / "oauth" / provider

        if not storage_path.exists():
            console.print(
                Panel(
                    f"[yellow]No authentication found for provider: {provider}[/yellow]\n\n"
                    f"Run 'vdm oauth login {provider}' to authenticate.",
                    title="Not Authenticated",
                    border_style="yellow",
                )
            )
            raise typer.Exit(1) from None

        storage = FileSystemAuthStorage(base_path=storage_path)
        token_mgr = TokenManager(storage)

        if not token_mgr.is_authenticated():
            console.print(
                Panel(
                    f"[yellow]No valid authentication found for provider: {provider}[/yellow]\n\n"
                    f"Run 'vdm oauth login {provider}' to authenticate.",
                    title="Not Authenticated",
                    border_style="yellow",
                )
            )
            raise typer.Exit(1) from None

        # Get current token status
        auth_data = storage.read_auth()

        # Create status table
        table = Table(title=f"OAuth Status: {provider}")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Provider", provider)
        table.add_row("Status", "[green]✅ Authenticated[/green]")
        if auth_data:
            table.add_row("Account ID", auth_data.account_id)
            table.add_row("Expires At", auth_data.expires_at or "Unknown")
            table.add_row("Last Refresh", auth_data.last_refresh or "Unknown")
        table.add_row("Storage Path", str(storage_path))

        console.print(table)

    except ImportError:
        console.print(
            Panel(
                "[red]OAuth authentication requires the oauth package.[/red]",
                title="Import Error",
                border_style="red",
            )
        )
        raise typer.Exit(1) from None
    except typer.Exit:
        # Re-raise exit from handling above
        raise
    except Exception as e:
        console.print(
            Panel(
                f"[red]An error occurred while checking authentication status.[/red]\n\nError: {e}",
                title="Status Check Error",
                border_style="red",
            )
        )
        raise typer.Exit(1) from None


@app.command()
def logout(
    provider: str = typer.Argument(..., help="Provider name (e.g., 'chatgpt')"),
) -> None:
    """Remove OAuth authentication for a provider.

    Example:
        vdm oauth logout chatgpt
    """
    console = Console()

    # Validate provider name
    provider = provider.lower()
    if not provider:
        console.print("[red]Error: Provider name is required[/red]")
        raise typer.Exit(1) from None

    try:
        from src.core.oauth import FileSystemAuthStorage  # type: ignore[import-untyped]

        # Create per-provider storage path: ~/.vandamme/oauth/{provider}/
        storage_path = Path.home() / ".vandamme" / "oauth" / provider

        if not storage_path.exists():
            console.print(
                Panel(
                    f"[yellow]No authentication found for provider: {provider}[/yellow]",
                    title="Logout Info",
                    border_style="yellow",
                )
            )
            return

        storage = FileSystemAuthStorage(base_path=storage_path)

        # Clear authentication
        storage.clear_auth()

        console.print(
            Panel(
                f"[green]✅ Successfully logged out from provider: {provider}[/green]",
                title="Logout Success",
                border_style="green",
            )
        )

    except ImportError:
        console.print(
            Panel(
                "[red]OAuth authentication requires the oauth package.[/red]",
                title="Import Error",
                border_style="red",
            )
        )
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(
            Panel(
                f"[red]An error occurred during logout.[/red]\n\nError: {e}",
                title="Logout Error",
                border_style="red",
            )
        )
        raise typer.Exit(1) from None
