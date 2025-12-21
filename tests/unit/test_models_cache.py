"""Tests for the ModelsDiskCache implementation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.models.cache import ModelsDiskCache


@pytest.fixture
def temp_cache_dir():
    """Create a temporary directory for cache files."""
    with tempfile.TemporaryDirectory(prefix="vdm-test-cache-") as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def models_cache(temp_cache_dir):
    """Create a ModelsDiskCache instance with test directory."""
    return ModelsDiskCache(cache_dir=temp_cache_dir, ttl_hours=1)


@pytest.fixture
def sample_models():
    """Sample models data like what OpenAI API returns."""
    return [
        {
            "id": "gpt-4",
            "object": "model",
            "created": 1687882410,
            "owned_by": "openai",
        },
        {
            "id": "gpt-3.5-turbo",
            "object": "model",
            "created": 1677610602,
            "owned_by": "openai",
        },
    ]


class TestModelsDiskCache:
    """Test ModelsDiskCache functionality."""

    def test_file_path_generation(self, models_cache):
        """Test cache file path generation."""
        provider = "openai"
        base_url = "https://api.openai.com/v1"
        headers = {"Authorization": "Bearer test"}

        path = models_cache.make_file_path(provider, base_url, headers)
        expected_parts = [
            str(models_cache.cache_dir),
            "models",
            provider,
            "models-",
        ]
        assert all(part in str(path) for part in expected_parts)
        assert path.suffix == ".json"

    def test_file_path_deterministic(self, models_cache):
        """Test that same inputs generate same path."""
        provider = "openai"
        base_url = "https://api.openai.com/v1"
        headers = {"Authorization": "Bearer test"}

        path1 = models_cache.make_file_path(provider, base_url, headers)
        path2 = models_cache.make_file_path(provider, base_url, headers)
        assert path1 == path2

    def test_file_path_different_headers(self, models_cache):
        """Test that different headers generate different paths."""
        provider = "openai"
        base_url = "https://api.openai.com/v1"

        path1 = models_cache.make_file_path(provider, base_url, {"X-Test": "1"})
        path2 = models_cache.make_file_path(provider, base_url, {"X-Test": "2"})
        assert path1 != path2

    def test_read_cache_miss(self, models_cache):
        """Test reading from empty cache."""
        result = models_cache.read_models_if_fresh("openai", "https://api.openai.com", {})
        assert result is None

    def test_write_and_read_cache(self, models_cache, sample_models):
        """Test writing to and reading from cache."""
        provider = "openai"
        base_url = "https://api.openai.com"
        headers = {"X-Test": "value"}

        # Write models to cache
        models_cache.write_models(provider, base_url, headers, sample_models)

        # Read models from cache
        result = models_cache.read_models_if_fresh(provider, base_url, headers)
        assert result is not None
        assert len(result) == len(sample_models)
        assert result[0]["id"] == sample_models[0]["id"]

    def test_cache_file_contents(self, models_cache, sample_models):
        """Test that cache file contains expected data."""
        provider = "openai"
        base_url = "https://api.openai.com"
        headers = {}

        models_cache.write_models(provider, base_url, headers, sample_models)

        cache_file = models_cache.make_file_path(provider, base_url, headers)
        assert cache_file.exists()

        with cache_file.open("r") as f:
            data = json.load(f)

        assert data["schema_version"] == 1
        assert data["provider"] == provider
        assert data["base_url"] == base_url
        assert "last_updated" in data
        assert data["models"] == sample_models

    def test_atomic_write_prevents_corruption(self, models_cache, sample_models):
        """Test that atomic writes prevent corruption on error."""
        provider = "openai"
        base_url = "https://api.openai.com"
        headers = {}

        path = models_cache.make_file_path(provider, base_url, headers)
        temp_path = path.with_suffix(".json.tmp")

        # Create parent directory
        path.parent.mkdir(parents=True, exist_ok=True)

        # Simulate a partially written file
        temp_path.write_text('{"incomplete": "data"')

        # Try to write good data
        models_cache.write_models(provider, base_url, headers, sample_models)

        # Temp file should be cleaned up
        assert not temp_path.exists()

        # Real file should contain good data
        with path.open("r") as f:
            data = json.load(f)
        assert "schema_version" in data
        assert data["models"] == sample_models

    def test_cache_isolation(self, models_cache, sample_models):
        """Test that different providers have isolated caches."""
        provider1 = "openai"
        provider2 = "anthropic"
        base_url1 = "https://api.openai.com"
        base_url2 = "https://api.anthropic.com"
        headers = {}

        # Write models for provider1
        models_cache.write_models(provider1, base_url1, headers, sample_models)

        # Provider2 should not find provider1's data
        result = models_cache.read_models_if_fresh(provider2, base_url2, headers)
        assert result is None

        # Provider1 should find its data
        result = models_cache.read_models_if_fresh(provider1, base_url1, headers)
        assert result is not None

    def test_cache_bypass_in_tests(self, models_cache, sample_models):
        """Test that cache is bypassed when cache dir contains 'testserver'."""
        provider = "openai"
        base_url = "https://api.openai.com"
        headers = {}

        # Create a cache with testserver in the path to trigger bypass
        import tempfile

        with tempfile.TemporaryDirectory(prefix="testserver-") as test_dir:
            bypass_cache = ModelsDiskCache(
                cache_dir=Path(test_dir),
                ttl_hours=1,
            )

            # Write to cache (should be skipped)
            bypass_cache.write_models(provider, base_url, headers, sample_models)

            # Read from cache (should return None)
            result = bypass_cache.read_models_if_fresh(provider, base_url, headers)
            assert result is None

            # Cache file should not exist
            path = bypass_cache.make_file_path(provider, base_url, headers)
            assert not path.exists()

    def test_invalid_cached_data_handling(self, models_cache):
        """Test handling of invalid cached data."""
        provider = "openai"
        base_url = "https://api.openai.com"
        headers = {}

        cache_file = models_cache.make_file_path(provider, base_url, headers)
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        # Write invalid JSON
        cache_file.write_text('{"invalid": json}')

        # Should return None instead of raising
        result = models_cache.read_models_if_fresh(provider, base_url, headers)
        assert result is None

        # Write valid JSON but wrong schema
        cache_file.write_text('{"schema_version": 999, "not_models": "data"}')

        # Should return None due to schema mismatch
        result = models_cache.read_models_if_fresh(provider, base_url, headers)
        assert result is None

    def test_empty_models_list(self, models_cache):
        """Test caching empty models list."""
        provider = "openai"
        base_url = "https://api.openai.com"
        headers = {}

        # Write empty models list
        models_cache.write_models(provider, base_url, headers, [])

        # Should read back empty list
        result = models_cache.read_models_if_fresh(provider, base_url, headers)
        assert result == []
