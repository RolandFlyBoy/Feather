"""
Cache Decorators
================

Decorators for caching function results and API responses.

Usage
-----
::

    from feather.cache import cached, cache_response

    # Cache function results
    @cached(ttl=60)
    def expensive_calculation(x, y):
        return x ** y

    # Cache API responses
    @api.get('/products')
    @cache_response(ttl=300)
    def list_products():
        return {'products': Product.query.all()}

    # Cache with custom key
    @api.get('/users/<user_id>')
    @cache_response(ttl=60, key='user:{user_id}')
    def get_user(user_id):
        return {'user': User.query.get(user_id)}
"""

import hashlib
import json
from functools import wraps
from typing import Any, Callable, Optional, Union

from flask import request, Response, make_response


def _get_cache():
    """Get cache backend lazily to avoid circular imports."""
    from feather.cache import get_cache

    return get_cache()


def _make_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate a cache key from function arguments."""
    key_parts = [prefix]

    # Add positional args
    for arg in args:
        key_parts.append(str(arg))

    # Add keyword args (sorted for consistency)
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}={v}")

    return ":".join(key_parts)


def cached(
    ttl: int = 300,
    key: Optional[str] = None,
    key_prefix: Optional[str] = None,
) -> Callable:
    """Cache the result of a function.

    Caches the return value of a function based on its arguments.
    Useful for expensive computations or database queries.

    Args:
        ttl: Time-to-live in seconds (default: 300).
        key: Static cache key. If provided, ignores function arguments.
        key_prefix: Prefix for auto-generated keys (default: function name).

    Returns:
        Decorator function.

    Example::

        @cached(ttl=60)
        def get_user_stats(user_id):
            # Expensive database aggregation
            return calculate_stats(user_id)

        # First call - hits database
        stats = get_user_stats(123)

        # Second call - returns cached result
        stats = get_user_stats(123)

        # Different argument - hits database again
        stats = get_user_stats(456)
    """

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs) -> Any:
            cache = _get_cache()

            # Generate cache key
            if key:
                cache_key = key
            else:
                prefix = key_prefix or f"cached:{f.__module__}.{f.__name__}"
                cache_key = _make_cache_key(prefix, *args, **kwargs)

            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result

            # Call function and cache result
            result = f(*args, **kwargs)
            if result is not None:
                cache.set(cache_key, result, ttl)

            return result

        # Expose cache invalidation
        def invalidate(*args, **kwargs) -> bool:
            """Invalidate the cached result for given arguments."""
            cache = _get_cache()
            if key:
                cache_key = key
            else:
                prefix = key_prefix or f"cached:{f.__module__}.{f.__name__}"
                cache_key = _make_cache_key(prefix, *args, **kwargs)
            return cache.delete(cache_key)

        decorated_function.invalidate = invalidate
        return decorated_function

    return decorator


def cache_response(
    ttl: int = 300,
    key: Optional[str] = None,
    key_prefix: str = "response",
    vary_on: Optional[list[str]] = None,
    unless: Optional[Callable[[], bool]] = None,
) -> Callable:
    """Cache API response.

    Caches the full response including status code and headers.
    Only caches successful responses (2xx status codes).

    Args:
        ttl: Time-to-live in seconds (default: 300).
        key: Cache key template with placeholders for URL params.
            Example: 'user:{user_id}' uses the user_id URL parameter.
        key_prefix: Prefix for auto-generated keys (default: 'response').
        vary_on: List of request attributes to include in cache key.
            Options: 'query', 'user', 'headers'. Default varies on query string.
        unless: Callable that returns True to skip caching.
            Example: lambda: current_user.is_admin

    Returns:
        Decorator function.

    Example::

        @api.get('/products')
        @cache_response(ttl=300)
        def list_products():
            return {'products': [...]}

        @api.get('/users/<user_id>')
        @cache_response(ttl=60, key='user:{user_id}')
        def get_user(user_id):
            return {'user': {...}}

        # Vary by query string
        @api.get('/search')
        @cache_response(ttl=60, vary_on=['query'])
        def search():
            q = request.args.get('q')
            return {'results': [...]}

        # Skip cache for admins
        @api.get('/dashboard')
        @cache_response(ttl=300, unless=lambda: current_user.is_admin)
        def dashboard():
            return {'stats': {...}}
    """

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs) -> Any:
            # Check unless condition
            if unless and unless():
                return f(*args, **kwargs)

            # Only cache GET requests
            if request.method != "GET":
                return f(*args, **kwargs)

            cache = _get_cache()
            cache_key = _build_response_cache_key(
                key, key_prefix, f, vary_on, kwargs
            )

            # Try to get from cache
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return _restore_response(cached_data)

            # Call function
            result = f(*args, **kwargs)

            # Convert to response if needed
            if isinstance(result, Response):
                response = result
            elif isinstance(result, tuple):
                response = make_response(*result)
            else:
                response = make_response(result)

            # Only cache successful responses
            if 200 <= response.status_code < 300:
                cached_data = _serialize_response(response)
                cache.set(cache_key, cached_data, ttl)

            return response

        return decorated_function

    return decorator


def _build_response_cache_key(
    key_template: Optional[str],
    prefix: str,
    func: Callable,
    vary_on: Optional[list[str]],
    url_params: dict,
) -> str:
    """Build cache key for response caching."""
    if key_template:
        # Format template with URL parameters
        try:
            cache_key = f"{prefix}:{key_template.format(**url_params)}"
        except KeyError:
            # Fall back to path-based key if template fails
            cache_key = f"{prefix}:{request.path}"
    else:
        # Auto-generate from path
        cache_key = f"{prefix}:{func.__name__}:{request.path}"

    # Add variations
    vary_on = vary_on or ["query"]
    vary_parts = []

    if "query" in vary_on and request.query_string:
        query_hash = hashlib.md5(request.query_string).hexdigest()[:8]
        vary_parts.append(f"q:{query_hash}")

    if "user" in vary_on:
        try:
            from flask_login import current_user

            if current_user.is_authenticated:
                vary_parts.append(f"u:{current_user.id}")
            else:
                vary_parts.append("u:anon")
        except ImportError:
            pass

    if "headers" in vary_on:
        # Include Accept and Accept-Language headers
        accept = request.headers.get("Accept", "")
        lang = request.headers.get("Accept-Language", "")
        header_hash = hashlib.md5(f"{accept}:{lang}".encode()).hexdigest()[:8]
        vary_parts.append(f"h:{header_hash}")

    if vary_parts:
        cache_key = f"{cache_key}:{':'.join(vary_parts)}"

    return cache_key


def _serialize_response(response: Response) -> dict:
    """Serialize a Flask response for caching."""
    return {
        "data": response.get_data(as_text=True),
        "status": response.status_code,
        "headers": dict(response.headers),
        "content_type": response.content_type,
    }


def _restore_response(cached_data: dict) -> Response:
    """Restore a Flask response from cached data."""
    response = make_response(cached_data["data"], cached_data["status"])
    response.content_type = cached_data.get("content_type", "application/json")

    # Restore safe headers (skip hop-by-hop headers)
    skip_headers = {
        "content-encoding",
        "transfer-encoding",
        "connection",
        "keep-alive",
    }
    for header, value in cached_data.get("headers", {}).items():
        if header.lower() not in skip_headers:
            response.headers[header] = value

    # Add cache hit header
    response.headers["X-Cache"] = "HIT"

    return response


def invalidate_cache(pattern: str) -> int:
    """Invalidate cache entries matching a pattern.

    Args:
        pattern: Cache key or pattern to invalidate.
            For Redis, supports wildcards (e.g., 'user:*').
            For memory cache, does exact match only.

    Returns:
        Number of entries invalidated.

    Example::

        # Invalidate specific key
        invalidate_cache('user:123')

        # Invalidate all user caches (Redis only)
        invalidate_cache('user:*')
    """
    cache = _get_cache()

    # Check if Redis backend with pattern support
    if hasattr(cache, "_client") and "*" in pattern:
        # Redis with pattern
        prefix = cache._prefix if hasattr(cache, "_prefix") else ""
        full_pattern = f"{prefix}{pattern}"
        keys_deleted = 0
        cursor = 0
        while True:
            cursor, keys = cache._client.scan(cursor, match=full_pattern, count=100)
            if keys:
                keys_deleted += cache._client.delete(*keys)
            if cursor == 0:
                break
        return keys_deleted
    else:
        # Simple delete
        return 1 if cache.delete(pattern) else 0
