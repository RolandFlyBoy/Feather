"""E2E tests for admin panel workflow.

Tests admin user management operations through the stack.
"""

import pytest
from flask_login import login_user, current_user, LoginManager, UserMixin
from feather import Feather, admin_required, auth_required
from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin
from tests.conftest import make_csrf_client

pytestmark = pytest.mark.e2e


# Define model at module level to avoid SQLAlchemy redefinition warnings
class AdminPanelUser(UUIDMixin, TimestampMixin, UserMixin, Model):
    """Test user model for admin workflow tests."""
    __tablename__ = 'admin_panel_users'
    __table_args__ = {'extend_existing': True}
    email = db.Column(db.String(255), unique=True, nullable=False)
    display_name = db.Column(db.String(100))
    active = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(50), default='user')

    @property
    def is_admin(self):
        return self.role == 'admin'

    def is_active(self):
        return self.active


@pytest.fixture
def admin_app():
    """Create a test app with admin panel functionality."""
    app = Feather(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    # CSRF enabled to match production - use CsrfTestClient for POST/PUT/DELETE

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(AdminPanelUser, user_id)

    # Test login endpoint
    @app.route('/test-login/<user_id>', methods=['POST'])
    def test_login(user_id):
        user = db.session.get(AdminPanelUser, user_id)
        if user:
            login_user(user)
            return {'logged_in': True}
        return {'logged_in': False}, 401

    # Admin routes
    @app.route('/api/admin/users')
    @admin_required
    def list_users():
        users = AdminPanelUser.query.all()
        return {
            'users': [{
                'id': u.id,
                'email': u.email,
                'display_name': u.display_name,
                'active': u.active,
                'role': u.role,
            } for u in users]
        }

    @app.route('/api/admin/users/<user_id>')
    @admin_required
    def get_user(user_id):
        from feather import NotFoundError
        user = db.session.get(AdminPanelUser, user_id)
        if not user:
            raise NotFoundError('User', user_id)
        return {
            'id': user.id,
            'email': user.email,
            'display_name': user.display_name,
            'active': user.active,
            'role': user.role,
        }

    @app.route('/api/admin/users/<user_id>/toggle-status', methods=['POST'])
    @admin_required
    def toggle_user_status(user_id):
        from feather import NotFoundError
        user = db.session.get(AdminPanelUser, user_id)
        if not user:
            raise NotFoundError('User', user_id)
        user.active = not user.active
        db.session.commit()
        return {'id': user.id, 'active': user.active}

    @app.route('/api/admin/users/<user_id>/update-role', methods=['POST'])
    @admin_required
    def update_user_role(user_id):
        from flask import request
        from feather import NotFoundError, ValidationError
        user = db.session.get(AdminPanelUser, user_id)
        if not user:
            raise NotFoundError('User', user_id)
        data = request.get_json() or {}
        new_role = data.get('role')
        if new_role not in ['user', 'editor', 'admin']:
            raise ValidationError('Invalid role', field='role')
        user.role = new_role
        db.session.commit()
        return {'id': user.id, 'role': user.role}

    @app.route('/api/admin/stats')
    @admin_required
    def admin_stats():
        total_users = AdminPanelUser.query.count()
        active_users = AdminPanelUser.query.filter_by(active=True).count()
        pending_users = AdminPanelUser.query.filter_by(active=False).count()
        admin_count = AdminPanelUser.query.filter_by(role='admin').count()
        return {
            'total_users': total_users,
            'active_users': active_users,
            'pending_users': pending_users,
            'admin_count': admin_count,
        }

    @app.route('/api/admin/users/search')
    @admin_required
    def search_users():
        from flask import request
        query = request.args.get('q', '')
        users = AdminPanelUser.query.filter(AdminPanelUser.email.contains(query)).all()
        return {
            'users': [{
                'id': u.id,
                'email': u.email,
                'display_name': u.display_name,
            } for u in users]
        }

    # Setup: create tables and seed data
    with app.app_context():
        db.create_all()

        # Create test users
        admin = AdminPanelUser(
            email='admin@example.com',
            display_name='Admin User',
            active=True,
            role='admin'
        )
        user1 = AdminPanelUser(
            email='user1@example.com',
            display_name='User One',
            active=True,
            role='user'
        )
        user2 = AdminPanelUser(
            email='user2@example.com',
            display_name='User Two',
            active=True,
            role='user'
        )
        pending = AdminPanelUser(
            email='pending@example.com',
            display_name='Pending User',
            active=False,
            role='user'
        )

        db.session.add_all([admin, user1, user2, pending])
        db.session.commit()

        app.test_users = {
            'admin': admin.id,
            'user1': user1.id,
            'user2': user2.id,
            'pending': pending.id,
        }

    # Yield OUTSIDE app_context so each test client gets proper CSRF isolation
    yield app

    # Cleanup
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def admin_client(admin_app):
    """Create a CSRF-aware test client logged in as admin."""
    client = make_csrf_client(admin_app)
    client.post(f'/test-login/{admin_app.test_users["admin"]}')
    return client


@pytest.fixture
def regular_client(admin_app):
    """Create a CSRF-aware test client logged in as regular user."""
    client = make_csrf_client(admin_app)
    client.post(f'/test-login/{admin_app.test_users["user1"]}')
    return client


class TestAdminAccess:
    """Test admin panel access control."""

    def test_admin_routes_require_admin_role(self, regular_client):
        """Regular users cannot access admin routes."""
        response = regular_client.get('/api/admin/users')
        assert response.status_code == 403

    def test_admin_can_access_admin_routes(self, admin_client):
        """Admin users can access admin routes."""
        response = admin_client.get('/api/admin/users')
        assert response.status_code == 200


class TestUserListing:
    """Test user listing functionality."""

    def test_list_all_users(self, admin_client):
        """Admin can list all users."""
        response = admin_client.get('/api/admin/users')
        data = response.get_json()

        assert response.status_code == 200
        assert len(data['users']) == 4  # admin + 2 users + pending

    def test_user_list_contains_required_fields(self, admin_client):
        """User list includes required fields."""
        response = admin_client.get('/api/admin/users')
        data = response.get_json()

        user = data['users'][0]
        assert 'id' in user
        assert 'email' in user
        assert 'active' in user
        assert 'role' in user


class TestUserDetail:
    """Test user detail view."""

    def test_get_user_detail(self, admin_client, admin_app):
        """Admin can view user details."""
        user_id = admin_app.test_users['user1']
        response = admin_client.get(f'/api/admin/users/{user_id}')
        data = response.get_json()

        assert response.status_code == 200
        assert data['email'] == 'user1@example.com'
        assert data['display_name'] == 'User One'

    def test_get_nonexistent_user(self, admin_client):
        """Getting nonexistent user returns 404."""
        response = admin_client.get('/api/admin/users/fake-id')
        assert response.status_code == 404


class TestUserStatusManagement:
    """Test user activation/suspension."""

    def test_approve_pending_user(self, admin_client, admin_app):
        """Admin can approve a pending user."""
        pending_id = admin_app.test_users['pending']

        # Verify initially inactive
        response = admin_client.get(f'/api/admin/users/{pending_id}')
        assert response.get_json()['active'] is False

        # Toggle status (approve)
        toggle_response = admin_client.post(f'/api/admin/users/{pending_id}/toggle-status')
        data = toggle_response.get_json()

        assert toggle_response.status_code == 200
        assert data['active'] is True

    def test_suspend_active_user(self, admin_client, admin_app):
        """Admin can suspend an active user."""
        user_id = admin_app.test_users['user1']

        # Verify initially active
        response = admin_client.get(f'/api/admin/users/{user_id}')
        assert response.get_json()['active'] is True

        # Toggle status (suspend)
        toggle_response = admin_client.post(f'/api/admin/users/{user_id}/toggle-status')
        data = toggle_response.get_json()

        assert toggle_response.status_code == 200
        assert data['active'] is False

    def test_toggle_nonexistent_user(self, admin_client):
        """Toggling nonexistent user returns 404."""
        response = admin_client.post('/api/admin/users/fake-id/toggle-status')
        assert response.status_code == 404


class TestUserRoleManagement:
    """Test role assignment."""

    def test_promote_user_to_editor(self, admin_client, admin_app):
        """Admin can promote user to editor."""
        user_id = admin_app.test_users['user1']

        response = admin_client.post(
            f'/api/admin/users/{user_id}/update-role',
            json={'role': 'editor'}
        )
        data = response.get_json()

        assert response.status_code == 200
        assert data['role'] == 'editor'

    def test_promote_user_to_admin(self, admin_client, admin_app):
        """Admin can promote user to admin."""
        user_id = admin_app.test_users['user2']

        response = admin_client.post(
            f'/api/admin/users/{user_id}/update-role',
            json={'role': 'admin'}
        )
        data = response.get_json()

        assert response.status_code == 200
        assert data['role'] == 'admin'

    def test_demote_user(self, admin_client, admin_app):
        """Admin can demote user back to user role."""
        user_id = admin_app.test_users['user1']

        # First promote to editor
        admin_client.post(
            f'/api/admin/users/{user_id}/update-role',
            json={'role': 'editor'}
        )

        # Then demote back
        response = admin_client.post(
            f'/api/admin/users/{user_id}/update-role',
            json={'role': 'user'}
        )
        data = response.get_json()

        assert response.status_code == 200
        assert data['role'] == 'user'

    def test_invalid_role_rejected(self, admin_client, admin_app):
        """Invalid role values are rejected."""
        user_id = admin_app.test_users['user1']

        response = admin_client.post(
            f'/api/admin/users/{user_id}/update-role',
            json={'role': 'superadmin'}
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data['error']['code'] == 'VALIDATION_ERROR'


class TestAdminStats:
    """Test admin statistics."""

    def test_get_user_stats(self, admin_client):
        """Admin can view user statistics."""
        response = admin_client.get('/api/admin/stats')
        data = response.get_json()

        assert response.status_code == 200
        assert data['total_users'] == 4
        assert data['active_users'] == 3  # admin + user1 + user2
        assert data['pending_users'] == 1
        assert data['admin_count'] == 1


class TestUserSearch:
    """Test user search functionality."""

    def test_search_by_email(self, admin_client):
        """Admin can search users by email."""
        response = admin_client.get('/api/admin/users/search?q=user1')
        data = response.get_json()

        assert response.status_code == 200
        assert len(data['users']) == 1
        assert data['users'][0]['email'] == 'user1@example.com'

    def test_search_multiple_results(self, admin_client):
        """Search can return multiple results."""
        response = admin_client.get('/api/admin/users/search?q=user')
        data = response.get_json()

        assert response.status_code == 200
        # Should find user1 and user2 (not admin or pending)
        assert len(data['users']) >= 2

    def test_search_no_results(self, admin_client):
        """Search with no matches returns empty list."""
        response = admin_client.get('/api/admin/users/search?q=nonexistent')
        data = response.get_json()

        assert response.status_code == 200
        assert len(data['users']) == 0


class TestFullAdminWorkflow:
    """Test complete admin workflow scenarios."""

    def test_onboard_new_user(self, admin_client, admin_app):
        """Test full user onboarding workflow."""
        pending_id = admin_app.test_users['pending']

        # 1. View pending user
        user_response = admin_client.get(f'/api/admin/users/{pending_id}')
        assert user_response.get_json()['active'] is False

        # 2. Check stats show pending
        stats = admin_client.get('/api/admin/stats').get_json()
        assert stats['pending_users'] >= 1

        # 3. Approve user
        approve_response = admin_client.post(
            f'/api/admin/users/{pending_id}/toggle-status'
        )
        assert approve_response.get_json()['active'] is True

        # 4. Stats updated
        stats_after = admin_client.get('/api/admin/stats').get_json()
        assert stats_after['active_users'] > stats['active_users']

    def test_promote_and_demote_user(self, admin_client, admin_app):
        """Test role promotion and demotion workflow."""
        user_id = admin_app.test_users['user1']

        # 1. User starts as regular user
        initial = admin_client.get(f'/api/admin/users/{user_id}').get_json()
        assert initial['role'] == 'user'

        # 2. Promote to editor
        admin_client.post(
            f'/api/admin/users/{user_id}/update-role',
            json={'role': 'editor'}
        )
        editor = admin_client.get(f'/api/admin/users/{user_id}').get_json()
        assert editor['role'] == 'editor'

        # 3. Promote to admin
        admin_client.post(
            f'/api/admin/users/{user_id}/update-role',
            json={'role': 'admin'}
        )
        admin = admin_client.get(f'/api/admin/users/{user_id}').get_json()
        assert admin['role'] == 'admin'

        # 4. Demote back to user
        admin_client.post(
            f'/api/admin/users/{user_id}/update-role',
            json={'role': 'user'}
        )
        final = admin_client.get(f'/api/admin/users/{user_id}').get_json()
        assert final['role'] == 'user'

    def test_suspend_and_reinstate_user(self, admin_client, admin_app):
        """Test user suspension and reinstatement workflow."""
        user_id = admin_app.test_users['user2']

        # 1. User is active
        initial = admin_client.get(f'/api/admin/users/{user_id}').get_json()
        assert initial['active'] is True

        # 2. Suspend user
        admin_client.post(f'/api/admin/users/{user_id}/toggle-status')
        suspended = admin_client.get(f'/api/admin/users/{user_id}').get_json()
        assert suspended['active'] is False

        # 3. Reinstate user
        admin_client.post(f'/api/admin/users/{user_id}/toggle-status')
        reinstated = admin_client.get(f'/api/admin/users/{user_id}').get_json()
        assert reinstated['active'] is True
