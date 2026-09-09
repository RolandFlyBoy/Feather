"""Auth hardening: safe ?next handling, logout clears the session, cookies."""

import pytest

from feather.auth.google import _safe_next
from feather.core.config import Config, ProductionConfig


@pytest.mark.parametrize("bad", [
    "https://evil.example/x", "http://evil.example", "//evil.example/path",
    "/\\evil.example", "javascript:alert(1)", "evil.example", "", None,
    "/ok\r\nSet-Cookie: x=y",
])
def test_next_rejects_anything_but_a_site_path(bad):
    assert _safe_next(bad) is None


@pytest.mark.parametrize("good", ["/", "/dashboard", "/recruiter/jobs?tab=open&x=1", " /settings "])
def test_next_accepts_site_paths(good):
    assert _safe_next(good) == good.strip()


def test_cookie_defaults():
    assert Config.SESSION_COOKIE_HTTPONLY and Config.REMEMBER_COOKIE_HTTPONLY
    assert Config.SESSION_COOKIE_SAMESITE == "Lax" and Config.REMEMBER_COOKIE_SAMESITE == "Lax"
    assert ProductionConfig.SESSION_COOKIE_SECURE and ProductionConfig.REMEMBER_COOKIE_SECURE
