"""Integration tests for cache backends and decorators.

Tests the memory cache backend and caching decorators.
"""

import time
import pytest

from feather.cache.memory import MemoryCache
import feather.cache


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def reset_cache_singleton():
    """Reset cache singleton before each test."""
    feather.cache._cache_instance = None
    yield
    feather.cache._cache_instance = None


# =============================================================================
# Test MemoryCache Basic Operations
# =============================================================================

class TestMemoryCacheSetGet:
    """Tests for MemoryCache set and get operations."""

    def test_set_and_get_value(self):
        """Can set and retrieve a value."""
        cache = MemoryCache()
        cache.set('key', 'value')

        assert cache.get('key') == 'value'

    def test_get_missing_returns_none(self):
        """Get returns None for missing key."""
        cache = MemoryCache()

        assert cache.get('nonexistent') is None

    def test_set_overwrites_existing(self):
        """Set overwrites existing value."""
        cache = MemoryCache()
        cache.set('key', 'original')
        cache.set('key', 'updated')

        assert cache.get('key') == 'updated'

    def test_set_complex_value(self):
        """Can cache complex values."""
        cache = MemoryCache()
        data = {'users': [{'id': 1, 'name': 'John'}], 'count': 1}
        cache.set('key', data)

        assert cache.get('key') == data

    def test_set_with_custom_ttl(self):
        """Can set with custom TTL."""
        cache = MemoryCache(default_ttl=300)
        cache.set('key', 'value', ttl=60)

        assert cache.get('key') == 'value'

    def test_set_with_zero_ttl_no_expiration(self):
        """TTL of 0 means no expiration."""
        cache = MemoryCache(default_ttl=1)
        cache.set('key', 'value', ttl=0)

        # Even after the default TTL, should still exist
        time.sleep(0.1)
        assert cache.get('key') == 'value'


class TestMemoryCacheTTL:
    """Tests for TTL expiration."""

    def test_value_expires_after_ttl(self):
        """Value expires after TTL."""
        cache = MemoryCache()
        cache.set('key', 'value', ttl=0.1)  # 100ms TTL

        time.sleep(0.15)
        assert cache.get('key') is None

    def test_expired_value_removed_on_get(self):
        """Expired values are removed when accessed."""
        cache = MemoryCache()
        cache.set('key', 'value', ttl=0.1)

        time.sleep(0.15)
        cache.get('key')

        # Key should be removed from internal storage
        assert 'key' not in cache._cache


class TestMemoryCacheDelete:
    """Tests for MemoryCache delete operations."""

    def test_delete_removes_value(self):
        """Delete removes a value."""
        cache = MemoryCache()
        cache.set('key', 'value')

        result = cache.delete('key')

        assert result is True
        assert cache.get('key') is None

    def test_delete_missing_returns_false(self):
        """Delete returns False for missing key."""
        cache = MemoryCache()

        result = cache.delete('nonexistent')

        assert result is False


class TestMemoryCacheExists:
    """Tests for MemoryCache exists operations."""

    def test_exists_returns_true_for_existing(self):
        """Exists returns True for existing key."""
        cache = MemoryCache()
        cache.set('key', 'value')

        assert cache.exists('key') is True

    def test_exists_returns_false_for_missing(self):
        """Exists returns False for missing key."""
        cache = MemoryCache()

        assert cache.exists('nonexistent') is False

    def test_exists_returns_false_for_expired(self):
        """Exists returns False for expired key."""
        cache = MemoryCache()
        cache.set('key', 'value', ttl=0.1)

        time.sleep(0.15)
        assert cache.exists('key') is False


class TestMemoryCacheClear:
    """Tests for MemoryCache clear operations."""

    def test_clear_removes_all_values(self):
        """Clear removes all values."""
        cache = MemoryCache()
        cache.set('key1', 'value1')
        cache.set('key2', 'value2')

        result = cache.clear()

        assert result is True
        assert cache.get('key1') is None
        assert cache.get('key2') is None


class TestMemoryCacheIncrement:
    """Tests for MemoryCache increment operations."""

    def test_increment_numeric_value(self):
        """Increment increases numeric value."""
        cache = MemoryCache()
        cache.set('counter', 5)

        result = cache.increment('counter')

        assert result == 6
        assert cache.get('counter') == 6

    def test_increment_with_delta(self):
        """Increment with custom delta."""
        cache = MemoryCache()
        cache.set('counter', 5)

        result = cache.increment('counter', delta=10)

        assert result == 15

    def test_increment_negative_delta(self):
        """Increment with negative delta (decrement)."""
        cache = MemoryCache()
        cache.set('counter', 10)

        result = cache.increment('counter', delta=-3)

        assert result == 7

    def test_increment_missing_returns_none(self):
        """Increment returns None for missing key."""
        cache = MemoryCache()

        result = cache.increment('nonexistent')

        assert result is None

    def test_increment_non_numeric_returns_none(self):
        """Increment returns None for non-numeric value."""
        cache = MemoryCache()
        cache.set('key', 'not a number')

        result = cache.increment('key')

        assert result is None


class TestMemoryCacheSize:
    """Tests for MemoryCache size operations."""

    def test_size_returns_count(self):
        """Size returns number of entries."""
        cache = MemoryCache()
        cache.set('key1', 'value1')
        cache.set('key2', 'value2')

        assert cache.size() == 2

    def test_size_empty_cache(self):
        """Size returns 0 for empty cache."""
        cache = MemoryCache()

        assert cache.size() == 0


