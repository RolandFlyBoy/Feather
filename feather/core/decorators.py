"""
Route Decorators and Blueprints
===============================

This module provides the core routing primitives for Feather applications:

Blueprints
----------
- **api**: Blueprint for API routes, mounted at /api/*
- **page**: Blueprint for page routes, mounted at /*

Decorators
----------
- **@auth_required**: Require authentication for a route
- **@inject**: Inject service instances into route handlers

Quick Example
-------------
Create API routes::

    from feather import api, inject, auth_required
    from services import UserService

    @api.get('/users')
    @inject(UserService)
    def list_users(user_service):
        users = user_service.list_all()
        return {'users': [u.to_dict() for u in users]}

    @api.get('/me')
    @auth_required
    def get_current_user():
        return {'user': current_user.to_dict()}

    @api.post('/users')
    @inject(UserService)
    def create_user(user_service):
        data = request.get_json()
        user = user_service.create(**data)
        return {'user': user.to_dict()}, 201

Create page routes::

    from feather import page
    from flask import render_template

    @page.get('/')
    def home():
        return render_template('pages/home.html')

    @page.get('/profile/<username>')
    def profile(username):
        return render_template('pages/profile.html', username=username)

HTTP Method Shortcuts
---------------------
Both blueprints support these convenience decorators:

- ``@api.get('/path')`` - GET request
- ``@api.post('/path')`` - POST request
- ``@api.put('/path')`` - PUT request
- ``@api.patch('/path')`` - PATCH request
- ``@api.delete('/path')`` - DELETE request

Same for ``@page.get()``, ``@page.post()``, etc.
"""

from functools import wraps
from typing import Callable, Type, Optional

from flask import Blueprint, jsonify, request, g, session
from flask_login import current_user, login_required as flask_login_required


# =============================================================================
# Blueprints
# =============================================================================

#: API Blueprint - For REST API endpoints.
#: Routes defined with @api.get('/users') become GET /api/users
api = Blueprint("api", __name__)

#: Page Blueprint - For HTML page routes.
#: Routes defined with @page.get('/') become GET /
page = Blueprint("page", __name__)


@page.context_processor
def inject_page_context():
    """Inject common page context into all templates.

    Provides:
        pending_toast: Toast notification to show after redirect (if any)
    """
    pending_toast = session.pop("_pending_toast", None)
    return {
        "pending_toast": pending_toast,
    }


# =============================================================================
# Decorators
# =============================================================================

def csrf_exempt(view: Callable) -> Callable:
    """Exempt a view from CSRF protection.

    Use this decorator on routes that don't need CSRF protection, such as
    webhook endpoints that use signature verification instead.

    Args:
        view: The route function to exempt.

    Returns:
        The same function, registered as CSRF-exempt.

    Example:
        Exempt a webhook route::

            from feather import api, csrf_exempt

            @api.post('/webhooks/stripe')
            @csrf_exempt
            def stripe_webhook():
                # Webhook uses Stripe signature verification
                return {'status': 'received'}

    Note:
        This decorator accesses Flask-WTF's CSRFProtect instance from
        app.extensions. It must be used on routes registered with Feather.
    """
    from flask import current_app

    # Build the view location string that Flask-WTF uses
    view_location = f"{view.__module__}.{view.__name__}"

    # Get the CSRFProtect instance and register exemption
    # Note: This works because Flask-WTF stores itself in app.extensions["csrf"]
    # The actual exemption happens at request time via current_app
    @wraps(view)
    def decorated_function(*args, **kwargs):
        # Ensure this view is exempt (idempotent)
        csrf = current_app.extensions.get("csrf")
        if csrf and view_location not in csrf._exempt_views:
            csrf._exempt_views.add(view_location)
        return view(*args, **kwargs)

    # Also store the location for early registration during import
    decorated_function._csrf_exempt_location = view_location

    return decorated_function


def auth_required(f: Callable) -> Callable:
    """Require authentication for a route.

    Use this decorator on routes that require a logged-in user.

    Two-step check:
    1. If user has no session (is_anonymous=True) → 401 AuthenticationError
    2. If user is suspended (is_active=False) → 403 AuthorizationError

    This distinction is important: suspended users have a valid session but
    are blocked from accessing protected resources with a clear "suspended"
    message, not a confusing "please log in" message.

    Args:
        f: The route function to protect.

    Returns:
        Decorated function that checks authentication first.

    Raises:
        AuthenticationError: If user has no session (401).
        AuthorizationError: If user is suspended (403).

    Example:
        Protect an API route::

            @api.get('/me')
            @auth_required
            def get_current_user():
                return {'user': current_user.to_dict()}

        Protect a page route::

            @page.get('/settings')
            @auth_required
            def settings():
                return render_template('settings.html')

        Combined with service injection (note decorator order)::

            @api.post('/posts')
            @auth_required      # Check auth first
            @inject(PostService)  # Then inject services
            def create_post(post_service):
                data = request.get_json()
                post = post_service.create(user_id=current_user.id, **data)
                return {'post': post.to_dict()}, 201

    Note:
        This decorator uses Flask-Login's ``current_user`` proxy. Make sure
        you have Flask-Login configured with a user loader.
    """
    from feather.exceptions import AuthenticationError, AuthorizationError

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Step 1: Check if user has a session (is_anonymous is False for real users)
        # We use is_anonymous instead of is_authenticated because Flask-Login's
        # is_authenticated returns is_active, which would conflate "no session"
        # with "suspended user"
        if current_user.is_anonymous:
            raise AuthenticationError("Authentication required")

        # Step 2: Check if user is active (not suspended)
        # is_active should be a @property, but handle method for backwards compat
        is_active = getattr(current_user, "is_active", True)
        if callable(is_active):
            is_active = is_active()
        if not is_active:
            raise AuthorizationError("Account suspended")

        return f(*args, **kwargs)

    return decorated_function


