"""Security headers middleware.

Adds standard HTTP security headers to all responses when not in debug mode.
Configurable via app config keys.

Configuration:
    FEATHER_SECURITY_HEADERS: bool (default True) — set to False to disable.
    FEATHER_HSTS_MAX_AGE: int (default 31536000 = 1 year).
    FEATHER_CSP_DIRECTIVES: dict — override or extend default CSP directives.

Example::

    # config.py
    FEATHER_CSP_DIRECTIVES = {
        "script-src": "'self' https://js.stripe.com",
        "frame-src": "'self' https://js.stripe.com",
    }
"""

DEFAULT_CSP_DIRECTIVES = {
    "default-src": "'self'",
    "script-src": "'self'",
    "style-src": "'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src": "'self' https://fonts.gstatic.com",
    "img-src": "'self' data: https://*.googleusercontent.com",
    "connect-src": "'self'",
    "frame-ancestors": "'none'",
}


def init_security_headers(app):
    """Register security headers on the application.

    Headers are only added when ``app.debug`` is False (production mode).
    Disable entirely with ``FEATHER_SECURITY_HEADERS = False`` in config.

    Args:
        app: Flask application instance.
    """

    @app.after_request
    def add_security_headers(response):
        if app.debug:
            return response

        if not app.config.get("FEATHER_SECURITY_HEADERS", True):
            return response

        # HSTS
        max_age = app.config.get("FEATHER_HSTS_MAX_AGE", 31536000)
        response.headers["Strict-Transport-Security"] = (
            f"max-age={max_age}; includeSubDomains"
        )

        # CSP
        directives = {**DEFAULT_CSP_DIRECTIVES}
        custom = app.config.get("FEATHER_CSP_DIRECTIVES")
        if custom:
            directives.update(custom)

        csp_value = "; ".join(
            f"{key} {value}" for key, value in directives.items()
        )
        response.headers["Content-Security-Policy"] = csp_value

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking (derive from frame-ancestors)
        fa = directives.get("frame-ancestors", "'none'")
        if fa == "'none'":
            response.headers["X-Frame-Options"] = "DENY"
        elif fa == "'self'":
            response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser features
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        return response