class TestMemoryCacheMaxSize:
    """Tests for MemoryCache max size eviction."""

    def test_evicts_oldest_when_full(self):
        """Evicts oldest entries when max size reached."""
        cache = MemoryCache(max_size=3)
        cache.set('key1', 'value1')
        cache.set('key2', 'value2')
        cache.set('key3', 'value3')

        # Adding 4th should evict key1
        cache.set('key4', 'value4')

        assert cache.get('key1') is None
        assert cache.get('key4') == 'value4'
        assert cache.size() == 3


class TestMemoryCacheCleanup:
    """Tests for MemoryCache cleanup operations."""

    def test_cleanup_removes_expired(self):
        """Cleanup removes expired entries."""
        cache = MemoryCache()
        cache.set('expired', 'value', ttl=0.1)
        cache.set('valid', 'value', ttl=60)

        time.sleep(0.15)
        removed = cache.cleanup()

        assert removed == 1
        assert cache.exists('expired') is False
        assert cache.exists('valid') is True


# =============================================================================
# Test Cache Decorators
# =============================================================================

class TestCachedDecorator:
    """Tests for @cached decorator."""

    def test_cached_returns_cached_value(self):
        """@cached returns cached value on subsequent calls."""
        from feather.cache import cached
        from tests.conftest import feather_app

        call_count = 0

        @cached(ttl=60)
        def expensive_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        with feather_app(CACHE_BACKEND='memory') as app:
            with app.app_context():
                result1 = expensive_func(5)
                result2 = expensive_func(5)

                assert result1 == 10
                assert result2 == 10
                assert call_count == 1  # Only called once

    def test_cached_different_args_different_cache(self):
        """@cached caches separately for different arguments."""
        from feather.cache import cached
        from tests.conftest import feather_app

        call_count = 0

        @cached(ttl=60, key_prefix='test_diff_args')
        def expensive_func_diff(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        with feather_app(CACHE_BACKEND='memory') as app:
            with app.app_context():
                result1 = expensive_func_diff(5)
                result2 = expensive_func_diff(10)

                assert result1 == 10
                assert result2 == 20
                assert call_count == 2  # Called for each unique arg

    def test_cached_invalidate(self):
        """@cached.invalidate clears cached value."""
        from feather.cache import cached
        from tests.conftest import feather_app

        call_count = 0

        @cached(ttl=60, key_prefix='test_invalidate')
        def expensive_func_inv(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        with feather_app(CACHE_BACKEND='memory') as app:
            with app.app_context():
                expensive_func_inv(5)
                expensive_func_inv.invalidate(5)
                expensive_func_inv(5)

                assert call_count == 2  # Called twice due to invalidation


class TestCacheResponseDecorator:
    """Tests for @cache_response decorator."""

    def test_cache_response_caches_get_request(self):
        """@cache_response caches GET request responses."""
        from feather.cache import cache_response
        from tests.conftest import feather_app

        call_count = 0

        with feather_app(CACHE_BACKEND='memory') as app:
            @app.route('/test')
            @cache_response(ttl=60)
            def test_route():
                nonlocal call_count
                call_count += 1
                return {'result': 'data'}

            with app.app_context():
                client = app.test_client()
                response1 = client.get('/test')
                response2 = client.get('/test')

                assert response1.status_code == 200
                assert response2.status_code == 200
                assert call_count == 1

    def test_cache_response_adds_hit_header(self):
        """@cache_response adds X-Cache: HIT header on cache hit."""
        from feather.cache import cache_response
        from tests.conftest import feather_app

        with feather_app(CACHE_BACKEND='memory') as app:
            @app.route('/test')
            @cache_response(ttl=60)
            def test_route():
                return {'result': 'data'}

            with app.app_context():
                client = app.test_client()
                client.get('/test')  # First request - populates cache
                response = client.get('/test')  # Second request - from cache

                assert response.headers.get('X-Cache') == 'HIT'

    def test_cache_response_skips_post_requests(self):
        """@cache_response doesn't cache POST requests."""
        from feather.cache import cache_response
        from tests.conftest import feather_app, make_csrf_client

        call_count = 0

        with feather_app(CACHE_BACKEND='memory') as app:
            @app.route('/test-post', methods=['POST'])
            @cache_response(ttl=60)
            def test_route_post():
                nonlocal call_count
                call_count += 1
                return {'result': 'data'}

            with app.app_context():
                client = make_csrf_client(app)
                client.post('/test-post')
                client.post('/test-post')

                assert call_count == 2  # Both calls executed


# =============================================================================
# Test get_cache Factory
# =============================================================================

class TestGetCacheFactory:
    """Tests for the get_cache factory function."""

    def test_get_cache_returns_memory_by_default(self):
        """get_cache returns MemoryCache when CACHE_BACKEND is 'memory'."""
        from tests.conftest import feather_app

        with feather_app(CACHE_BACKEND='memory') as app:
            with app.app_context():
                from feather.cache import get_cache
                cache = get_cache()

                assert isinstance(cache, MemoryCache)

    def test_get_cache_uses_default_ttl(self):
        """get_cache uses CACHE_DEFAULT_TTL config."""
        from tests.conftest import feather_app

        with feather_app(CACHE_BACKEND='memory', CACHE_DEFAULT_TTL=600) as app:
            with app.app_context():
                from feather.cache import get_cache
                cache = get_cache()

                assert cache._default_ttl == 600
