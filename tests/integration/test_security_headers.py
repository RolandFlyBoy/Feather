"""Integration tests for security headers middleware.

Tests that HTTP security headers are added in production mode and
absent in debug mode.
"""

import pytest
from feather import Feather
from feather.core.security import DEFAULT_CSP_DIRECTIVES


pytestmark = pytest.mark.integration


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def prod_app():
    """Create a test app with DEBUG=False (production mode)."""
    from feather.db import db

    app = Feather(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True
    app.config['DEBUG'] = False
    app.config['SECRET_KEY'] = 'test-secret-key-not-default'

    with app.app_context():
        db.create_all()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def debug_app():
    """Create a test app with DEBUG=True (development mode)."""
    from feather.db import db

    app = Feather(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True
    app.config['DEBUG'] = True
    app.config['SECRET_KEY'] = 'test-secret'

    with app.app_context():
        db.create_all()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


# =============================================================================
# Production Mode — Headers Present
# =============================================================================

class TestSecurityHeadersProduction:
    """Security headers are added when DEBUG=False."""

    def test_hsts_header_present(self, prod_app):
        """Strict-Transport-Security header is set."""
        client = prod_app.test_client()
        response = client.get('/health')

        assert 'Strict-Transport-Security' in response.headers
        assert 'max-age=' in response.headers['Strict-Transport-Security']
        assert 'includeSubDomains' in response.headers['Strict-Transport-Security']

    def test_csp_header_present(self, prod_app):
        """Content-Security-Policy header is set."""
        client = prod_app.test_client()
        response = client.get('/health')

        assert 'Content-Security-Policy' in response.headers
        csp = response.headers['Content-Security-Policy']
        assert "default-src 'self'" in csp
        assert "script-src" in csp
        assert "frame-ancestors 'none'" in csp

    def test_x_content_type_options(self, prod_app):
        """X-Content-Type-Options header is set to nosniff."""
        client = prod_app.test_client()
        response = client.get('/health')

        assert response.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_x_frame_options(self, prod_app):
        """X-Frame-Options header is set to DENY."""
        client = prod_app.test_client()
        response = client.get('/health')

        assert response.headers.get('X-Frame-Options') == 'DENY'

    def test_referrer_policy(self, prod_app):
        """Referrer-Policy header is set."""
        client = prod_app.test_client()
        response = client.get('/health')

        assert response.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'

    def test_permissions_policy(self, prod_app):
        """Permissions-Policy header restricts browser features."""
        client = prod_app.test_client()
        response = client.get('/health')

        policy = response.headers.get('Permissions-Policy')
        assert policy is not None
        assert 'camera=()' in policy
        assert 'microphone=()' in policy


# =============================================================================
# Debug Mode — Headers Absent
# =============================================================================

class TestSecurityHeadersDebug:
    """Security headers are NOT added when DEBUG=True."""

    def test_no_hsts_in_debug(self, debug_app):
        """HSTS header is not set in debug mode."""
        client = debug_app.test_client()
        response = client.get('/health')

        assert 'Strict-Transport-Security' not in response.headers

    def test_no_csp_in_debug(self, debug_app):
        """CSP header is not set in debug mode."""
        client = debug_app.test_client()
        response = client.get('/health')

        assert 'Content-Security-Policy' not in response.headers

    def test_no_x_frame_options_in_debug(self, debug_app):
        """X-Frame-Options header is not set in debug mode."""
        client = debug_app.test_client()
        response = client.get('/health')

        assert 'X-Frame-Options' not in response.headers


# =============================================================================
# Configuration
# =============================================================================

class TestSecurityHeadersConfig:
    """Tests for security headers configuration options."""

    def test_custom_csp_directives(self):
        """Custom CSP directives merge with defaults."""
        from feather.db import db

        app = Feather(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['TESTING'] = True
        app.config['DEBUG'] = False
        app.config['SECRET_KEY'] = 'test-secret-key-not-default'
        app.config['FEATHER_CSP_DIRECTIVES'] = {
            'script-src': "'self' https://js.stripe.com",
            'frame-src': "'self' https://js.stripe.com",
        }

        with app.app_context():
            db.create_all()

        client = app.test_client()
        response = client.get('/health')

        csp = response.headers['Content-Security-Policy']
        assert "script-src 'self' https://js.stripe.com" in csp
        assert "frame-src 'self' https://js.stripe.com" in csp
        # Default directives still present
        assert "default-src 'self'" in csp

        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_disable_security_headers(self):
        """FEATHER_SECURITY_HEADERS=False disables all headers."""
        from feather.db import db

        app = Feather(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['TESTING'] = True
        app.config['DEBUG'] = False
        app.config['SECRET_KEY'] = 'test-secret-key-not-default'
        app.config['FEATHER_SECURITY_HEADERS'] = False

        with app.app_context():
            db.create_all()

        client = app.test_client()
        response = client.get('/health')

        assert 'Strict-Transport-Security' not in response.headers
        assert 'Content-Security-Policy' not in response.headers

        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_custom_hsts_max_age(self):
        """FEATHER_HSTS_MAX_AGE customizes HSTS duration."""
        from feather.db import db

        app = Feather(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['TESTING'] = True
        app.config['DEBUG'] = False
        app.config['SECRET_KEY'] = 'test-secret-key-not-default'
        app.config['FEATHER_HSTS_MAX_AGE'] = 86400

        with app.app_context():
            db.create_all()

        client = app.test_client()
        response = client.get('/health')

        assert 'max-age=86400' in response.headers['Strict-Transport-Security']

        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
