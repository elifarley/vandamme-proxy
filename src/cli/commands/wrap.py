"""Wrap command for running CLI tools through the VDM proxy."""

import asyncio
import contextlib
import logging
import os

import typer

from src.cli.wrap.proxy_manager import ProxyManager
from src.cli.wrap.wrappers import BaseWrapper, get_wrapper
from src.core.config import config
from src.core.logging.configuration import configure_root_logging


def wrap(
    ctx: typer.Context,
    tool: str,
    port: int | None = typer.Option(None, "--port", help="Proxy port (temporary override)"),
    host: str | None = typer.Option(None, "--host", help="Proxy host (temporary override)"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print what would be executed without running"
    ),
) -> None:
    """Wrap a CLI tool to use the VDM proxy.

    Examples:
        vdm wrap claude --port 9999 --model sonnet
        vdm wrap gemini --host 127.0.0.1
        vdm wrap --dry-run claude --model sonnet
    """
    # Get all remaining args from ctx.args
    # ctx.args contains everything after the tool name when using allow_extra_args
    tool_args = list(ctx.args) if hasattr(ctx, "args") else []

    execute_wrap(tool, port, host, tool_args, dry_run=dry_run)


def execute_wrap(
    tool: str,
    port: int | None,
    host: str | None,
    tool_args: list[str],
    dry_run: bool = False,
) -> None:
    """Execute the wrap logic."""
    # Configure logging
    configure_root_logging(use_systemd=False)
    logger = logging.getLogger(__name__)

    # Get host and port from args or config
    if port is None:
        port = int(config.port)
    if host is None:
        host = config.host or "127.0.0.1"

    logger.info(f"Wrapping tool '{tool}' with args: {tool_args}")

    # Get the wrapper for the tool
    wrapper = get_wrapper(tool, f"http://{host}:{port}")
    if wrapper is None:
        typer.echo(f"Error: Unknown tool '{tool}'. Supported tools: claude, gemini", err=True)
        raise typer.Exit(1)

    # Handle dry-run mode
    if dry_run:
        typer.echo(f"Would wrap tool: {tool}")
        typer.echo(f"Proxy URL: http://{host}:{port}")
        typer.echo(f"Tool arguments: {tool_args}")

        # Show what command would be run
        cmd = wrapper.get_tool_command() + tool_args
        typer.echo(f"Command that would be executed: {' '.join(cmd)}")

        # Show environment variables that would be set
        env = wrapper.prepare_environment(tool_args)
        if env:
            typer.echo("Environment variables that would be set:")
            for k, v in env.items():
                if k in ["ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "GEMINI_API_BASE_URL"]:
                    typer.echo(f"  {k}={v}")

        # Show settings file that would be created
        settings_file = wrapper.create_settings_file()
        if settings_file:
            typer.echo(f"Settings file that would be created: {settings_file}")
            # Clean up the dry-run settings file
            with contextlib.suppress(Exception):
                os.unlink(settings_file)

        raise typer.Exit(0)

    # Run the wrapper logic
    try:
        # Create an event loop for the async parts
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Run the async main function
            loop.run_until_complete(main_async(wrapper, host, port, tool_args))
        finally:
            loop.close()

    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        raise typer.Exit(0) from None
    except Exception as e:
        logger.error(f"Error: {e}")
        raise typer.Exit(1) from None


async def main_async(wrapper: BaseWrapper, host: str, port: int, tool_args: list[str]) -> None:
    """Async main function to handle proxy lifecycle."""
    logger = logging.getLogger(__name__)

    # Create proxy manager
    proxy_manager = ProxyManager(host=host, port=port)

    try:
        # Ensure proxy is running
        await proxy_manager.ensure_proxy_running()
        if not await proxy_manager._is_proxy_running():
            typer.echo(f"Error: Failed to start proxy at {host}:{port}", err=True)
            raise typer.Exit(1)

        # Get the proxy URL for the wrapper
        proxy_url = proxy_manager.get_proxy_url()
        logger.info(f"Using proxy at: {proxy_url}")

        # Update wrapper with actual proxy URL
        wrapper.proxy_url = proxy_url

        # Run the wrapped tool
        logger.info(f"Running tool with arguments: {tool_args}")
        exit_code = wrapper.run(tool_args)

        # Exit with the same code as the wrapped tool
        raise typer.Exit(exit_code)

    finally:
        # Clean up the proxy if we started it
        await proxy_manager.cleanup_if_needed()


# Export for imports
__all__ = ["wrap"]
