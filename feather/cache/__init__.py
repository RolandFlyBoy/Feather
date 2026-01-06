"""
Cache Module
============

Provides caching functionality for Feather applications.

Supported Backends:
- MemoryCache: In-memory cache for development (default)
- RedisCache: Redis-compatible cache for production

Configuration
-------------
Set in environment variables or config.py::

    # Use memory cache (default)
    CACHE_BACKEND=memory
    CACHE_DEFAULT_TTL=300

    # Use Redis cache
    CACHE_BACKEND=redis
    CACHE_URL=redis://localhost:6379/0

Quick Start
-----------
::

    from feather.cache import get_cache, cached, cache_response

    # Direct cache access
    cache = get_cache()
    cache.set('key', 'value', ttl=60)
    value = cache.get('key')

    # Cache function results
    @cached(ttl=60)
    def expensive_query(user_id):
        return User.query.get(user_id)

    # Cache API responses
    @api.get('/products')
    @cache_response(ttl=300)
    def list_products():
        return {'products': [...]}

Response Caching
----------------
The @cache_response decorator caches API responses::

    # Basic caching (5 minutes)
    @api.get('/items')
    @cache_response(ttl=300)
    def list_items():
        return {'items': Item.query.all()}

    # Cache with custom key using URL params
    @api.get('/users/<user_id>')
    @cache_response(ttl=60, key='user:{user_id}')
    def get_user(user_id):
        return {'user': User.query.get(user_id)}

    # Vary by query string (default behavior)
    @api.get('/search')
    @cache_response(ttl=60, vary_on=['query'])
    def search():
        q = request.args.get('q')
        return {'results': search_products(q)}

    # Skip caching for certain conditions
    @api.get('/dashboard')
    @cache_response(ttl=300, unless=lambda: current_user.is_admin)
    def dashboard():
        return {'stats': get_stats()}

Cache Invalidation
------------------
::

    from feather.cache import get_cache, invalidate_cache

    # Invalidate specific key
    cache = get_cache()
    cache.delete('user:123')

    # Invalidate with pattern (Redis only)
    invalidate_cache('user:*')

    # Function result invalidation
    @cached(ttl=60)
    def get_user_stats(user_id):
        return calculate_stats(user_id)

    # Later, invalidate cached result
    get_user_stats.invalidate(123)
"""

import os
from typing import Optional

from feather.cache.base import CacheBackend
from feather.cache.decorators import cached, cache_response, invalidate_cache

# Singleton cache instance
_cache_instance: Optional[CacheBackend] = None


def get_cache() -> CacheBackend:
    """Get the configured cache backend.

    Creates a singleton cache instance based on configuration.
    Uses CACHE_BACKEND environment variable or config.

    Returns:
        CacheBackend instance.

    Configuration:
        CACHE_BACKEND: 'memory' (default) or 'redis'
        CACHE_URL: Redis connection URL (for redis backend)
        CACHE_DEFAULT_TTL: Default TTL in seconds (default: 300)

    Example::

        from feather.cache import get_cache

        cache = get_cache()
        cache.set('user:123', user_data, ttl=60)
        user = cache.get('user:123')
    """
    global _cache_instance

    if _cache_instance is not None:
        return _cache_instance

    # Get configuration
    try:
        from flask import current_app

        backend = current_app.config.get("CACHE_BACKEND", os.environ.get("CACHE_BACKEND", "memory"))
        cache_url = current_app.config.get("CACHE_URL", os.environ.get("CACHE_URL"))
        default_ttl = current_app.config.get(
            "CACHE_DEFAULT_TTL",
            int(os.environ.get("CACHE_DEFAULT_TTL", "300"))
        )
    except RuntimeError:
        # No Flask app context
        backend = os.environ.get("CACHE_BACKEND", "memory")
        cache_url = os.environ.get("CACHE_URL")
        default_ttl = int(os.environ.get("CACHE_DEFAULT_TTL", "300"))

    # Create backend
    if backend == "redis":
        from feather.cache.redis import RedisCache

        if not cache_url:
            cache_url = "redis://localhost:6379/0"
        _cache_instance = RedisCache(url=cache_url, default_ttl=default_ttl)
    else:
        from feather.cache.memory import MemoryCache

        _cache_instance = MemoryCache(default_ttl=default_ttl)

    return _cache_instance


def init_cache(app) -> CacheBackend:
    """Initialize cache with Flask app.

    Optionally called to set up cache with app configuration.
    The cache is also lazily initialized on first use.

    Args:
        app: Flask application instance.

    Returns:
        CacheBackend instance.
    """
    global _cache_instance

    # Reset instance to pick up new config
    _cache_instance = None

    # Get cache within app context
    with app.app_context():
        return get_cache()


__all__ = [
    # Factory
    "get_cache",
    "init_cache",
    # Base class
    "CacheBackend",
    # Decorators
    "cached",
    "cache_response",
    "invalidate_cache",
]
