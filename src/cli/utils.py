"""Utility functions for the vdm CLI."""

import sys
from pathlib import Path

from rich.console import Console


def get_project_root() -> Path:
    """Get the root directory of the project."""
    return Path(__file__).parent.parent.parent


def exit_with_error(message: str, exit_code: int = 1) -> None:
    """Print an error message and exit."""
    console = Console()
    console.print(f"[red]❌ {message}[/red]")
    sys.exit(exit_code)
