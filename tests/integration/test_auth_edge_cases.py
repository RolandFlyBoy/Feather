"""Integration tests for authentication edge cases.

Tests inactive users, session security, and role inheritance.
These are security-critical tests for access control.
"""

import pytest
from flask_login import login_user, logout_user, LoginManager, UserMixin
from feather import Feather, auth_required, admin_required
from feather.auth import role_required, platform_admin_required
from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin
from tests.conftest import make_csrf_client

pytestmark = pytest.mark.integration


# =============================================================================
# Test Models (Module Level to avoid SQLAlchemy warnings)
# =============================================================================

class AuthEdgeCaseUser(UUIDMixin, TimestampMixin, UserMixin, Model):
    """Test user model for auth edge case tests."""
    __tablename__ = 'auth_edge_case_users'
    __table_args__ = {'extend_existing': True}

    email = db.Column(db.String(255), unique=True, nullable=False)
    tenant_id = db.Column(db.String(36), nullable=True)
    active = db.Column(db.Boolean, default=True)
    role = db.Column(db.String(50), default='user')
    is_platform_admin = db.Column(db.Boolean, default=False)

    @property
    def is_active(self):
        """Flask-Login requires is_active to be a property, not a method."""
        return self.active


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def auth_edge_app():
    """Create a test app for auth edge case testing."""
    app = Feather(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    # CSRF enabled to match production
    app.config['FEATHER_MULTI_TENANT'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(AuthEdgeCaseUser, user_id)

    # Test login endpoint (simulates successful OAuth)
    @app.route('/test-login/<user_id>', methods=['POST'])
    def test_login(user_id):
        user = db.session.get(AuthEdgeCaseUser, user_id)
        if user:
            # Force login regardless of active status (simulates OAuth callback)
            # In production, OAuth callback logs user in before active check
            login_user(user, force=True)
            return {'logged_in': True, 'user_id': user.id}
        return {'logged_in': False}, 401

    # Test logout endpoint
    @app.route('/logout', methods=['POST'])
    def logout():
        logout_user()
        return {'logged_out': True}

    # Protected routes for testing
    @app.route('/api/protected')
    @auth_required
    def protected():
        return {'message': 'success'}

    @app.route('/api/admin-only')
    @admin_required
    def admin_only():
        return {'message': 'admin access'}

    @app.route('/api/editor-required')
    @role_required('editor')
    def editor_required():
        return {'message': 'editor access'}

    @app.route('/api/moderator-required')
    @role_required('moderator')
    def moderator_required():
        return {'message': 'moderator access'}

    @app.route('/api/user-required')
    @role_required('user')
    def user_required():
        return {'message': 'user access'}

    @app.route('/api/platform-admin')
    @platform_admin_required
    def platform_admin_only():
        return {'message': 'platform admin access'}

    # Setup: create tables and seed data
    with app.app_context():
        db.create_all()
        tenant_id = 'test-tenant-uuid'
        active_user = AuthEdgeCaseUser(
            email='active@example.com', tenant_id=tenant_id, active=True, role='user'
        )
        inactive_user = AuthEdgeCaseUser(
            email='inactive@example.com', tenant_id=tenant_id, active=False, role='user'
        )
        admin_user = AuthEdgeCaseUser(
            email='admin@example.com', tenant_id=tenant_id, active=True, role='admin'
        )
        editor_user = AuthEdgeCaseUser(
            email='editor@example.com', tenant_id=tenant_id, active=True, role='editor'
        )
        moderator_user = AuthEdgeCaseUser(
            email='moderator@example.com', tenant_id=tenant_id, active=True, role='moderator'
        )
        platform_admin = AuthEdgeCaseUser(
            email='platform@example.com', tenant_id=tenant_id, active=True,
            role='user', is_platform_admin=True
        )
        db.session.add_all([
            active_user, inactive_user, admin_user,
            editor_user, moderator_user, platform_admin
        ])
        db.session.commit()
        app.test_users = {
            'active': active_user.id,
            'inactive': inactive_user.id,
            'admin': admin_user.id,
            'editor': editor_user.id,
            'moderator': moderator_user.id,
            'platform_admin': platform_admin.id,
        }

    # Yield OUTSIDE app_context for proper CSRF isolation
    yield app

    # Cleanup
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


# =============================================================================
# Test Inactive Users
# =============================================================================

class TestInactiveUsers:
    """Tests for inactive/suspended user handling.

    Inactive users (is_active=False) have a valid session but are blocked
    with 403 "Account suspended". This is distinct from unauthenticated
    users who get 401 "Authentication required".
    """

    def test_inactive_user_gets_403_not_401(self, auth_edge_app):
        """Inactive users get 403 (suspended), not 401 (unauthenticated)."""
        client = make_csrf_client(auth_edge_app)

        # Login as inactive user
        login_response = client.post(f'/test-login/{auth_edge_app.test_users["inactive"]}')
        assert login_response.status_code == 200
        assert login_response.get_json()['logged_in'] is True

        # Inactive users get 403 with clear "suspended" message
        response = client.get('/api/protected')
        assert response.status_code == 403
        data = response.get_json()
        assert data['error']['code'] == 'AUTHORIZATION_ERROR'
        assert 'suspended' in data['error']['message'].lower()

    def test_inactive_user_session_exists_but_blocked(self, auth_edge_app):
        """Inactive users have a session but are blocked on protected routes."""
        client = make_csrf_client(auth_edge_app)

        # Login succeeds (stores user ID in session)
        login_response = client.post(f'/test-login/{auth_edge_app.test_users["inactive"]}')
        assert login_response.status_code == 200

        # Protected routes block them with 403, not 401
        response = client.get('/api/protected')
        assert response.status_code == 403

    def test_active_user_can_access_protected(self, auth_edge_app):
        """Active users can access protected routes."""
        client = make_csrf_client(auth_edge_app)

        client.post(f'/test-login/{auth_edge_app.test_users["active"]}')

        response = client.get('/api/protected')
        assert response.status_code == 200
        assert response.get_json()['message'] == 'success'

    def test_inactive_user_sees_suspended_message(self, auth_edge_app):
        """Inactive users see a clear 'account suspended' message."""
        client = make_csrf_client(auth_edge_app)

        client.post(f'/test-login/{auth_edge_app.test_users["inactive"]}')

        response = client.get('/api/protected')
        data = response.get_json()

        assert response.status_code == 403
        assert data['error']['code'] == 'AUTHORIZATION_ERROR'
        # Message should clearly indicate suspension, not ask for login
        assert 'suspended' in data['error']['message'].lower()


# =============================================================================
# Test Session Security
# =============================================================================

class TestSessionSecurity:
    """Tests for session security settings."""

    def test_session_invalidated_on_logout(self, auth_edge_app):
        """Logout properly invalidates the session."""
        client = make_csrf_client(auth_edge_app)

        # Login
        client.post(f'/test-login/{auth_edge_app.test_users["active"]}')

        # Verify logged in
        response = client.get('/api/protected')
        assert response.status_code == 200

        # Logout
        logout_response = client.post('/logout')
        assert logout_response.status_code == 200
        assert logout_response.get_json()['logged_out'] is True

        # Verify can no longer access protected
        response = client.get('/api/protected')
        assert response.status_code == 401

    def test_new_client_is_unauthenticated(self, auth_edge_app):
        """A fresh test client should not be authenticated.

        Note: Due to fixture setup with app_context(), testing true session
        isolation requires clients created outside the context. This test
        verifies a fresh client without login is unauthenticated.
        """
        client = make_csrf_client(auth_edge_app)

        # No login performed - should be unauthenticated
        response = client.get('/api/protected')
        assert response.status_code == 401


# =============================================================================
# Test Role Inheritance
# =============================================================================

class TestRoleInheritance:
    """Tests for role inheritance in authorization."""

    def test_admin_satisfies_editor_requirement(self, auth_edge_app):
        """Admin role satisfies @role_required('editor')."""
        client = make_csrf_client(auth_edge_app)

        client.post(f'/test-login/{auth_edge_app.test_users["admin"]}')

        response = client.get('/api/editor-required')
        assert response.status_code == 200
        assert response.get_json()['message'] == 'editor access'

    def test_admin_satisfies_moderator_requirement(self, auth_edge_app):
        """Admin role satisfies @role_required('moderator')."""
        client = make_csrf_client(auth_edge_app)

        client.post(f'/test-login/{auth_edge_app.test_users["admin"]}')

        response = client.get('/api/moderator-required')
        assert response.status_code == 200
        assert response.get_json()['message'] == 'moderator access'

    def test_admin_satisfies_user_requirement(self, auth_edge_app):
        """Admin role satisfies @role_required('user')."""
        client = make_csrf_client(auth_edge_app)

        client.post(f'/test-login/{auth_edge_app.test_users["admin"]}')

        response = client.get('/api/user-required')
        assert response.status_code == 200
        assert response.get_json()['message'] == 'user access'

    def test_editor_does_not_satisfy_admin_requirement(self, auth_edge_app):
        """Editor role does NOT satisfy @admin_required."""
        client = make_csrf_client(auth_edge_app)

        client.post(f'/test-login/{auth_edge_app.test_users["editor"]}')

        response = client.get('/api/admin-only')
        assert response.status_code == 403
        data = response.get_json()
        assert data['error']['code'] == 'AUTHORIZATION_ERROR'

    def test_editor_satisfies_user_requirement(self, auth_edge_app):
        """Editor role satisfies @role_required('user')."""
        client = make_csrf_client(auth_edge_app)

        client.post(f'/test-login/{auth_edge_app.test_users["editor"]}')

        response = client.get('/api/user-required')
        assert response.status_code == 200

    def test_moderator_does_not_satisfy_editor_requirement(self, auth_edge_app):
        """Moderator role does NOT satisfy @role_required('editor')."""
        client = make_csrf_client(auth_edge_app)

        client.post(f'/test-login/{auth_edge_app.test_users["moderator"]}')

        response = client.get('/api/editor-required')
        assert response.status_code == 403

    def test_moderator_satisfies_user_requirement(self, auth_edge_app):
        """Moderator role satisfies @role_required('user')."""
        client = make_csrf_client(auth_edge_app)

        client.post(f'/test-login/{auth_edge_app.test_users["moderator"]}')

        response = client.get('/api/user-required')
        assert response.status_code == 200

    def test_user_does_not_satisfy_admin_requirement(self, auth_edge_app):
        """User role does NOT satisfy @admin_required."""
        client = make_csrf_client(auth_edge_app)

        client.post(f'/test-login/{auth_edge_app.test_users["active"]}')

        response = client.get('/api/admin-only')
        assert response.status_code == 403


# =============================================================================
# Test Platform Admin
# =============================================================================

class TestPlatformAdmin:
    """Tests for platform admin access."""

    def test_platform_admin_can_access_platform_routes(self, auth_edge_app):
        """Platform admins can access @platform_admin_required routes."""
        client = make_csrf_client(auth_edge_app)

        client.post(f'/test-login/{auth_edge_app.test_users["platform_admin"]}')

        response = client.get('/api/platform-admin')
        assert response.status_code == 200
        assert response.get_json()['message'] == 'platform admin access'

    def test_tenant_admin_cannot_access_platform_routes(self, auth_edge_app):
        """Tenant admins cannot access @platform_admin_required routes."""
        client = make_csrf_client(auth_edge_app)

        client.post(f'/test-login/{auth_edge_app.test_users["admin"]}')

        response = client.get('/api/platform-admin')
        assert response.status_code == 403
        data = response.get_json()
        assert 'platform admin' in data['error']['message'].lower()

    def test_platform_admin_bypasses_role_checks(self, auth_edge_app):
        """Platform admins bypass @role_required checks."""
        client = make_csrf_client(auth_edge_app)

        # Platform admin has role='user' but is_platform_admin=True
        client.post(f'/test-login/{auth_edge_app.test_users["platform_admin"]}')

        # Should access admin-only routes despite role='user'
        response = client.get('/api/admin-only')
        assert response.status_code == 200

    def test_regular_user_cannot_access_platform_routes(self, auth_edge_app):
        """Regular users cannot access platform admin routes."""
        client = make_csrf_client(auth_edge_app)

        client.post(f'/test-login/{auth_edge_app.test_users["active"]}')

        response = client.get('/api/platform-admin')
        assert response.status_code == 403


# =============================================================================
# Test Unauthenticated Access
# =============================================================================

class TestUnauthenticatedAccess:
    """Tests for unauthenticated request handling."""

    def test_unauthenticated_user_gets_401_on_api(self, auth_edge_app):
        """Unauthenticated users get 401 on API routes."""
        client = make_csrf_client(auth_edge_app)

        response = client.get('/api/protected')
        assert response.status_code == 401
        data = response.get_json()
        assert data['error']['code'] == 'AUTHENTICATION_ERROR'

    def test_unauthenticated_user_gets_401_on_admin(self, auth_edge_app):
        """Unauthenticated users get 401 on admin routes."""
        client = make_csrf_client(auth_edge_app)

        response = client.get('/api/admin-only')
        assert response.status_code == 401

    def test_unauthenticated_user_gets_401_on_platform(self, auth_edge_app):
        """Unauthenticated users get 401 on platform admin routes."""
        client = make_csrf_client(auth_edge_app)

        response = client.get('/api/platform-admin')
        assert response.status_code == 401
