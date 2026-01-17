"""Main CLI entry point for vandamme-proxy."""

import argparse
import logging
import sys

import typer

# Import command modules
from src.cli.commands import config, health, models, oauth, server, test
from src.cli.commands.wrap import wrap

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
app.add_typer(models.app, name="models", help="Model discovery")
app.add_typer(test.app, name="test", help="Test commands")
app.add_typer(oauth.app, name="oauth", help="OAuth authentication management")

# Add wrap as a command directly with support for extra arguments
app.command(context_settings={"allow_extra_args": True})(wrap)

# Note: wrap command handles its own logging configuration

# Get the application logger
logger = logging.getLogger(__name__)


def claude_alias() -> None:
    """Alias that is called by the CLI as `claude.vdm`.

    Intercepts proxy parameters (--host, --port, --pid-file) and passes
    remaining arguments to the wrapped claude command.

    Examples:
        claude.vdm --model sonnet
        claude.vdm --port 9999 --model sonnet
        claude.vdm --host 127.0.0.1 --pid-file /tmp/vdm.pid -- -v
    """
    # Create parser for proxy params only (no help to let wrapped command handle it)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--host", type=str, default=None, help="Override proxy host")
    parser.add_argument("--port", type=int, default=None, help="Override proxy port")
    parser.add_argument("--pid-file", type=str, default=None, help="PID file path")

    # Parse known args (proxy params), leaving unknown for the wrapped command
    proxy_args, tool_args = parser.parse_known_args(sys.argv[1:])

    # Build the vdm wrap command
    cmd = ["vdm", "wrap", "claude"]

    # Add proxy params if provided
    if proxy_args.host is not None:
        cmd.extend(["--host", proxy_args.host])
    if proxy_args.port is not None:
        cmd.extend(["--port", str(proxy_args.port)])
    if proxy_args.pid_file is not None:
        cmd.extend(["--pid-file", proxy_args.pid_file])

    # Add separator before tool args (required for typer's allow_extra_args)
    # The '--' is consumed by typer and doesn't appear in ctx.args
    if tool_args:
        cmd.append("--")
        cmd.extend(tool_args)

    # Execute the command
    import subprocess

    try:
        process = subprocess.run(cmd)
        sys.exit(process.returncode)
    except KeyboardInterrupt:
        sys.exit(130)  # Standard SIGINT exit code
    except FileNotFoundError:
        logger.error("vdm command not found. Make sure vandamme-proxy is installed.")
        sys.exit(1)


@app.command()
def version() -> None:
    """Show version information."""
    from src import __version__

    typer.echo(f"vdm version {__version__}")


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    config_file: str = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """Vandamme Proxy CLI."""
    # Note: Verbose flag sets DEBUG level globally.
    # Individual commands (like server start) may override this with their own logging config.
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if config_file:
        # Load custom config file
        logger.warning(f"Config file loading not yet implemented: {config_file}")
        # TODO: Implement config file loading


if __name__ == "__main__":
    app()
