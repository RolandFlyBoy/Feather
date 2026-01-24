"""
Feather - A Flask-based web framework for solo developers using AI coding tools.

Server-first architecture with progressive enhancement, batteries included.

Quick Start
-----------
Create a new project and start developing in seconds::

    $ pip install feather-framework
    $ feather new myapp
    $ cd myapp
    $ feather dev

Then open http://localhost:5000 in your browser.

Basic Usage
-----------
Your app.py is just 3 lines::

    from feather import Feather

    app = Feather(__name__)

    if __name__ == "__main__":
        app.run()

Feather auto-discovers your models, services, and routes. No configuration needed.

Creating Routes
---------------
API routes (mounted at /api/*)::

    from feather import api

    @api.get('/users')
    def list_users():
        return {'users': [...]}

Page routes (mounted at /*)::

    from feather import page
    from flask import render_template

    @page.get('/')
    def home():
        return render_template('pages/home.html')

Using Services
--------------
Services contain your business logic::

    from feather import Service
    from feather.exceptions import NotFoundError

    class UserService(Service):
        def get_by_id(self, user_id: str):
            return self.get_or_404(User, user_id)

        def create(self, email: str, username: str):
            user = User(email=email, username=username)
            self.save(user)
            return user

Inject services into routes::

    from feather import api, inject

    @api.get('/users/<user_id>')
    @inject(UserService)
    def get_user(user_id, user_service):
        user = user_service.get_by_id(user_id)
        return {'user': user.to_dict()}

Error Handling
--------------
Use exceptions for clean error handling::

    from feather.exceptions import ValidationError, NotFoundError

    if not email:
        raise ValidationError('Email is required', field='email')

    user = User.query.get(user_id)
    if not user:
        raise NotFoundError('User', user_id)

Events
------
Dispatch events for loose coupling::

    from feather import dispatch, listen
    from feather.events import Event

    class UserCreatedEvent(Event):
        pass

    @listen(UserCreatedEvent)
    def send_welcome_email(event):
        # Send email to event.user_id
        pass

    # In your service:
    dispatch(UserCreatedEvent(user_id=user.id))

For more information, see the full documentation in feather_framework.md.
"""

__version__ = "0.8.0"

# =============================================================================
# Core Application
# =============================================================================
# The main Feather class extends Flask with auto-discovery and batteries-included
# features. Use this as your application entry point.
from feather.core.app import Feather

# Route blueprints and decorators for building your application:
# - api: Blueprint for API routes, mounted at /api/*
# - page: Blueprint for page routes, mounted at /*
# - inject: Decorator to inject service instances into routes
# - auth_required: Decorator to require authentication
# - csrf_exempt: Decorator to exempt webhook routes from CSRF protection
from feather.core.decorators import api, page, inject, auth_required, csrf_exempt

# =============================================================================
# Services Layer
# =============================================================================
# Services contain business logic and are the recommended way to interact with
# your data. Keep routes thin - delegate to services.
from feather.services.base import Service, transactional, singleton

# =============================================================================
# Authentication Decorators
# =============================================================================
# Role-based access control decorators for routes.
from feather.auth.decorators import (
    admin_required,
    login_only,
    role_required,
    permission_required,
    platform_admin_required,
    rate_limit,
)

# =============================================================================
# Tenancy
# =============================================================================
# Multi-tenant utilities for tenant isolation.
from feather.auth.tenancy import get_current_tenant_id, tenant_required

# =============================================================================
# Database
# =============================================================================
# SQLAlchemy database instance and base model class. All models should inherit
# from Model to get common functionality like save(), delete(), get_by_id().
from feather.db.base import db, Model

# Database mixins for common patterns - use only what you need
from feather.db.mixins import (
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
    OrderingMixin,
    TenantScopedMixin,
)

# Pagination utilities for list endpoints
from feather.db.pagination import paginate, PaginatedResult

# =============================================================================
# Event System
# =============================================================================
# Pub/sub pattern for loose coupling between components. Dispatch events after
# actions complete, and listen for them in separate handlers.
from feather.events.dispatcher import dispatch, listen

# =============================================================================
# Storage
# =============================================================================
# File storage abstraction supporting local filesystem and Google Cloud Storage.
# Use get_storage() to get the configured backend.
from feather.storage import get_storage

# =============================================================================
# Caching
# =============================================================================
# Response and function result caching with memory or Redis backends.
from feather.cache import get_cache, cached, cache_response

# =============================================================================
# Background Jobs
# =============================================================================
# Background job processing with sync (dev) or RQ (production) backends.
from feather.jobs import get_queue, job, scheduled

# =============================================================================
# Request Tracking
# =============================================================================
# Get the current request ID for logging and tracing.
from feather.core.middleware import get_request_id

# =============================================================================
# Exceptions
# =============================================================================
# Use these exceptions throughout your application for consistent error handling.
# They are automatically converted to proper JSON API responses with appropriate
# HTTP status codes.
from feather.exceptions import (
    FeatherException,     # Base exception - 500 Internal Server Error
    ValidationError,      # Invalid input - 400 Bad Request
    AuthenticationError,  # Not logged in - 401 Unauthorized
    AuthorizationError,   # No permission - 403 Forbidden
    NotFoundError,        # Resource not found - 404 Not Found
    ConflictError,        # Already exists - 409 Conflict
    StorageError,         # File storage failed - 500 Internal Server Error
    DatabaseError,        # Database operation failed - 500 Internal Server Error
)

# =============================================================================
# Public API
# =============================================================================
# These are the recommended imports for Feather applications. Import what you
# need directly from feather:
#
#     from feather import Feather, api, Service, ValidationError
#
__all__ = [
    # Core - The application class and route decorators
    "Feather",
    "api",
    "page",
    "inject",
    "auth_required",
    "csrf_exempt",
    # Services - Business logic layer
    "Service",
    "transactional",
    "singleton",
    # Authentication - Role-based access control
    "admin_required",
    "login_only",
    "role_required",
    "permission_required",
    "platform_admin_required",
    "rate_limit",
    # Tenancy - Multi-tenant utilities
    "get_current_tenant_id",
    "tenant_required",
    # Database - SQLAlchemy integration
    "db",
    "Model",
    # Database Mixins - Common model patterns
    "UUIDMixin",
    "TimestampMixin",
    "SoftDeleteMixin",
    "OrderingMixin",
    "TenantScopedMixin",
    # Pagination - List endpoints
    "paginate",
    "PaginatedResult",
    # Events - Pub/sub for loose coupling
    "dispatch",
    "listen",
    # Storage - File upload/download
    "get_storage",
    # Caching - Response and result caching
    "get_cache",
    "cached",
    "cache_response",
    # Background Jobs - Async job processing
    "get_queue",
    "job",
    "scheduled",
    # Request Tracking - For logging and tracing
    "get_request_id",
    # Exceptions - Error handling (automatically converted to JSON responses)
    "FeatherException",
    "ValidationError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "ConflictError",
    "StorageError",
    "DatabaseError",
]
