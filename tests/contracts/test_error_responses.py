"""Contract tests for error response format.

Ensures all errors return a consistent JSON structure that clients can rely on.
These are contract tests - they verify the API contract doesn't break.
"""

import pytest
from feather import Feather
from feather.exceptions import (
    ValidationError,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ConflictError,
    RateLimitError,
    StorageError,
    DatabaseError,
)

pytestmark = pytest.mark.api_contract


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def error_app():
    """Create a test app with routes that raise various errors."""
    app = Feather(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    # CSRF enabled to match production
    # Allow 500 handler to catch exceptions instead of propagating
    app.config['PROPAGATE_EXCEPTIONS'] = False

    # Routes that raise each exception type
    @app.route('/api/validation-error')
    def raise_validation():
        raise ValidationError('Email is required', field='email')

    @app.route('/api/validation-error-no-field')
    def raise_validation_no_field():
        raise ValidationError('Invalid request format')

    @app.route('/api/authentication-error')
    def raise_auth():
        raise AuthenticationError('Please log in')

    @app.route('/api/authentication-error-default')
    def raise_auth_default():
        raise AuthenticationError()

    @app.route('/api/authorization-error')
    def raise_authz():
        raise AuthorizationError('Admin access required')

    @app.route('/api/authorization-error-default')
    def raise_authz_default():
        raise AuthorizationError()

    @app.route('/api/not-found-error')
    def raise_not_found():
        raise NotFoundError('User', 'user-123')

    @app.route('/api/not-found-error-no-id')
    def raise_not_found_no_id():
        raise NotFoundError('Post')

    @app.route('/api/conflict-error')
    def raise_conflict():
        raise ConflictError('Email already registered')

    @app.route('/api/rate-limit-error')
    def raise_rate_limit():
        raise RateLimitError('Too many requests. Try again later.')

    @app.route('/api/rate-limit-error-default')
    def raise_rate_limit_default():
        raise RateLimitError()

    @app.route('/api/storage-error')
    def raise_storage():
        raise StorageError('Failed to upload file')

    @app.route('/api/storage-error-default')
    def raise_storage_default():
        raise StorageError()

    @app.route('/api/database-error')
    def raise_database():
        raise DatabaseError('Connection failed')

    @app.route('/api/database-error-default')
    def raise_database_default():
        raise DatabaseError()

    @app.route('/api/internal-error')
    def raise_internal():
        raise Exception('Unexpected error')

    with app.app_context():
        from feather.db import db
        db.create_all()

    # Yield OUTSIDE app_context for proper CSRF isolation
    yield app

    # Cleanup
    with app.app_context():
        from feather.db import db
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


# =============================================================================
# Test Error Response Structure
# =============================================================================

class TestErrorResponseStructure:
    """All error responses must have consistent structure."""

    def test_error_response_has_success_false(self, error_app):
        """Error responses have success: false."""
        client = error_app.test_client()
        response = client.get('/api/validation-error')

        data = response.get_json()
        assert data['success'] is False

    def test_error_response_has_data_null(self, error_app):
        """Error responses have data: null."""
        client = error_app.test_client()
        response = client.get('/api/validation-error')

        data = response.get_json()
        assert data['data'] is None

    def test_error_response_has_error_object(self, error_app):
        """Error responses have an error object."""
        client = error_app.test_client()
        response = client.get('/api/validation-error')

        data = response.get_json()
        assert 'error' in data
        assert isinstance(data['error'], dict)

    def test_error_object_has_code(self, error_app):
        """Error object has a code field."""
        client = error_app.test_client()
        response = client.get('/api/validation-error')

        data = response.get_json()
        assert 'code' in data['error']
        assert isinstance(data['error']['code'], str)

    def test_error_object_has_message(self, error_app):
        """Error object has a message field."""
        client = error_app.test_client()
        response = client.get('/api/validation-error')

        data = response.get_json()
        assert 'message' in data['error']
        assert isinstance(data['error']['message'], str)

    def test_error_response_has_meta(self, error_app):
        """Error responses have a meta object."""
        client = error_app.test_client()
        response = client.get('/api/validation-error')

        data = response.get_json()
        assert 'meta' in data
        assert isinstance(data['meta'], dict)

    def test_meta_has_timestamp(self, error_app):
        """Meta object has a timestamp."""
        client = error_app.test_client()
        response = client.get('/api/validation-error')

        data = response.get_json()
        assert 'timestamp' in data['meta']
        # ISO format timestamp
        assert 'T' in data['meta']['timestamp']


# =============================================================================
# Test ValidationError (400)
# =============================================================================

class TestValidationErrorFormat:
    """ValidationError returns 400 with correct format."""

    def test_status_code_400(self, error_app):
        """ValidationError returns 400 status code."""
        client = error_app.test_client()
        response = client.get('/api/validation-error')

        assert response.status_code == 400

    def test_error_code_is_validation_error(self, error_app):
        """Error code is VALIDATION_ERROR."""
        client = error_app.test_client()
        response = client.get('/api/validation-error')

        data = response.get_json()
        assert data['error']['code'] == 'VALIDATION_ERROR'

    def test_message_matches(self, error_app):
        """Error message matches what was raised."""
        client = error_app.test_client()
        response = client.get('/api/validation-error')

        data = response.get_json()
        assert data['error']['message'] == 'Email is required'

    def test_field_included_when_provided(self, error_app):
        """Field is included in error when provided."""
        client = error_app.test_client()
        response = client.get('/api/validation-error')

        data = response.get_json()
        assert 'field' in data['error']
        assert data['error']['field'] == 'email'

    def test_field_absent_when_not_provided(self, error_app):
        """Field is absent when not provided."""
        client = error_app.test_client()
        response = client.get('/api/validation-error-no-field')

        data = response.get_json()
        # Field should either be absent or null
        assert data['error'].get('field') is None


# =============================================================================
# Test AuthenticationError (401)
# =============================================================================

class TestAuthenticationErrorFormat:
    """AuthenticationError returns 401 with correct format."""

    def test_status_code_401(self, error_app):
        """AuthenticationError returns 401 status code."""
        client = error_app.test_client()
        response = client.get('/api/authentication-error')

        assert response.status_code == 401

    def test_error_code_is_authentication_error(self, error_app):
        """Error code is AUTHENTICATION_ERROR."""
        client = error_app.test_client()
        response = client.get('/api/authentication-error')

        data = response.get_json()
        assert data['error']['code'] == 'AUTHENTICATION_ERROR'

    def test_custom_message(self, error_app):
        """Custom message is returned."""
        client = error_app.test_client()
        response = client.get('/api/authentication-error')

        data = response.get_json()
        assert data['error']['message'] == 'Please log in'

    def test_default_message(self, error_app):
        """Default message is 'Authentication required'."""
        client = error_app.test_client()
        response = client.get('/api/authentication-error-default')

        data = response.get_json()
        assert data['error']['message'] == 'Authentication required'


# =============================================================================
# Test AuthorizationError (403)
# =============================================================================

class TestAuthorizationErrorFormat:
    """AuthorizationError returns 403 with correct format."""

    def test_status_code_403(self, error_app):
        """AuthorizationError returns 403 status code."""
        client = error_app.test_client()
        response = client.get('/api/authorization-error')

        assert response.status_code == 403

    def test_error_code_is_authorization_error(self, error_app):
        """Error code is AUTHORIZATION_ERROR."""
        client = error_app.test_client()
        response = client.get('/api/authorization-error')

        data = response.get_json()
        assert data['error']['code'] == 'AUTHORIZATION_ERROR'

    def test_custom_message(self, error_app):
        """Custom message is returned."""
        client = error_app.test_client()
        response = client.get('/api/authorization-error')

        data = response.get_json()
        assert data['error']['message'] == 'Admin access required'

    def test_default_message(self, error_app):
        """Default message is 'Permission denied'."""
        client = error_app.test_client()
        response = client.get('/api/authorization-error-default')

        data = response.get_json()
        assert data['error']['message'] == 'Permission denied'


# =============================================================================
# Test NotFoundError (404)
# =============================================================================

class TestNotFoundErrorFormat:
    """NotFoundError returns 404 with correct format."""

    def test_status_code_404(self, error_app):
        """NotFoundError returns 404 status code."""
        client = error_app.test_client()
        response = client.get('/api/not-found-error')

        assert response.status_code == 404

    def test_error_code_is_not_found(self, error_app):
        """Error code is NOT_FOUND."""
        client = error_app.test_client()
        response = client.get('/api/not-found-error')

        data = response.get_json()
        assert data['error']['code'] == 'NOT_FOUND'

    def test_message_with_id(self, error_app):
        """Message includes resource type and ID."""
        client = error_app.test_client()
        response = client.get('/api/not-found-error')

        data = response.get_json()
        assert 'User' in data['error']['message']
        assert 'user-123' in data['error']['message']

    def test_message_without_id(self, error_app):
        """Message works without ID."""
        client = error_app.test_client()
        response = client.get('/api/not-found-error-no-id')

        data = response.get_json()
        assert 'Post' in data['error']['message']
        assert data['error']['message'] == 'Post not found'


# =============================================================================
# Test ConflictError (409)
# =============================================================================

class TestConflictErrorFormat:
    """ConflictError returns 409 with correct format."""

    def test_status_code_409(self, error_app):
        """ConflictError returns 409 status code."""
        client = error_app.test_client()
        response = client.get('/api/conflict-error')

        assert response.status_code == 409

    def test_error_code_is_conflict(self, error_app):
        """Error code is CONFLICT."""
        client = error_app.test_client()
        response = client.get('/api/conflict-error')

        data = response.get_json()
        assert data['error']['code'] == 'CONFLICT'

    def test_message_matches(self, error_app):
        """Error message matches what was raised."""
        client = error_app.test_client()
        response = client.get('/api/conflict-error')

        data = response.get_json()
        assert data['error']['message'] == 'Email already registered'


# =============================================================================
# Test RateLimitError (429)
# =============================================================================

class TestRateLimitErrorFormat:
    """RateLimitError returns 429 with correct format."""

    def test_status_code_429(self, error_app):
        """RateLimitError returns 429 status code."""
        client = error_app.test_client()
        response = client.get('/api/rate-limit-error')

        assert response.status_code == 429

    def test_error_code_is_rate_limit_error(self, error_app):
        """Error code is RATE_LIMIT_ERROR."""
        client = error_app.test_client()
        response = client.get('/api/rate-limit-error')

        data = response.get_json()
        assert data['error']['code'] == 'RATE_LIMIT_ERROR'

    def test_custom_message(self, error_app):
        """Custom message is returned."""
        client = error_app.test_client()
        response = client.get('/api/rate-limit-error')

        data = response.get_json()
        assert data['error']['message'] == 'Too many requests. Try again later.'

    def test_default_message(self, error_app):
        """Default message is 'Too many requests'."""
        client = error_app.test_client()
        response = client.get('/api/rate-limit-error-default')

        data = response.get_json()
        assert data['error']['message'] == 'Too many requests'


# =============================================================================
# Test StorageError (500)
# =============================================================================

class TestStorageErrorFormat:
    """StorageError returns 500 with correct format."""

    def test_status_code_500(self, error_app):
        """StorageError returns 500 status code."""
        client = error_app.test_client()
        response = client.get('/api/storage-error')

        assert response.status_code == 500

    def test_error_code_is_storage_error(self, error_app):
        """Error code is STORAGE_ERROR."""
        client = error_app.test_client()
        response = client.get('/api/storage-error')

        data = response.get_json()
        assert data['error']['code'] == 'STORAGE_ERROR'

    def test_custom_message(self, error_app):
        """Custom message is returned."""
        client = error_app.test_client()
        response = client.get('/api/storage-error')

        data = response.get_json()
        assert data['error']['message'] == 'Failed to upload file'

    def test_default_message(self, error_app):
        """Default message is 'Storage operation failed'."""
        client = error_app.test_client()
        response = client.get('/api/storage-error-default')

        data = response.get_json()
        assert data['error']['message'] == 'Storage operation failed'


# =============================================================================
# Test DatabaseError (500)
# =============================================================================

class TestDatabaseErrorFormat:
    """DatabaseError returns 500 with correct format."""

    def test_status_code_500(self, error_app):
        """DatabaseError returns 500 status code."""
        client = error_app.test_client()
        response = client.get('/api/database-error')

        assert response.status_code == 500

    def test_error_code_is_database_error(self, error_app):
        """Error code is DATABASE_ERROR."""
        client = error_app.test_client()
        response = client.get('/api/database-error')

        data = response.get_json()
        assert data['error']['code'] == 'DATABASE_ERROR'

    def test_custom_message(self, error_app):
        """Custom message is returned."""
        client = error_app.test_client()
        response = client.get('/api/database-error')

        data = response.get_json()
        assert data['error']['message'] == 'Connection failed'

    def test_default_message(self, error_app):
        """Default message is 'Database operation failed'."""
        client = error_app.test_client()
        response = client.get('/api/database-error-default')

        data = response.get_json()
        assert data['error']['message'] == 'Database operation failed'


# =============================================================================
# Test 500 Internal Server Error
# =============================================================================

class TestInternalErrorFormat:
    """Unhandled exceptions return 500 with safe message."""

    def test_status_code_500(self, error_app):
        """Unhandled exceptions return 500 status code."""
        client = error_app.test_client()
        response = client.get('/api/internal-error')

        assert response.status_code == 500

    def test_error_code_is_internal_error(self, error_app):
        """Error code is INTERNAL_ERROR."""
        client = error_app.test_client()
        response = client.get('/api/internal-error')

        data = response.get_json()
        assert data['error']['code'] == 'INTERNAL_ERROR'

    def test_message_is_safe(self, error_app):
        """Message doesn't leak internal details."""
        client = error_app.test_client()
        response = client.get('/api/internal-error')

        data = response.get_json()
        # Should NOT contain the actual exception message
        assert 'Unexpected error' not in data['error']['message']
        # Should have a generic safe message
        assert 'unexpected' in data['error']['message'].lower() or 'error' in data['error']['message'].lower()


# =============================================================================
# Test 404 for Missing Routes
# =============================================================================

class TestMissingRouteFormat:
    """Missing routes return proper 404."""

    def test_status_code_404(self, error_app):
        """Missing routes return 404."""
        client = error_app.test_client()
        response = client.get('/api/nonexistent-route')

        assert response.status_code == 404

    def test_error_code_is_not_found(self, error_app):
        """Error code is NOT_FOUND."""
        client = error_app.test_client()
        response = client.get('/api/nonexistent-route')

        data = response.get_json()
        assert data['error']['code'] == 'NOT_FOUND'
