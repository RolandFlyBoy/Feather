"""Security: Google OAuth token handling and logging."""

import logging
import time
from unittest.mock import Mock, patch

import pytest
from flask import Flask, redirect, session
from flask_login import LoginManager, UserMixin

pytestmark = pytest.mark.unit


def _app(**config):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    app.config["GOOGLE_CLIENT_ID"] = "test-client-id"
    app.config["GOOGLE_CLIENT_SECRET"] = "test-client-secret"
    app.config.update(config)
    return app


class _User(UserMixin):
    def __init__(self, refresh_token=None):
        self.id = "u1"
        self.google_refresh_token = refresh_token


def _login_manager(app, user):
    lm = LoginManager()
    lm.init_app(app)

    @lm.user_loader
    def load_user(user_id):
        return user if user_id == user.id else None

    return lm


# =============================================================================
# 5. Refresh token must not live in the (signed, not encrypted) session
# =============================================================================


class TestRefreshTokenNotInSession:
    def test_store_token_omits_refresh_token(self):
        from feather.auth.google import _store_token, _TOKEN_SESSION_KEY

        with _app().test_request_context():
            _store_token({
                "access_token": "at",
                "refresh_token": "rt-secret",
                "expires_at": 123,
                "token_type": "Bearer",
            })
            stored = session[_TOKEN_SESSION_KEY]
            assert "refresh_token" not in stored
            assert "rt-secret" not in repr(stored)
            assert stored["access_token"] == "at"
            assert stored["expires_at"] == 123
            assert stored["token_type"] == "Bearer"

    def test_refresh_reads_token_from_user_model(self):
        from feather.auth.google import get_google_token, _store_token, _TOKEN_SESSION_KEY

        app = _app()
        user = _User(refresh_token="rt-from-db")
        _login_manager(app, user)

        with app.test_request_context():
            session["_user_id"] = user.id
            _store_token({"access_token": "old", "expires_at": time.time() - 10})

            with patch("feather.auth.google._refresh_google_token") as refresh:
                refresh.return_value = {
                    "access_token": "new",
                    "expires_at": time.time() + 3600,
                    "refresh_token": "rt-from-db",
                }
                token = get_google_token()

            refresh.assert_called_once_with("rt-from-db")
            assert token["access_token"] == "new"
            # The refreshed token is stored without the refresh token, too.
            assert "refresh_token" not in session[_TOKEN_SESSION_KEY]

    def test_no_refresh_token_anywhere_skips_refresh_gracefully(self):
        from feather.auth.google import get_google_token, _store_token

        app = _app()
        user = _User(refresh_token=None)
        _login_manager(app, user)

        with app.test_request_context():
            session["_user_id"] = user.id
            _store_token({"access_token": "old", "expires_at": time.time() - 10})
            with patch("feather.auth.google._refresh_google_token") as refresh:
                assert get_google_token() is None
            refresh.assert_not_called()

    def test_user_model_without_column_skips_refresh_gracefully(self):
        from feather.auth.google import get_google_token, _store_token

        class Bare(UserMixin):
            id = "u1"

        app = _app()
        _login_manager(app, Bare())

        with app.test_request_context():
            session["_user_id"] = "u1"
            _store_token({"access_token": "old", "expires_at": time.time() - 10})
            assert get_google_token() is None

    def test_legacy_session_refresh_token_is_used_once_then_dropped(self):
        """Sessions issued by 0.9.5 still carry the key: honour it, then pop it."""
        from feather.auth.google import get_google_token, _TOKEN_SESSION_KEY

        app = _app()
        user = _User(refresh_token=None)
        _login_manager(app, user)

        with app.test_request_context():
            session["_user_id"] = user.id
            session[_TOKEN_SESSION_KEY] = {
                "access_token": "old",
                "refresh_token": "rt-legacy",
                "expires_at": time.time() - 10,
                "token_type": "Bearer",
            }
            with patch("feather.auth.google._refresh_google_token") as refresh:
                refresh.return_value = {
                    "access_token": "new",
                    "expires_at": time.time() + 3600,
                    "refresh_token": "rt-legacy",
                }
                token = get_google_token()

            refresh.assert_called_once_with("rt-legacy")
            assert token["access_token"] == "new"
            assert "refresh_token" not in session[_TOKEN_SESSION_KEY]

    def test_legacy_key_is_popped_even_when_token_is_still_valid(self):
        from feather.auth.google import get_google_token, _TOKEN_SESSION_KEY

        with _app().test_request_context():
            session[_TOKEN_SESSION_KEY] = {
                "access_token": "ok",
                "refresh_token": "rt-legacy",
                "expires_at": time.time() + 3600,
                "token_type": "Bearer",
            }
            token = get_google_token()
            assert token["access_token"] == "ok"
            assert "refresh_token" not in session[_TOKEN_SESSION_KEY]
            assert "refresh_token" not in token


