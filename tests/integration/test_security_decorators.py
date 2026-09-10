"""Security: decorators — suspended platform admins, rate-limit keying and
store growth, and ``?next=`` survival through the login redirect."""

import logging
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask, redirect
from flask_login import LoginManager, UserMixin, login_user

from feather.exceptions import (
    AccountPendingError,
    AccountSuspendedError,
    AuthorizationError,
    AuthenticationError,
    RateLimitError,
)

pytestmark = pytest.mark.integration


class _User(UserMixin):
    def __init__(self, id="u1", active=True, approved_at="2026-01-01",
                 platform_admin=False, tenant_id="t1"):
        self.id = id
        self.active = active
        self.approved_at = approved_at
        self.is_platform_admin = platform_admin
        self.tenant_id = tenant_id

    @property
    def is_active(self):
        return self.active


def _app(user=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    app.config["TESTING"] = True
    lm = LoginManager()
    lm.init_app(app)

    @lm.user_loader
    def load(user_id):
        return user if user and user.id == user_id else None

    return app


# =============================================================================
# 2. platform_admin_required honours suspension
# =============================================================================


class TestPlatformAdminSuspension:
    def _call(self, user):
        from feather.auth import platform_admin_required

        app = _app(user)

        @platform_admin_required
        def view():
            return "ok"

        with app.test_request_context():
            if user is not None:
                login_user(user, force=True)
            return view()

    def test_active_platform_admin_passes(self):
        assert self._call(_User(platform_admin=True)) == "ok"

    def test_suspended_platform_admin_is_blocked(self):
        with pytest.raises(AccountSuspendedError):
            self._call(_User(platform_admin=True, active=False, approved_at="x"))

    def test_pending_platform_admin_is_blocked(self):
        with pytest.raises(AccountPendingError):
            self._call(_User(platform_admin=True, active=False, approved_at=None))

    def test_suspension_is_a_403(self):
        assert issubclass(AccountSuspendedError, AuthorizationError)

    def test_anonymous_still_401(self):
        with pytest.raises(AuthenticationError):
            self._call(None)

    def test_non_platform_admin_still_403(self):
        with pytest.raises(AuthorizationError):
            self._call(_User(platform_admin=False))


# =============================================================================
# 3. rate_limit keys on request.remote_addr, prunes its store
# =============================================================================


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    from feather.auth.decorators import get_rate_limiter

    get_rate_limiter()._requests.clear()
    yield
    get_rate_limiter()._requests.clear()


class TestRateLimitClientKey:
    def _app(self):
        from feather.auth import rate_limit

        app = _app()

        @app.route("/limited")
        @rate_limit(2, 60)
        def limited():
            return "ok"

        @app.errorhandler(RateLimitError)
        def too_many(e):
            return "limited", 429

        return app

    def test_x_forwarded_for_cannot_reset_the_bucket(self):
        """Without ProxyFix the header is client-controlled: it must be ignored."""
        client = self._app().test_client()
        for i in range(2):
            assert client.get("/limited", headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code == 200
        assert client.get("/limited", headers={"X-Forwarded-For": "10.0.0.99"}).status_code == 429
        assert client.get("/limited", headers={"X-Real-IP": "10.0.0.98"}).status_code == 429

    def test_remote_addr_is_the_key(self):
        client = self._app().test_client()
        for _ in range(2):
            assert client.get("/limited", environ_base={"REMOTE_ADDR": "1.1.1.1"}).status_code == 200
        assert client.get("/limited", environ_base={"REMOTE_ADDR": "1.1.1.1"}).status_code == 429
        # a different client address is a different bucket
        assert client.get("/limited", environ_base={"REMOTE_ADDR": "2.2.2.2"}).status_code == 200


class TestRateLimiterPruning:
    def test_store_is_pruned_opportunistically(self):
        from feather.auth.decorators import _RateLimiter

        limiter = _RateLimiter(cleanup_every=50)
        now = [1_000_000.0]
        with patch("feather.auth.decorators.time.time", side_effect=lambda: now[0]):
            for i in range(40):
                limiter.is_allowed(f"ep:ip:10.0.0.{i}", 5, 60)
            assert len(limiter._requests) == 40

            # A full window later, further calls trigger the sweep.
            now[0] += 61
            for i in range(40, 60):
                limiter.is_allowed(f"ep:ip:10.0.0.{i}", 5, 60)

            # Old keys are gone; only the ones touched in this window remain.
            assert len(limiter._requests) <= 20
            assert "ep:ip:10.0.0.0" not in limiter._requests
            assert "ep:ip:10.0.0.59" in limiter._requests

    def test_prune_keeps_entries_inside_the_longest_window(self):
        from feather.auth.decorators import _RateLimiter

        limiter = _RateLimiter(cleanup_every=2)
        now = [1_000_000.0]
        with patch("feather.auth.decorators.time.time", side_effect=lambda: now[0]):
            limiter.is_allowed("long", 5, 3600)   # hour window
            limiter.is_allowed("short", 5, 60)
            now[0] += 120
            limiter.is_allowed("other", 5, 60)
            limiter.is_allowed("other", 5, 60)
            assert "long" in limiter._requests
            assert "short" not in limiter._requests

    def test_size_threshold_triggers_prune(self):
        from feather.auth.decorators import _RateLimiter

        limiter = _RateLimiter(cleanup_every=10_000, max_keys=30)
        now = [1_000_000.0]
        with patch("feather.auth.decorators.time.time", side_effect=lambda: now[0]):
            for i in range(30):
                limiter.is_allowed(f"k{i}", 5, 60)
            now[0] += 61
            limiter.is_allowed("fresh", 5, 60)
            assert len(limiter._requests) < 30

    def test_default_limiter_prunes_without_configuration(self):
        from feather.auth.decorators import _RateLimiter

        limiter = _RateLimiter()
        now = [1_000_000.0]
        with patch("feather.auth.decorators.time.time", side_effect=lambda: now[0]):
            for i in range(limiter._cleanup_every):
                limiter.is_allowed(f"k{i}", 5, 60)
            now[0] += 61
            for i in range(limiter._cleanup_every):
                limiter.is_allowed(f"j{i}", 5, 60)
            assert len(limiter._requests) <= limiter._cleanup_every

    def test_docstring_says_per_process(self):
        from feather.auth.decorators import rate_limit

        doc = rate_limit.__doc__
        assert "per-process" in doc
        assert "Flask-Limiter" in doc


# =============================================================================
# 9. ?next= survives the login redirect
# =============================================================================


class TestNextSurvivesRedirect:
    def _next_from(self, location):
        parts = urlsplit(location)
        assert parts.path.endswith("/auth/google/login")
        return parse_qs(parts.query)["next"][0]

    def test_login_only_encodes_path_and_query(self):
        from feather.auth.decorators import login_only

        app = _app()

        @app.route("/only")
        @login_only
        def only():
            return "ok"

        resp = app.test_client().get("/only?tab=1&q=a%20b&r=x%26y")
        assert resp.status_code == 302
        assert "next=%2Fonly%3Ftab%3D1%26q%3Da%2520b%26r%3Dx%2526y" in resp.headers["Location"]
        assert self._next_from(resp.headers["Location"]) == "/only?tab=1&q=a%20b&r=x%26y"

    def test_login_only_without_query_has_no_dangling_question_mark(self):
        from feather.auth.decorators import login_only

        app = _app()

        @app.route("/only")
        @login_only
        def only():
            return "ok"

        resp = app.test_client().get("/only")
        assert self._next_from(resp.headers["Location"]) == "/only"

    def _auth_app(self):
        from feather.auth.setup import init_auth
        from feather.auth.google import init_google_oauth

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        app.config["TESTING"] = True
        app.config["GOOGLE_CLIENT_ID"] = "id"
        app.config["GOOGLE_CLIENT_SECRET"] = "secret"

        class NoUsers:
            @staticmethod
            def get_by_id(user_id):
                return None

        init_auth(app, user_model=NoUsers)
        init_google_oauth(app)

        from flask_login import login_required

        @app.route("/secret")
        @login_required
        def secret():
            return "ok"

        return app

    def test_unauthorized_handler_keeps_a_site_relative_next(self):
        app = self._auth_app()
        resp = app.test_client().get("/secret?tab=1&q=a%20b")
        assert resp.status_code == 302
        next_value = self._next_from(resp.headers["Location"])
        assert next_value == "/secret?tab=1&q=a%20b"
        assert not next_value.startswith("http")

    def test_round_trip_into_the_login_session(self):
        """The value the handler emits is the one the login route stores."""
        app = self._auth_app()
        client = app.test_client()
        resp = client.get("/secret?tab=1&q=a%20b")
        login_location = resp.headers["Location"]
        with patch("feather.auth.google.oauth") as oauth:
            oauth.google.authorize_redirect.return_value = redirect("https://accounts.google.com")
            client.get(login_location)
        with client.session_transaction() as sess:
            assert sess["next"] == "/secret?tab=1&q=a%20b"

    def test_unauthorized_handler_respects_script_root(self):
        app = self._auth_app()
        resp = app.test_client().get(
            "/secret?x=1",
            environ_overrides={"SCRIPT_NAME": "/prefix", "PATH_INFO": "/secret"},
        )
        assert self._next_from(resp.headers["Location"]) == "/prefix/secret?x=1"