def inject(*service_classes: Type) -> Callable:
    """Inject service instances into route handlers.

    This decorator creates instances of the specified service classes and
    passes them as keyword arguments to your route handler. Parameter names
    are automatically derived from class names (PascalCase → snake_case).

    Args:
        *service_classes: One or more Service subclasses to inject.

    Returns:
        Decorated function with service instances as keyword arguments.

    Example:
        Single service::

            from feather import api, inject
            from services import UserService

            @api.get('/users')
            @inject(UserService)
            def list_users(user_service):  # ← UserService → user_service
                return {'users': user_service.list_all()}

        Multiple services::

            @api.post('/posts')
            @inject(PostService, NotificationService)
            def create_post(post_service, notification_service):
                post = post_service.create(**request.get_json())
                notification_service.notify_followers(post)
                return {'post': post.to_dict()}, 201

        With authentication (order matters - auth first)::

            @api.delete('/posts/<post_id>')
            @auth_required      # ← Check auth before injecting
            @inject(PostService)
            def delete_post(post_id, post_service):
                post_service.delete(post_id, user_id=current_user.id)
                return '', 204

    Note:
        - Checks the service registry first for singleton instances
        - If not in registry, creates a new instance for each request
        - Service classes must be importable at decoration time
        - Name conversion: ``UserService`` → ``user_service``
        - Non-singleton services have on_cleanup() called after request
    """
    from feather.services.base import registry

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Track non-singleton services for cleanup
            services_to_cleanup = []

            # Create an instance of each service and add to kwargs
            for service_class in service_classes:
                # Convert PascalCase to snake_case: UserService → user_service
                param_name = _class_to_param_name(service_class.__name__)
                # Check registry first (for singleton services)
                instance = registry.get(service_class)
                if instance is None:
                    instance = service_class()
                    # Track for cleanup (non-singleton)
                    services_to_cleanup.append(instance)
                kwargs[param_name] = instance

            try:
                return f(*args, **kwargs)
            finally:
                # Call on_cleanup for non-singleton services
                for service in services_to_cleanup:
                    try:
                        if hasattr(service, 'on_cleanup'):
                            service.on_cleanup()
                    except Exception:
                        # Don't let cleanup errors break the request
                        import logging
                        logging.getLogger(__name__).exception(
                            f"Error in {service.__class__.__name__}.on_cleanup()"
                        )

        return decorated_function

    return decorator


# =============================================================================
# Internal Helpers
# =============================================================================

def _class_to_param_name(class_name: str) -> str:
    """Convert PascalCase class name to snake_case parameter name.

    Used by @inject to determine the keyword argument name for each service.

    Args:
        class_name: PascalCase class name like 'UserService'.

    Returns:
        snake_case name like 'user_service'.

    Examples:
        >>> _class_to_param_name('UserService')
        'user_service'
        >>> _class_to_param_name('BlogPostService')
        'blog_post_service'
        >>> _class_to_param_name('HTTPClient')
        'http_client'
    """
    import re

    # Insert underscore before uppercase letters following lowercase
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", class_name)
    # Insert underscore before uppercase following lowercase/digit
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _add_route_methods(blueprint: Blueprint) -> None:
    """Add HTTP method convenience decorators to a blueprint.

    Adds .get(), .post(), .put(), .patch(), .delete() methods so you can
    write ``@api.get('/users')`` instead of ``@api.route('/users', methods=['GET'])``.

    Args:
        blueprint: Flask Blueprint to enhance.
    """

    def get(rule: str, **options):
        """Register a GET route: @blueprint.get('/path')"""
        options["methods"] = ["GET"]
        return blueprint.route(rule, **options)

    def post(rule: str, **options):
        """Register a POST route: @blueprint.post('/path')"""
        options["methods"] = ["POST"]
        return blueprint.route(rule, **options)

    def put(rule: str, **options):
        """Register a PUT route: @blueprint.put('/path')"""
        options["methods"] = ["PUT"]
        return blueprint.route(rule, **options)

    def delete(rule: str, **options):
        """Register a DELETE route: @blueprint.delete('/path')"""
        options["methods"] = ["DELETE"]
        return blueprint.route(rule, **options)

    def patch(rule: str, **options):
        """Register a PATCH route: @blueprint.patch('/path')"""
        options["methods"] = ["PATCH"]
        return blueprint.route(rule, **options)

    blueprint.get = get
    blueprint.post = post
    blueprint.put = put
    blueprint.delete = delete
    blueprint.patch = patch


# Add convenience methods to both blueprints at import time
_add_route_methods(api)
_add_route_methods(page)


# =============================================================================
# Role-Based Access Control (re-exported from auth module)
# =============================================================================

# These are re-exported here for convenience so users can do:
# from feather import auth_required, admin_required, role_required

try:
    from feather.auth.decorators import admin_required, role_required
except ImportError:
    # Auth module not available - provide stub decorators that raise
    def admin_required(f: Callable) -> Callable:
        """Stub decorator - auth module not initialized."""

        @wraps(f)
        def decorated(*args, **kwargs):
            raise RuntimeError(
                "Authentication not initialized. "
                "Create a User model with flask_login.UserMixin to enable auth."
            )

        return decorated

    def role_required(roles):
        """Stub decorator - auth module not initialized."""

        def decorator(f: Callable) -> Callable:
            @wraps(f)
            def decorated(*args, **kwargs):
                raise RuntimeError(
                    "Authentication not initialized. "
                    "Create a User model with flask_login.UserMixin to enable auth."
                )

            return decorated

        return decorator
