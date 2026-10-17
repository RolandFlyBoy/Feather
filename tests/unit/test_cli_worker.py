"""Unit tests for `feather worker`'s start-up banner.

The banner is the first thing a hosted worker prints, so it lands in the
platform's log: it must never carry the Redis password.
"""

import pytest

from feather.cli.worker import _without_password

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("url, shown", [
    ("redis://:s3cret@kvs.example.svc:6379/0", "redis://:***@kvs.example.svc:6379/0"),
    ("rediss://default:s3cret@cache.example.com:6380/1", "rediss://default:***@cache.example.com:6380/1"),
    ("redis://:p%40ss@[::1]:6379/0", "redis://:***@[::1]:6379/0"),
    ("redis://localhost:6379/0", "redis://localhost:6379/0"),
    ("redis://user@localhost/0", "redis://user@localhost/0"),
])
def test_the_banner_hides_the_password(url, shown):
    assert _without_password(url) == shown
