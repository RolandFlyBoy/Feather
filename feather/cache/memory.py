"""
In-Memory Cache Backend
=======================

Simple thread-safe in-memory cache for development and single-process deployments.

This cache stores values in memory with optional TTL expiration.
Data is lost when the process restarts.

Usage
-----
::

    from feather.cache.memory import MemoryCache

    cache = MemoryCache(default_ttl=300)
    cache.set('user:123', {'name': 'John'}, ttl=60)
    user = cache.get('user:123')

Note:
    For multi-process or multi-server deployments, use RedisCache instead.
"""

import threading
import time
from typing import Any, Optional

from feather.cache.base import CacheBackend


class MemoryCache(CacheBackend):
    """Thread-safe in-memory cache with TTL support.

    Stores values in a dictionary with expiration timestamps.
    Expired entries are cleaned up lazily on access.

    Args:
        default_ttl: Default time-to-live in seconds (default: 300).
        max_size: Maximum number of entries (default: 10000).
            When exceeded, oldest entries are evicted.

    Example::

        cache = MemoryCache(default_ttl=60)
        cache.set('key', 'value')
        cache.get('key')  # Returns 'value'

        # After 60 seconds...
        cache.get('key')  # Returns None
    """

    def __init__(self, default_ttl: int = 300, max_size: int = 10000):
        self._cache: dict[str, tuple[Any, float]] = {}  # key -> (value, expires_at)
        self._lock = threading.RLock()
        self._default_ttl = default_ttl
        self._max_size = max_size

    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache.

        Args:
            key: Cache key.

        Returns:
            Cached value, or None if not found or expired.
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            value, expires_at = entry
            if expires_at and time.time() > expires_at:
                # Entry expired, remove it
                del self._cache[key]
                return None

            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a value in the cache.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: Time-to-live in seconds. None uses default TTL.
                 0 means no expiration.

        Returns:
            True if successful.
        """
        if ttl is None:
            ttl = self._default_ttl

        expires_at = time.time() + ttl if ttl > 0 else 0

        with self._lock:
            # Evict oldest entries if at max size
            if len(self._cache) >= self._max_size and key not in self._cache:
                self._evict_oldest()

            self._cache[key] = (value, expires_at)
            return True

    def delete(self, key: str) -> bool:
        """Delete a value from the cache.

        Args:
            key: Cache key.

        Returns:
            True if key existed and was deleted.
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> bool:
        """Clear all values from the cache.

        Returns:
            True if successful.
        """
        with self._lock:
            self._cache.clear()
            return True

    def exists(self, key: str) -> bool:
        """Check if a key exists and hasn't expired.

        Args:
            key: Cache key.

        Returns:
            True if key exists and is valid.
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False

            _, expires_at = entry
            if expires_at and time.time() > expires_at:
                del self._cache[key]
                return False

            return True

    def increment(self, key: str, delta: int = 1) -> Optional[int]:
        """Atomically increment a numeric value.

        Args:
            key: Cache key.
            delta: Amount to increment.

        Returns:
            New value, or None if key doesn't exist.
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            value, expires_at = entry
            if expires_at and time.time() > expires_at:
                del self._cache[key]
                return None

            try:
                new_value = int(value) + delta
                self._cache[key] = (new_value, expires_at)
                return new_value
            except (TypeError, ValueError):
                return None

    def _evict_oldest(self) -> None:
        """Evict expired entries, then oldest entries if still over limit."""
        now = time.time()

        # First, remove expired entries
        expired = [k for k, (_, exp) in self._cache.items() if exp and now > exp]
        for key in expired:
            del self._cache[key]

        # If still over limit, remove oldest (by insertion order in Python 3.7+)
        while len(self._cache) >= self._max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

    def cleanup(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed.
        """
        with self._lock:
            now = time.time()
            expired = [k for k, (_, exp) in self._cache.items() if exp and now > exp]
            for key in expired:
                del self._cache[key]
            return len(expired)

    def size(self) -> int:
        """Get the number of entries in the cache.

        Returns:
            Number of entries (including potentially expired ones).
        """
        return len(self._cache)
