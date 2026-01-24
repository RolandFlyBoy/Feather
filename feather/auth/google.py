"""
Google OAuth Integration
========================

Implements Google OAuth 2.0 login flow using Authlib.

This provides a simple way for users to log in with their Google accounts.
On first login, a new User record is created. On subsequent logins, the
existing user is logged in.

Configuration
-------------
Set these environment variables (or in config.py)::

    GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
    GOOGLE_CLIENT_SECRET=your-client-secret

Get these values from the Google Cloud Console:
https://console.cloud.google.com/apis/credentials

Setup
-----
Automatically initialized by Feather if GOOGLE_CLIENT_ID is set::

    # This happens automatically
    from feather.auth.google import init_google_oauth
    init_google_oauth(app)

Routes
------
After initialization, these routes are available:

- GET /auth/google/login - Redirects to Google login
- GET /auth/google/callback - Handles OAuth callback

Usage
-----
Add a "Login with Google" button::

    <a href="{{ url_for('google_auth.login') }}"
       class="btn">
        Login with Google
    </a>

User Creation
-------------
On first login, a user is created with:

- email: From Google profile
- username: Email prefix (before @)
- display_name: Full name from Google
- profile_image_url: Google profile picture

You can customize this by overriding _get_or_create_user().

Token Refresh
-------------
For accessing Google APIs on behalf of users, use get_google_token()::

    from feather.auth.google import get_google_token

    @api.get('/my-drive-files')
    @auth_required
    def list_drive_files():
        token = get_google_token()
        if not token:
            return {'error': 'Google token not available'}, 401

        # Use token['access_token'] with Google APIs
        headers = {'Authorization': f'Bearer {token["access_token"]}'}
        # ... make API call

To enable token storage and refresh, request additional scopes and enable
offline access in init_google_oauth().
"""

import os
import time
from typing import Optional

from flask import Blueprint, current_app, redirect, render_template, url_for, session
from authlib.integrations.flask_client import OAuth
from flask_login import login_user, current_user

#: Authlib OAuth client
oauth = OAuth()

#: Blueprint for Google OAuth routes
google_bp = Blueprint("google_auth", __name__, url_prefix="/auth/google")

# Session key for storing Google OAuth token
_TOKEN_SESSION_KEY = "google_oauth_token"


def _set_toast(message: str, toast_type: str = "error") -> None:
    """Set a pending toast message to be shown after redirect.

    Args:
        message: The message to display
        toast_type: Type of toast - "error", "success", or "info"
    """
    session["_pending_toast"] = {"message": message, "type": toast_type}


def _call_post_login_callback(user, token: dict) -> Optional[str]:
    """Call the configured post-login callback if set.

    The callback receives the user object and OAuth token, and can:
    - Perform custom logic (assign tenant, create account, send welcome email)
    - Return a redirect URL to override the default redirect
    - Return None to use the default redirect behavior

    This is useful for B2B+B2C apps that need custom account setup logic
    after OAuth authentication (e.g., creating Account/Membership records).

    Args:
        user: The User model instance that was logged in.
        token: The OAuth token dict with access_token, refresh_token, etc.

    Returns:
        Redirect URL string if callback returns one, otherwise None.

    Note:
        Errors are logged but do not interrupt the login flow (graceful degradation).
    """
    callback_path = current_app.config.get("FEATHER_POST_LOGIN_CALLBACK")
    if not callback_path:
        return None

    try:
        import importlib

        # Parse "module.path:function_name" or "module.path.function_name" format
        if ":" in callback_path:
            module_path, func_name = callback_path.rsplit(":", 1)
        else:
            module_path, func_name = callback_path.rsplit(".", 1)

        module = importlib.import_module(module_path)
        callback_func = getattr(module, func_name)

        # Call the callback with user and token
        result = callback_func(user, token)

        # Result can be a redirect URL string or None
        return result if isinstance(result, str) else None

    except ImportError as e:
        current_app.logger.error(
            f"Failed to import post-login callback '{callback_path}': {e}"
        )
        return None
    except AttributeError as e:
        current_app.logger.error(
            f"Post-login callback function not found in '{callback_path}': {e}"
        )
        return None
    except Exception as e:
        current_app.logger.error(
            f"Error in post-login callback '{callback_path}': {e}"
        )
        return None


