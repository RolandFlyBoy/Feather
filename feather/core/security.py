"""Security headers middleware.

Adds standard HTTP security headers to all responses when not in debug mode.
Configurable via app config keys.

Configuration:
    FEATHER_SECURITY_HEADERS: bool (default True) — set to False to disable.
    FEATHER_HSTS_MAX_AGE: int (default 31536000 = 1 year).
    FEATHER_CSP_DIRECTIVES: dict — override or extend default CSP directives.

The app's own storage host is added to the image and media directives
automatically (``storage_origin``), so an app that keeps uploads in a bucket
can show them without configuring anything.

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
    # data: and blob: are how a page previews a file someone just chose,
    # before it has been uploaded anywhere.
    "img-src": "'self' data: blob: https://*.googleusercontent.com",
    "media-src": "'self' blob:",
    "font-src": "'self' https://fonts.gstatic.com",
    "connect-src": "'self'",
    "frame-ancestors": "'none'",
}

#: Directives the storage host is added to, when the app stores files
#: somewhere else: an app that uploads photos has to be able to show them.
_STORAGE_DIRECTIVES = ("img-src", "media-src")


def storage_origin(config) -> str | None:
    """The origin files are served from, when it is not this app.

    ``S3_PUBLIC_URL`` when the bucket has a public address, else
    ``S3_ENDPOINT``, which is what a signed link is built on. Returns the
    scheme and host only, which is what a policy directive takes.
    """
    from urllib.parse import urlsplit

    for key in ("S3_PUBLIC_URL", "S3_ENDPOINT"):
        value = (config.get(key) or "").strip()
        if not value:
            continue
        parts = urlsplit(value if "//" in value else f"https://{value}")
        if parts.netloc:
            return f"{parts.scheme or 'https'}://{parts.netloc}"
    return None


def csp_directives(config) -> dict:
    """The policy for this app: the defaults, plus wherever its files live,
    with ``FEATHER_CSP_DIRECTIVES`` having the last word."""
    directives = {**DEFAULT_CSP_DIRECTIVES}
    origin = storage_origin(config)
    if origin:
        for key in _STORAGE_DIRECTIVES:
            value = directives.get(key, "'self'")
            if origin not in value:
                directives[key] = f"{value} {origin}"
    custom = config.get("FEATHER_CSP_DIRECTIVES")
    if custom:
        directives.update(custom)
    return directives


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
        directives = csp_directives(app.config)

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
        # Apps that use the camera/microphone (video interviews) or the
        # Payment Request API set FEATHER_PERMISSIONS_POLICY themselves;
        # the default denies all four to every origin, including self.
        response.headers["Permissions-Policy"] = app.config.get(
            "FEATHER_PERMISSIONS_POLICY",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )

        return response
