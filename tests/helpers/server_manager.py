"""Server management utilities for integration tests."""

import asyncio
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import httpx
import os


class TestServerManager:
    """Manages a test server instance for integration tests."""

    def __init__(self, port: int = 8082):
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.base_url = f"http://localhost:{port}"
        self.startup_timeout = 30  # seconds

    async def start(self) -> None:
        """Start the test server."""
        if self.process:
            return  # Already running

        # Set test environment variables
        env = os.environ.copy()
        env["VDM_TEST_PORT"] = str(self.port)
        env["LOG_LEVEL"] = "DEBUG"

        # Use uv to run the server
        cmd = [
            sys.executable, "-m", "uvicorn",
            "src.main:app",
            "--host", "localhost",
            "--port", str(self.port),
            "--log-level", "debug"
        ]

        # Check if we're in a virtual environment
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            # We're in a virtual environment
            self.process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
        else:
            # Try to use uv if available
            cmd = ["uv", "run"] + cmd
            self.process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

        # Wait for server to be ready
        start_time = time.time()
        while time.time() - start_time < self.startup_timeout:
            try:
                async with httpx.AsyncClient(timeout=1.0) as client:
                    response = await client.get(f"{self.base_url}/health")
                    if response.status_code == 200:
                        return
            except Exception:
                pass

            # Check if process exited with error
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                raise RuntimeError(
                    f"Server failed to start:\n"
                    f"Exit code: {self.process.returncode}\n"
                    f"Stderr: {stderr}"
                )

            await asyncio.sleep(0.5)

        # Timeout reached
        self.stop()
        raise TimeoutError(f"Server did not start within {self.startup_timeout} seconds")

    async def stop(self) -> None:
        """Stop the test server."""
        if self.process:
            try:
                self.process.terminate()
                await asyncio.sleep(1)
                if self.process.poll() is None:
                    self.process.kill()
                await asyncio.sleep(0.5)
            finally:
                self.process = None

    async def is_ready(self) -> bool:
        """Check if the server is ready."""
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception:
            return False


@asynccontextmanager
async def test_server(port: int = 8082) -> AsyncGenerator[str, None]:
    """
    Context manager that starts a test server and yields its base URL.

    Usage:
        async with test_server() as base_url:
            # Server is running at base_url
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url}/health")
    """
    manager = TestServerManager(port)
    base_url = manager.base_url

    try:
        await manager.start()
        yield base_url
    finally:
        await manager.stop()


# Singleton instance for module-level use
_server_manager: Optional[TestServerManager] = None


async def start_global_server(port: int = 8082) -> str:
    """Start a global test server for use across multiple tests."""
    global _server_manager
    if _server_manager is None:
        _server_manager = TestServerManager(port)
        await _server_manager.start()
    return _server_manager.base_url


async def stop_global_server() -> None:
    """Stop the global test server."""
    global _server_manager
    if _server_manager:
        await _server_manager.stop()
        _server_manager = None