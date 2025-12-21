"""Base classes for disk-based JSON caching.

Provides atomic writes, TTL validation, schema versioning, and test isolation.
"""

# type: ignore

from __future__ import annotations

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DiskCacheError(Exception):
    """Base exception for disk cache operations."""

    pass


class DiskJsonCache(ABC):
    """Abstract base class for disk-based JSON caches.

    Features:
    - Atomic writes via temporary file + rename
    - TTL-based expiration with UTC timestamps
    - Schema versioning for migrations
    - Automatic test isolation (bypass when PYTEST_CURRENT_TEST set)
    - Configurable cache directory hierarchy

    Subclasses must implement:
    - _file_path(): Returns the Path for the cache file
    - _serialize(): Converts domain object to JSON-serializable dict
    - _deserialize(): Converts JSON dict back to domain object
    """

    def __init__(
        self,
        cache_dir: Path,
        ttl: timedelta,
        schema_version: int,
        *,
        namespace: str = "default",
    ) -> None:
        """Initialize cache with directory, TTL, and schema version.

        Args:
            cache_dir: Base directory for caches (e.g., ~/.cache/vandamme-proxy)
            ttl: Time-to-live for cached entries
            schema_version: Version number for cache format migrations
            namespace: Optional namespace for grouping related caches
        """
        self.cache_dir = Path(cache_dir).expanduser()
        self.ttl = ttl
        self.schema_version = schema_version
        self.namespace = namespace

    def _should_skip_cache(self) -> bool:
        """Check if cache should be bypassed (e.g., during tests)."""
        return "testserver" in str(self.cache_dir)

    def _is_cache_fresh(self, cache_data: dict[str, Any]) -> bool:
        """Check if cached data is still within TTL."""
        try:
            last_updated_str = cache_data.get("last_updated")
            if not last_updated_str:
                return False

            last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            return (now - last_updated) <= self.ttl
        except (ValueError, TypeError) as e:
            logger.debug(f"Cache timestamp validation failed: {e}")
            return False

    def _atomic_write(self, path: Path, data: dict[str, Any]) -> None:
        """Write data atomically to prevent corruption."""
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = path.with_suffix(".json.tmp")
        try:
            temp_path.write_text(
                json.dumps(data, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temp_path.replace(path)
            logger.debug(f"Cache written to {path}")
        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    logger.debug(f"Failed to cleanup temp file: {temp_path}")
            raise DiskCacheError(f"Failed to write cache to {path}: {e}") from e

    def _read_cache_file(self, path: Path) -> dict[str, Any] | None:
        """Read and validate cache file."""
        try:
            if not path.exists():
                return None

            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate schema version
            if data.get("schema_version") != self.schema_version:
                logger.debug(
                    f"Cache schema version mismatch: "
                    f"{data.get('schema_version')} != {self.schema_version}"
                )
                return None

            return data
        except (OSError, json.JSONDecodeError) as e:
            logger.debug(f"Cache read failed from {path}: {e}")
            return None

    @abstractmethod
    def _file_path(self) -> Path:
        """Return the full path to the cache file."""
        ...

    @abstractmethod
    def _serialize(self, payload: Any) -> dict[str, Any]:
        """Convert domain object to cache-serializable dict."""
        ...

    @abstractmethod
    def _deserialize(self, cache_data: dict[str, Any]) -> Any:
        """Convert cache dict back to domain object."""
        ...

    def read_if_fresh(self) -> Any:  # noqa: ANN401
        """Read from cache if fresh and valid.

        Returns:
            Deserialized domain object if cache is fresh, None otherwise.
        """
        if self._should_skip_cache():
            logger.debug("Cache bypassed due to test environment")
            return None

        path = self._file_path()
        cache_data = self._read_cache_file(path)

        if not cache_data:
            return None

        if not self._is_cache_fresh(cache_data):
            logger.debug("Cache expired")
            return None

        try:
            return self._deserialize(cache_data)
        except Exception as e:
            logger.debug(f"Cache deserialization failed: {e}")
            return None

    def write(self, payload: Any) -> None:  # noqa: ANN401
        """Write payload to cache with metadata.

        Args:
            payload: Domain object to cache
        """
        if self._should_skip_cache():
            logger.debug("Cache write skipped due to test environment")
            return

        path = self._file_path()

        # Prepare cache data with metadata
        cache_data = {
            "schema_version": self.schema_version,
            "last_updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            **self._serialize(payload),
        }

        self._atomic_write(path, cache_data)

    def clear(self) -> bool:
        """Remove the cache file if it exists.

        Returns:
            True if file was removed, False if it didn't exist
        """
        path = self._file_path()
        if path.exists():
            try:
                path.unlink()
                logger.debug(f"Cache cleared: {path}")
                return True
            except Exception as e:
                raise DiskCacheError(f"Failed to clear cache {path}: {e}") from e
        return False


def make_cache_key(*args: str) -> str:
    """Create deterministic cache key from string arguments.

    Args:
        *args: String values to include in cache key

    Returns:
        12-character hex hash of the input data
    """
    data = json.dumps(list(args), sort_keys=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:12]
