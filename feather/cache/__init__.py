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

import warnings

from feather.cache.base import CacheBackend
from feather.cache.decorators import cached, cache_response, invalidate_cache
from feather.core.config import get_setting
from feather.core.registry import get_backend, set_backend

#: Registry key for the per-app cache.
_CACHE_KEY = "cache"


def _build_cache(app) -> CacheBackend:
    """Create the cache backend this app's configuration asks for.

    Configuration comes from :func:`feather.core.config.get_setting`: the
    app config first, the environment when the app has no value (or when
    there is no app at all). Defaults are unchanged from 0.9.7.
    """
    backend = get_setting("CACHE_BACKEND", "memory")
    cache_url = get_setting("CACHE_URL", None)
    default_ttl = get_setting("CACHE_DEFAULT_TTL", 300, cast=int)

    if backend == "redis":
        from feather.cache.redis import RedisCache

        return RedisCache(url=cache_url or "redis://localhost:6379/0", default_ttl=default_ttl)

    from feather.cache.memory import MemoryCache

    return MemoryCache(default_ttl=default_ttl)


def get_cache() -> CacheBackend:
    """Get the configured cache backend for the current app.

    The cache is created once per Flask app and stored in
    ``app.extensions["feather"]``, so two apps in one process never share
    cache entries. Outside an app context it resolves to the process-level
    default cache.

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
    return get_backend(_CACHE_KEY, _build_cache)


def init_cache(app) -> CacheBackend:
    """Initialize the cache for a Flask app.

    Optional: the cache is created lazily on first use. Calling this stores
    the cache on ``app.extensions["feather"]["cache"]`` up front.

    Args:
        app: Flask application instance.

    Returns:
        CacheBackend instance for this app.
    """
    with app.app_context():
        cache = _build_cache(app)
    return set_backend(_CACHE_KEY, cache, app=app)


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


def __getattr__(name):
    """Deprecation shim for the 0.9.7 module-level cache singleton.

    ``feather.cache._cache_instance`` was the process-wide cache. It is now
    per app (``app.extensions["feather"]["cache"]``); reading the old name
    returns the current app's cache and warns. Assigning to it no longer
    has any effect - use
    ``feather.core.registry.set_backend("cache", cache)`` (or
    ``reset_backends(None, "cache")``) instead.
    """
    if name == "_cache_instance":
        warnings.warn(
            "feather.cache._cache_instance was replaced by the per-app registry in "
            "0.9.8. Use feather.cache.get_cache(), or "
            "feather.core.registry.set_backend('cache', cache) to override it. "
            "Assigning to _cache_instance no longer has any effect.",
            DeprecationWarning,
            stacklevel=2,
        )
        return get_cache()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
