"""Shared fixtures for Feather framework tests."""

import os
import pytest
import shutil
import tempfile
from pathlib import Path
from unittest.mock import Mock


# =============================================================================
# Test Environment Setup
# =============================================================================

@pytest.fixture(scope="session", autouse=True)
def set_testing_environment():
    """Set FLASK_ENV=testing for all tests.

    This ensures Feather uses TestingConfig with in-memory SQLite,
    preventing creation of instance/app.db file artifacts.
    """
    old_env = os.environ.get("FLASK_ENV")
    os.environ["FLASK_ENV"] = "testing"
    yield
    if old_env is None:
        os.environ.pop("FLASK_ENV", None)
    else:
        os.environ["FLASK_ENV"] = old_env


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_artifacts():
    """Clean up any database artifacts created during tests."""
    yield
    # Remove instance directory if created
    instance_dir = Path(__file__).parent.parent / "instance"
    if instance_dir.exists():
        shutil.rmtree(instance_dir)


# =============================================================================
# App Cleanup Context Manager
# =============================================================================

from contextlib import contextmanager


@contextmanager
def feather_app(**config):
    """Create a Feather app with proper cleanup.

    Use this context manager when creating apps in test methods
    to ensure database connections are properly closed.

    Usage:
        with feather_app(CACHE_BACKEND='memory') as app:
            with app.app_context():
                # test code here
    """
    from feather import Feather
    from feather.db import db

    app = Feather(__name__)
    app.config['TESTING'] = True
    for key, value in config.items():
        app.config[key] = value

    try:
        yield app
    finally:
        # Cleanup database connections
        if 'sqlalchemy' in app.extensions:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()


# =============================================================================
# CSRF-Aware Test Client
# =============================================================================

class CsrfTestClient:
    """Test client wrapper that automatically handles CSRF tokens.

    This client extracts the CSRF token from the session and includes it
    in all state-changing requests (POST, PUT, DELETE, PATCH).

    Usage:
        client = CsrfTestClient(app.test_client(), app)
        response = client.post('/api/items', data={'name': 'test'})

    The CSRF token is passed via the X-CSRFToken header, matching how
    the ApiUtility.js handles it in production.
    """

    # Track which apps have the CSRF endpoint registered
    _apps_with_csrf_endpoint = set()

    def __init__(self, flask_client, app):
        self._client = flask_client
        self._app = app
        self._csrf_token = None

        # Register CSRF token endpoint if not already registered
        self._ensure_csrf_endpoint()

    def _ensure_csrf_endpoint(self):
        """Register a test endpoint that returns a valid CSRF token."""
        app_id = id(self._app)
        if app_id not in CsrfTestClient._apps_with_csrf_endpoint:
            from flask import jsonify
            from flask_wtf.csrf import generate_csrf

            @self._app.route('/_test_csrf_token')
            def _get_csrf_token():
                return jsonify({'token': generate_csrf()})

            CsrfTestClient._apps_with_csrf_endpoint.add(app_id)

    def _get_csrf_token(self):
        """Get a valid CSRF token from the test endpoint."""
        if self._csrf_token is None:
            response = self._client.get('/_test_csrf_token')
            if response.status_code != 200:
                raise RuntimeError(f"Failed to get CSRF token: {response.status_code} - {response.data}")
            data = response.get_json()
            if data is None:
                raise RuntimeError(f"CSRF endpoint returned non-JSON: {response.data}")
            self._csrf_token = data['token']
        return self._csrf_token

    def reset_csrf(self):
        """Reset the cached CSRF token.

        Call this after clearing the session to get a fresh token.
        """
        self._csrf_token = None

    def _add_csrf_header(self, kwargs):
        """Add CSRF token to request headers."""
        headers = kwargs.get('headers', {})
        if isinstance(headers, dict):
            headers = dict(headers)
        else:
            headers = dict(headers)
        headers['X-CSRFToken'] = self._get_csrf_token()
        kwargs['headers'] = headers
        return kwargs

    def get(self, *args, **kwargs):
        """GET request (no CSRF needed)."""
        return self._client.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        """POST request with automatic CSRF token."""
        return self._client.post(*args, **self._add_csrf_header(kwargs))

    def put(self, *args, **kwargs):
        """PUT request with automatic CSRF token."""
        return self._client.put(*args, **self._add_csrf_header(kwargs))

    def delete(self, *args, **kwargs):
        """DELETE request with automatic CSRF token."""
        return self._client.delete(*args, **self._add_csrf_header(kwargs))

    def patch(self, *args, **kwargs):
        """PATCH request with automatic CSRF token."""
        return self._client.patch(*args, **self._add_csrf_header(kwargs))

    def __getattr__(self, name):
        """Delegate other methods to the underlying client."""
        return getattr(self._client, name)

    def __enter__(self):
        """Support context manager protocol."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Support context manager protocol."""
        return False


