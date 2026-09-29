"""Sign in with a code sent by email.

For apps whose users should not need a Google account, and for developers who
should not need a Google Cloud project. Turn it on with
``SIGN_IN_METHOD = "email"`` (``feather new --sign-in email`` sets it).

The flow:

1. ``GET /auth/email/login`` asks for an email address.
2. ``POST /auth/email/login`` emails a six-digit code and asks for it, whether
   or not the address has an account, so the form can't be used to find out
   who does.
3. ``POST /auth/email/verify`` signs the person in with the code. The page
   submits by itself once six digits are typed, pasted or filled in by the
   phone (``feather-static/sign-in-code.js``); without JavaScript it has a
   button.
4. ``POST /auth/email/resend`` sends a new code to the same address.

Why a code and not a link: a link signs in whoever opens it, so an email that
is forwarded, read over a shoulder, opened by a mail scanner or intercepted
signs someone else in. A code works only in the browser that asked for it: the
pending sign-in lives in that browser's session, holding a keyed hash of the
code (never the code), the address and when it expires. Someone with the email
alone has nothing to type it into.

A code is six random digits, lasts ``SIGN_IN_CODE_MINUTES`` (15), works once, and dies after ``MAX_ATTEMPTS`` wrong
tries; asking again replaces it. Who may sign in, and what happens to a new
address, is exactly what Google sign-in does (``google._get_or_create_user``):
the same approval, admin and tenant rules.

Where the email goes, in order:

- ``SIGN_IN_RELAY_URL`` and ``SIGN_IN_RELAY_TOKEN``: a relay sends it. Appentic
  sets these on its projects, so nothing needs configuring there. The relay is
  told only the address, the code and the app's name, and writes the email
  itself.
- ``RESEND_API_KEY``: sent through Resend, from ``RESEND_FROM_EMAIL``.
- Neither: in development and tests the code is written to the log. Anywhere
  else nothing is sent, the person is told so, and an error is logged without
  the code, since a log line holding it would help its reader sign in.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import logging
import re
import secrets
import time
from typing import Optional

import requests
from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user

logger = logging.getLogger(__name__)

email_auth_bp = Blueprint("email_auth", __name__, url_prefix="/auth/email")

DEFAULT_CODE_MINUTES = 15
CODE_LENGTH = 6
#: Wrong codes allowed before a code stops working. One in a million per try,
#: so five tries leave a guesser at 1 in 200,000 per email they can trigger,
#: and a host's relay limits how many of those there are (5 an hour).
MAX_ATTEMPTS = 5
#: Where the pending sign-in lives in the session.
PENDING_KEY = "feather_sign_in"
_EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
_RELAY_TIMEOUT = 10

#: Counters and used codes, when no shared cache is configured. Per process
#: only, which is why a real deployment should have a cache (REDIS_URL).
_here: dict = {}


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


def _minutes() -> int:
    return int(_setting("SIGN_IN_CODE_MINUTES", DEFAULT_CODE_MINUTES))


def _normalise(email: str) -> str:
    return (email or "").strip().lower()


def new_code() -> str:
    """Six random digits, leading zeros kept."""
    return f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"


def _digest(nonce: str, email: str, code: str) -> str:
    """A keyed hash of the code, bound to this sign-in and this address. The
    session is signed but readable, so it holds this, never the code."""
    key = str(current_app.config["SECRET_KEY"]).encode()
    return hmac.new(key, f"{nonce}:{email}:{code}".encode(), hashlib.sha256).hexdigest()


def start(email: str) -> str:
    """Begin a sign-in for ``email`` in this browser: a new code, held (as a
    hash) in the session, replacing any earlier one. Returns the code to send."""
    code = new_code()
    nonce = secrets.token_urlsafe(12)
    session[PENDING_KEY] = {
        "e": _normalise(email),
        "n": nonce,
        "h": _digest(nonce, _normalise(email), code),
        "x": int(time.time()) + _minutes() * 60,
    }
    return code


def pending() -> Optional[dict]:
    """The sign-in this browser is waiting on, if it is still in date."""
    data = session.get(PENDING_KEY)
    if not isinstance(data, dict) or not all(data.get(k) for k in ("e", "n", "h", "x")):
        return None
    if int(data["x"]) < time.time():
        return None
    return data


def _cache():
    try:
        from feather.cache import get_cache

        return get_cache()
    except Exception:
        return None


def _bump(key: str) -> int:
    """Add one to a counter that lasts as long as a code does; return it."""
    ttl = _minutes() * 60
    cache = _cache()
    if cache is not None:
        try:
            count = int(cache.get(key) or 0) + 1
            cache.set(key, count, ttl=ttl)
            return count
        except Exception:
            logger.warning("Sign-in cache unavailable; counting in this process only")
    now = time.time()
    for stale in [k for k, (_v, expires) in _here.items() if expires < now]:
        _here.pop(stale, None)
    count = _here.get(key, (0, 0))[0] + 1
    _here[key] = (count, now + ttl)
    return count


def _count(key: str) -> int:
    cache = _cache()
    if cache is not None:
        try:
            return int(cache.get(key) or 0)
        except Exception:
            pass
    entry = _here.get(key)
    return entry[0] if entry and entry[1] >= time.time() else 0


def check(code: str) -> tuple[Optional[str], Optional[str]]:
    """Check a typed code against this browser's pending sign-in.

    Returns ``(email, None)`` when it is right (and uses the code up), or
    ``(None, reason)``: "expired" when there is no code in date to check
    against, "attempts" once it has had too many wrong tries, "wrong" for a
    wrong code with tries to spare. The tries are counted outside the session
    as well, so replaying an old cookie buys no extra guesses.
    """
    data = pending()
    if data is None:
        return None, "expired"
    tries_key = f"feather:sign-in-code:{data['n']}:tries"
    if _count(tries_key) >= MAX_ATTEMPTS:
        return None, "attempts"
    typed = re.sub(r"\D", "", code or "")
    if len(typed) != CODE_LENGTH or not hmac.compare_digest(_digest(data["n"], data["e"], typed), data["h"]):
        return None, ("attempts" if _bump(tries_key) >= MAX_ATTEMPTS else "wrong")
    # Right: once only, whichever process sees it first.
    if _bump(f"feather:sign-in-code:{data['n']}:used") > 1:
        return None, "expired"
    session.pop(PENDING_KEY, None)
    return data["e"], None


def tries_left() -> int:
    data = pending()
    if data is None:
        return 0
    return max(0, MAX_ATTEMPTS - _count(f"feather:sign-in-code:{data['n']}:tries"))


def _app_name() -> str:
    """The app's name for people, from APP_NAME. Flask's own name for the app
    is usually just "app", which is no name to put in an email."""
    name = _setting("APP_NAME") or ""
    return name if name and name != "app" else ""


def code_email_html(code: str, name: str, minutes: int) -> str:
    """The email for Resend: the code alone, large and centred."""
    return (
        '<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;'
        'max-width:480px;margin:0 auto;padding:32px 24px;color:#111827;text-align:center;">'
        f'<p style="font-size:16px;margin:0 0 24px;">Your code to sign in to {html.escape(name)}:</p>'
        '<p style="font-family:\'SF Mono\',SFMono-Regular,Menlo,Consolas,\'Liberation Mono\',monospace;'
        'font-size:36px;font-weight:700;letter-spacing:10px;margin:0 0 24px;padding:16px 8px;'
        f'background:#F3F4F6;border-radius:8px;">{html.escape(code)}</p>'
        f'<p style="font-size:14px;color:#6B7280;margin:0;">It works once, in the browser where you asked for it, '
        f'and expires in {minutes} minutes. If you didn\'t ask to sign in, ignore this email.</p>'
        "</div>"
    )


def send_code(email: str, code: str) -> bool:
    """Send ``code`` to ``email`` by whichever way is configured."""
    relay_url = _setting("SIGN_IN_RELAY_URL")
    relay_token = _setting("SIGN_IN_RELAY_TOKEN")
    if relay_url and relay_token:
        try:
            response = requests.post(
                relay_url,
                json={"email": email, "code": code, "app_name": _app_name(), "minutes": _minutes()},
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
                "subject": f"{code} is your code for {name}",
                "text": (
                    f"Your code to sign in to {name}: {code}\n\n"
                    f"It works once, in the browser where you asked for it, and expires in {minutes} "
                    "minutes. If you didn't ask to sign in, ignore this email."
                ),
                "html": code_email_html(code, name, minutes),
            })
        except Exception as exc:
            logger.error("Sign-in email not sent: %s", type(exc).__name__)
            return False
        return True

    # Only in development or tests is the code written to the log. Anywhere
    # else a log line holding a live code helps whoever reads the logs sign in.
    if current_app.debug or current_app.testing:
        logger.info("No way to send email is configured; sign-in code for %s: %s", email, code)
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
        code_length=CODE_LENGTH,
        **context,
    )


def _404_unless_enabled():
    from flask import abort

    if not enabled():
        abort(404)


@email_auth_bp.get("/login")
def login():
    """Ask for an email address."""
    from feather.auth.google import _safe_next

    _404_unless_enabled()
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
    """Email a code, and ask for it, whether or not the address has an account."""
    _404_unless_enabled()
    email = _normalise(request.form.get("email"))
    if not _EMAIL_RE.match(email) or len(email) > 254:
        return _render("form", error="Enter an email address, like you@example.com.", email=email), 400
    if not send_code(email, start(email)):
        session.pop(PENDING_KEY, None)
        return _render("form", error="The email couldn't be sent. Try again in a minute.", email=email), 503
    return _render("code", email=email)


@email_auth_bp.post("/resend")
def resend():
    """A new code to the address this browser is signing in with."""
    _404_unless_enabled()
    data = session.get(PENDING_KEY)
    email = data.get("e") if isinstance(data, dict) else None
    if not email:
        return redirect(url_for("email_auth.login"))
    if not send_code(email, start(email)):
        return _render("code", email=email, error="The email couldn't be sent. Try again in a minute."), 503
    return _render("code", email=email, notice="We sent a new code. Earlier ones no longer work.")


@email_auth_bp.post("/verify")
def verify_post():
    """Sign in with the code, once."""
    from feather.auth.google import _get_or_create_user, _safe_next, _set_toast

    _404_unless_enabled()
    email, problem = check(request.form.get("code"))
    if problem == "wrong":
        left = tries_left()
        message = f"That code isn't right. {left} {'try' if left == 1 else 'tries'} left."
        return _render("code", email=pending()["e"], error=message), 400
    if problem:
        session.pop(PENDING_KEY, None)
        return _render("expired", reason=problem), 400

    user = _get_or_create_user({"email": email, "email_verified": True}, None, source="email")
    next_url = _safe_next(session.pop("next", None)) or url_for("page.home")
    if user is None:
        if not session.pop("_auth_error_handled", False) and not session.pop("_auth_silent_redirect", False):
            _set_toast("Sign-in failed. Please try again.", "error")
        return redirect(next_url)

    login_user(user, remember=True, force=True)
    return redirect(next_url)
