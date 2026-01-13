"""Comprehensive unit tests for the API key rotation helper.

This test file ensures the `make_next_provider_key_fn` helper works correctly
for all scenarios including normal rotation, exclusion, and edge cases.
"""

import pytest
from fastapi import HTTPException

from src.api.services.key_rotation import make_next_provider_key_fn
from src.core.config import config
from src.core.provider_config import ProviderConfig


@pytest.mark.unit
@pytest.mark.asyncio
class TestMakeNextProviderKeyFn:
    """Test the provider API key rotation helper."""

    async def test_returns_first_key_when_empty_exclude(self, monkeypatch):
        """Should return the first available key when no keys are excluded."""
        call_count = 0

        async def fake_get_next_provider_api_key(provider_name: str) -> str:
            nonlocal call_count
            call_count += 1
            return "key1"

        monkeypatch.setattr(
            config.provider_manager,
            "get_next_provider_api_key",
            fake_get_next_provider_api_key,
        )

        # Mock get_provider_config to return a test provider config
        test_config = ProviderConfig(
            name="test_provider",
            api_key="key1",
            api_keys=["key1", "key2"],
            base_url="https://api.test.com",
        )
        monkeypatch.setattr(config.provider_manager, "get_provider_config", lambda _: test_config)

        next_key = make_next_provider_key_fn(provider_name="test_provider")
        result = await next_key(set())

        assert result == "key1"
        assert call_count == 1

    async def test_skips_single_excluded_key(self, monkeypatch):
        """Should skip excluded keys and return the next available key."""
        call_count = 0

        async def fake_get_next_provider_api_key(provider_name: str) -> str:
            nonlocal call_count
            call_count += 1
            # Return key1 first, then key2
            return "key1" if call_count == 1 else "key2"

        monkeypatch.setattr(
            config.provider_manager,
            "get_next_provider_api_key",
            fake_get_next_provider_api_key,
        )

        test_config = ProviderConfig(
            name="test_provider",
            api_key="key1",
            api_keys=["key1", "key2"],
            base_url="https://api.test.com",
        )
        monkeypatch.setattr(config.provider_manager, "get_provider_config", lambda _: test_config)

        next_key = make_next_provider_key_fn(provider_name="test_provider")
        result = await next_key({"key1"})

        assert result == "key2"
        assert call_count == 2

    async def test_skips_multiple_excluded_keys(self, monkeypatch):
        """Should skip all excluded keys and return the first non-excluded key."""
        call_count = 0

        async def fake_get_next_provider_api_key(provider_name: str) -> str:
            nonlocal call_count
            call_count += 1
            # Cycle through keys
            keys = ["key1", "key2", "key3"]
            return keys[(call_count - 1) % 3]

        monkeypatch.setattr(
            config.provider_manager,
            "get_next_provider_api_key",
            fake_get_next_provider_api_key,
        )

        test_config = ProviderConfig(
            name="test_provider",
            api_key="key1",
            api_keys=["key1", "key2", "key3"],
            base_url="https://api.test.com",
        )
        monkeypatch.setattr(config.provider_manager, "get_provider_config", lambda _: test_config)

        next_key = make_next_provider_key_fn(provider_name="test_provider")
        result = await next_key({"key1", "key2"})

        assert result == "key3"
        assert call_count == 3

    async def test_rotates_through_multiple_keys(self, monkeypatch):
        """Should properly rotate through all configured keys."""
        call_count = 0

        async def fake_get_next_provider_api_key(provider_name: str) -> str:
            nonlocal call_count
            call_count += 1
            # Return keys in order: key1, key2, key3
            keys = ["key1", "key2", "key3"]
            return keys[(call_count - 1) % 3]

        monkeypatch.setattr(
            config.provider_manager,
            "get_next_provider_api_key",
            fake_get_next_provider_api_key,
        )

        test_config = ProviderConfig(
            name="test_provider",
            api_key="key1",
            api_keys=["key1", "key2", "key3"],
            base_url="https://api.test.com",
        )
        monkeypatch.setattr(config.provider_manager, "get_provider_config", lambda _: test_config)

        next_key = make_next_provider_key_fn(provider_name="test_provider")

        # First call returns key1
        result1 = await next_key(set())
        assert result1 == "key1"

        # Second call returns key2
        result2 = await next_key(set())
        assert result2 == "key2"

        # Third call returns key3
        result3 = await next_key(set())
        assert result3 == "key3"

        # Fourth call wraps around to key1
        result4 = await next_key(set())
        assert result4 == "key1"

    async def test_raises_429_when_all_keys_exhausted(self, monkeypatch):
        """Should raise HTTP 429 when all keys are in the exclude set."""

        async def fake_get_next_provider_api_key(provider_name: str) -> str:
            return "key1"

        monkeypatch.setattr(
            config.provider_manager,
            "get_next_provider_api_key",
            fake_get_next_provider_api_key,
        )

        test_config = ProviderConfig(
            name="test_provider",
            api_key="key1",
            api_keys=["key1", "key2"],
            base_url="https://api.test.com",
        )
        monkeypatch.setattr(config.provider_manager, "get_provider_config", lambda _: test_config)

        next_key = make_next_provider_key_fn(provider_name="test_provider")

        with pytest.raises(HTTPException) as exc_info:
            await next_key({"key1", "key2"})

        assert exc_info.value.status_code == 429
        assert "exhausted" in str(exc_info.value.detail).lower()

    async def test_raises_429_when_all_keys_exhausted_single_key(self, monkeypatch):
        """Should raise HTTP 429 even with only one key configured."""

        async def fake_get_next_provider_api_key(provider_name: str) -> str:
            return "only-key"

        monkeypatch.setattr(
            config.provider_manager,
            "get_next_provider_api_key",
            fake_get_next_provider_api_key,
        )

        test_config = ProviderConfig(
            name="test_provider",
            api_key="only-key",
            api_keys=["only-key"],
            base_url="https://api.test.com",
        )
        monkeypatch.setattr(config.provider_manager, "get_provider_config", lambda _: test_config)

        next_key = make_next_provider_key_fn(provider_name="test_provider")

        with pytest.raises(HTTPException) as exc_info:
            await next_key({"only-key"})

        assert exc_info.value.status_code == 429

    async def test_uses_provider_manager_rotation(self, monkeypatch):
        """Should delegate to provider_manager for key rotation logic."""
        rotation_order = []

        async def fake_get_next_provider_api_key(provider_name: str) -> str:
            rotation_order.append(provider_name)
            keys = ["alpha", "beta", "gamma"]
            return keys[len(rotation_order) - 1]

        monkeypatch.setattr(
            config.provider_manager,
            "get_next_provider_api_key",
            fake_get_next_provider_api_key,
        )

        test_config = ProviderConfig(
            name="my_provider",
            api_key="alpha",
            api_keys=["alpha", "beta", "gamma"],
            base_url="https://api.test.com",
        )
        monkeypatch.setattr(config.provider_manager, "get_provider_config", lambda _: test_config)

        next_key = make_next_provider_key_fn(provider_name="my_provider")

        result1 = await next_key(set())
        assert result1 == "alpha"
        assert rotation_order == ["my_provider"]

        result2 = await next_key(set())
        assert result2 == "beta"
        assert rotation_order == ["my_provider", "my_provider"]

    async def test_single_key_provider(self, monkeypatch):
        """Should work correctly with providers that have only one API key."""

        async def fake_get_next_provider_api_key(provider_name: str) -> str:
            return "solo-key"

        monkeypatch.setattr(
            config.provider_manager,
            "get_next_provider_api_key",
            fake_get_next_provider_api_key,
        )

        test_config = ProviderConfig(
            name="single_key_provider",
            api_key="solo-key",
            api_keys=["solo-key"],
            base_url="https://api.test.com",
        )
        monkeypatch.setattr(config.provider_manager, "get_provider_config", lambda _: test_config)

        next_key = make_next_provider_key_fn(provider_name="single_key_provider")

        # Should work with empty exclude
        result = await next_key(set())
        assert result == "solo-key"

        # Should raise 429 when the only key is excluded
        with pytest.raises(HTTPException) as exc_info:
            await next_key({"solo-key"})
        assert exc_info.value.status_code == 429

    async def test_excludes_current_key_on_retry(self, monkeypatch):
        """Should be able to exclude the current key and get a different one."""
        call_count = 0

        async def fake_get_next_provider_api_key(provider_name: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "current-key"
            return "next-key"

        monkeypatch.setattr(
            config.provider_manager,
            "get_next_provider_api_key",
            fake_get_next_provider_api_key,
        )

        test_config = ProviderConfig(
            name="test_provider",
            api_key="current-key",
            api_keys=["current-key", "next-key", "backup-key"],
            base_url="https://api.test.com",
        )
        monkeypatch.setattr(config.provider_manager, "get_provider_config", lambda _: test_config)

        next_key = make_next_provider_key_fn(provider_name="test_provider")

        # Simulate a scenario where current-key failed and we need the next one
        result = await next_key({"current-key"})
        assert result in ("next-key", "backup-key")
        assert result != "current-key"

    async def test_handles_large_key_lists(self, monkeypatch):
        """Should efficiently handle providers with many API keys."""
        key_list = [f"key-{i}" for i in range(100)]
        exclude_set = {f"key-{i}" for i in range(99)}  # Exclude all but the last key

        call_count = 0

        async def fake_get_next_provider_api_key(provider_name: str) -> str:
            nonlocal call_count
            call_count += 1
            return key_list[min(call_count, len(key_list)) - 1]

        monkeypatch.setattr(
            config.provider_manager,
            "get_next_provider_api_key",
            fake_get_next_provider_api_key,
        )

        test_config = ProviderConfig(
            name="large_provider",
            api_key="key-0",
            api_keys=key_list,
            base_url="https://api.test.com",
        )
        monkeypatch.setattr(config.provider_manager, "get_provider_config", lambda _: test_config)

        next_key = make_next_provider_key_fn(provider_name="large_provider")

        result = await next_key(exclude_set)
        assert result == "key-99"
        # Should iterate through excluded keys to find a valid one
        assert call_count >= 100
