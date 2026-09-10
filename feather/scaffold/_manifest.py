"""Which overlays apply to a set of options, and what the tokens expand to.

``OVERLAYS`` is the ordered list of overlay directories with the condition
each one is applied under. Order matters: a later overlay replaces a file or a
fragment an earlier one supplied.

``token_values`` returns the tokens that come from the options rather than
from a fragment file. Everything else - the optional blocks of ``config.py``,
``.env`` and the AGENTS.md body, the admin routes only multi-tenant apps get -
comes from an overlay's ``_fragments/`` directory and is filled in by
``_render``.
"""

from typing import Any, Callable, NamedTuple


class Overlay(NamedTuple):
    """One overlay directory and the condition it is applied under."""

    name: str
    applies: Callable[[dict], bool]
    doc: str


def _has_database(o: dict) -> bool:
    return o.get("database", "postgresql") != "none"


def _auth(o: dict) -> bool:
    return bool(o.get("include_auth"))


def _multi(o: dict) -> bool:
    return _auth(o) and o.get("tenant_mode") == "multi"


#: Applied in this order. Every project gets ``base``; the rest are conditional.
OVERLAYS: list[Overlay] = [
    Overlay("base", lambda o: True, "Every app."),
    Overlay("db", _has_database, "A database was selected."),
    Overlay("auth", _auth, "Google OAuth, the admin panel and the User model."),
    Overlay(
        "auth_manual_approval",
        lambda o: _auth(o) and not o.get("auto_approve_users"),
        "New users wait for an admin to approve them.",
    ),
    Overlay(
        "auth_auto_approval",
        lambda o: _auth(o) and bool(o.get("auto_approve_users")),
        "New users are active as soon as they sign in.",
    ),
    Overlay("multi_tenant", _multi, "Tenants, and tenant-scoped admin queries."),
    Overlay("cache", lambda o: bool(o.get("include_cache")), "Redis cache."),
    Overlay("jobs", lambda o: bool(o.get("include_jobs")), "Background jobs."),
    Overlay(
        "cache_jobs",
        lambda o: bool(o.get("include_cache")) and bool(o.get("include_jobs")),
        "Cache and jobs share one REDIS_URL.",
    ),
    Overlay("storage", lambda o: bool(o.get("include_storage")), "Cloud storage."),
    Overlay("email", lambda o: bool(o.get("include_email")), "Resend email."),
    Overlay(
        "auth_email",
        lambda o: _auth(o) and bool(o.get("include_email")),
        "The admin panel's send-email tool.",
    ),
]

#: Tokens whose value comes from the options rather than from a fragment file.
TOKENS: tuple[str, ...] = (
    "APP_NAME",
    "DB_URL",
    "ADMIN_EMAIL_LINE",
    "ACCOUNT_NAME_EXPR",
    "TEST_ADMIN_DISPLAY_NAME",
    "TEST_USER_DISPLAY_NAME",
    "REQUIREMENT_SPEC",
    "MULTI_TENANT",
    "STORAGE_BACKEND",
    "RECIPIENT_ERROR",
    "USER_FIELD_DEFS",
    "USER_FIELD_DOCS",
    "AGENTS_FEATURES",
)


def overlays_for(options: dict) -> list[str]:
    """Return the overlay directory names that apply, in application order."""
    return [o.name for o in OVERLAYS if o.applies(options)]


def _user_fields(options: dict) -> dict:
    fields = options.get("user_fields")
    if fields is None:
        fields = {"display_name": True, "profile_image_url": True}
    return fields


def _display_name(options: dict) -> bool:
    """Whether the generated admin tests seed a ``display_name``.

    ``new.py`` reads this off the raw ``user_fields`` argument rather than off
    the defaulted dict, so ``user_fields=None`` - the default, and what
    ``feather new`` passes unless the prompt ran - means no ``display_name``
    in the tests even though the model does have the column.
    """
    fields = options.get("user_fields")
    return bool(fields and fields.get("display_name", True))


def _feather_version() -> str:
    from feather.cli.new import _get_feather_version

    return _get_feather_version()


def _requirement_spec(options: dict) -> str:
    """The requirements.txt line, naming the extras this app actually needs.

    Since 0.9.8 a bare ``feather-framework`` installs neither psycopg2 nor
    redis, resend, gunicorn or pytest, so a generated app that enables a
    feature and does not name its extra fails at startup rather than at
    install time. `prod` and `test` are always included: every app is meant
    to be deployable with `feather start` and testable with `feather test`.
    """
    from feather._optional import requirement_spec

    extras = {"prod", "test"}
    if (options.get("database") or "none") == "postgresql":
        extras.add("postgres")
    if options.get("include_cache") or options.get("include_jobs"):
        extras.add("redis")
    if options.get("include_email"):
        extras.add("email")
    if (options.get("storage_backend") or "") == "gcs":
        extras.add("gcs")
    return requirement_spec(_feather_version(), sorted(extras))


def token_values(options: dict) -> dict[str, Any]:
    """Return the option-derived token values for one set of options.

    Keys are bare names; ``_render`` wraps them in ``__FEATHER_..__``.
    """
    fields = _user_fields(options)
    multi = options.get("tenant_mode") == "multi"

    field_defs = ""
    field_docs = ""
    if fields.get("display_name", True):
        field_defs += "    display_name = db.Column(db.String(100))\n"
        field_docs += "        display_name: Display name for UI\n"
    if fields.get("profile_image_url", True):
        field_defs += "    profile_image_url = db.Column(db.String(500))\n"
        field_docs += "        profile_image_url: URL to profile image (from Google OAuth)\n"

    features = []
    if _has_database(options):
        features.append(f"Database: {options.get('database')}")
    if _auth(options):
        features.append(f"Auth: {'multi-tenant' if multi else 'single-tenant'}")
    if options.get("include_cache"):
        features.append("Cache: yes")
    if options.get("include_jobs"):
        features.append("Jobs: yes")

    return {
        "APP_NAME": options.get("name", ""),
        "DB_URL": options.get("db_url") or "",
        "ADMIN_EMAIL_LINE": (
            f'"{options["admin_email"]}"'
            if options.get("admin_email")
            else "None  # Set your admin email here"
        ),
        "ACCOUNT_NAME_EXPR": (
            'user.display_name or user.email.split("@")[0]'
            if fields.get("display_name", True)
            else 'user.email.split("@")[0]'
        ),
        "TEST_ADMIN_DISPLAY_NAME": (
            '\n            display_name="Test Admin",' if _display_name(options) else ""
        ),
        "TEST_USER_DISPLAY_NAME": (
            '\n            display_name="Test User",' if _display_name(options) else ""
        ),
        "REQUIREMENT_SPEC": _requirement_spec(options),
        "MULTI_TENANT": "True" if multi else "False",
        "STORAGE_BACKEND": options.get("storage_backend") or "local",
        "RECIPIENT_ERROR": (
            "Recipient must be an existing user in your organization."
            if multi
            else "Recipient must be an existing user."
        ),
        "USER_FIELD_DEFS": field_defs,
        "USER_FIELD_DOCS": field_docs,
        "AGENTS_FEATURES": ", ".join(features) if features else "Minimal (no database)",
    }
