"""Security: ``?next=`` values must never leave the site.

Control characters (tab, NUL, ...) are stripped by browsers before the URL
is resolved, so ``/\t/evil.com`` becomes ``//evil.com`` — a protocol-relative
redirect to another host. ``_safe_next`` has to reject them.
"""

import pytest

from feather.auth.google import _safe_next

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("good", [
    "/",
    "/dashboard",
    "/dashboard?tab=1",
    "/recruiter/jobs?tab=open&x=1",
    "/path/with%20encoded?q=a%26b",
    " /settings ",
])
def test_accepts_site_paths(good):
    assert _safe_next(good) == good.strip()


@pytest.mark.parametrize("bad", [
    "/\t/evil.com",          # tab: browsers strip it -> //evil.com
    "/\x09/evil.com",        # decoded form of /%09/evil.com
    "/\x00/evil.com",        # NUL
    "/\x7f/evil.com",        # DEL
    "/dash\tboard",          # control char anywhere, not only at the start
    "/dash\x0bboard",        # vertical tab inside the path
    "/dash board",           # whitespace inside the path
    "//evil.com",
    "/\\evil.com",
    "https://x",
    "http://evil.example",
    "javascript:alert(1)",
    "/\n/x",
    "/\r/x",
    "/ok\r\nSet-Cookie: x=y",
    "evil.example",
    "",
    None,
    123,
])
def test_rejects_anything_that_could_leave_the_site(bad):
    assert _safe_next(bad) is None


def test_rejects_values_urlsplit_reads_as_having_a_host():
    # Belt and braces: anything urlsplit parses with a scheme or netloc is out.
    assert _safe_next("/\\\\evil.com") is None
    assert _safe_next("////evil.com") is None
