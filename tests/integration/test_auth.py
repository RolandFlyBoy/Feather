"""Integration tests for authentication and authorization.

Tests auth decorators, role checking, and tenant isolation.
"""

import pytest
from unittest.mock import Mock, patch

pytestmark = pytest.mark.integration


class TestAuthRequiredDecorator:
    """Test @auth_required decorator."""

    def test_decorator_can_be_applied(self, test_app):
        """@auth_required can be applied to routes."""
        from feather import auth_required

        @test_app.route('/test/protected')
        @auth_required
        def protected():
            return {'data': 'secret'}

        # Route should be registered
        rules = [rule.rule for rule in test_app.url_map.iter_rules()]
        assert '/test/protected' in rules

    def test_route_is_registered(self, test_app):
        """@auth_required allows route registration."""
        from feather import auth_required

        @test_app.route('/test/protected2')
        @auth_required
        def protected2():
            return {'data': 'secret'}

        # Route should be registered with the decorator applied
        rules = [rule.rule for rule in test_app.url_map.iter_rules()]
        assert '/test/protected2' in rules


class TestAdminRequiredDecorator:
    """Test @admin_required decorator."""

    def test_decorator_can_be_applied(self, test_app):
        """@admin_required can be applied to routes."""
        from feather import admin_required

        @test_app.route('/test/admin-only')
        @admin_required
        def admin_only():
            return {'data': 'admin secret'}

        # Route should be registered
        rules = [rule.rule for rule in test_app.url_map.iter_rules()]
        assert '/test/admin-only' in rules

    def test_route_is_registered(self, test_app):
        """@admin_required allows route registration."""
        from feather import admin_required

        @test_app.route('/test/admin-only2')
        @admin_required
        def admin_only2():
            return {'data': 'admin secret'}

        # Route should be registered with the decorator applied
        rules = [rule.rule for rule in test_app.url_map.iter_rules()]
        assert '/test/admin-only2' in rules


class TestRoleRequiredDecorator:
    """Test @role_required decorator."""

    def test_decorator_can_be_applied(self, test_app):
        """@role_required can be applied to routes."""
        from feather import role_required

        @test_app.route('/test/editor')
        @role_required('editor')
        def editor_route():
            return {'data': 'editor content'}

        # Route should be registered
        rules = [rule.rule for rule in test_app.url_map.iter_rules()]
        assert '/test/editor' in rules

    def test_accepts_list_of_roles(self, test_app):
        """@role_required accepts list of roles."""
        from feather import role_required

        @test_app.route('/test/multi-role')
        @role_required(['editor', 'admin'])
        def multi_role():
            return {'data': 'content'}

        rules = [rule.rule for rule in test_app.url_map.iter_rules()]
        assert '/test/multi-role' in rules


class TestPermissionRequiredDecorator:
    """Test @permission_required decorator."""

    def test_decorator_can_be_applied(self, test_app):
        """@permission_required can be applied to routes."""
        from feather import permission_required

        @test_app.route('/test/permission')
        @permission_required('users.create')
        def create_user():
            return {'created': True}

        rules = [rule.rule for rule in test_app.url_map.iter_rules()]
        assert '/test/permission' in rules


class TestPlatformAdminDecorator:
    """Test @platform_admin_required decorator."""

    def test_decorator_can_be_applied(self, test_app):
        """@platform_admin_required can be applied to routes."""
        from feather import platform_admin_required

        @test_app.route('/test/platform')
        @platform_admin_required
        def platform_route():
            return {'data': 'platform admin'}

        rules = [rule.rule for rule in test_app.url_map.iter_rules()]
        assert '/test/platform' in rules


class TestTenantIsolation:
    """Test tenant isolation utilities."""

    def test_get_current_tenant_id_exists(self):
        """get_current_tenant_id function exists."""
        from feather import get_current_tenant_id
        assert callable(get_current_tenant_id)

    def test_tenant_required_decorator_exists(self):
        """@tenant_required decorator exists."""
        from feather import tenant_required
        assert callable(tenant_required)


class TestRateLimitDecorator:
    """Test @rate_limit decorator."""

    def test_decorator_can_be_applied(self, test_app):
        """@rate_limit can be applied to routes."""
        from feather import rate_limit

        @test_app.route('/test/rate-limited')
        @rate_limit(10, 60)
        def rate_limited():
            return {'data': 'limited'}

        rules = [rule.rule for rule in test_app.url_map.iter_rules()]
        assert '/test/rate-limited' in rules

    def test_accepts_key_parameter(self, test_app):
        """@rate_limit accepts key parameter."""
        from feather import rate_limit

        @test_app.route('/test/user-limited')
        @rate_limit(10, 60, key='user')
        def user_limited():
            return {'data': 'limited'}

        rules = [rule.rule for rule in test_app.url_map.iter_rules()]
        assert '/test/user-limited' in rules

    def test_accepts_message_parameter(self, test_app):
        """@rate_limit accepts message parameter."""
        from feather import rate_limit

        @test_app.route('/test/custom-message')
        @rate_limit(10, 60, message='Custom rate limit message')
        def custom_message():
            return {'data': 'limited'}

        rules = [rule.rule for rule in test_app.url_map.iter_rules()]
        assert '/test/custom-message' in rules


class TestCsrfExemptDecorator:
    """Test @csrf_exempt decorator."""

    def test_decorator_can_be_applied(self, test_app):
        """@csrf_exempt can be applied to routes."""
        from feather import csrf_exempt

        @test_app.route('/test/no-csrf', methods=['POST'])
        @csrf_exempt
        def no_csrf():
            return {'data': 'no csrf check'}

        rules = [rule.rule for rule in test_app.url_map.iter_rules()]
        assert '/test/no-csrf' in rules


class TestCurrentUserAccess:
    """Test current_user access patterns."""

    def test_current_user_importable(self):
        """current_user can be imported from flask_login."""
        from flask_login import current_user
        assert current_user is not None

    def test_current_user_proxy_exists(self):
        """current_user is a LocalProxy."""
        from flask_login import current_user
        from werkzeug.local import LocalProxy
        assert isinstance(current_user, LocalProxy)
