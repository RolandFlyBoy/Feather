"""Integration tests for rate limiting.

Tests the @rate_limit decorator for protecting routes from abuse.
"""

import time
import pytest
from flask_login import login_user, LoginManager, UserMixin
from feather import Feather
from feather.auth import rate_limit
from feather.auth.decorators import get_rate_limiter
from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin
from tests.conftest import make_csrf_client

pytestmark = pytest.mark.integration


# =============================================================================
# Test Models
# =============================================================================

class RateLimitUser(UUIDMixin, TimestampMixin, UserMixin, Model):
    """Test user model for rate limit tests."""
    __tablename__ = 'rate_limit_users'
    __table_args__ = {'extend_existing': True}

    email = db.Column(db.String(255), unique=True, nullable=False)
    tenant_id = db.Column(db.String(36), nullable=True)
    active = db.Column(db.Boolean, default=True)

    @property
    def is_active(self):
        return self.active


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Clear rate limits before and after each test."""
    limiter = get_rate_limiter()
    limiter._requests.clear()
    yield
    limiter._requests.clear()


@pytest.fixture
def rate_limit_app():
    """Create a test app with rate-limited routes."""
    app = Feather(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    # CSRF enabled to match production

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(RateLimitUser, user_id)

    # Test login endpoint
    @app.route('/test-login/<user_id>', methods=['POST'])
    def test_login(user_id):
        user = db.session.get(RateLimitUser, user_id)
        if user:
            login_user(user, force=True)
            return {'logged_in': True}
        return {'logged_in': False}, 401

    # Rate limited routes
    @app.route('/api/limited-by-ip')
    @rate_limit(3, 60)  # 3 requests per minute by IP
    def limited_by_ip():
        return {'message': 'success'}

    @app.route('/api/limited-by-user')
    @rate_limit(3, 60, key='user')  # 3 requests per minute by user
    def limited_by_user():
        return {'message': 'success'}

    @app.route('/api/limited-by-both')
    @rate_limit(3, 60, key='ip+user')  # 3 requests per minute by IP and user
    def limited_by_both():
        return {'message': 'success'}

    @app.route('/api/custom-message')
    @rate_limit(2, 60, message='Too many requests! Please slow down.')
    def custom_message():
        return {'message': 'success'}

    @app.route('/api/short-window')
    @rate_limit(2, 1)  # 2 requests per second (for testing reset)
    def short_window():
        return {'message': 'success'}

    # Setup: create tables and seed data
    with app.app_context():
        db.create_all()
        user1 = RateLimitUser(email='user1@example.com', tenant_id='tenant-1', active=True)
        user2 = RateLimitUser(email='user2@example.com', tenant_id='tenant-1', active=True)
        db.session.add_all([user1, user2])
        db.session.commit()
        app.test_users = {
            'user1': user1.id,
            'user2': user2.id,
        }

    # Yield OUTSIDE app_context so each test client gets proper isolation
    yield app

    # Cleanup
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


# =============================================================================
# Test Rate Limit by IP
# =============================================================================

class TestRateLimitByIP:
    """Tests for IP-based rate limiting."""

    def test_allows_requests_under_limit(self, rate_limit_app):
        """Requests under the limit succeed."""
        client = rate_limit_app.test_client()

        for i in range(3):
            response = client.get('/api/limited-by-ip')
            assert response.status_code == 200, f"Request {i+1} should succeed"

    def test_blocks_requests_over_limit(self, rate_limit_app):
        """Requests over the limit are blocked with 429."""
        client = rate_limit_app.test_client()

        # Use up the limit
        for _ in range(3):
            client.get('/api/limited-by-ip')

        # Next request should be blocked
        response = client.get('/api/limited-by-ip')
        assert response.status_code == 429
        data = response.get_json()
        assert data['error']['code'] == 'RATE_LIMIT_ERROR'

    def test_different_endpoints_have_separate_limits(self, rate_limit_app):
        """Rate limits are per-endpoint."""
        client = rate_limit_app.test_client()

        # Use up limit on one endpoint
        for _ in range(3):
            client.get('/api/limited-by-ip')

        # Different endpoint should still work
        response = client.get('/api/custom-message')
        assert response.status_code == 200


# =============================================================================
# Test Rate Limit by User
# =============================================================================

class TestRateLimitByUser:
    """Tests for user-based rate limiting."""

    def test_rate_limit_by_user(self, rate_limit_app):
        """Rate limit applies per authenticated user."""
        client = make_csrf_client(rate_limit_app)

        # Login as user1
        client.post(f'/test-login/{rate_limit_app.test_users["user1"]}')

        # Use up the limit
        for _ in range(3):
            client.get('/api/limited-by-user')

        # Should be blocked
        response = client.get('/api/limited-by-user')
        assert response.status_code == 429

    def test_different_users_have_separate_limits(self, rate_limit_app):
        """Different users have independent rate limits.

        Uses separate test clients to simulate different user sessions.
        """
        # Client for user1
        client1 = make_csrf_client(rate_limit_app)
        client1.post(f'/test-login/{rate_limit_app.test_users["user1"]}')

        # Use up user1's limit
        for _ in range(3):
            client1.get('/api/limited-by-user')

        # User1 is blocked
        response1 = client1.get('/api/limited-by-user')
        assert response1.status_code == 429

        # Client for user2 (fresh session)
        client2 = make_csrf_client(rate_limit_app)
        client2.post(f'/test-login/{rate_limit_app.test_users["user2"]}')

        # User2 has their own limit - should succeed
        response2 = client2.get('/api/limited-by-user')
        assert response2.status_code == 200

    def test_unauthenticated_falls_back_to_ip(self, rate_limit_app):
        """Unauthenticated users fall back to IP-based limiting."""
        client = rate_limit_app.test_client()

        # No login - should use IP-based limiting
        for _ in range(3):
            client.get('/api/limited-by-user')

        response = client.get('/api/limited-by-user')
        assert response.status_code == 429


# =============================================================================
# Test Rate Limit by IP+User
# =============================================================================

class TestRateLimitByIPAndUser:
    """Tests for combined IP and user rate limiting."""

    def test_rate_limit_by_ip_and_user(self, rate_limit_app):
        """Rate limit applies to combination of IP and user."""
        client = make_csrf_client(rate_limit_app)

        client.post(f'/test-login/{rate_limit_app.test_users["user1"]}')

        # Use up the limit
        for _ in range(3):
            client.get('/api/limited-by-both')

        response = client.get('/api/limited-by-both')
        assert response.status_code == 429


# =============================================================================
# Test Custom Error Message
# =============================================================================

class TestCustomErrorMessage:
    """Tests for custom rate limit error messages."""

    def test_custom_error_message(self, rate_limit_app):
        """Custom error message is returned when rate limited."""
        client = rate_limit_app.test_client()

        # Use up the limit
        for _ in range(2):
            client.get('/api/custom-message')

        response = client.get('/api/custom-message')
        assert response.status_code == 429
        data = response.get_json()
        assert 'Too many requests! Please slow down.' in data['error']['message']


# =============================================================================
# Test Rate Limit Reset
# =============================================================================

class TestRateLimitReset:
    """Tests for rate limit window reset."""

    def test_rate_limit_resets_after_window(self, rate_limit_app):
        """Rate limit resets after the time window expires."""
        client = rate_limit_app.test_client()

        # Use up the limit (2 per second window)
        for _ in range(2):
            client.get('/api/short-window')

        # Blocked immediately after
        response = client.get('/api/short-window')
        assert response.status_code == 429

        # Wait for window to expire
        time.sleep(1.1)

        # Should be allowed again
        response = client.get('/api/short-window')
        assert response.status_code == 200


# =============================================================================
# Test Rate Limiter Cleanup
# =============================================================================

class TestRateLimiterCleanup:
    """Tests for rate limiter cleanup."""

    def test_cleanup_removes_stale_entries(self, rate_limit_app):
        """Cleanup removes old rate limit entries."""
        limiter = get_rate_limiter()

        # Add some entries
        limiter._requests['old_key'] = [time.time() - 7200]  # 2 hours ago
        limiter._requests['new_key'] = [time.time()]

        # Cleanup entries older than 1 hour
        limiter.cleanup(max_age=3600)

        assert 'old_key' not in limiter._requests
        assert 'new_key' in limiter._requests
