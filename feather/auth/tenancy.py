"""
Tenant Resolution and Enforcement
=================================

Multi-tenancy enforcement for Feather applications.

Every user belongs to exactly one tenant. Tenant isolation is enforced
at the service layer - admins do NOT bypass tenant boundaries.

Functions
---------
- **get_current_tenant_id()**: Get tenant ID from authenticated user
- **tenant_required**: Decorator ensuring request has valid tenant context
- **require_same_tenant(resource_tenant_id)**: Guard for cross-tenant access

Usage
-----
Get current tenant in a route or service::

    from feather.auth import get_current_tenant_id

    @api.get('/resources')
    @auth_required
    def list_resources():
        tenant_id = get_current_tenant_id()
        return Resource.for_tenant(tenant_id).all()

Enforce tenant isolation in services::

    from feather.auth.tenancy import require_same_tenant

    def get_resource_or_404(resource_id):
        resource = Resource.query.get(resource_id)
        if not resource:
            raise NotFoundError("Resource not found")
        require_same_tenant(resource.tenant_id)
        return resource

Note:
    Platform admins (is_platform_admin=True) still have a tenant_id and
    are subject to tenant scoping by default. Cross-tenant operations
    require explicit platform admin routes with @platform_admin_required.
"""

from functools import wraps
from typing import Callable

from flask import current_app, g
from flask_login import current_user

from feather.exceptions import (
    AuthenticationError,
    AuthorizationError,
    AccountPendingError,
    AccountSuspendedError,
)


def get_current_tenant_id() -> str:
    """Get the current user's tenant ID.

    Single source of truth for request tenant context. The tenant is
    always derived from the authenticated user's tenant_id.

    Returns:
        The current user's tenant_id.

    Raises:
        AuthenticationError: If user is not authenticated (no session).
        AuthorizationError: If user is suspended or has no tenant_id.

    Example::

        from feather.auth import get_current_tenant_id

        tenant_id = get_current_tenant_id()
        resources = Resource.for_tenant(tenant_id).all()
    """
    # Check if there's a real user in session (vs anonymous)
    # is_anonymous is False for real users, True for AnonymousUserMixin
    if current_user.is_anonymous:
        raise AuthenticationError("Authentication required")

    # User is in session - now check if they're active
    # is_active should be a property, not a method
    is_active = getattr(current_user, "is_active", True)
    if callable(is_active):
        is_active = is_active()
    if not is_active:
        # Check if user was ever approved to distinguish pending vs suspended
        # approved_at is set when admin first activates the account
        approved_at = getattr(current_user, "approved_at", None)
        if approved_at is None:
            raise AccountPendingError("Your account is pending approval")
        else:
            raise AccountSuspendedError("Your account has been suspended")

    # Platform admins can operate without a tenant
    if getattr(current_user, "is_platform_admin", False):
        return getattr(current_user, "tenant_id", None)  # May be None

    # In single-tenant mode, tenant_id is optional
    multi_tenant = current_app.config.get("FEATHER_MULTI_TENANT", False)
    if not multi_tenant:
        return getattr(current_user, "tenant_id", None)

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise AuthorizationError("Tenant required")

    return tenant_id


def tenant_required(fn: Callable) -> Callable:
    """Decorator ensuring request has an authenticated user with tenant_id.

    Stores tenant_id on flask.g for convenience in the request context.

    Args:
        fn: The route function to protect.

    Returns:
        Decorated function that enforces tenant context.

    Raises:
        AuthenticationError: If user is not authenticated.
        AuthorizationError: If user has no tenant_id.

    Example::

        from feather.auth import tenant_required

        @api.get('/my-tenant')
        @tenant_required
        def get_tenant_info():
            # g.tenant_id is available here
            return {'tenant_id': g.tenant_id}
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        tenant_id = get_current_tenant_id()
        g.tenant_id = tenant_id
        return fn(*args, **kwargs)

    return wrapper


def require_same_tenant(resource_tenant_id: str) -> None:
    """Enforce that a resource belongs to the current user's tenant.

    Hard boundary: tenant isolation is NEVER bypassed, not even by admins.
    Cross-tenant access requires platform admin routes with explicit handling.

    Args:
        resource_tenant_id: The tenant_id of the resource being accessed.

    Raises:
        AuthorizationError: If resource belongs to a different tenant.

    Example::

        def get_resource_or_404(resource_id):
            resource = Resource.query.get(resource_id)
            if not resource:
                raise NotFoundError("Resource not found")
            require_same_tenant(resource.tenant_id)
            return resource
    """
    tenant_id = get_current_tenant_id()
    if tenant_id != resource_tenant_id:
        raise AuthorizationError("Cross-tenant access denied")
