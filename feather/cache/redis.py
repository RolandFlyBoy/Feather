"""
Redis Cache Backend
===================

Redis-compatible cache backend for production deployments.

Supports any Redis-compatible server including:
- Redis
- Redis on Render
- Upstash Redis
- KeyDB
- Dragonfly

Configuration
-------------
Set in environment variables or config.py::

    CACHE_BACKEND=redis
    CACHE_URL=redis://localhost:6379/0

    # Or with authentication
    CACHE_URL=redis://:password@host:6379/0

    # Or Render Redis
    CACHE_URL=redis://red-xxx:6379

Usage
-----
::

    from feather.cache.redis import RedisCache

    cache = RedisCache(url='redis://localhost:6379/0')
    cache.set('user:123', {'name': 'John'}, ttl=60)
    user = cache.get('user:123')

Note:
    Requires the `redis` package: pip install redis
"""

import json
from typing import Any, Optional

from feather.cache.base import CacheBackend


class RedisCache(CacheBackend):
    """Redis-compatible cache backend.

    Uses JSON serialization for values, supporting dicts, lists, strings,
    numbers, and booleans.

    Args:
        url: Redis connection URL (e.g., 'redis://localhost:6379/0').
        default_ttl: Default time-to-live in seconds (default: 300).
        prefix: Key prefix for namespacing (default: 'feather:').

    Example::

        cache = RedisCache(url='redis://localhost:6379/0')
        cache.set('session:abc', {'user_id': 123}, ttl=3600)
        session = cache.get('session:abc')
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        default_ttl: int = 300,
        prefix: str = "feather:",
    ):
        try:
            import redis
        except ImportError:
            raise ImportError(
                "Redis cache requires the 'redis' package. "
                "Install it with: pip install redis"
            )

        self._client = redis.from_url(url, decode_responses=True)
        self._default_ttl = default_ttl
        self._prefix = prefix

    def _make_key(self, key: str) -> str:
        """Add prefix to key for namespacing."""
        return f"{self._prefix}{key}"

    def _serialize(self, value: Any) -> str:
        """Serialize value to JSON string."""
        return json.dumps(value)

    def _deserialize(self, data: Optional[str]) -> Optional[Any]:
        """Deserialize JSON string to value."""
        if data is None:
            return None
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return data  # Return as-is if not JSON

    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache.

        Args:
            key: Cache key.

        Returns:
            Cached value, or None if not found.
        """
        data = self._client.get(self._make_key(key))
        return self._deserialize(data)

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a value in the cache.

        Args:
            key: Cache key.
            value: Value to cache (must be JSON-serializable).
            ttl: Time-to-live in seconds. None uses default TTL.
                 0 means no expiration.

        Returns:
            True if successful.
        """
        if ttl is None:
            ttl = self._default_ttl

        full_key = self._make_key(key)
        serialized = self._serialize(value)

        if ttl > 0:
            return bool(self._client.setex(full_key, ttl, serialized))
        else:
            return bool(self._client.set(full_key, serialized))

    def delete(self, key: str) -> bool:
        """Delete a value from the cache.

        Args:
            key: Cache key.

        Returns:
            True if key existed and was deleted.
        """
        return bool(self._client.delete(self._make_key(key)))

    def clear(self) -> bool:
        """Clear all values with our prefix from the cache.

        Returns:
            True if successful.
        """
        pattern = f"{self._prefix}*"
        cursor = 0
        while True:
            cursor, keys = self._client.scan(cursor, match=pattern, count=100)
            if keys:
                self._client.delete(*keys)
            if cursor == 0:
                break
        return True

    def exists(self, key: str) -> bool:
        """Check if a key exists in the cache.

        Args:
            key: Cache key.

        Returns:
            True if key exists.
        """
        return bool(self._client.exists(self._make_key(key)))

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from the cache.

        Args:
            keys: List of cache keys.

        Returns:
            Dictionary of key-value pairs for keys that exist.
        """
        if not keys:
            return {}

        full_keys = [self._make_key(k) for k in keys]
        values = self._client.mget(full_keys)

        result = {}
        for key, value in zip(keys, values):
            if value is not None:
                result[key] = self._deserialize(value)
        return result

    def set_many(self, mapping: dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set multiple values in the cache.

        Args:
            mapping: Dictionary of key-value pairs.
            ttl: Time-to-live in seconds.

        Returns:
            True if successful.
        """
        if not mapping:
            return True

        if ttl is None:
            ttl = self._default_ttl

        pipe = self._client.pipeline()
        for key, value in mapping.items():
            full_key = self._make_key(key)
            serialized = self._serialize(value)
            if ttl > 0:
                pipe.setex(full_key, ttl, serialized)
            else:
                pipe.set(full_key, serialized)
        pipe.execute()
        return True

    def delete_many(self, keys: list[str]) -> int:
        """Delete multiple values from the cache.

        Args:
            keys: List of cache keys.

        Returns:
            Number of keys that were deleted.
        """
        if not keys:
            return 0
        full_keys = [self._make_key(k) for k in keys]
        return self._client.delete(*full_keys)

    def increment(self, key: str, delta: int = 1) -> Optional[int]:
        """Atomically increment a numeric value.

        Args:
            key: Cache key.
            delta: Amount to increment.

        Returns:
            New value, or None if key doesn't exist.
        """
        full_key = self._make_key(key)
        if not self._client.exists(full_key):
            return None
        return self._client.incrby(full_key, delta)

    def decrement(self, key: str, delta: int = 1) -> Optional[int]:
        """Atomically decrement a numeric value.

        Args:
            key: Cache key.
            delta: Amount to decrement.

        Returns:
            New value, or None if key doesn't exist.
        """
        return self.increment(key, -delta)

    def ttl(self, key: str) -> Optional[int]:
        """Get the time-to-live for a key.

        Args:
            key: Cache key.

        Returns:
            TTL in seconds, -1 if no expiration, -2 if key doesn't exist.
        """
        return self._client.ttl(self._make_key(key))

    def expire(self, key: str, ttl: int) -> bool:
        """Set expiration on an existing key.

        Args:
            key: Cache key.
            ttl: Time-to-live in seconds.

        Returns:
            True if key exists and expiration was set.
        """
        return bool(self._client.expire(self._make_key(key), ttl))

    @property
    def client(self):
        """Access the underlying Redis client for advanced operations."""
        return self._client
