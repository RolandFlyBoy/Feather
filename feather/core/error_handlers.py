"""Error handlers and response builders."""

import traceback
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from flask import jsonify, redirect, render_template, request, url_for

if TYPE_CHECKING:
    from flask import Flask


def _log_error_to_db(
    app,
    event_type: str,
    message: str,
    level: str = "ERROR",
    include_trace: bool = False,
    skip_auth_filter: bool = False,
) -> None:
    """Log event to database if Log model exists.

    This is a best-effort operation - failures are silently ignored
    to avoid breaking the error handler.

    Args:
        app: Flask app instance.
        event_type: Type of event (e.g., NotFoundError, InternalError).
        message: Human-readable message.
        level: Log level (INFO, WARNING, ERROR).
        include_trace: Whether to include stack trace.
        skip_auth_filter: If True, skip auth filtering (always log).
    """
    try:
        # For 4xx errors (WARNING level), only log for authenticated users
        # Unauthenticated 404s are almost always bots probing for vulnerabilities
        if level == "WARNING" and not skip_auth_filter:
            from flask_login import current_user
            if not (hasattr(current_user, 'is_authenticated') and current_user.is_authenticated):
                return

        # Try to find Log model or ErrorLog model (alternative naming)
        import importlib
        Log = None
        use_error_log_schema = False

        try:
            log_module = importlib.import_module("models.log")
            Log = getattr(log_module, "Log", None)
        except ImportError:
            pass

        if not Log:
            # Try ErrorLog model as alternative
            try:
                error_log_module = importlib.import_module("models.error_log")
                Log = getattr(error_log_module, "ErrorLog", None)
                use_error_log_schema = True
            except ImportError:
                pass

        if not Log:
            return

        from feather.db import db
        from flask_login import current_user

        user_id = None
        tenant_id = None
        if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            user_id = getattr(current_user, 'id', None)
            tenant_id = getattr(current_user, 'tenant_id', None)

        # Create log entry
        log_data = {
            "id": str(uuid.uuid4()),
            "message": message,
            "path": request.path,
            "method": request.method,
            "user_id": user_id,
            "stack_trace": traceback.format_exc() if include_trace else None,
        }

        if use_error_log_schema:
            # ErrorLog model uses error_type field, no level
            log_data["error_type"] = event_type
        else:
            # Log model uses event_type and level fields
            log_data["event_type"] = event_type
            log_data["level"] = level

        # Add tenant_id if the model supports it
        if hasattr(Log, "tenant_id"):
            log_data["tenant_id"] = tenant_id

        log_entry = Log(**log_data)
        db.session.add(log_entry)
        db.session.commit()
    except Exception:
        # Don't let logging failures break the error handler
        # Rollback any partial transaction
        try:
            from feather.db import db
            db.session.rollback()
        except Exception:
            pass


