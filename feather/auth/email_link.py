"""Sign in with a link sent by email.

For apps whose users should not need a Google account, and for developers who
should not need a Google Cloud project. Turn it on with
``SIGN_IN_METHOD = "email"`` (``feather new --sign-in email`` sets it).

The flow:

1. ``GET /auth/email/login`` asks for an email address.
2. ``POST /auth/email/login`` sends a link and says so, whether or not the
   address has an account, so the form can't be used to find out who does.
3. ``GET /auth/email/verify?token=...`` shows a **Sign in** button. It doesn't
   sign in by itself: mail scanners open links to check them, and a link that
   worked on GET would be used up by the scanner before the person clicked it.
4. ``POST /auth/email/verify`` signs the person in.

A link is signed with ``SECRET_KEY``, lasts ``SIGN_IN_LINK_MINUTES`` (15), and
works once. Who may sign in, and what happens to a new address, is exactly what
Google sign-in does (``google._get_or_create_user``): the same approval, admin
and tenant rules.

Where the email goes, in order:

- ``SIGN_IN_RELAY_URL`` and ``SIGN_IN_RELAY_TOKEN``: a relay sends it. Appentic
  sets these on its projects, so nothing needs configuring there. The relay is
  told only the address, the link and the app's name, and writes the email
  itself.
- ``RESEND_API_KEY``: sent through Resend, from ``RESEND_FROM_EMAIL``.
- Neither: in development and tests the link is written to the log. Anywhere
  else nothing is sent, the person is told so, and an error is logged without
  the link, since a log line holding it would let its reader sign in.
"""

from __future__ import annotations

import html
import logging
import re
import secrets
from typing import Optional

import requests
from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

email_auth_bp = Blueprint("email_auth", __name__, url_prefix="/auth/email")

SALT = "feather-email-sign-in"
DEFAULT_LINK_MINUTES = 15
_EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
_RELAY_TIMEOUT = 10

#: Links already used, when no shared cache is configured. Per process only,
#: which is why a real deployment should have a cache (REDIS_URL).
_used_here: dict = {}


def init_email_sign_in(app) -> None:
    """Mount the email sign-in routes. Feather calls this for every app with a
    User model; the routes answer 404 unless ``SIGN_IN_METHOD`` is "email"."""
    app.register_blueprint(email_auth_bp)


def _setting(name: str, default=None):
    """A sign-in setting from the app's config, else the environment.

    An app's config.py class lists the keys it uses, and Feather's own
    defaults for the rest don't reach app.config, so a host that sets
    SIGN_IN_RELAY_URL in the environment would otherwise go unseen.
    """
    import os

    value = current_app.config.get(name)
    if value in (None, ""):
        value = os.environ.get(name)
    return default if value in (None, "") else value


def enabled() -> bool:
    return str(_setting("SIGN_IN_METHOD", "google")).lower() == "email"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=SALT)


def _minutes() -> int:
    return int(_setting("SIGN_IN_LINK_MINUTES", DEFAULT_LINK_MINUTES))


def _normalise(email: str) -> str:
    return (email or "").strip().lower()


def make_link(email: str) -> str:
    """A sign-in link for ``email``, absolute, for this app."""
    token = _serializer().dumps({"e": _normalise(email), "n": secrets.token_urlsafe(12)})
    return url_for("email_auth.verify", token=token, _external=True)


def read_token(token: str) -> Optional[dict]:
    """The token's contents if it is genuine and in date, else None."""
    try:
        data = _serializer().loads(token, max_age=_minutes() * 60)
    except (SignatureExpired, BadSignature):
        return None
    if not isinstance(data, dict) or not data.get("e") or not data.get("n"):
        return None
    return data


def _mark_used(nonce: str) -> bool:
    """Record a link's use. False if it had been used already."""
    key = f"feather:sign-in-link:{nonce}"
    ttl = _minutes() * 60
    try:
        from feather.cache import get_cache

        cache = get_cache()
    except Exception:
        cache = None
    if cache is not None:
        try:
            if cache.get(key):
                return False
            cache.set(key, 1, ttl=ttl)
            return True
        except Exception:
            logger.warning("Sign-in link cache unavailable; checking use in this process only")
    import time

    now = time.time()
    for stale in [k for k, expires in _used_here.items() if expires < now]:
        _used_here.pop(stale, None)
    if key in _used_here:
        return False
    _used_here[key] = now + ttl
    return True


def _app_name() -> str:
    """The app's name for people, from APP_NAME. Flask's own name for the app
    is usually just "app", which is no name to put in an email."""
    name = _setting("APP_NAME") or ""
    return name if name and name != "app" else ""


