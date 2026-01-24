"""
Authorization Decorators
========================

Role-based and permission-based access control decorators for protecting routes.

Feather uses a two-axis authority model:
1. **Tenant role** (`role`): Authority within a tenant (admin, editor, user)
2. **Platform authority** (`is_platform_admin`): Cross-tenant operator power

Available Decorators
-------------------
- **auth_required**: Requires authenticated user with valid tenant
- **admin_required**: Requires user.role == "admin" (tenant admin)
- **role_required(roles)**: Requires user to have one of the specified roles
- **permission_required(permission)**: Requires CRUD permission (resources.*)
- **platform_admin_required**: Requires is_platform_admin=True (cross-tenant)
- **rate_limit(limit, period)**: Rate limit requests per IP or user

Usage
-----
Protect tenant admin routes::

    from feather import api
    from feather.auth import admin_required

    @api.delete('/admin/users/<user_id>')
    @admin_required
    def delete_user(user_id):
        # Only tenant admins can access this
        pass

Protect routes by role (with inheritance)::

    from feather import api
    from feather.auth import role_required

    @api.post('/resources')
    @role_required('editor')
    def create_resource():
        # Editors and admins can create (admin inherits editor)
        pass

Protect routes by permission::

    from feather import api
    from feather.auth import permission_required

    @api.post('/resources')
    @permission_required('resources.create')
    def create_resource():
        pass

Platform admin routes (cross-tenant)::

    from feather import api
    from feather.auth import platform_admin_required

    @api.post('/platform/tenants')
    @platform_admin_required
    def create_tenant():
        # Only platform admins can manage tenants
        pass

Note:
    Role inheritance means admin includes editor, moderator, and user.
    Tenant admins do NOT bypass tenant isolation - they can only access
    their own tenant's data.
"""

import time
import threading
from collections import defaultdict
from functools import wraps
from typing import Callable, List, Union, Optional, Set

from flask import current_app, g, render_template, request
from flask_login import current_user

from feather.exceptions import AuthenticationError, AuthorizationError, RateLimitError
from feather.auth.tenancy import tenant_required, get_current_tenant_id
from feather.auth.roles import effective_roles
from feather.auth.permissions_logic import effective_permissions


