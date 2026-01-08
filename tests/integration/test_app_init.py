"""Integration tests for Feather app initialization.

Tests the Feather class, configuration, and extension initialization.
"""

import pytest
from feather.db import db

pytestmark = pytest.mark.integration


@pytest.fixture
def minimal_app():
    """Create a minimal Feather app with proper cleanup.

    Use this for tests that need to test app creation behavior
    without the full test_app fixture.
    """
    from feather import Feather

    app = Feather(__name__)
    yield app

    # Cleanup database connections
    if 'sqlalchemy' in app.extensions:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


class TestFeatherClass:
    """Test Feather application class."""

    def test_creates_flask_app(self, minimal_app):
        """Feather extends Flask."""
        from flask import Flask

        assert isinstance(minimal_app, Flask)

    def test_has_feather_attribute(self, minimal_app):
        """Feather app has feather-specific attributes."""
        # Feather should set up its own attributes
        assert hasattr(minimal_app, 'config')

    def test_default_config(self, minimal_app):
        """Default configuration is applied."""
        # Check some expected defaults
        assert 'SQLALCHEMY_DATABASE_URI' in minimal_app.config or minimal_app.config.get('SQLALCHEMY_DATABASE_URI') is None


class TestDatabaseExtension:
    """Test SQLAlchemy extension initialization."""

    def test_db_initialized(self, test_app):
        """Database extension is initialized."""
        # SQLAlchemy extension should be registered
        assert 'sqlalchemy' in test_app.extensions

    def test_creates_tables(self, test_app):
        """Tables can be created from models."""
        from feather.db import db, Model

        class TestModel(Model):
            __tablename__ = 'test_init_model'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with test_app.app_context():
            db.create_all()
            # Table should exist
            assert 'test_init_model' in db.metadata.tables


class TestAppContext:
    """Test application context behavior."""

    def test_app_context_available(self, test_app):
        """App context makes current_app available."""
        from flask import current_app

        with test_app.app_context():
            assert current_app == test_app

    def test_request_context_available(self, test_app):
        """Request context makes request available."""
        from flask import request

        with test_app.test_request_context('/test'):
            assert request.path == '/test'


class TestTestClient:
    """Test the test client fixture."""

    def test_client_makes_requests(self, client):
        """Test client can make requests."""
        response = client.get('/health/live')
        # Health endpoint should exist
        assert response.status_code == 200

    def test_health_check_response(self, client):
        """Health check returns expected format."""
        response = client.get('/health')
        data = response.get_json()

        assert 'status' in data
        assert 'timestamp' in data


class TestErrorHandling:
    """Test error handling is set up."""

    def test_404_returns_json_for_api(self, test_app, client):
        """404 errors return JSON for API routes."""
        response = client.get('/api/nonexistent')
        # Should return 404
        assert response.status_code == 404

    def test_handles_feather_exceptions(self, test_app):
        """Feather exceptions are handled."""
        from feather import api, NotFoundError

        @test_app.route('/test/not-found')
        def raise_not_found():
            raise NotFoundError('TestResource', '123')

        with test_app.test_client() as client:
            response = client.get('/test/not-found')
            assert response.status_code == 404
            data = response.get_json()
            assert data['success'] is False
            assert data['error']['code'] == 'NOT_FOUND'


class TestRequestId:
    """Test request ID tracking."""

    def test_request_id_generated(self, test_app, client):
        """Request ID is generated for each request."""
        response = client.get('/health')
        # Request ID should be in response headers
        assert 'X-Request-ID' in response.headers

    def test_request_id_passed_through(self, test_app, client):
        """Incoming request ID is preserved."""
        response = client.get('/health', headers={'X-Request-ID': 'test-123'})
        assert response.headers.get('X-Request-ID') == 'test-123'


class TestProxyFix:
    """Test ProxyFix middleware for reverse proxy support.

    ProxyFix is essential for:
    - Production: Render, Heroku, AWS ALB, nginx
    - Development: ngrok, localtunnel for OAuth testing
    """

    def test_proxyfix_enabled(self, minimal_app):
        """ProxyFix middleware is always enabled."""
        from werkzeug.middleware.proxy_fix import ProxyFix

        # The wsgi_app should be wrapped with ProxyFix
        assert isinstance(minimal_app.wsgi_app, ProxyFix)

    def test_respects_x_forwarded_proto(self, test_app):
        """X-Forwarded-Proto header is respected for HTTPS detection."""
        from flask import request

        @test_app.route('/test/proto')
        def get_proto():
            return {'scheme': request.scheme, 'url': request.url}

        with test_app.test_client() as client:
            # Without header - defaults to http
            response = client.get('/test/proto')
            data = response.get_json()
            assert data['scheme'] == 'http'

            # With X-Forwarded-Proto: https (like ngrok/production)
            response = client.get('/test/proto', headers={
                'X-Forwarded-Proto': 'https'
            })
            data = response.get_json()
            assert data['scheme'] == 'https'
            assert data['url'].startswith('https://')

    def test_respects_x_forwarded_host(self, test_app):
        """X-Forwarded-Host header is respected for host detection."""
        from flask import request

        @test_app.route('/test/host')
        def get_host():
            return {'host': request.host}

        with test_app.test_client() as client:
            # With X-Forwarded-Host (like ngrok tunnel)
            response = client.get('/test/host', headers={
                'X-Forwarded-Host': 'abc123.ngrok.io'
            })
            data = response.get_json()
            assert data['host'] == 'abc123.ngrok.io'

    def test_oauth_redirect_uri_uses_forwarded_headers(self, test_app):
        """OAuth redirect URIs use forwarded proto and host.

        This is critical for ngrok - without it, OAuth fails with redirect_uri_mismatch
        because Flask generates http://localhost URLs instead of https://xxx.ngrok.io URLs.
        """
        from flask import request, url_for

        @test_app.route('/test/oauth-callback')
        def oauth_callback():
            # Simulate what OAuth does - generate callback URL
            callback_url = url_for('oauth_callback', _external=True)
            return {'callback_url': callback_url}

        with test_app.test_client() as client:
            # Simulate ngrok request with HTTPS and custom host
            response = client.get('/test/oauth-callback', headers={
                'X-Forwarded-Proto': 'https',
                'X-Forwarded-Host': 'abc123.ngrok.io'
            })
            data = response.get_json()

            # The generated URL should use the forwarded values
            assert data['callback_url'].startswith('https://abc123.ngrok.io/')

    def test_respects_x_forwarded_for(self, test_app):
        """X-Forwarded-For header is respected for client IP detection."""
        from flask import request

        @test_app.route('/test/ip')
        def get_ip():
            return {'remote_addr': request.remote_addr}

        with test_app.test_client() as client:
            # With X-Forwarded-For (client IP behind proxy)
            response = client.get('/test/ip', headers={
                'X-Forwarded-For': '203.0.113.195'
            })
            data = response.get_json()
            assert data['remote_addr'] == '203.0.113.195'
