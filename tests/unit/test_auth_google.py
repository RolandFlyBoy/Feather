"""Unit tests for feather/auth/google.py.

Tests the Google OAuth integration module.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock

pytestmark = pytest.mark.unit


class TestGoogleBlueprintStructure:
    """Test Google OAuth blueprint structure and configuration."""

    def test_blueprint_exists(self):
        """google_bp is a Flask Blueprint."""
        from feather.auth.google import google_bp
        from flask import Blueprint

        assert isinstance(google_bp, Blueprint)

    def test_blueprint_name(self):
        """Blueprint is named 'google_auth'."""
        from feather.auth.google import google_bp

        assert google_bp.name == "google_auth"

    def test_blueprint_url_prefix(self):
        """Blueprint has /auth/google URL prefix."""
        from feather.auth.google import google_bp

        assert google_bp.url_prefix == "/auth/google"

    def test_oauth_instance_exists(self):
        """OAuth instance is created."""
        from feather.auth.google import oauth
        from authlib.integrations.flask_client import OAuth

        assert isinstance(oauth, OAuth)


class TestInitGoogleOAuth:
    """Test init_google_oauth function."""

    def test_init_registers_blueprint(self):
        """init_google_oauth registers the google_bp blueprint."""
        from flask import Flask
        from feather.auth.google import init_google_oauth

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        app.config["GOOGLE_CLIENT_ID"] = "test-client-id"
        app.config["GOOGLE_CLIENT_SECRET"] = "test-client-secret"

        init_google_oauth(app)

        # Check blueprint is registered
        assert "google_auth" in app.blueprints

    def test_init_registers_oauth_client(self):
        """init_google_oauth registers Google OAuth client."""
        from flask import Flask
        from feather.auth.google import init_google_oauth, oauth

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        app.config["GOOGLE_CLIENT_ID"] = "test-client-id"
        app.config["GOOGLE_CLIENT_SECRET"] = "test-client-secret"

        init_google_oauth(app)

        # Check Google client is registered
        with app.app_context():
            assert oauth.google is not None


class TestLoginRoute:
    """Test login route functionality."""

    def test_login_without_config_checks_credentials(self):
        """Login checks for Google credentials configuration."""
        from flask import Flask
        from feather.auth.google import google_bp

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        # Deliberately not setting GOOGLE_CLIENT_ID/SECRET
        app.register_blueprint(google_bp)

        # Mock render_template to avoid template lookup
        with patch("feather.auth.google.render_template") as mock_render:
            mock_render.return_value = "OAuth not configured"

            with app.test_client() as client:
                response = client.get("/auth/google/login")
                # render_template should be called with auth_required.html
                mock_render.assert_called_once()
                call_args = mock_render.call_args
                assert "errors/auth_required.html" in call_args[0]
                assert call_args[1]["show_config_hint"] is True

    def test_login_stores_next_url_in_session(self):
        """Login stores next parameter in session."""
        from flask import Flask, session
        from feather.auth.google import init_google_oauth

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        app.config["GOOGLE_CLIENT_ID"] = "test-client-id"
        app.config["GOOGLE_CLIENT_SECRET"] = "test-client-secret"

        init_google_oauth(app)

        with app.test_client() as client:
            with patch("feather.auth.google.oauth") as mock_oauth:
                mock_oauth.google.authorize_redirect.return_value = Mock(
                    status_code=302, headers={"Location": "https://accounts.google.com"}
                )
                response = client.get("/auth/google/login?next=/dashboard")
                # Session should have stored the next URL
                with client.session_transaction() as sess:
                    assert sess.get("next") == "/dashboard"

    def test_login_clears_stale_oauth_state(self):
        """Login clears stale OAuth state from session."""
        from flask import Flask, session
        from feather.auth.google import init_google_oauth

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        app.config["GOOGLE_CLIENT_ID"] = "test-client-id"
        app.config["GOOGLE_CLIENT_SECRET"] = "test-client-secret"

        init_google_oauth(app)

        with app.test_client() as client:
            # Pre-populate session with stale state
            with client.session_transaction() as sess:
                sess["_state_google_old123"] = "stale-state"
                sess["_google_authlib_nonce_"] = "stale-nonce"

            with patch("feather.auth.google.oauth") as mock_oauth:
                mock_oauth.google.authorize_redirect.return_value = Mock(
                    status_code=302, headers={"Location": "https://accounts.google.com"}
                )
                response = client.get("/auth/google/login")

                # Stale state should be cleared
                with client.session_transaction() as sess:
                    assert "_state_google_old123" not in sess
                    assert "_google_authlib_nonce_" not in sess


class TestCallbackRoute:
    """Test callback route functionality."""

    def test_callback_error_redirects_home_with_flash(self):
        """Callback error redirects to home with error flash."""
        from flask import Flask
        from feather.auth.google import init_google_oauth

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        app.config["GOOGLE_CLIENT_ID"] = "test-client-id"
        app.config["GOOGLE_CLIENT_SECRET"] = "test-client-secret"

        @app.route("/")
        def home():
            return "home"

        # Add page.home endpoint
        app.add_url_rule("/", "page.home", home)
        init_google_oauth(app)

        with app.test_client() as client:
            with patch("feather.auth.google.oauth") as mock_oauth:
                mock_oauth.google.authorize_access_token.side_effect = Exception(
                    "Token exchange failed"
                )
                response = client.get("/auth/google/callback")
                assert response.status_code == 302
                assert response.location == "/"


class TestTokenStorage:
    """Test token storage functions."""

    def test_store_token_saves_to_session(self):
        """_store_token saves token data to session."""
        from flask import Flask, session
        from feather.auth.google import _store_token, _TOKEN_SESSION_KEY

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"

        with app.test_request_context():
            token = {
                "access_token": "test-access-token",
                "refresh_token": "test-refresh-token",
                "expires_at": 1234567890,
                "token_type": "Bearer",
            }
            _store_token(token)

            stored = session.get(_TOKEN_SESSION_KEY)
            assert stored["access_token"] == "test-access-token"
            assert stored["refresh_token"] == "test-refresh-token"
            assert stored["expires_at"] == 1234567890
            assert stored["token_type"] == "Bearer"

    def test_clear_google_token_removes_from_session(self):
        """clear_google_token removes token from session."""
        from flask import Flask, session
        from feather.auth.google import (
            _store_token,
            clear_google_token,
            _TOKEN_SESSION_KEY,
        )

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"

        with app.test_request_context():
            # Store a token first
            _store_token({"access_token": "test"})
            assert _TOKEN_SESSION_KEY in session

            # Clear it
            clear_google_token()
            assert _TOKEN_SESSION_KEY not in session


class TestGetGoogleToken:
    """Test get_google_token function."""

    def test_returns_none_when_no_token(self):
        """get_google_token returns None when no token in session."""
        from flask import Flask
        from feather.auth.google import get_google_token

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"

        with app.test_request_context():
            token = get_google_token()
            assert token is None

    def test_returns_valid_token(self):
        """get_google_token returns valid non-expired token."""
        from flask import Flask
        from feather.auth.google import get_google_token, _store_token

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"

        with app.test_request_context():
            # Store a token that expires in the future
            future_time = time.time() + 3600  # 1 hour from now
            _store_token(
                {
                    "access_token": "valid-token",
                    "expires_at": future_time,
                    "token_type": "Bearer",
                }
            )

            token = get_google_token()
            assert token is not None
            assert token["access_token"] == "valid-token"

    def test_returns_none_for_expired_token_without_refresh(self):
        """get_google_token returns None for expired token without refresh token."""
        from flask import Flask
        from flask_login import LoginManager
        from feather.auth.google import get_google_token, _store_token

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"

        # Set up Flask-Login
        login_manager = LoginManager()
        login_manager.init_app(app)

        @login_manager.user_loader
        def load_user(user_id):
            return None

        with app.test_request_context():
            # Store an expired token without refresh token
            past_time = time.time() - 3600  # 1 hour ago
            _store_token(
                {
                    "access_token": "expired-token",
                    "expires_at": past_time,
                    "token_type": "Bearer",
                    # No refresh_token
                }
            )

            token = get_google_token()
            # Token is expired and no refresh token available, returns None
            assert token is None

    def test_refreshes_expired_token(self):
        """get_google_token refreshes expired token with refresh_token."""
        from flask import Flask
        from feather.auth.google import get_google_token, _store_token

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        app.config["GOOGLE_CLIENT_ID"] = "test-client-id"
        app.config["GOOGLE_CLIENT_SECRET"] = "test-client-secret"

        with app.test_request_context():
            # Store an expired token with refresh token
            past_time = time.time() - 3600  # 1 hour ago
            _store_token(
                {
                    "access_token": "expired-token",
                    "expires_at": past_time,
                    "refresh_token": "test-refresh-token",
                    "token_type": "Bearer",
                }
            )

            # Mock the refresh endpoint
            with patch("feather.auth.google._refresh_google_token") as mock_refresh:
                mock_refresh.return_value = {
                    "access_token": "new-access-token",
                    "expires_at": time.time() + 3600,
                    "refresh_token": "test-refresh-token",
                    "token_type": "Bearer",
                }

                token = get_google_token()
                assert token is not None
                assert token["access_token"] == "new-access-token"
                mock_refresh.assert_called_once_with("test-refresh-token")


class TestRefreshGoogleToken:
    """Test _refresh_google_token function."""

    def test_successful_refresh(self):
        """_refresh_google_token returns new token on success."""
        import requests
        from flask import Flask
        from feather.auth.google import _refresh_google_token

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        app.config["GOOGLE_CLIENT_ID"] = "test-client-id"
        app.config["GOOGLE_CLIENT_SECRET"] = "test-client-secret"

        with app.app_context():
            with patch.object(requests, "post") as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "access_token": "new-access-token",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                }
                mock_post.return_value = mock_response

                token = _refresh_google_token("test-refresh-token")
                assert token is not None
                assert token["access_token"] == "new-access-token"
                assert "expires_at" in token  # Should be calculated from expires_in
                assert token["refresh_token"] == "test-refresh-token"  # Preserved

    def test_failed_refresh_returns_none(self):
        """_refresh_google_token returns None on failure."""
        import requests
        from flask import Flask
        from feather.auth.google import _refresh_google_token

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        app.config["GOOGLE_CLIENT_ID"] = "test-client-id"
        app.config["GOOGLE_CLIENT_SECRET"] = "test-client-secret"

        with app.app_context():
            with patch.object(requests, "post") as mock_post:
                mock_response = Mock()
                mock_response.status_code = 400
                mock_response.text = "Invalid refresh token"
                mock_post.return_value = mock_response

                token = _refresh_google_token("invalid-refresh-token")
                assert token is None

    def test_exception_during_refresh_returns_none(self):
        """_refresh_google_token returns None on exception."""
        import requests
        from flask import Flask
        from feather.auth.google import _refresh_google_token

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        app.config["GOOGLE_CLIENT_ID"] = "test-client-id"
        app.config["GOOGLE_CLIENT_SECRET"] = "test-client-secret"

        with app.app_context():
            with patch.object(requests, "post") as mock_post:
                mock_post.side_effect = Exception("Network error")

                token = _refresh_google_token("test-refresh-token")
                assert token is None


class TestGetOrCreateUser:
    """Test _get_or_create_user function."""

    def test_returns_none_when_no_email(self):
        """_get_or_create_user returns None when no email in user_info."""
        from flask import Flask
        from feather.auth.google import _get_or_create_user

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        app.config["FEATHER_MULTI_TENANT"] = False

        with app.app_context():
            user = _get_or_create_user({})
            assert user is None

    def test_returns_none_when_email_is_none(self):
        """_get_or_create_user returns None when email is None."""
        from flask import Flask
        from feather.auth.google import _get_or_create_user

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        app.config["FEATHER_MULTI_TENANT"] = False

        with app.app_context():
            user = _get_or_create_user({"email": None})
            assert user is None


class TestPublicEmailDomainBlocking:
    """Test that public email domains are blocked in multi-tenant mode."""

    def test_public_domain_detection(self):
        """Public email domains are detected correctly."""
        from feather.auth.domains import is_public_email_domain

        # Known public domains should be detected
        assert is_public_email_domain("gmail.com") is True
        assert is_public_email_domain("outlook.com") is True
        assert is_public_email_domain("yahoo.com") is True
        assert is_public_email_domain("hotmail.com") is True

        # Work domains should not be detected as public
        assert is_public_email_domain("acme.com") is False
        assert is_public_email_domain("example.org") is False

    def test_domain_extraction(self):
        """Domain is correctly extracted from email."""
        from feather.auth.domains import extract_domain

        assert extract_domain("user@example.com") == "example.com"
        assert extract_domain("admin@sub.domain.org") == "sub.domain.org"

    def test_invalid_email_raises_error(self):
        """Invalid email raises ValueError."""
        from feather.auth.domains import extract_domain
        import pytest

        with pytest.raises(ValueError):
            extract_domain("not-an-email")

        with pytest.raises(ValueError):
            extract_domain("")


class TestTokenSessionKey:
    """Test token session key constant."""

    def test_token_session_key_exists(self):
        """_TOKEN_SESSION_KEY constant exists."""
        from feather.auth.google import _TOKEN_SESSION_KEY

        assert _TOKEN_SESSION_KEY == "google_oauth_token"
