"""
Exception Hierarchy
===================

Feather's exception classes for consistent error handling across your application.

Raise these exceptions in your services and routes - Feather automatically
converts them to proper JSON API responses with the correct HTTP status codes.

Quick Reference
---------------
============== ====== ===================================================
Exception      Status Description
============== ====== ===================================================
Validation     400    Invalid input, missing fields, format errors
Authentication 401    User not logged in
Authorization  403    Logged in but no permission
NotFound       404    Resource doesn't exist
Conflict       409    Resource already exists (duplicate email, etc.)
RateLimit      429    Too many requests
Storage        500    File upload/download failed
Database       500    Database operation failed
============== ====== ===================================================

Quick Start
-----------
Use in services::

    from feather.exceptions import ValidationError, NotFoundError, AuthorizationError

    class PostService(Service):
        def create(self, user_id: str, title: str, content: str) -> Post:
            if not title:
                raise ValidationError('Title is required', field='title')

            if len(title) > 200:
                raise ValidationError('Title too long (max 200 chars)', field='title')

            post = Post(user_id=user_id, title=title, content=content)
            self.save(post)
            return post

        def delete(self, post_id: str, user_id: str) -> None:
            post = self.get_or_404(Post, post_id)  # Raises NotFoundError

            if post.user_id != user_id:
                raise AuthorizationError('You can only delete your own posts')

            super().delete(post)

The JSON Response
-----------------
When you raise an exception, Feather returns a standardized JSON response::

    {
        "success": false,
        "data": null,
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Title is required",
            "field": "title"
        },
        "meta": {
            "timestamp": "2024-01-15T10:30:00+00:00",
            "request_id": "abc123"
        }
    }

See Also
--------
- :class:`feather.Service`: Uses these exceptions in business logic
- :mod:`feather.core.error_handlers`: Converts exceptions to JSON
"""