def send_link(email: str, link: str) -> bool:
    """Send ``link`` to ``email`` by whichever way is configured."""
    relay_url = _setting("SIGN_IN_RELAY_URL")
    relay_token = _setting("SIGN_IN_RELAY_TOKEN")
    if relay_url and relay_token:
        try:
            response = requests.post(
                relay_url,
                json={"email": email, "link": link, "app_name": _app_name()},
                headers={"Authorization": f"Bearer {relay_token}"},
                timeout=_RELAY_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.error("Sign-in relay unreachable: %s", type(exc).__name__)
            return False
        if response.status_code >= 300:
            logger.error("Sign-in relay refused the email (%s)", response.status_code)
            return False
        return True

    resend_key = _setting("RESEND_API_KEY")
    if resend_key:
        try:
            import resend
        except ImportError:
            logger.error("RESEND_API_KEY is set but resend is not installed (feather-framework[email])")
            return False
        resend.api_key = resend_key
        name = _app_name() or "the app"
        minutes = _minutes()
        try:
            resend.Emails.send({
                "from": _setting("RESEND_FROM_EMAIL", "noreply@example.com"),
                "to": [email],
                "subject": f"Sign in to {name}",
                "text": (
                    f"Use this link to sign in to {name}:\n\n{link}\n\n"
                    f"It works once and expires in {minutes} minutes. "
                    "If you didn't ask to sign in, ignore this email."
                ),
                "html": (
                    f"<p>Use this link to sign in to {html.escape(name)}:</p>"
                    f'<p><a href="{html.escape(link)}">Sign in to {html.escape(name)}</a></p>'
                    f"<p>It works once and expires in {minutes} minutes. "
                    "If you didn't ask to sign in, ignore this email.</p>"
                ),
            })
        except Exception as exc:
            logger.error("Sign-in email not sent: %s", type(exc).__name__)
            return False
        return True

    # Only in development or tests is the link written to the log. Anywhere
    # else a log line holding a live sign-in link lets whoever reads the logs
    # sign in as that person.
    if current_app.debug or current_app.testing:
        logger.info("No way to send email is configured; sign-in link for %s: %s", email, link)
        return True
    logger.error(
        "Sign-in email not sent: no way to send email is configured "
        "(SIGN_IN_RELAY_URL and SIGN_IN_RELAY_TOKEN, or RESEND_API_KEY)."
    )
    return False


def _render(state: str, **context):
    return render_template(
        "auth/email_sign_in.html",
        state=state,
        app_name=_app_name() or "this app",
        minutes=_minutes(),
        **context,
    )


@email_auth_bp.get("/login")
def login():
    """Ask for an email address."""
    from flask import abort

    from feather.auth.google import _safe_next

    if not enabled():
        abort(404)
    if current_user.is_authenticated:
        return redirect(_safe_next(request.args.get("next")) or url_for("page.home"))
    next_url = _safe_next(request.args.get("next"))
    if next_url:
        session["next"] = next_url
    else:
        session.pop("next", None)
    return _render("form")


@email_auth_bp.post("/login")
def login_post():
    """Send a link, and say it was sent whether or not the address has an account."""
    from flask import abort

    if not enabled():
        abort(404)
    email = _normalise(request.form.get("email"))
    if not _EMAIL_RE.match(email) or len(email) > 254:
        return _render("form", error="Enter an email address, like you@example.com.", email=email), 400
    if not send_link(email, make_link(email)):
        return _render("form", error="The email couldn't be sent. Try again in a minute.", email=email), 503
    return _render("sent", email=email)


@email_auth_bp.get("/verify")
def verify():
    """Show a Sign in button for a valid link. Doesn't sign in: see the module docstring."""
    from flask import abort

    if not enabled():
        abort(404)
    token = request.args.get("token") or ""
    data = read_token(token)
    if data is None:
        return _render("invalid"), 400
    return _render("confirm", token=token, email=data["e"])


@email_auth_bp.post("/verify")
def verify_post():
    """Sign in with a valid link, once."""
    from flask import abort

    from feather.auth.google import _get_or_create_user, _safe_next, _set_toast

    if not enabled():
        abort(404)
    data = read_token(request.form.get("token") or "")
    if data is None or not _mark_used(data["n"]):
        return _render("invalid"), 400

    user = _get_or_create_user({"email": data["e"], "email_verified": True}, None, source="email")
    next_url = _safe_next(session.pop("next", None)) or url_for("page.home")
    if user is None:
        if not session.pop("_auth_error_handled", False) and not session.pop("_auth_silent_redirect", False):
            _set_toast("Sign-in failed. Please try again.", "error")
        return redirect(next_url)

    login_user(user, remember=True, force=True)
    return redirect(next_url)
