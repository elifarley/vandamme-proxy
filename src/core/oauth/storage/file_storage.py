"""
Filesystem-based authentication storage.

Stores authentication data in ~/.chatgpt-local/auth.json with secure permissions.
"""

import json
import logging
import os
from pathlib import Path

from ..constants import StorageDefaults
from ..exceptions import StorageError
from . import AuthData, AuthStorage

_logger = logging.getLogger(__name__)


class FileSystemAuthStorage(AuthStorage):
    """File-based authentication storage.

    Uses ~/.chatgpt-local/auth.json by default, but can be configured
    to use any directory via the home_dir parameter.

    The auth file is created with mode 0600 (read/write for owner only)
    on Unix systems for security.
    """

    def __init__(self, home_dir: str | None = None, *, base_path: Path | None = None):
        """Initialize file-based storage.

        Args:
            home_dir: Directory to store auth.json. Defaults to:
                - $CHATGPT_LOCAL_HOME if set
                - $CODEX_HOME if set
                - ~/.chatgpt-local otherwise
            base_path: Alternative path specification (takes precedence over home_dir)
        """
        if base_path:
            self.home_dir = base_path
        elif home_dir:
            self.home_dir = Path(home_dir).expanduser()
        else:
            # Check environment variables
            env_home = os.getenv("CHATGPT_LOCAL_HOME") or os.getenv("CODEX_HOME")
            if env_home:
                self.home_dir = Path(env_home).expanduser()
            else:
                self.home_dir = Path.home() / ".chatgpt-local"

        self.auth_file = self.home_dir / "auth.json"

    def read_auth(self) -> AuthData | None:
        """Read authentication data from file.

        Returns:
            AuthData if file exists and contains valid data, None otherwise

        Raises:
            StorageError: If file exists but cannot be read or contains invalid data
        """
        if not self.auth_file.exists():
            return None

        try:
            with open(self.auth_file, encoding="utf-8") as f:
                data = json.load(f)
                return AuthData.from_dict(data)
        except FileNotFoundError:
            # File doesn't exist - this is acceptable
            return None
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            _logger.error("Corrupted auth file %s: %s", self.auth_file, e)
            raise StorageError(f"Invalid auth data in {self.auth_file}: {e}") from e
        except OSError as e:
            _logger.error("Failed to read auth file %s: %s", self.auth_file, e)
            raise StorageError(f"Cannot read auth file: {e}") from e

    def write_auth(self, data: AuthData) -> None:
        """Write authentication data to file.

        Creates the directory if it doesn't exist.
        Sets file permissions to 0600 on Unix systems.

        Args:
            data: Authentication data to write

        Raises:
            StorageError: If write fails due to I/O errors
        """
        try:
            self.home_dir.mkdir(parents=True, exist_ok=True)

            with open(self.auth_file, "w", encoding="utf-8") as f:
                # Set restrictive permissions on Unix-like systems
                if hasattr(os, "fchmod"):
                    os.fchmod(f.fileno(), StorageDefaults.FILE_PERMISSIONS)
                json.dump(data.to_dict(), f, indent=2)
        except OSError as e:
            _logger.error("Failed to write auth file %s: %s", self.auth_file, e)
            raise StorageError(f"Cannot write auth file: {e}") from e

    def clear_auth(self) -> None:
        """Remove authentication data file.

        Raises:
            StorageError: If file removal fails due to I/O errors
        """
        try:
            self.auth_file.unlink(missing_ok=True)
        except OSError as e:
            _logger.error("Failed to remove auth file %s: %s", self.auth_file, e)
            raise StorageError(f"Cannot remove auth file: {e}") from e

    @property
    def path(self) -> str:
        """Get the path to the auth file.

        Returns:
            Absolute path to auth.json as string
        """
        return str(self.auth_file)