def _is_api_request() -> bool:
    """Check if this is an API request (should return JSON)."""
    # Explicit API path
    if request.path.startswith("/api/"):
        return True
    # HTMX requests should get HTML partials, not JSON
    if request.headers.get("HX-Request"):
        return False
    # Check Accept header for JSON preference
    accept = request.headers.get("Accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return True
    return False


def register_error_handlers(app: "Flask") -> None:
    """Register error handlers for the application.

    Args:
        app: Flask application instance.
    """
    from feather.exceptions import (
        FeatherException,
        AuthenticationError,
        AuthorizationError,
        AccountPendingError,
        AccountSuspendedError,
    )

    @app.errorhandler(FeatherException)
    def handle_feather_exception(error: FeatherException):
        """Handle Feather exceptions."""
        request_id = str(uuid.uuid4())

        # Log the error
        if error.status_code >= 500:
            app.logger.error(f"[{request_id}] {error.__class__.__name__}: {error.message}")
            if app.debug:
                app.logger.error(traceback.format_exc())
        else:
            app.logger.warning(f"[{request_id}] {error.__class__.__name__}: {error.message}")

        # For page routes (non-API), handle auth errors with HTML response
        if not _is_api_request():
            if isinstance(error, AuthenticationError):
                # Check if Google OAuth is configured
                google_configured = bool(
                    app.config.get("GOOGLE_CLIENT_ID") and
                    app.config.get("GOOGLE_CLIENT_SECRET")
                )

                # If OAuth not configured, show setup instructions
                if not google_configured:
                    try:
                        return render_template(
                            "errors/auth_required.html",
                            message=error.message,
                            show_config_hint=True,
                            next_url=request.url,
                        ), error.status_code
                    except Exception:
                        pass  # Fall through to JSON

                # OAuth configured: redirect to home page (which has login)
                return redirect(url_for('page.home'))

            # Handle account pending/suspended with dedicated pages
            if isinstance(error, AccountPendingError):
                try:
                    return redirect(url_for('page.account_pending'))
                except Exception:
                    pass  # Fall through to generic auth error

            if isinstance(error, AccountSuspendedError):
                try:
                    return redirect(url_for('page.account_suspended'))
                except Exception:
                    pass  # Fall through to generic auth error

            if isinstance(error, AuthorizationError):
                # Render authorization error template with next_url
                try:
                    return render_template(
                        "errors/auth_required.html",
                        message=error.message,
                        show_config_hint=False,
                        next_url=request.url,
                    ), error.status_code
                except Exception:
                    pass  # Fall through to JSON

        # Default: JSON response for API routes
        response = build_error_response(
            code=error.error_code,
            message=error.message,
            status_code=error.status_code,
            request_id=request_id,
            field=getattr(error, "field", None),
        )

        return jsonify(response), error.status_code

    @app.errorhandler(404)
    def handle_not_found(error):
        """Handle 404 errors."""
        # Log to database (WARNING level, filtered to authenticated users only)
        _log_error_to_db(app, "NotFoundError", f"Not found: {request.path}", level="WARNING")

        if request.path.startswith("/api/"):
            response = build_error_response(
                code="NOT_FOUND",
                message="Resource not found",
                status_code=404,
            )
            return jsonify(response), 404

        # For non-API routes, return styled HTML error page
        try:
            return render_template(
                "errors/error.html",
                error_code=404,
                error_title="Page Not Found",
                error_message="The page you're looking for doesn't exist or has been moved.",
                error_icon="search_off",
            ), 404
        except Exception:
            return "Not Found", 404

    @app.errorhandler(500)
    def handle_server_error(error):
        """Handle 500 errors."""
        request_id = str(uuid.uuid4())
        app.logger.error(f"[{request_id}] Internal Server Error: {error}")
        app.logger.error(traceback.format_exc())

        # Log to database (ERROR level, always logged regardless of auth)
        _log_error_to_db(app, "InternalError", str(error), level="ERROR", include_trace=True, skip_auth_filter=True)

        if request.path.startswith("/api/"):
            response = build_error_response(
                code="INTERNAL_ERROR",
                message="An unexpected error occurred",
                status_code=500,
                request_id=request_id,
            )
            return jsonify(response), 500

        # For non-API routes, return styled HTML error page
        try:
            return render_template(
                "errors/error.html",
                error_code=500,
                error_title="Server Error",
                error_message="Something went wrong on our end. Please try again later.",
                error_icon="error",
            ), 500
        except Exception:
            return "Internal Server Error", 500


def build_success_response(
    data: dict = None,
    message: str = None,
    request_id: str = None,
) -> dict:
    """Build a standardized success response.

    Args:
        data: Response data.
        message: Optional success message.
        request_id: Optional request ID.

    Returns:
        Standardized response dict.
    """
    response = {
        "success": True,
        "data": data,
        "error": None,
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    if message:
        response["message"] = message

    if request_id:
        response["meta"]["request_id"] = request_id

    return response


def build_error_response(
    code: str,
    message: str,
    status_code: int,
    request_id: str = None,
    field: str = None,
) -> dict:
    """Build a standardized error response.

    Args:
        code: Error code (e.g., 'VALIDATION_ERROR').
        message: Human-readable error message.
        status_code: HTTP status code.
        request_id: Optional request ID.
        field: Optional field name for validation errors.

    Returns:
        Standardized error response dict.
    """
    error = {
        "code": code,
        "message": message,
    }

    if field:
        error["field"] = field

    response = {
        "success": False,
        "data": None,
        "error": error,
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    if request_id:
        response["meta"]["request_id"] = request_id

    return response
