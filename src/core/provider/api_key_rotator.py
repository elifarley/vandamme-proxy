"""API key rotation with round-robin failover."""

import asyncio


class ApiKeyRotator:
    """Thread-safe round-robin API key rotation per provider.

    Responsibilities:
    - Track rotation state per provider
    - Provide next key with thread-safe locking
    - Support multiple keys per provider

    This class uses asyncio.Lock for thread-safe rotation in async contexts.
    """

    def __init__(self) -> None:
        """Initialize a new API key rotator."""
        self._locks: dict[str, asyncio.Lock] = {}
        self._indices: dict[str, int] = {}

    async def get_next_key(self, provider_name: str, api_keys: list[str]) -> str:
        """Get the next API key using round-robin rotation.

        Args:
            provider_name: The name of the provider.
            api_keys: List of available API keys for this provider.

        Returns:
            The next API key in the rotation.

        Raises:
            ValueError: If api_keys is empty.
        """
        if not api_keys:
            raise ValueError(f"No API keys available for provider '{provider_name}'")

        lock = self._locks.setdefault(provider_name, asyncio.Lock())
        async with lock:
            idx = self._indices.get(provider_name, 0)
            key = api_keys[idx % len(api_keys)]
            self._indices[provider_name] = (idx + 1) % len(api_keys)
            return key

    def reset_rotation(self, provider_name: str) -> None:
        """Reset rotation state for a provider.

        This is primarily useful for testing.

        Args:
            provider_name: The name of the provider to reset.
        """
        self._indices.pop(provider_name, None)