class FeatherException(Exception):
    """Base exception for all Feather errors.

    All Feather exception classes inherit from this. You can catch this
    to catch all Feather-specific errors.

    Attributes:
        message: Human-readable error message for the client.
        status_code: HTTP status code (400, 401, 403, 404, etc.).
        error_code: Machine-readable code like 'VALIDATION_ERROR'.

    Example:
        Catch all Feather errors::

            try:
                user_service.create(**data)
            except FeatherException as e:
                print(f"Error {e.status_code}: {e.message}")

    Note:
        You usually don't raise FeatherException directly - use the
        specific subclasses like ValidationError, NotFoundError, etc.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or self.__class__.__name__.upper()


class ValidationError(FeatherException):
    """400 Bad Request - Invalid input or validation failure.

    Use this when the client sends invalid data: missing fields, wrong format,
    values out of range, etc.

    Args:
        message: Human-readable error message.
        field: Optional field name that caused the error.

    Example::

        # Missing required field
        if not data.get('email'):
            raise ValidationError('Email is required', field='email')

        # Invalid format
        if not is_valid_email(data['email']):
            raise ValidationError('Invalid email format', field='email')

        # Value out of range
        if len(data['title']) > 200:
            raise ValidationError('Title must be 200 characters or less', field='title')

        # Multiple validations
        if not data.get('password'):
            raise ValidationError('Password is required', field='password')
        if len(data['password']) < 8:
            raise ValidationError('Password must be at least 8 characters', field='password')
    """

    def __init__(self, message: str, field: str = None):
        super().__init__(message, status_code=400, error_code="VALIDATION_ERROR")
        self.field = field


class AuthenticationError(FeatherException):
    """401 Unauthorized - User is not logged in.

    Use this when an operation requires a logged-in user but the request
    has no valid session or token.

    Args:
        message: Human-readable error message. Defaults to "Authentication required".

    Example::

        # Manual check (usually @auth_required handles this)
        if not current_user.is_authenticated:
            raise AuthenticationError('Please log in to continue')

        # Custom message
        raise AuthenticationError('Your session has expired')

    Note:
        The @auth_required decorator automatically raises this when needed.
    """

    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, status_code=401, error_code="AUTHENTICATION_ERROR")


class AuthorizationError(FeatherException):
    """403 Forbidden - User doesn't have permission.

    Use this when a user is logged in but doesn't have permission to
    perform the requested action.

    Args:
        message: Human-readable error message. Defaults to "Permission denied".

    Example::

        # Only owner can edit
        if post.user_id != current_user.id:
            raise AuthorizationError('You can only edit your own posts')

        # Admin-only action
        if not current_user.is_admin:
            raise AuthorizationError('Admin access required')

        # Custom message
        raise AuthorizationError('You are not a member of this organization')
    """

    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, status_code=403, error_code="AUTHORIZATION_ERROR")


class NotFoundError(FeatherException):
    """404 Not Found - Resource doesn't exist.

    Use this when a requested resource (user, post, etc.) cannot be found.

    Args:
        resource_type: Type of resource (e.g., 'User', 'Post').
        resource_id: Optional ID that was requested.

    Example::

        # In a service method
        user = User.get_by_id(user_id)
        if not user:
            raise NotFoundError('User', user_id)

        # Or use the helper method
        user = self.get_or_404(User, user_id)  # Raises NotFoundError automatically

        # Without ID
        if not Post.query.filter_by(slug=slug).first():
            raise NotFoundError('Post')

    Note:
        The Service.get_or_404() and Model.get_or_404() methods
        automatically raise this exception.
    """

    def __init__(self, resource_type: str, resource_id: str = None):
        if resource_id:
            message = f"{resource_type} not found: {resource_id}"
        else:
            message = f"{resource_type} not found"
        super().__init__(message, status_code=404, error_code="NOT_FOUND")
        self.resource_type = resource_type
        self.resource_id = resource_id


class ConflictError(FeatherException):
    """409 Conflict - Resource already exists or conflicts.

    Use this when creating a resource would conflict with an existing one,
    typically for unique constraint violations.

    Args:
        message: Human-readable error message.

    Example::

        # Check before creating
        if User.query.filter_by(email=email).first():
            raise ConflictError('Email already registered')

        if User.query.filter_by(username=username).first():
            raise ConflictError('Username already taken')

        # In an update operation
        existing = Post.query.filter_by(slug=new_slug).first()
        if existing and existing.id != post_id:
            raise ConflictError('A post with this URL already exists')
    """

    def __init__(self, message: str):
        super().__init__(message, status_code=409, error_code="CONFLICT")


class StorageError(FeatherException):
    """500 Internal Server Error - File storage operation failed.

    Use this when file upload, download, or deletion fails.

    Args:
        message: Human-readable error message. Defaults to "Storage operation failed".

    Example::

        try:
            url = storage_service.upload(file)
        except Exception as e:
            raise StorageError(f'Failed to upload file: {e}')

        if not storage_service.delete(file_path):
            raise StorageError('Failed to delete file')
    """

    def __init__(self, message: str = "Storage operation failed"):
        super().__init__(message, status_code=500, error_code="STORAGE_ERROR")


class DatabaseError(FeatherException):
    """500 Internal Server Error - Database operation failed.

    Use this when a database operation fails unexpectedly.

    Args:
        message: Human-readable error message. Defaults to "Database operation failed".

    Example::

        try:
            self.db.commit()
        except SQLAlchemyError as e:
            self.db.rollback()
            raise DatabaseError(f'Failed to save: {e}')

    Note:
        Usually you let database errors propagate naturally. Use this
        for cases where you want to provide a user-friendly message.
    """

    def __init__(self, message: str = "Database operation failed"):
        super().__init__(message, status_code=500, error_code="DATABASE_ERROR")


class RateLimitError(FeatherException):
    """429 Too Many Requests - Rate limit exceeded.

    Use this when a client has made too many requests in a given time period.

    Args:
        message: Human-readable error message. Defaults to "Too many requests".

    Example::

        # Manual rate limiting
        if request_count > MAX_REQUESTS_PER_MINUTE:
            raise RateLimitError('Too many requests. Please wait a minute.')

        # With custom message
        raise RateLimitError('You can only post 10 comments per hour')

    Note:
        For automatic rate limiting, use Flask-Limiter or similar middleware.
    """

    def __init__(self, message: str = "Too many requests"):
        super().__init__(message, status_code=429, error_code="RATE_LIMIT_ERROR")


class AccountPendingError(AuthorizationError):
    """403 Forbidden - User account is pending approval.

    Raised when an authenticated user tries to access a protected resource
    but their account has not yet been approved by an administrator.

    This is distinct from AccountSuspendedError - pending means the account
    was never approved, while suspended means it was approved then deactivated.

    Args:
        message: Human-readable error message. Defaults to "Account pending approval".

    Example::

        # In auth flow
        if not current_user.active and not current_user.approved_at:
            raise AccountPendingError()

    Note:
        The @auth_required decorator raises this automatically for pending users.
        Use @login_only for pages that should be accessible to pending users.
    """

    def __init__(self, message: str = "Account pending approval"):
        super().__init__(message)
        self.error_code = "ACCOUNT_PENDING"


class AccountSuspendedError(AuthorizationError):
    """403 Forbidden - User account has been suspended.

    Raised when an authenticated user tries to access a protected resource
    but their account has been suspended by an administrator.

    This is distinct from AccountPendingError - suspended means the account
    was previously approved but has been deactivated.

    Args:
        message: Human-readable error message. Defaults to "Account suspended".

    Example::

        # In auth flow
        if not current_user.active and current_user.approved_at:
            raise AccountSuspendedError()

    Note:
        The @auth_required decorator raises this automatically for suspended users.
        Use @login_only for pages that should be accessible to suspended users.
    """

    def __init__(self, message: str = "Account suspended"):
        super().__init__(message)
        self.error_code = "ACCOUNT_SUSPENDED"


__all__ = [
    "FeatherException",
    "ValidationError",
    "AuthenticationError",
    "AuthorizationError",
    "AccountPendingError",
    "AccountSuspendedError",
    "NotFoundError",
    "ConflictError",
    "StorageError",
    "DatabaseError",
    "RateLimitError",
]