# =============================================================================
# Integration Test Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_csrf_endpoint_cache():
    """Reset the CSRF endpoint cache before each test.

    This ensures each test's app gets its own CSRF endpoint,
    preventing test order dependencies.
    """
    CsrfTestClient._apps_with_csrf_endpoint = set()
    yield
    CsrfTestClient._apps_with_csrf_endpoint = set()


@pytest.fixture
def test_app():
    """Create a minimal Feather app for integration testing.

    Uses SQLite in-memory database for speed.
    CSRF is enabled to match production behavior.
    """
    from feather import Feather
    from feather.db import db

    app = Feather(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    # CSRF enabled to match production - use CsrfTestClient for POST/PUT/DELETE

    # Setup: create tables
    with app.app_context():
        db.create_all()

    # Yield OUTSIDE app_context so each test client gets proper CSRF isolation
    yield app

    # Cleanup
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(test_app):
    """Create a CSRF-aware test client.

    This client automatically handles CSRF tokens for POST/PUT/DELETE requests,
    matching production behavior where ApiUtility.js handles CSRF.
    """
    return CsrfTestClient(test_app.test_client(), test_app)


@pytest.fixture
def raw_client(test_app):
    """Create a raw test client without CSRF handling.

    Use this when testing CSRF rejection behavior or when you need
    direct access to the underlying Flask test client.
    """
    return test_app.test_client()


def make_csrf_client(app):
    """Create a CSRF-aware test client for any Feather app.

    Use this helper when you need to create a CSRF-enabled client
    for a test that creates its own app instance.

    Usage:
        from tests.conftest import make_csrf_client

        def test_something(self, test_app):
            client = make_csrf_client(test_app)
            response = client.post('/api/items', json={'name': 'test'})
    """
    return CsrfTestClient(app.test_client(), app)


@pytest.fixture
def app_context(test_app):
    """Provide an app context for tests that need it."""
    with test_app.app_context():
        yield test_app


@pytest.fixture
def request_context(test_app):
    """Provide a request context for tests that need it."""
    with test_app.test_request_context():
        yield test_app


@pytest.fixture
def mock_current_user():
    """Create a mock current_user for auth tests."""
    user = Mock()
    user.id = 'test-user-id'
    user.email = 'test@example.com'
    user.is_authenticated = True
    user.is_active = True
    user.is_admin = False
    user.role = 'user'
    user.tenant_id = 'test-tenant-id'
    user.is_platform_admin = False
    return user


# =============================================================================
# Scaffolding Test Fixtures
# =============================================================================


@pytest.fixture
def temp_project_dir():
    """Create a temporary directory for scaffolding tests."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    # Cleanup after test
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


@pytest.fixture
def scaffold_project(temp_project_dir):
    """Factory fixture to scaffold a project with given config.

    Usage:
        project = scaffold_project({
            "database": "postgresql",
            "include_auth": True,
            "tenant_mode": "multi",
            "admin_email": "admin@test.com",
        })
    """
    from feather.cli.new import _create_project_structure, _create_project_files

    created_projects = []

    def _scaffold(config):
        # Generate unique project name for each call
        project_name = f"testapp_{len(created_projects)}"
        project_path = temp_project_dir / project_name
        project_path.mkdir()
        created_projects.append(project_path)

        database = config.get("database", "postgresql")
        include_auth = config.get("include_auth", False)

        _create_project_structure(project_path, database=database, include_auth=include_auth)
        _create_project_files(
            project_path=project_path,
            name=project_name,
            database=database,
            include_auth=config.get("include_auth", False),
            tenant_mode=config.get("tenant_mode"),
            include_cache=config.get("include_cache", False),
            include_jobs=config.get("include_jobs", False),
            include_storage=config.get("include_storage", False),
            storage_backend=config.get("storage_backend"),
            include_email=config.get("include_email", False),
            db_url=config.get("db_url"),
            admin_email=config.get("admin_email"),
        )
        return project_path

    return _scaffold
