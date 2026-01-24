"""
Authentication Module
=====================

Provides authentication and authorization for Feather applications.

Feather uses a **two-axis authority model**:
1. **Tenant role** (`role`): Authority within a tenant (admin, editor, user)
2. **Platform authority** (`is_platform_admin`): Cross-tenant operator power

This module includes:
- Flask-Login integration for session management
- Google OAuth 2.0 support
- Role-based and permission-based access control
- Multi-tenant isolation utilities
- Domain validation for tenant assignment

Quick Start
-----------
Enable authentication in your app::

    # app.py
    from feather import Feather

    app = Feather(__name__)
    # Auth is automatically initialized if User model exists
    # and GOOGLE_CLIENT_ID is configured

Using Decorators
----------------
Protect routes with role or permission requirements::

    from feather import api, auth_required
    from feather.auth import admin_required, role_required, permission_required

    @api.get('/admin/users')
    @admin_required
    def list_users():
        return {'users': [...]}

    @api.post('/resources')
    @permission_required('resources.create')
    def create_resource():
        return {'resource': {...}}

    @api.post('/platform/tenants')
    @platform_admin_required
    def create_tenant():
        # Only platform admins can manage tenants
        pass

Tenant Isolation
----------------
Use tenant utilities in your services::

    from feather.auth import get_current_tenant_id
    from models import Resource

    def list_resources():
        tenant_id = get_current_tenant_id()
        return Resource.for_tenant(tenant_id).all()

Google OAuth
------------
Configure in .env::

    GOOGLE_CLIENT_ID=your-client-id
    GOOGLE_CLIENT_SECRET=your-client-secret

Then users can log in at /auth/google/login
"""

from feather.auth.setup import init_auth, login_manager, set_user_loader

# Decorators
from feather.auth.decorators import (
    admin_required,
    auth_required,
    login_only,
    permission_required,
    platform_admin_required,
    rate_limit,
    role_required,
)

# Tenancy
from feather.auth.tenancy import (
    get_current_tenant_id,
    require_same_tenant,
    tenant_required,
)

# Roles and permissions
from feather.auth.roles import effective_roles, ROLE_INHERITS
from feather.auth.permissions import ROLE_PERMISSIONS
from feather.auth.permissions_logic import effective_permissions

# Domain validation
from feather.auth.domains import (
    extract_domain,
    get_tenant_slug_from_domain,
    is_public_email_domain,
    PUBLIC_EMAIL_DOMAINS,
)

__all__ = [
    # Setup
    "init_auth",
    "login_manager",
    "set_user_loader",
    # Decorators
    "admin_required",
    "auth_required",
    "login_only",
    "permission_required",
    "platform_admin_required",
    "rate_limit",
    "role_required",
    # Tenancy
    "get_current_tenant_id",
    "require_same_tenant",
    "tenant_required",
    # Roles and permissions
    "effective_roles",
    "effective_permissions",
    "ROLE_INHERITS",
    "ROLE_PERMISSIONS",
    # Domain validation
    "extract_domain",
    "get_tenant_slug_from_domain",
    "is_public_email_domain",
    "PUBLIC_EMAIL_DOMAINS",
]