def auth_required(f: Callable) -> Callable:
    """Require authenticated user with valid tenant context.

    Checks that:
    1. User is authenticated (has session)
    2. User account is active (not suspended)
    3. User has a valid tenant_id (in multi-tenant mode)

    For page routes (non-API), unauthenticated users are redirected to login.
    For API routes, returns JSON 401/403 errors.

    Args:
        f: The route function to protect.

    Returns:
        Decorated function that enforces authentication and tenant context.

    Raises:
        AuthenticationError: If user is not logged in (401).
        AuthorizationError: If user is suspended or has no tenant (403).

    Example::

        from feather import api
        from feather.auth import auth_required

        @api.get('/my-profile')
        @auth_required
        def get_profile():
            return {'user': current_user.to_dict()}
    """
    @wraps(f)
    @tenant_required  # Handles auth check, is_active check, and tenant check
    def wrapper(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper


def login_only(f: Callable) -> Callable:
    """Require only that the user is authenticated (has a session).

    Unlike @auth_required, this decorator does NOT check:
    - Whether the user account is active (not suspended)
    - Whether the user has a valid tenant_id (multi-tenant mode)

    Use this for pages that need to be accessible to users who are:
    - Pending approval (active=False)
    - Without a tenant assignment (tenant_id=None)

    Common use cases:
    - "Pending approval" status page
    - Account setup wizard for new users
    - Pages where users can select/request a tenant

    Args:
        f: The route function to protect.

    Returns:
        Decorated function that only checks authentication.

    Raises:
        AuthenticationError: If user is not logged in (401).

    Example::

        from feather import page
        from feather.auth import login_only

        @page.get('/pending-approval')
        @login_only
        def pending_approval():
            # User is authenticated but may be suspended or without tenant
            return render_template('pages/pending_approval.html')

        @page.get('/select-organization')
        @login_only
        def select_organization():
            # User can select which organization to join
            return render_template('pages/select_org.html')
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            # Check if this is an API route or page route
            if request.path.startswith('/api/'):
                raise AuthenticationError("Login required")
            else:
                # Redirect to login for page routes
                from flask import redirect
                login_url = current_app.config.get('LOGIN_URL', '/auth/google/login')
                return redirect(f"{login_url}?next={request.path}")

        return f(*args, **kwargs)

    return wrapper


def role_required(roles: Union[str, List[str], Set[str]]) -> Callable:
    """Require the current user to have one of the specified roles.

    Uses role inheritance: admin inherits editor, moderator, and user roles.
    This means a user with role="admin" passes @role_required('editor').

    Args:
        roles: Single role string, list, or set of acceptable role strings.

    Returns:
        Decorator function.

    Raises:
        AuthenticationError: If user is not logged in (401).
        AuthorizationError: If user doesn't have required role (403).

    Example::

        from feather import api
        from feather.auth import role_required

        @api.post('/resources')
        @role_required('editor')
        def create_resource():
            # Editors and admins can access (admin inherits editor)
            pass

        @api.get('/moderator/queue')
        @role_required(['moderator', 'admin'])
        def mod_queue():
            pass

    Note:
        Role inheritance is automatic. Admins can access all role-protected
        routes because they inherit all roles.
    """
    # Normalize to set
    if isinstance(roles, str):
        required_roles = {roles}
    else:
        required_roles = set(roles)

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        @auth_required
        def wrapper(*args, **kwargs):
            # Platform admins bypass role checks - they have access to everything
            if getattr(current_user, "is_platform_admin", False):
                return f(*args, **kwargs)

            # Get user's effective roles (includes inherited roles)
            user_role = getattr(current_user, "role", "user")
            user_roles = effective_roles(user_role)

            # Check if user has any of the required roles
            if user_roles.isdisjoint(required_roles):
                raise AuthorizationError(f"Required role: {', '.join(required_roles)}")

            return f(*args, **kwargs)

        return wrapper

    return decorator


def admin_required(f: Callable) -> Callable:
    """Require the current user to be a tenant admin.

    Equivalent to @role_required('admin'). Checks that the user has
    role="admin" within their tenant.

    Note:
        This is a tenant-scoped admin check. Tenant admins can only access
        their own tenant's data. For cross-tenant operations, use
        @platform_admin_required instead.

    Args:
        f: The route function to protect.

    Returns:
        Decorated function that checks admin role.

    Raises:
        AuthenticationError: If user is not logged in (401).
        AuthorizationError: If user is not an admin (403).

    Example::

        from feather import api
        from feather.auth import admin_required

        @api.delete('/admin/users/<user_id>')
        @admin_required
        def delete_user(user_id):
            # Only tenant admins can delete users
            pass
    """
    return role_required("admin")(f)


def permission_required(permission: str) -> Callable:
    """Require the current user to have a specific CRUD permission.

    Permissions use domain-agnostic CRUD language:
    - resources.create
    - resources.read
    - resources.update
    - resources.delete
    - resources.manage

    Permission inheritance is based on role:
    - admin: "*" (all permissions)
    - editor: create, update
    - moderator: manage
    - user: read

    Args:
        permission: Permission string (e.g., 'resources.create').

    Returns:
        Decorator function.

    Raises:
        AuthenticationError: If user is not logged in (401).
        AuthorizationError: If user lacks the permission (403).

    Example::

        from feather import api
        from feather.auth import permission_required

        @api.post('/resources')
        @permission_required('resources.create')
        def create_resource():
            # Editors and admins can create
            pass

        @api.delete('/resources/<id>')
        @permission_required('resources.delete')
        def delete_resource(id):
            # Only admins can delete (they have "*")
            pass
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        @auth_required
        def wrapper(*args, **kwargs):
            user_role = getattr(current_user, "role", "user")
            perms = effective_permissions(user_role)

            # Check for wildcard or specific permission
            if "*" not in perms and permission not in perms:
                raise AuthorizationError(f"Missing permission: {permission}")

            return f(*args, **kwargs)

        return wrapper

    return decorator


def platform_admin_required(f: Callable) -> Callable:
    """Require the current user to be a platform admin.

    Platform admins have cross-tenant authority and can:
    - Create and manage tenants
    - View data across tenants (when explicitly coded)
    - Perform platform-level operations

    Note:
        Platform admin is orthogonal to tenant role. A platform admin
        still has a tenant_id and is subject to normal tenant scoping
        unless explicitly bypassed in platform admin routes.

    Args:
        f: The route function to protect.

    Returns:
        Decorated function that checks platform admin status.

    Raises:
        AuthenticationError: If user is not logged in (401).
        AuthorizationError: If user is not a platform admin (403).

    Example::

        from feather import api
        from feather.auth import platform_admin_required

        @api.post('/platform/tenants')
        @platform_admin_required
        def create_tenant():
            # Only platform admins can create tenants
            pass

        @api.get('/platform/stats')
        @platform_admin_required
        def platform_stats():
            # Cross-tenant statistics
            pass
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            raise AuthenticationError("Login required")

        if not getattr(current_user, "is_platform_admin", False):
            raise AuthorizationError("Platform admin required")

        return f(*args, **kwargs)

    return wrapper


# =============================================================================
# Rate Limiting
# =============================================================================


class _RateLimiter:
    """Simple in-memory rate limiter using sliding window.

    Thread-safe implementation for single-process deployments.
    For multi-process deployments (Gunicorn with multiple workers),
    use Redis-based rate limiting instead.
    """

    def __init__(self):
        self._requests: dict = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str, limit: int, period: int) -> tuple[bool, int]:
        """Check if a request is allowed under the rate limit.

        Args:
            key: Unique identifier (IP, user ID, etc.)
            limit: Maximum requests allowed in the period.
            period: Time window in seconds.

        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        now = time.time()
        window_start = now - period

        with self._lock:
            # Remove expired timestamps
            self._requests[key] = [
                ts for ts in self._requests[key] if ts > window_start
            ]

            # Check limit
            current_count = len(self._requests[key])
            if current_count >= limit:
                return False, 0

            # Record this request
            self._requests[key].append(now)
            return True, limit - current_count - 1

    def cleanup(self, max_age: int = 3600) -> None:
        """Remove stale entries older than max_age seconds."""
        cutoff = time.time() - max_age
        with self._lock:
            keys_to_remove = []
            for key, timestamps in self._requests.items():
                if not timestamps or max(timestamps) < cutoff:
                    keys_to_remove.append(key)
            for key in keys_to_remove:
                del self._requests[key]


# Global rate limiter instance
_rate_limiter = _RateLimiter()


def rate_limit(
    limit: int,
    period: int = 60,
    key: str = "ip",
    message: Optional[str] = None,
) -> Callable:
    """Rate limit requests by IP address or user.

    Uses a sliding window algorithm. Thread-safe for single-process deployments.
    For multi-process (e.g., Gunicorn workers), consider Redis-based rate limiting.

    Args:
        limit: Maximum number of requests allowed in the period.
        period: Time window in seconds (default: 60 seconds).
        key: What to rate limit by:
            - 'ip': Rate limit by client IP address (default)
            - 'user': Rate limit by authenticated user ID
            - 'ip+user': Rate limit by both (stricter)
        message: Custom error message when rate limited.

    Returns:
        Decorator function.

    Raises:
        RateLimitError: When rate limit is exceeded (429).

    Example::

        from feather import api
        from feather.auth import rate_limit

        # 5 login attempts per minute per IP
        @api.post('/login')
        @rate_limit(5, 60)
        def login():
            pass

        # 100 API calls per minute per user
        @api.post('/api/search')
        @rate_limit(100, 60, key='user')
        def search():
            pass

        # Very strict: 10 per hour by IP and user
        @api.post('/api/expensive-operation')
        @rate_limit(10, 3600, key='ip+user')
        def expensive():
            pass

        # Custom error message
        @api.post('/api/comments')
        @rate_limit(10, 3600, message='You can only post 10 comments per hour')
        def create_comment():
            pass

    Note:
        - In development with debug mode, rate limiting still applies
        - Rate limits reset after the period passes
        - For production with multiple workers, use Redis-based limiting
    """

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Build rate limit key based on configuration
            parts = []

            if "ip" in key:
                # Get real IP (handle proxies)
                client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                if not client_ip:
                    client_ip = request.headers.get("X-Real-IP", request.remote_addr)
                parts.append(f"ip:{client_ip}")

            if "user" in key:
                if current_user.is_authenticated:
                    parts.append(f"user:{current_user.id}")
                else:
                    # Fall back to IP for unauthenticated users
                    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                    if not client_ip:
                        client_ip = request.headers.get("X-Real-IP", request.remote_addr)
                    parts.append(f"ip:{client_ip}")

            # Add endpoint to make limits per-endpoint
            rate_key = f"{f.__name__}:{':'.join(parts)}"

            # Check rate limit
            allowed, remaining = _rate_limiter.is_allowed(rate_key, limit, period)

            if not allowed:
                error_message = message or f"Rate limit exceeded. Try again in {period} seconds."
                raise RateLimitError(error_message)

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def get_rate_limiter() -> _RateLimiter:
    """Get the global rate limiter instance.

    Useful for testing or custom rate limit logic.

    Returns:
        The global _RateLimiter instance.

    Example::

        from feather.auth.decorators import get_rate_limiter

        # In tests, clear rate limits between tests
        def teardown_function():
            get_rate_limiter()._requests.clear()
    """
    return _rate_limiter
