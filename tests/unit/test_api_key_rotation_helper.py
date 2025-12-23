import pytest
from fastapi import HTTPException


@pytest.mark.unit
@pytest.mark.asyncio
async def test_make_next_provider_key_fn_skips_excluded(monkeypatch):
    from src.api.services.key_rotation import make_next_provider_key_fn

    calls = []

    async def fake_get_next_provider_api_key(provider_name: str) -> str:
        calls.append(provider_name)
        # Always returns key1 first, then key2
        return "key1" if len(calls) == 1 else "key2"

    from src.core.config import config

    monkeypatch.setattr(
        config.provider_manager, "get_next_provider_api_key", fake_get_next_provider_api_key
    )

    next_key = make_next_provider_key_fn(provider_name="openai", api_keys=["key1", "key2"])
    k = await next_key({"key1"})
    assert k == "key2"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_make_next_provider_key_fn_exhausted_raises():
    from src.api.services.key_rotation import make_next_provider_key_fn

    next_key = make_next_provider_key_fn(provider_name="openai", api_keys=["key1", "key2"])

    with pytest.raises(HTTPException) as exc:
        await next_key({"key1", "key2"})

    assert exc.value.status_code == 429
    assert "exhausted" in str(exc.value.detail).lower()
