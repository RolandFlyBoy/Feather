"""
Cache Backend Base Class
========================

Abstract base class for cache backends.

Feather supports multiple cache backends:
- MemoryCache: In-memory cache for development (default)
- RedisCache: Redis-compatible cache for production

Configuration
-------------
Set in environment variables or config.py::

    CACHE_BACKEND=memory  # or 'redis'
    CACHE_URL=redis://localhost:6379/0  # for Redis
    CACHE_DEFAULT_TTL=300  # default TTL in seconds

Usage
-----
::

    from feather.cache import get_cache

    cache = get_cache()
    cache.set('key', 'value', ttl=60)
    value = cache.get('key')
    cache.delete('key')
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class CacheBackend(ABC):
    """Abstract base class for cache backends.

    All cache backends must implement these methods to provide
    a consistent caching interface.

    Example::

        class MyCache(CacheBackend):
            def get(self, key):
                # Retrieve from cache
                pass

            def set(self, key, value, ttl=None):
                # Store in cache
                pass

            def delete(self, key):
                # Remove from cache
                pass

            def clear(self):
                # Clear all cache
                pass
    """

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache.

        Args:
            key: Cache key.

        Returns:
            Cached value, or None if not found or expired.
        """
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a value in the cache.

        Args:
            key: Cache key.
            value: Value to cache (must be serializable).
            ttl: Time-to-live in seconds. None uses default TTL.

        Returns:
            True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a value from the cache.

        Args:
            key: Cache key.

        Returns:
            True if key existed and was deleted, False otherwise.
        """
        pass

    @abstractmethod
    def clear(self) -> bool:
        """Clear all values from the cache.

        Returns:
            True if successful, False otherwise.
        """
        pass

    def exists(self, key: str) -> bool:
        """Check if a key exists in the cache.

        Args:
            key: Cache key.

        Returns:
            True if key exists and hasn't expired.
        """
        return self.get(key) is not None

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from the cache.

        Args:
            keys: List of cache keys.

        Returns:
            Dictionary of key-value pairs for keys that exist.
        """
        result = {}
        for key in keys:
            value = self.get(key)
            if value is not None:
                result[key] = value
        return result

    def set_many(self, mapping: dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set multiple values in the cache.

        Args:
            mapping: Dictionary of key-value pairs.
            ttl: Time-to-live in seconds for all keys.

        Returns:
            True if all keys were set successfully.
        """
        success = True
        for key, value in mapping.items():
            if not self.set(key, value, ttl):
                success = False
        return success

    def delete_many(self, keys: list[str]) -> int:
        """Delete multiple values from the cache.

        Args:
            keys: List of cache keys.

        Returns:
            Number of keys that were deleted.
        """
        count = 0
        for key in keys:
            if self.delete(key):
                count += 1
        return count

    def increment(self, key: str, delta: int = 1) -> Optional[int]:
        """Increment a numeric value in the cache.

        Args:
            key: Cache key.
            delta: Amount to increment by (can be negative).

        Returns:
            New value after increment, or None if key doesn't exist.
        """
        value = self.get(key)
        if value is None:
            return None
        try:
            new_value = int(value) + delta
            self.set(key, new_value)
            return new_value
        except (TypeError, ValueError):
            return None

    def decrement(self, key: str, delta: int = 1) -> Optional[int]:
        """Decrement a numeric value in the cache.

        Args:
            key: Cache key.
            delta: Amount to decrement by.

        Returns:
            New value after decrement, or None if key doesn't exist.
        """
        return self.increment(key, -delta)
