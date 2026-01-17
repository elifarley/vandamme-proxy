"""
In-memory authentication storage for testing and ephemeral use.

This implementation stores auth data in memory only - data is lost
when the process exits. Useful for testing and scenarios where
persistence is not needed.
"""

from . import AuthData, AuthStorage


class InMemoryAuthStorage(AuthStorage):
    """In-memory authentication storage.

    Stores authentication data in a dictionary. Data persists only
    for the lifetime of the process. Useful for:
    - Testing (no file I/O, easy cleanup)
    - Ephemeral sessions
    - Example code and demos
    """

    def __init__(self) -> None:
        """Initialize in-memory storage."""
        self._data: AuthData | None = None

    def read_auth(self) -> AuthData | None:
        """Read authentication data from memory.

        Returns:
            AuthData if previously written, None otherwise
        """
        return self._data

    def write_auth(self, data: AuthData) -> None:
        """Write authentication data to memory.

        Args:
            data: Authentication data to store
        """
        self._data = data

    def clear_auth(self) -> None:
        """Remove authentication data from memory."""
        self._data = None

    def __repr__(self) -> str:
        """String representation showing auth state."""
        if self._data:
            return f"InMemoryAuthStorage(authenticated=True, account={self._data.account_id})"
        return "InMemoryAuthStorage(authenticated=False)"
