"""Integration tests for multi-tenancy isolation.

Tests tenant data isolation, access control, and tenant-scoped queries.
These are security-critical tests - tenant data must NEVER leak across boundaries.
"""

import pytest
from flask_login import login_user, LoginManager, UserMixin
from feather import Feather, auth_required
from feather.db import db, Model
from feather.db.mixins import UUIDMixin, TimestampMixin, TenantScopedMixin
from feather.auth.tenancy import get_current_tenant_id, require_same_tenant, tenant_required
from feather.exceptions import AuthenticationError, AuthorizationError
from tests.conftest import make_csrf_client

pytestmark = pytest.mark.integration


# =============================================================================
# Test Models (Module Level to avoid SQLAlchemy warnings)
# =============================================================================

class TenantTestUser(UUIDMixin, TimestampMixin, UserMixin, Model):
    """Test user model with tenant."""
    __tablename__ = 'tenant_test_users'
    __table_args__ = {'extend_existing': True}

    email = db.Column(db.String(255), unique=True, nullable=False)
    tenant_id = db.Column(db.String(36), nullable=True)
    is_platform_admin = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)

    def is_active(self):
        return self.active


class TenantResource(UUIDMixin, TimestampMixin, TenantScopedMixin, Model):
    """Test resource model with tenant isolation."""
    __tablename__ = 'tenant_resources'
    __table_args__ = {'extend_existing': True}

    name = db.Column(db.String(100), nullable=False)
    secret_data = db.Column(db.String(255))


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def tenant_app():
    """Create a test app with multi-tenancy enabled."""
    app = Feather(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    # CSRF enabled to match production
    app.config['FEATHER_MULTI_TENANT'] = True

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(TenantTestUser, user_id)

    # Test login endpoint
    @app.route('/test-login/<user_id>', methods=['POST'])
    def test_login(user_id):
        user = db.session.get(TenantTestUser, user_id)
        if user:
            login_user(user)
            return {'logged_in': True}
        return {'logged_in': False}, 401

    # Route that uses get_current_tenant_id
    @app.route('/api/tenant-id')
    @auth_required
    def get_tenant():
        tenant_id = get_current_tenant_id()
        return {'tenant_id': tenant_id}

    # Route that uses tenant_required decorator
    @app.route('/api/with-tenant')
    @tenant_required
    def with_tenant():
        from flask import g
        return {'tenant_id': g.tenant_id}

    # Route that lists resources
    @app.route('/api/resources')
    @auth_required
    def list_resources():
        tenant_id = get_current_tenant_id()
        resources = TenantResource.for_tenant(tenant_id).all()
        return {'resources': [{'id': r.id, 'name': r.name} for r in resources]}

    # Setup: create tables and seed data
    with app.app_context():
        db.create_all()

        tenant_a = 'tenant-a-uuid'
        tenant_b = 'tenant-b-uuid'

        user_a = TenantTestUser(email='user_a@example.com', tenant_id=tenant_a)
        user_b = TenantTestUser(email='user_b@example.com', tenant_id=tenant_b)
        platform_admin = TenantTestUser(
            email='platform@example.com',
            tenant_id=tenant_a,
            is_platform_admin=True
        )
        user_no_tenant = TenantTestUser(email='orphan@example.com', tenant_id=None)

        db.session.add_all([user_a, user_b, platform_admin, user_no_tenant])
        db.session.commit()

        resource_a1 = TenantResource(name='Resource A1', tenant_id=tenant_a, secret_data='Secret A1')
        resource_a2 = TenantResource(name='Resource A2', tenant_id=tenant_a, secret_data='Secret A2')
        resource_b1 = TenantResource(name='Resource B1', tenant_id=tenant_b, secret_data='Secret B1')

        db.session.add_all([resource_a1, resource_a2, resource_b1])
        db.session.commit()

        app.test_data = {
            'tenant_a': tenant_a,
            'tenant_b': tenant_b,
            'user_a': user_a.id,
            'user_b': user_b.id,
            'platform_admin': platform_admin.id,
            'user_no_tenant': user_no_tenant.id,
            'resource_a1': resource_a1.id,
            'resource_a2': resource_a2.id,
            'resource_b1': resource_b1.id,
        }

    # Yield OUTSIDE app_context for proper CSRF isolation
    yield app

    # Cleanup
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def single_tenant_app():
    """Create a test app with single-tenant mode (multi-tenant disabled)."""
    app = Feather(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    # CSRF enabled to match production
    app.config['FEATHER_MULTI_TENANT'] = False

    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(TenantTestUser, user_id)

    @app.route('/test-login/<user_id>', methods=['POST'])
    def test_login(user_id):
        user = db.session.get(TenantTestUser, user_id)
        if user:
            login_user(user)
            return {'logged_in': True}
        return {'logged_in': False}, 401

    @app.route('/api/tenant-id')
    @auth_required
    def get_tenant():
        tenant_id = get_current_tenant_id()
        return {'tenant_id': tenant_id}

    # Setup: create tables and seed data
    with app.app_context():
        db.create_all()
        user_no_tenant = TenantTestUser(email='user@example.com', tenant_id=None)
        db.session.add(user_no_tenant)
        db.session.commit()
        app.test_data = {'user_no_tenant': user_no_tenant.id}

    # Yield OUTSIDE app_context for proper CSRF isolation
    yield app

    # Cleanup
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


# =============================================================================
# Test get_current_tenant_id()
# =============================================================================

class TestGetCurrentTenantId:
    """Tests for get_current_tenant_id function."""

    def test_returns_tenant_id_for_authenticated_user(self, tenant_app):
        """Authenticated user gets their tenant_id."""
        client = make_csrf_client(tenant_app)
        client.post(f'/test-login/{tenant_app.test_data["user_a"]}')

        response = client.get('/api/tenant-id')
        data = response.get_json()

        assert response.status_code == 200
        assert data['tenant_id'] == tenant_app.test_data['tenant_a']

    def test_raises_for_unauthenticated_user(self, tenant_app):
        """Unauthenticated user raises AuthenticationError."""
        client = tenant_app.test_client()

        response = client.get('/api/tenant-id')

        assert response.status_code == 401

    def test_raises_for_user_without_tenant_in_multi_tenant_mode(self, tenant_app):
        """User without tenant_id in multi-tenant mode raises AuthorizationError."""
        client = make_csrf_client(tenant_app)
        client.post(f'/test-login/{tenant_app.test_data["user_no_tenant"]}')

        response = client.get('/api/tenant-id')

        assert response.status_code == 403

    def test_platform_admin_can_have_no_tenant(self, tenant_app):
        """Platform admin can operate even with tenant context."""
        client = make_csrf_client(tenant_app)
        client.post(f'/test-login/{tenant_app.test_data["platform_admin"]}')

        response = client.get('/api/tenant-id')
        data = response.get_json()

        # Platform admin still has a tenant_id (their home tenant)
        assert response.status_code == 200
        assert data['tenant_id'] == tenant_app.test_data['tenant_a']

    def test_single_tenant_mode_allows_no_tenant(self, single_tenant_app):
        """Single-tenant mode allows users without tenant_id."""
        client = make_csrf_client(single_tenant_app)
        client.post(f'/test-login/{single_tenant_app.test_data["user_no_tenant"]}')

        response = client.get('/api/tenant-id')
        data = response.get_json()

        assert response.status_code == 200
        assert data['tenant_id'] is None


# =============================================================================
# Test tenant_required Decorator
# =============================================================================

class TestTenantRequiredDecorator:
    """Tests for @tenant_required decorator."""

    def test_sets_g_tenant_id(self, tenant_app):
        """Decorator sets g.tenant_id for convenience."""
        client = make_csrf_client(tenant_app)
        client.post(f'/test-login/{tenant_app.test_data["user_a"]}')

        response = client.get('/api/with-tenant')
        data = response.get_json()

        assert response.status_code == 200
        assert data['tenant_id'] == tenant_app.test_data['tenant_a']

    def test_blocks_unauthenticated(self, tenant_app):
        """Decorator blocks unauthenticated requests."""
        client = tenant_app.test_client()

        response = client.get('/api/with-tenant')

        assert response.status_code == 401


# =============================================================================
# Test require_same_tenant()
# =============================================================================

class TestRequireSameTenant:
    """Tests for require_same_tenant function."""

    def test_allows_same_tenant_access(self, tenant_app):
        """Same tenant can access resource."""
        with tenant_app.test_request_context():
            with tenant_app.app_context():
                user = db.session.get(TenantTestUser, tenant_app.test_data['user_a'])
                login_user(user)

                # Access resource from same tenant - should not raise
                require_same_tenant(tenant_app.test_data['tenant_a'])

    def test_blocks_cross_tenant_access(self, tenant_app):
        """Different tenant cannot access resource."""
        with tenant_app.test_request_context():
            with tenant_app.app_context():
                user = db.session.get(TenantTestUser, tenant_app.test_data['user_a'])
                login_user(user)

                # Access resource from different tenant - should raise
                with pytest.raises(AuthorizationError) as exc_info:
                    require_same_tenant(tenant_app.test_data['tenant_b'])

                assert 'Cross-tenant access denied' in str(exc_info.value)


# =============================================================================
# Test TenantScopedMixin
# =============================================================================

class TestTenantScopedMixin:
    """Tests for TenantScopedMixin model behavior."""

    def test_for_tenant_returns_only_tenant_resources(self, tenant_app):
        """for_tenant() filters to only that tenant's resources."""
        client = make_csrf_client(tenant_app)
        client.post(f'/test-login/{tenant_app.test_data["user_a"]}')

        response = client.get('/api/resources')
        data = response.get_json()

        # User A should only see tenant A resources
        assert response.status_code == 200
        assert len(data['resources']) == 2
        names = [r['name'] for r in data['resources']]
        assert 'Resource A1' in names
        assert 'Resource A2' in names
        assert 'Resource B1' not in names

    def test_for_tenant_excludes_other_tenants(self, tenant_app):
        """for_tenant() excludes resources from other tenants."""
        client = make_csrf_client(tenant_app)
        client.post(f'/test-login/{tenant_app.test_data["user_b"]}')

        response = client.get('/api/resources')
        data = response.get_json()

        # User B should only see tenant B resources
        assert response.status_code == 200
        assert len(data['resources']) == 1
        assert data['resources'][0]['name'] == 'Resource B1'

    def test_for_tenant_returns_empty_for_nonexistent_tenant(self, tenant_app):
        """for_tenant() returns empty query for tenant with no resources."""
        with tenant_app.app_context():
            resources = TenantResource.for_tenant('nonexistent-tenant').all()
            assert resources == []

    def test_for_tenant_can_chain_with_other_filters(self, tenant_app):
        """for_tenant() can be chained with additional filters."""
        with tenant_app.app_context():
            resources = TenantResource.for_tenant(
                tenant_app.test_data['tenant_a']
            ).filter_by(name='Resource A1').all()

            assert len(resources) == 1
            assert resources[0].name == 'Resource A1'


# =============================================================================
# Test Tenant Isolation End-to-End
# =============================================================================

class TestTenantIsolationE2E:
    """End-to-end tests for tenant data isolation."""

    def test_user_cannot_see_other_tenant_resources(self, tenant_app):
        """User from tenant A cannot see tenant B resources."""
        client = make_csrf_client(tenant_app)
        client.post(f'/test-login/{tenant_app.test_data["user_a"]}')

        response = client.get('/api/resources')
        data = response.get_json()

        # Should not contain any tenant B data
        for resource in data['resources']:
            assert 'B1' not in resource['name']

    def test_user_cannot_access_other_tenant_resource_directly(self, tenant_app):
        """User from tenant A cannot access tenant B resource by ID."""
        with tenant_app.test_request_context():
            with tenant_app.app_context():
                user = db.session.get(TenantTestUser, tenant_app.test_data['user_a'])
                login_user(user)

                # Try to access tenant B's resource
                resource_b = db.session.get(
                    TenantResource,
                    tenant_app.test_data['resource_b1']
                )

                # The resource exists
                assert resource_b is not None

                # But cross-tenant access should be denied
                with pytest.raises(AuthorizationError):
                    require_same_tenant(resource_b.tenant_id)

    def test_admin_does_not_bypass_tenant_isolation(self, tenant_app):
        """Admin users do NOT bypass tenant isolation."""
        # This is a critical security test
        # Even platform admins have a tenant_id and are subject to scoping
        client = make_csrf_client(tenant_app)
        client.post(f'/test-login/{tenant_app.test_data["platform_admin"]}')

        response = client.get('/api/resources')
        data = response.get_json()

        # Platform admin should still only see their tenant's resources
        # when using for_tenant(get_current_tenant_id())
        assert len(data['resources']) == 2  # Only tenant A resources

    def test_switching_users_changes_tenant_context(self, tenant_app):
        """Logging in as different user changes visible resources."""
        # Use separate clients to simulate different user sessions
        client_a = make_csrf_client(tenant_app)
        client_a.post(f'/test-login/{tenant_app.test_data["user_a"]}')
        response_a = client_a.get('/api/resources')
        data_a = response_a.get_json()

        # Should see tenant A resources
        assert len(data_a['resources']) == 2

        # Login as user B with fresh client
        client_b = make_csrf_client(tenant_app)
        client_b.post(f'/test-login/{tenant_app.test_data["user_b"]}')
        response_b = client_b.get('/api/resources')
        data_b = response_b.get_json()

        # Should see only tenant B resources
        assert len(data_b['resources']) == 1
        assert data_b['resources'][0]['name'] == 'Resource B1'