def init_google_oauth(app) -> None:
    """Initialize Google OAuth with the Flask app.

    Registers the OAuth client and mounts the Google auth blueprint.

    Args:
        app: Flask application instance.

    Configuration Required:
        GOOGLE_CLIENT_ID: OAuth client ID from Google Cloud Console.
        GOOGLE_CLIENT_SECRET: OAuth client secret.

    Example::

        from feather import Feather
        from feather.auth.google import init_google_oauth

        app = Feather(__name__)
        init_google_oauth(app)

    Note:
        This is typically called automatically by Feather if
        GOOGLE_CLIENT_ID is configured.
    """
    oauth.init_app(app)

    # Register Google OAuth client
    oauth.register(
        name="google",
        client_id=app.config.get("GOOGLE_CLIENT_ID"),
        client_secret=app.config.get("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    # Mount the blueprint
    app.register_blueprint(google_bp)


@google_bp.route("/login")
def login():
    """Initiate Google OAuth login flow.

    Redirects the user to Google's login page. After authentication,
    Google will redirect back to the callback URL.

    If Google OAuth is not configured, renders a setup page with instructions.

    Query Parameters:
        next (optional): URL to redirect to after successful login.

    Returns:
        Redirect to Google OAuth authorization page, or setup page if not configured.
    """
    from flask import request

    # Check if Google OAuth is configured
    if not current_app.config.get("GOOGLE_CLIENT_ID") or not current_app.config.get("GOOGLE_CLIENT_SECRET"):
        return render_template(
            "errors/auth_required.html",
            message="Google OAuth not configured",
            show_config_hint=True,
        ), 503

    # Store next URL for after login (clear stale value if no ?next param)
    next_url = request.args.get("next")
    if next_url:
        session["next"] = next_url
    else:
        session.pop("next", None)

    # Build redirect URI from request host (preserves Vite proxy port)
    redirect_uri = current_app.config.get("OAUTH_CALLBACK_URL") or os.environ.get("OAUTH_CALLBACK_URL")
    if not redirect_uri:
        # X-Forwarded headers are set by Vite proxy to preserve original host
        scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
        host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host", request.host)
        redirect_uri = f"{scheme}://{host}/auth/google/callback"

    # Clear ALL stale OAuth state before starting new flow
    # Authlib uses _state_google_{value} format
    keys_to_remove = [k for k in session.keys() if k.startswith('_state_google_')]
    for key in keys_to_remove:
        session.pop(key, None)
    session.pop('_google_authlib_nonce_', None)
    session.pop('_google_authlib_code_verifier_', None)

    response = oauth.google.authorize_redirect(redirect_uri)

    # Force session to be saved
    session.modified = True

    return response


@google_bp.route("/callback")
def callback():
    """Handle Google OAuth callback.

    Called by Google after user authorizes the application. Exchanges
    the authorization code for tokens, fetches user info, and logs in
    (or creates) the user.

    Returns:
        Redirect to the stored 'next' URL or home page.
    """
    try:
        # Exchange code for token
        token = oauth.google.authorize_access_token()

        # Store the token for API access (includes refresh_token if offline access requested)
        _store_token(token)

        # Get user info from token or userinfo endpoint
        user_info = token.get("userinfo")
        if not user_info:
            user_info = oauth.google.get(
                "https://openidconnect.googleapis.com/v1/userinfo"
            ).json()

        # Get or create user
        user = _get_or_create_user(user_info, token)

        if user:
            # Log in the user with "remember me" enabled
            # force=True allows inactive users to be logged in temporarily
            # (they'll be redirected to pending page and logged out there)
            login_user(user, remember=True, force=True)

            # Call post-login callback if configured
            callback_redirect = _call_post_login_callback(user, token)
            if callback_redirect:
                session.pop("next", None)  # Clear stored next URL
                return redirect(callback_redirect)

            # Redirect to stored URL or home
            next_url = session.pop("next", None) or url_for("page.home")
            return redirect(next_url)
        else:
            # User creation was blocked or failed
            # Check flags set by _get_or_create_user for appropriate handling
            silent_redirect = session.pop("_auth_silent_redirect", False)
            auth_error_handled = session.pop("_auth_error_handled", False)
            next_url = session.pop("next", None) or url_for("page.home")

            if not silent_redirect and not auth_error_handled:
                # Only show generic error if _get_or_create_user didn't handle it
                current_app.logger.error("Failed to create user from Google profile")
                _set_toast("Authentication failed. Please try again.", "error")

            return redirect(next_url)

    except Exception as e:
        import traceback
        current_app.logger.error(f"Google OAuth callback error: {e}")
        current_app.logger.error(traceback.format_exc())
        _set_toast("Authentication failed. Please try again.", "error")
        return redirect(url_for("page.home"))


def _get_or_create_user(user_info: dict, token: dict = None):
    """Get existing user or create new one from Google profile.

    Called after successful OAuth authentication. Looks up the user by
    email, or creates a new one if not found.

    Login paths:
        - Admin login (next=/admin/...): Only existing users allowed.
          Returns None for new users (silent redirect to /).
        - Normal login (next=/ or no next): New users allowed IF tenant
          exists for their domain (multi-tenant mode).

    Multi-tenant mode (FEATHER_MULTI_TENANT=True):
        - Extracts email domain and finds tenant
        - Blocks public email domains (Gmail, Outlook, etc.)
        - New users created in suspended state (active=False)
        - Tenant must already exist (no auto-creation)

    Single-tenant mode (FEATHER_MULTI_TENANT=False):
        - All email domains allowed
        - Assigns to default tenant
        - New users created in suspended state (active=False)

    Args:
        user_info: Dictionary with Google profile data:
            - email: User's email address
            - name: Full name
            - picture: Profile image URL
            - sub: Google user ID (unique identifier)
        token: OAuth token dict (optional, for storing refresh token).

    Returns:
        User instance, or None if creation failed.

    Note:
        Override this function in your application if you need custom
        user creation logic (e.g., invite-only signups).
    """
    # Try to import User model from application
    try:
        from models import User
    except ImportError:
        current_app.logger.error(
            "User model not found. Create models/user.py with a User class "
            "that inherits from flask_login.UserMixin and feather.db.Model."
        )
        return None

    email = user_info.get("email")
    if not email:
        current_app.logger.error("No email in Google profile")
        return None

    from feather.db import db
    from feather.auth.domains import (
        extract_domain,
        is_public_email_domain,
    )

    # Check multi-tenant mode
    multi_tenant = current_app.config.get("FEATHER_MULTI_TENANT", False)

    # Import Tenant model only if in multi-tenant mode
    Tenant = None
    if multi_tenant:
        try:
            from models.tenant import Tenant
        except ImportError:
            current_app.logger.error(
                "Tenant model not found. Create models/tenant.py with a Tenant class."
            )
            return None

    # Extract domain for tenant assignment (only needed for multi-tenant)
    domain = None
    if multi_tenant:
        try:
            domain = extract_domain(email)
        except ValueError:
            current_app.logger.error(f"Invalid email format: {email}")
            _set_toast("Invalid email format.", "error")
            session["_auth_error_handled"] = True
            return None

    if multi_tenant:
        # Multi-tenant mode: Block public email domains (unless explicitly allowed)
        allow_public_emails = current_app.config.get("FEATHER_ALLOW_PUBLIC_EMAILS", False)
        if is_public_email_domain(domain) and not allow_public_emails:
            _set_toast(
                "Public email domains (Gmail, Outlook, etc.) are not allowed. "
                "Please sign in with your work email.",
                "error"
            )
            session["_auth_error_handled"] = True
            current_app.logger.warning(
                f"Blocked signup from public email domain: {email}"
            )
            return None

    # Find existing user
    user = User.query.filter_by(email=email).first()

    if user:
        # Existing user - update profile info from Google
        if hasattr(user, "display_name"):
            user.display_name = user_info.get("name")
        if hasattr(user, "profile_image_url"):
            user.profile_image_url = user_info.get("picture")
        db.session.commit()
    else:
        # ========== NEW USER LOGIC ==========

        # Check if this is an admin login attempt
        next_url = session.get("next", "") or ""
        is_admin_login = next_url.startswith("/admin")

        if is_admin_login:
            # Admin login: Don't create new users, silently redirect to /
            session["next"] = "/"  # Override to redirect to home
            session["_auth_silent_redirect"] = True  # Signal to callback: no error flash
            current_app.logger.info(
                f"Blocked new user creation via admin login: {email}"
            )
            return None  # No flash message, just redirect

        # Normal login: Check if tenant exists (multi-tenant mode only)
        tenant = None
        if multi_tenant:
            # Skip tenant lookup for public emails when allowed (app handles account creation)
            is_public = is_public_email_domain(domain) if domain else False
            allow_public_emails = current_app.config.get("FEATHER_ALLOW_PUBLIC_EMAILS", False)

            if is_public and allow_public_emails:
                # Public email with FEATHER_ALLOW_PUBLIC_EMAILS=True
                # Skip tenant lookup - app is responsible for account creation
                tenant = None
            else:
                tenant = Tenant.query.filter_by(domain=domain).first()
                if not tenant:
                    # NO auto-create - tenant must exist
                    _set_toast(
                        f"No organization found for {domain}. Please contact your administrator.",
                        "error"
                    )
                    session["_auth_error_handled"] = True
                    current_app.logger.warning(
                        f"Blocked signup - no tenant for domain: {email}"
                    )
                    return None

                # Check if tenant is active
                if hasattr(tenant, "status") and tenant.status != "active":
                    _set_toast(
                        f"The organization for {domain} is not yet active. Please contact your administrator.",
                        "error"
                    )
                    session["_auth_error_handled"] = True
                    current_app.logger.warning(
                        f"Blocked signup - tenant not active: {email} (tenant: {tenant.slug})"
                    )
                    return None

        # Generate username from email prefix
        username = email.split("@")[0]

        # Ensure username is unique
        base_username = username
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"{base_username}{counter}"
            counter += 1

        # Build user attributes
        user_attrs = {
            "email": email,
            "username": username,
            "display_name": user_info.get("name"),
            "profile_image_url": user_info.get("picture"),
            "active": False,  # Suspended until approved by admin
            "role": "user",
        }

        # Add tenant_id only if User model has it (multi-tenant mode)
        if tenant and hasattr(User, "tenant_id"):
            user_attrs["tenant_id"] = tenant.id

        # Create user in suspended state (requires admin approval)
        user = User(**user_attrs)
        db.session.add(user)
        db.session.commit()

        if tenant:
            current_app.logger.info(
                f"Created new user from Google: {email} (tenant: {tenant.slug}, suspended)"
            )
            _set_toast(
                "Your account has been created but requires approval from an administrator.",
                "info"
            )
        else:
            current_app.logger.info(
                f"Created new user from Google: {email} (no tenant, suspended)"
            )
            _set_toast(
                "Your account has been created and is pending setup.",
                "info"
            )

    # Update refresh token if provided and user has the field
    if token and hasattr(user, "google_refresh_token") and token.get("refresh_token"):
        user.google_refresh_token = token["refresh_token"]
        db.session.commit()

    return user


# =============================================================================
# Token Storage and Refresh
# =============================================================================


def _store_token(token: dict) -> None:
    """Store OAuth token in session.

    Args:
        token: OAuth token dict with access_token, refresh_token, expires_at, etc.
    """
    # Store token data we need
    token_data = {
        "access_token": token.get("access_token"),
        "refresh_token": token.get("refresh_token"),
        "expires_at": token.get("expires_at"),
        "token_type": token.get("token_type", "Bearer"),
    }
    session[_TOKEN_SESSION_KEY] = token_data


def get_google_token() -> Optional[dict]:
    """Get the current user's Google OAuth token, refreshing if needed.

    Returns a token dict with access_token that can be used to call Google APIs.
    Automatically refreshes the token if it's expired and a refresh_token is available.

    Returns:
        Token dict with 'access_token', 'token_type', etc., or None if not available.

    Example::

        from feather.auth.google import get_google_token

        @api.get('/google-calendar')
        @auth_required
        def get_calendar():
            token = get_google_token()
            if not token:
                return {'error': 'Please reconnect your Google account'}, 401

            # Use with Google API client
            headers = {'Authorization': f'Bearer {token["access_token"]}'}
            response = requests.get(
                'https://www.googleapis.com/calendar/v3/calendars/primary',
                headers=headers
            )
            return response.json()

    Note:
        - Token is stored in the user's session
        - If the token is expired and no refresh_token is available, returns None
        - To get a refresh_token, request offline access (access_type='offline')
    """
    token = session.get(_TOKEN_SESSION_KEY)
    if not token:
        return None

    # Check if token is expired
    expires_at = token.get("expires_at")
    if expires_at and time.time() > expires_at - 60:  # 60 second buffer
        # Token is expired, try to refresh
        refresh_token = token.get("refresh_token")

        # Also check User model for stored refresh token
        if not refresh_token and current_user.is_authenticated:
            refresh_token = getattr(current_user, "google_refresh_token", None)

        if refresh_token:
            new_token = _refresh_google_token(refresh_token)
            if new_token:
                _store_token(new_token)
                return new_token
            else:
                # Refresh failed, clear token
                session.pop(_TOKEN_SESSION_KEY, None)
                return None
        else:
            # No refresh token, can't refresh
            return None

    return token


def _refresh_google_token(refresh_token: str) -> Optional[dict]:
    """Refresh a Google OAuth token.

    Args:
        refresh_token: The refresh token from the original OAuth flow.

    Returns:
        New token dict, or None if refresh failed.
    """
    try:
        import requests

        client_id = current_app.config.get("GOOGLE_CLIENT_ID")
        client_secret = current_app.config.get("GOOGLE_CLIENT_SECRET")

        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )

        if response.status_code == 200:
            token_data = response.json()
            # Add expires_at from expires_in
            if "expires_in" in token_data:
                token_data["expires_at"] = time.time() + token_data["expires_in"]
            # Preserve refresh token (not always returned in refresh response)
            if "refresh_token" not in token_data:
                token_data["refresh_token"] = refresh_token
            return token_data
        else:
            current_app.logger.error(f"Failed to refresh Google token: {response.text}")
            return None

    except Exception as e:
        current_app.logger.error(f"Error refreshing Google token: {e}")
        return None


def clear_google_token() -> None:
    """Clear the stored Google OAuth token.

    Call this when the user logs out or disconnects their Google account.
    """
    session.pop(_TOKEN_SESSION_KEY, None)
