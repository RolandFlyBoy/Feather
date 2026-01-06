"""E2E tests for authentication workflow.

Tests login, session management, and logout flows through the stack.
"""

import pytest
from flask_login import login_user, logout_user, current_user, LoginManager, UserMixin
from feather import Feather, auth_required, admin_required
from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin
from tests.conftest import make_csrf_client

pytestmark = pytest.mark.e2e


# Define model at module level to avoid SQLAlchemy redefinition warnings
class AuthUser(UUIDMixin, TimestampMixin, UserMixin, Model):
    """Test user model for auth tests."""
    __tablename__ = 'auth_users'
    __table_args__ = {'extend_existing': True}
    email = db.Column(db.String(255), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True)
    role = db.Column(db.String(50), default='user')

    @property
    def is_admin(self):
        return self.role == 'admin'

    def is_active(self):
        return self.active


@pytest.fixture
def auth_app():
    """Create a test app with authentication setup."""
    app = Feather(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    # CSRF enabled to match production

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login_page'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(AuthUser, user_id)

    # Public routes
    @app.route('/')
    def home():
        return {'page': 'home', 'authenticated': bool(current_user.is_authenticated)}

    @app.route('/login')
    def login_page():
        return {'page': 'login'}

    # Test login endpoint (simulates OAuth callback)
    @app.route('/test-login/<user_id>', methods=['POST'])
    def test_login(user_id):
        user = db.session.get(AuthUser, user_id)
        if user and user.active:
            login_user(user)
            return {'logged_in': True, 'user_id': user.id}
        return {'logged_in': False, 'error': 'Invalid or inactive user'}, 401

    @app.route('/logout', methods=['POST'])
    def logout():
        logout_user()
        return {'logged_out': True}

    # Protected routes (using /api/ prefix for JSON error responses)
    @app.route('/api/protected')
    @auth_required
    def protected():
        return {'data': 'secret', 'user': current_user.email}

    @app.route('/api/admin')
    @admin_required
    def admin_panel():
        return {'data': 'admin only', 'user': current_user.email}

    @app.route('/api/profile')
    @auth_required
    def profile():
        return {
            'email': current_user.email,
            'role': current_user.role,
            'is_admin': current_user.is_admin,
        }

    # Setup: create tables and seed data
    with app.app_context():
        db.create_all()
        regular_user = AuthUser(email='user@example.com', active=True, role='user')
        admin_user = AuthUser(email='admin@example.com', active=True, role='admin')
        inactive_user = AuthUser(email='inactive@example.com', active=False, role='user')
        db.session.add_all([regular_user, admin_user, inactive_user])
        db.session.commit()
        app.test_users = {
            'regular': regular_user.id,
            'admin': admin_user.id,
            'inactive': inactive_user.id,
        }

    # Yield OUTSIDE app_context for proper CSRF isolation
    yield app

    # Cleanup
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(auth_app):
    """Create a CSRF-aware test client."""
    return make_csrf_client(auth_app)


class TestPublicAccess:
    """Test public route access."""

    def test_home_page_accessible(self, client):
        """Home page is accessible without auth."""
        response = client.get('/')
        assert response.status_code == 200
        data = response.get_json()
        assert data['page'] == 'home'
        assert data['authenticated'] is False

    def test_login_page_accessible(self, client):
        """Login page is accessible without auth."""
        response = client.get('/login')
        assert response.status_code == 200
        data = response.get_json()
        assert data['page'] == 'login'


class TestLoginWorkflow:
    """Test login flow."""

    def test_login_active_user(self, client, auth_app):
        """Active user can log in."""
        user_id = auth_app.test_users['regular']
        response = client.post(f'/test-login/{user_id}')

        assert response.status_code == 200
        data = response.get_json()
        assert data['logged_in'] is True
        assert data['user_id'] == user_id

    def test_login_inactive_user_rejected(self, client, auth_app):
        """Inactive user cannot log in."""
        user_id = auth_app.test_users['inactive']
        response = client.post(f'/test-login/{user_id}')

        assert response.status_code == 401
        data = response.get_json()
        assert data['logged_in'] is False

    def test_login_nonexistent_user(self, client):
        """Nonexistent user cannot log in."""
        response = client.post('/test-login/fake-user-id')

        assert response.status_code == 401
        data = response.get_json()
        assert data['logged_in'] is False


class TestSessionManagement:
    """Test session persistence."""

    def test_session_persists_across_requests(self, client, auth_app):
        """Session persists across multiple requests."""
        user_id = auth_app.test_users['regular']

        # Login
        client.post(f'/test-login/{user_id}')

        # First request
        response1 = client.get('/api/protected')
        assert response1.status_code == 200
        assert response1.get_json()['user'] == 'user@example.com'

        # Second request (same session)
        response2 = client.get('/api/profile')
        assert response2.status_code == 200
        assert response2.get_json()['email'] == 'user@example.com'

    def test_home_shows_authenticated_status(self, client, auth_app):
        """Home page shows authenticated status after login."""
        user_id = auth_app.test_users['regular']

        # Before login
        response_before = client.get('/')
        assert response_before.get_json()['authenticated'] is False

        # Login
        client.post(f'/test-login/{user_id}')

        # After login
        response_after = client.get('/')
        assert response_after.get_json()['authenticated'] is True


class TestProtectedRoutes:
    """Test protected route access."""

    def test_protected_route_requires_login(self, client):
        """Protected API route returns 401 for unauthenticated users."""
        response = client.get('/api/protected')
        # API routes return 401 for unauthenticated
        assert response.status_code == 401
        data = response.get_json()
        assert data['error']['code'] == 'AUTHENTICATION_ERROR'

    def test_protected_route_accessible_when_logged_in(self, client, auth_app):
        """Protected route accessible when logged in."""
        user_id = auth_app.test_users['regular']
        client.post(f'/test-login/{user_id}')

        response = client.get('/api/protected')
        assert response.status_code == 200
        data = response.get_json()
        assert data['data'] == 'secret'

    def test_admin_route_requires_admin_role(self, client, auth_app):
        """Admin route requires admin role."""
        user_id = auth_app.test_users['regular']
        client.post(f'/test-login/{user_id}')

        response = client.get('/api/admin')
        # Regular user should be forbidden
        assert response.status_code == 403

    def test_admin_route_accessible_to_admin(self, client, auth_app):
        """Admin route accessible to admin users."""
        user_id = auth_app.test_users['admin']
        client.post(f'/test-login/{user_id}')

        response = client.get('/api/admin')
        assert response.status_code == 200
        data = response.get_json()
        assert data['data'] == 'admin only'


class TestLogoutWorkflow:
    """Test logout flow."""

    def test_logout_clears_session(self, client, auth_app):
        """Logout clears user session."""
        user_id = auth_app.test_users['regular']

        # Login
        client.post(f'/test-login/{user_id}')

        # Verify logged in
        response_before = client.get('/api/protected')
        assert response_before.status_code == 200

        # Logout
        logout_response = client.post('/logout')
        assert logout_response.status_code == 200
        assert logout_response.get_json()['logged_out'] is True

        # Verify logged out
        response_after = client.get('/api/protected')
        assert response_after.status_code == 401  # API returns 401

    def test_home_shows_unauthenticated_after_logout(self, client, auth_app):
        """Home page shows unauthenticated after logout."""
        user_id = auth_app.test_users['regular']

        # Login
        client.post(f'/test-login/{user_id}')
        assert client.get('/').get_json()['authenticated'] is True

        # Logout
        client.post('/logout')

        # Verify
        assert client.get('/').get_json()['authenticated'] is False


class TestRoleBasedAccess:
    """Test role-based access control."""

    def test_regular_user_profile(self, client, auth_app):
        """Regular user sees their profile."""
        user_id = auth_app.test_users['regular']
        client.post(f'/test-login/{user_id}')

        response = client.get('/api/profile')
        data = response.get_json()

        assert data['email'] == 'user@example.com'
        assert data['role'] == 'user'
        assert data['is_admin'] is False

    def test_admin_user_profile(self, client, auth_app):
        """Admin user sees their profile with admin role."""
        user_id = auth_app.test_users['admin']
        client.post(f'/test-login/{user_id}')

        response = client.get('/api/profile')
        data = response.get_json()

        assert data['email'] == 'admin@example.com'
        assert data['role'] == 'admin'
        assert data['is_admin'] is True


class TestFullAuthWorkflow:
    """Test complete authentication lifecycle."""

    def test_complete_auth_lifecycle(self, client, auth_app):
        """Test full login-use-logout cycle."""
        user_id = auth_app.test_users['regular']

        # 1. Start unauthenticated
        home_response = client.get('/')
        assert home_response.get_json()['authenticated'] is False

        # 2. Can't access protected (API returns 401)
        protected_response = client.get('/api/protected')
        assert protected_response.status_code == 401

        # 3. Login
        login_response = client.post(f'/test-login/{user_id}')
        assert login_response.get_json()['logged_in'] is True

        # 4. Can access protected
        protected_response = client.get('/api/protected')
        assert protected_response.status_code == 200

        # 5. Can view profile
        profile_response = client.get('/api/profile')
        assert profile_response.status_code == 200

        # 6. Logout
        logout_response = client.post('/logout')
        assert logout_response.get_json()['logged_out'] is True

        # 7. Can't access protected anymore
        protected_response = client.get('/api/protected')
        assert protected_response.status_code == 401

    def test_admin_access_escalation_prevented(self, client, auth_app):
        """Regular user cannot access admin routes even after login."""
        regular_id = auth_app.test_users['regular']

        # Login as regular user
        client.post(f'/test-login/{regular_id}')

        # Try to access admin
        admin_response = client.get('/api/admin')
        assert admin_response.status_code == 403

        # Logout
        client.post('/logout')

        # Login as admin
        admin_id = auth_app.test_users['admin']
        client.post(f'/test-login/{admin_id}')

        # Now can access admin
        admin_response = client.get('/api/admin')
        assert admin_response.status_code == 200
