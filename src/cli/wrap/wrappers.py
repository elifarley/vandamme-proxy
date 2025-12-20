"""Simple wrapper functions for CLI tools."""

import logging
import os
import signal
import subprocess
import sys
import types

logger = logging.getLogger(__name__)


class BaseWrapper:
    """Base class for tool wrappers."""

    def __init__(self, proxy_url: str):
        self.proxy_url = proxy_url

    def prepare_environment(self, extra_args: list[str]) -> dict:
        """Prepare environment variables for the tool."""
        env = os.environ.copy()
        env["ANTHROPIC_BASE_URL"] = self.proxy_url

        # If proxy requires authentication, use placeholder
        # The actual API key will be validated by the proxy
        env["ANTHROPIC_API_KEY"] = "proxy-auth-required"

        return env

    def filter_args(self, args: list[str]) -> list[str]:
        """Filter out wrap-specific arguments."""
        # Base wrapper doesn't filter anything
        return args

    def create_settings_file(self) -> str | None:
        """Create a settings file if needed. Returns path to settings file."""
        return None

    def get_tool_command(self) -> list[str]:
        """Get the base command for the tool."""
        raise NotImplementedError

    def run(self, args: list[str]) -> int:
        """Run the wrapped tool."""
        # Filter arguments
        filtered_args = self.filter_args(args)

        # Prepare environment
        env = self.prepare_environment(filtered_args)

        # Create settings file if needed
        settings_file = self.create_settings_file()

        try:
            # Build the command
            cmd = self.get_tool_command() + filtered_args

            # Add settings file argument if created
            if settings_file:
                cmd.extend(["--settings", settings_file])

            logger.info(f"Running command: {' '.join(cmd)}")
            logger.info("To follow Vandamme logs, run:\n  `journalctl -t vandamme-proxy -f`")

            # Run the command
            process = subprocess.Popen(
                cmd,
                env=env,
                # Don't capture output - let it flow to the user
                text=True,
            )

            # Forward signals to the child process
            def signal_handler(sig: int, frame: types.FrameType | None) -> None:
                logger.info(f"Received signal {sig}, forwarding to child process")
                if process.poll() is None:  # Process still running
                    process.send_signal(sig)
                sys.exit(0)

            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            # Wait for the process to complete
            return process.wait()

        finally:
            # Clean up settings file
            if settings_file:
                try:
                    os.unlink(settings_file)
                except Exception as e:
                    logger.warning(f"Failed to clean up settings file {settings_file}: {e}")


class ClaudeWrapper(BaseWrapper):
    """Wrapper for Claude CLI."""

    def get_tool_command(self) -> list[str]:
        return ["claude"]

    def create_settings_file(self) -> str | None:
        """Claude doesn't need a settings file - use existing config."""
        # Return None to avoid creating temporary files that trigger conflicts
        return None


class GeminiWrapper(BaseWrapper):
    """Wrapper for Gemini CLI."""

    def get_tool_command(self) -> list[str]:
        return ["gemini"]

    def create_settings_file(self) -> str | None:
        """Gemini might not need a settings file."""
        # For now, we don't create a settings file for Gemini
        return None

    def prepare_environment(self, extra_args: list[str]) -> dict:
        """Prepare environment for Gemini."""
        env = os.environ.copy()

        # Gemini might use different env vars
        # This is a placeholder - actual implementation depends on Gemini's requirements
        env["GEMINI_API_BASE_URL"] = self.proxy_url

        return env


def get_wrapper(tool_name: str, proxy_url: str) -> BaseWrapper | None:
    """Get the appropriate wrapper for the given tool."""
    wrappers = {
        "claude": ClaudeWrapper,
        "gemini": GeminiWrapper,
    }

    wrapper_class = wrappers.get(tool_name.lower())
    if wrapper_class:
        return wrapper_class(proxy_url)

    return None