# =============================================================================
# 4. Outbound HTTP calls carry a timeout; logs never carry a full email
# =============================================================================


class TestOutboundTimeouts:
    def test_refresh_call_has_timeout(self):
        from feather.auth.google import _refresh_google_token

        with _app().test_request_context():
            with patch("requests.post") as post:
                post.return_value = Mock(status_code=200, json=lambda: {"access_token": "x", "expires_in": 10})
                _refresh_google_token("rt")
            assert post.call_args.kwargs.get("timeout") == 10


class TestEmailMasking:
    def test_no_log_line_contains_the_full_address(self, caplog):
        """Every log line about a signup must go through mask_email."""
        import feather.auth.google as google

        email = "someone.private@example.com"
        user_info = {"email": email, "name": "S", "sub": "1", "email_verified": True}

        class FakeQuery:
            def __init__(self, result=None):
                self._result = result

            def filter_by(self, **kw):
                return self

            def first(self):
                return self._result

        class User:
            query = FakeQuery(None)
            tenant_id = None

            def __init__(self, **kw):
                self.__dict__.update(kw)

        db = Mock()
        fake_models = Mock(User=User)
        app = _app(FEATHER_MULTI_TENANT=False, AUTO_APPROVE_USERS=True)

        with app.test_request_context(), caplog.at_level(logging.INFO):
            with patch.dict("sys.modules", {"models": fake_models}), \
                 patch("feather.db.db", db):
                # admin login path
                session["next"] = "/admin/users"
                assert google._get_or_create_user(user_info, {}) is None
                # blocked by pre-register callback
                session.pop("next", None)
                with patch.object(google, "_call_pre_register_callback", return_value="no"):
                    assert google._get_or_create_user(user_info, {}) is None
                # created, auto-approved
                assert google._get_or_create_user(user_info, {}) is not None

        assert caplog.records, "expected log lines from the signup paths"
        for record in caplog.records:
            assert email not in record.getMessage(), record.getMessage()
            assert "s***@example.com" in record.getMessage()

    def test_multi_tenant_log_lines_are_masked(self, caplog):
        import feather.auth.google as google

        email = "someone.private@gmail.com"
        user_info = {"email": email, "name": "S", "sub": "1"}
        fake_models = Mock(User=Mock())
        app = _app(FEATHER_MULTI_TENANT=True)

        with app.test_request_context(), caplog.at_level(logging.INFO):
            with patch.dict("sys.modules", {"models": fake_models, "models.tenant": Mock(Tenant=Mock())}), \
                 patch("feather.db.db", Mock()):
                assert google._get_or_create_user(user_info, {}) is None

        assert caplog.records
        for record in caplog.records:
            assert email not in record.getMessage(), record.getMessage()


# =============================================================================
# 6. OAUTH_CALLBACK_URL unset in production: warn once
# =============================================================================


class TestCallbackUrlWarning:
    def _client(self, app):
        from feather.auth.google import init_google_oauth

        init_google_oauth(app)
        return app.test_client()

    def test_warns_once_when_unset_and_not_debug(self, caplog, monkeypatch):
        monkeypatch.delenv("OAUTH_CALLBACK_URL", raising=False)
        app = _app(DEBUG=False)
        client = self._client(app)

        with caplog.at_level(logging.WARNING), patch("feather.auth.google.oauth") as oauth:
            oauth.google.authorize_redirect.return_value = redirect("https://accounts.google.com")
            client.get("/auth/google/login")
            client.get("/auth/google/login")

        warnings = [r for r in caplog.records if "OAUTH_CALLBACK_URL" in r.getMessage()]
        assert len(warnings) == 1
        assert "TRUSTED_HOSTS" in warnings[0].getMessage()
        assert warnings[0].levelno == logging.WARNING

    def test_no_warning_in_debug(self, caplog, monkeypatch):
        monkeypatch.delenv("OAUTH_CALLBACK_URL", raising=False)
        app = _app(DEBUG=True)
        client = self._client(app)

        with caplog.at_level(logging.WARNING), patch("feather.auth.google.oauth") as oauth:
            oauth.google.authorize_redirect.return_value = redirect("https://accounts.google.com")
            client.get("/auth/google/login")

        assert not [r for r in caplog.records if "OAUTH_CALLBACK_URL" in r.getMessage()]

    def test_no_warning_when_set(self, caplog):
        app = _app(DEBUG=False, OAUTH_CALLBACK_URL="https://app.example/auth/google/callback")
        client = self._client(app)

        with caplog.at_level(logging.WARNING), patch("feather.auth.google.oauth") as oauth:
            oauth.google.authorize_redirect.return_value = redirect("https://accounts.google.com")
            client.get("/auth/google/login")

        assert not [r for r in caplog.records if "OAUTH_CALLBACK_URL" in r.getMessage()]
