"""
Flask-Login Setup
=================

Initializes Flask-Login for session management.

Flask-Login provides:
- User session management
- "Remember me" functionality
- Protection of views that require authentication
- Session timeout configuration

Setup
-----
Called automatically by Feather if a User model is detected::

    # This happens automatically in Feather.__init__
    from feather.auth import init_auth
    init_auth(app, user_model=User)

Manual setup if needed::

    from feather.auth import init_auth, set_user_loader
    from models import User

    init_auth(app)
    set_user_loader(User)  # If User model defined after init

Configuration
-------------
Session timeout settings (via environment variables or config.py)::

    # Environment variables
    SESSION_LIFETIME_DAYS=7        # Session expires after 7 days (default)
    REMEMBER_COOKIE_DAYS=365       # Remember me lasts 365 days (default)
    SESSION_PROTECTION=strong      # None, basic, or strong (default: strong)

    # Or in config.py
    from datetime import timedelta
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    REMEMBER_COOKIE_DURATION = timedelta(days=365)
    SESSION_PROTECTION = 'strong'

Session Protection Levels:
- None: No session protection (not recommended)
- 'basic': Session regenerated on suspicious activity
- 'strong': Session invalidated on IP/user-agent change (most secure)
"""

from flask import Flask, redirect, url_for, request, jsonify, render_template
from flask_login import LoginManager

from feather.exceptions import AuthenticationError

#: The Flask-Login manager instance.
#: Initialized by init_auth() and used internally.
login_manager = LoginManager()


def init_auth(app: Flask, user_model=None) -> LoginManager:
    """Initialize Flask-Login with the application.

    Sets up session management, configures login redirects, and registers
    the user loader callback if a user model is provided.

    Args:
        app: Flask application instance.
        user_model: Optional User model class. Must have a get_by_id(id)
            class method that returns the user or None.

    Returns:
        The configured LoginManager instance.

    Configuration:
        Session timeout and protection can be configured via environment
        variables or config.py::

            # Environment variables
            SESSION_LIFETIME_DAYS=7        # Session expires after 7 days
            REMEMBER_COOKIE_DAYS=365       # Remember me lasts 365 days
            SESSION_PROTECTION=strong      # None, basic, or strong

            # Or config.py
            from datetime import timedelta
            PERMANENT_SESSION_LIFETIME = timedelta(days=7)
            REMEMBER_COOKIE_DURATION = timedelta(days=365)
            SESSION_PROTECTION = 'strong'

    Example::

        from feather import Feather
        from feather.auth import init_auth
        from models import User

        app = Feather(__name__)
        init_auth(app, user_model=User)

    Note:
        This is typically called automatically by Feather if a User model
        is found in your models/ directory.
    """
    login_manager.init_app(app)

    # Apply session protection setting from config
    session_protection = app.config.get("SESSION_PROTECTION", "strong")
    if session_protection and str(session_protection).lower() != "none":
        login_manager.session_protection = str(session_protection).lower()
    else:
        login_manager.session_protection = None

    # Configure login view for page redirects
    # Default to Google OAuth login, can be overridden via LOGIN_VIEW config
    login_manager.login_view = app.config.get("LOGIN_VIEW", "google_auth.login")
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "info"

    # Custom unauthorized handler - API gets 401, pages get redirect
    @login_manager.unauthorized_handler
    def unauthorized():
        """Handle unauthorized access based on request type."""
        from flask import current_app

        # API requests get JSON 401 response
        if request.is_json or request.path.startswith("/api/"):
            raise AuthenticationError("Authentication required")

        # Page requests get redirected to login
        next_url = request.url

        # Try to find a working login route
        login_routes = [
            login_manager.login_view,  # Configured login view
            "google_auth.login",       # Google OAuth
        ]

        for route in login_routes:
            try:
                login_url = url_for(route)
                return redirect(f"{login_url}?next={next_url}")
            except Exception:
                continue

        # No login route available - show error page
        # This happens when Google OAuth isn't configured
        show_config_hint = not current_app.config.get("GOOGLE_CLIENT_ID")
        return render_template(
            "errors/auth_required.html",
            message="Authentication is required but no login method is configured.",
            show_config_hint=show_config_hint,
        ), 401

    # Set up user loader if model provided
    if user_model:
        set_user_loader(user_model)

    return login_manager


def set_user_loader(user_model) -> None:
    """Set the user loader callback after initialization.

    Use this if you need to initialize auth before defining your User model,
    or if you want to change the user model at runtime.

    Args:
        user_model: User model class with a get_by_id(id) class method.

    Example::

        from feather.auth import init_auth, set_user_loader
        from models import User

        # Initialize without model
        init_auth(app)

        # Later, set the user loader
        set_user_loader(User)

    Note:
        The User model should:
        - Inherit from flask_login.UserMixin (provides is_authenticated, etc.)
        - Have a get_by_id(id) class method that returns the user or None
    """

    @login_manager.user_loader
    def load_user(user_id: str):
        """Load a user from the session.

        Called by Flask-Login on each request to load the current user
        from the user_id stored in the session.
        """
        return user_model.get_by_id(user_id)
