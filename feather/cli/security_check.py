"""feather security-check - Audit a project's production security settings.

Runs a set of cheap, offline checks against the application's effective
configuration and prints one line per check::

    $ feather security-check
    PASS  secret_key           SECRET_KEY is 64 chars
    FAIL  debug                DEBUG is on in production
          remedy: Set FLASK_DEBUG=0 (and DEBUG = False in ProductionConfig)

Exit code is 1 if any check FAILs, 0 otherwise (WARN and SKIP do not fail
the run). Use ``--json`` for machine-readable output.

Two modes:

* **app** - ``app.py`` is importable, so the live ``app.config`` is read.
  This is the accurate mode: it sees config.py, .env and defaults together.
* **env** - the app could not be imported (or there is no app.py). Values
  come from the ``.env`` file plus the process environment, layered on the
  framework defaults.
"""

import json as json_module
import os
import re
import sys
from importlib.metadata import PackageNotFoundError, version as installed_version
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import click

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"

DEV_SECRET_KEYS = {
    "dev-secret-key-change-in-production",
    "dev",
    "development",
    "changeme",
    "change-me",
    "secret",
    "your-secret-key",
}

MIN_SECRET_KEY_LENGTH = 32

#: Minimum versions with no known advisories at the 0.9.6 release.
MIN_DEPENDENCY_VERSIONS = {
    "flask": "3.1.3",
    "werkzeug": "3.1.5",
    "authlib": "1.6.5",
    "requests": "2.32.4",
    "weasyprint": "70",
    "jinja2": "3.1.6",
    "urllib3": "2.5.0",
}

TRUE_VALUES = {"1", "true", "yes", "on", "t", "y"}
FALSE_VALUES = {"0", "false", "no", "off", "f", "n", ""}

KNOWN_ENV_KEYS = [
    "FLASK_ENV", "FLASK_CONFIG", "FLASK_DEBUG", "DEBUG", "SECRET_KEY",
    "SESSION_COOKIE_SECURE", "SESSION_COOKIE_HTTPONLY", "SESSION_COOKIE_SAMESITE",
    "REMEMBER_COOKIE_SECURE", "REMEMBER_COOKIE_HTTPONLY", "REMEMBER_COOKIE_SAMESITE",
    "WTF_CSRF_ENABLED", "JOB_BACKEND", "JOB_SERIALIZER", "REDIS_URL", "CACHE_URL",
    "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "OAUTH_CALLBACK_URL",
    "TRUSTED_HOSTS", "FEATHER_SECURITY_HEADERS",
]

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "redis", "host.docker.internal"}


class Check:
    """One check result."""

    def __init__(self, name: str, status: str, message: str, remedy: str = ""):
        self.name = name
        self.status = status
        self.message = message
        self.remedy = remedy

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "remedy": self.remedy,
        }


# =============================================================================
# Value coercion
# =============================================================================


def as_bool(value: Any) -> Optional[bool]:
    """Coerce a config/env value to a bool, or None when unset/unknown."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return None


def parse_version(text: str) -> tuple:
    """Parse a version string into a comparable tuple of ints.

    Non-numeric suffixes (rc1, .post1, +local) are dropped, which is enough
    for a "at least this release" comparison.
    """
    parts = []
    for chunk in re.split(r"[.\-+]", str(text)):
        match = re.match(r"^(\d+)", chunk)
        if not match:
            break
        parts.append(int(match.group(1)))
    return tuple(parts) or (0,)


# =============================================================================
# Config sources
# =============================================================================


def read_env_file(path: Path) -> dict:
    """Parse a .env file into a dict without touching os.environ."""
    values = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


class Settings:
    """Effective settings, from a live app config or from .env + environ."""

    def __init__(self, mode: str, values: dict, notes: Optional[list] = None):
        self.mode = mode  # 'app' or 'env'
        self.values = values
        self.notes = notes or []

    def get(self, key: str, default: Any = None) -> Any:
        value = self.values.get(key)
        return default if value is None else value

    def is_set(self, key: str) -> bool:
        value = self.values.get(key)
        return value is not None and str(value) != ""


def load_app_settings(project_dir: Path) -> Optional[Settings]:
    """Import the project's app.py and return its live config, or None."""
    app_file = project_dir / "app.py"
    if not app_file.exists():
        return None

    cwd = str(project_dir)
    added = cwd not in sys.path
    if added:
        sys.path.insert(0, cwd)
    try:
        from app import app  # noqa: F401  (project module)

        return Settings("app", dict(app.config))
    except Exception as e:  # noqa: BLE001 - any import-time failure degrades to env mode
        return Settings(
            "env",
            {},
            notes=[f"Could not import app.py ({e.__class__.__name__}: {e}); "
                   "checked .env and environment instead."],
        )
    finally:
        if added and cwd in sys.path:
            sys.path.remove(cwd)


def framework_defaults(env: Optional[str]) -> dict:
    """Config-class defaults for the detected environment.

    In env mode there is no live app, so settings that a project never puts
    in ``.env`` (cookie flags, for example) come from the config class the
    app would have loaded.
    """
    from feather.core import config as config_module

    config_class = {
        "production": config_module.ProductionConfig,
        "testing": config_module.TestingConfig,
    }.get(env or "", config_module.DevelopmentConfig)

    return {
        key: getattr(config_class, key)
        for key in dir(config_class)
        if key.isupper()
    }


def load_env_settings(project_dir: Path, env_file: Optional[str], notes: list) -> Settings:
    """Build settings from an env file plus the process environment."""
    values = {}

    path = Path(env_file) if env_file else project_dir / ".env"
    if not path.is_absolute():
        path = project_dir / path
    if path.exists():
        values.update(read_env_file(path))
        notes.append(f"Read {path.name}")
    elif env_file:
        raise click.ClickException(f"Env file not found: {env_file}")

    # Process environment wins over the file, matching python-dotenv's default
    for key in list(values) + KNOWN_ENV_KEYS:
        if key in os.environ:
            values[key] = os.environ[key]

    # Layer explicit values over the config-class defaults for the detected
    # environment, so unset-but-defaulted settings are judged correctly.
    env = detect_environment(Settings("env", values))
    layered = framework_defaults(env)
    layered.update(values)

    return Settings("env", layered, notes=notes)


def resolve_settings(project_dir: Path, env_file: Optional[str]) -> Settings:
    """Prefer the live app config; fall back to .env + environment."""
    notes: list = []

    if env_file:
        # Explicit env file: the user is auditing a deployment file, not this app
        return load_env_settings(project_dir, env_file, notes)

    app_settings = load_app_settings(project_dir)
    if app_settings is not None and app_settings.mode == "app":
        return app_settings
    if app_settings is not None:
        notes.extend(app_settings.notes)

    return load_env_settings(project_dir, None, notes)


# =============================================================================
# Environment detection
# =============================================================================


def detect_environment(settings: Settings) -> Optional[str]:
    """Return 'production', 'development', 'testing', or None if unset."""
    from feather.core.config import CONFIG_SHORTCUTS

    for key in ("FLASK_CONFIG", "FLASK_ENV"):
        raw = os.environ.get(key) or settings.values.get(key)
        if not raw:
            continue
        text = str(raw).strip()
        expanded = CONFIG_SHORTCUTS.get(text.lower(), text)
        lowered = expanded.lower()
        if "production" in lowered or "prod" in lowered:
            return "production"
        if "testing" in lowered or "test" in lowered:
            return "testing"
        return "development"

    return None


# =============================================================================
# Individual checks
# =============================================================================


def check_secret_key(settings: Settings) -> Check:
    secret = settings.get("SECRET_KEY")
    if not secret:
        return Check(
            "secret_key", FAIL, "SECRET_KEY is not set",
            'Generate one: python -c "import secrets; print(secrets.token_hex(32))"',
        )
    secret = str(secret)
    if secret.lower() in DEV_SECRET_KEYS or "change-in-production" in secret.lower():
        return Check(
            "secret_key", FAIL, "SECRET_KEY is still the development default",
            'Generate one: python -c "import secrets; print(secrets.token_hex(32))"',
        )
    if len(secret) < MIN_SECRET_KEY_LENGTH:
        return Check(
            "secret_key", FAIL,
            f"SECRET_KEY is only {len(secret)} chars (need {MIN_SECRET_KEY_LENGTH}+)",
            'Generate one: python -c "import secrets; print(secrets.token_hex(32))"',
        )
    return Check("secret_key", PASS, f"SECRET_KEY is {len(secret)} chars")


def check_environment(env: Optional[str]) -> Check:
    if env is None:
        return Check(
            "environment", FAIL,
            "Neither FLASK_CONFIG nor FLASK_ENV is set; the app falls back to development",
            "Set FLASK_ENV=production (or FLASK_CONFIG=production) in the deployment environment",
        )
    return Check("environment", PASS, f"Environment is {env}")


def check_debug(settings: Settings, production: bool) -> Check:
    if not production:
        return Check("debug", SKIP, "Not production; DEBUG not checked")

    for key in ("FLASK_DEBUG", "DEBUG"):
        value = as_bool(os.environ.get(key, settings.values.get(key)))
        if value:
            return Check(
                "debug", FAIL, f"{key} is on in production",
                "Set FLASK_DEBUG=0 and DEBUG = False on ProductionConfig; "
                "the debugger allows remote code execution",
            )
    return Check("debug", PASS, "DEBUG is off")


def check_bool_setting(
    settings: Settings, name: str, key: str, production: bool, remedy: str
) -> Check:
    if not production:
        return Check(name, SKIP, f"Not production; {key} not checked")

    value = as_bool(settings.values.get(key))
    if value is True:
        return Check(name, PASS, f"{key} is true")
    if value is False:
        return Check(name, FAIL, f"{key} is false in production", remedy)
    return Check(name, FAIL, f"{key} is not set in production", remedy)


def check_samesite(settings: Settings, production: bool) -> Check:
    if not production:
        return Check("cookie_samesite", SKIP, "Not production; SameSite not checked")

    session = settings.get("SESSION_COOKIE_SAMESITE")
    remember = settings.get("REMEMBER_COOKIE_SAMESITE")
    missing = [k for k, v in (("SESSION_COOKIE_SAMESITE", session),
                              ("REMEMBER_COOKIE_SAMESITE", remember)) if not v]
    if missing:
        return Check(
            "cookie_samesite", WARN, f"{', '.join(missing)} not set",
            "Set SESSION_COOKIE_SAMESITE = 'Lax' (and the same for REMEMBER_COOKIE_SAMESITE)",
        )
    loose = [
        k for k, v in (("SESSION_COOKIE_SAMESITE", session),
                       ("REMEMBER_COOKIE_SAMESITE", remember))
        if str(v).lower() == "none"
    ]
    if loose:
        return Check(
            "cookie_samesite", WARN, f"{', '.join(loose)} is 'None' (cookies sent cross-site)",
            "Use 'Lax' unless a third-party embed genuinely needs SameSite=None",
        )
    return Check("cookie_samesite", PASS, f"SameSite is {session}")


def check_csrf(settings: Settings) -> Check:
    value = as_bool(settings.values.get("WTF_CSRF_ENABLED"))
    if value is False:
        return Check(
            "csrf", FAIL, "WTF_CSRF_ENABLED is false",
            "Remove WTF_CSRF_ENABLED=false; Feather enables CSRF protection by default",
        )
    if value is None:
        return Check("csrf", PASS, "WTF_CSRF_ENABLED unset (defaults to on)")
    return Check("csrf", PASS, "WTF_CSRF_ENABLED is true")


def check_job_serializer(settings: Settings) -> Check:
    backend = str(settings.get("JOB_BACKEND", "sync")).lower()
    if backend != "rq":
        return Check("job_serializer", SKIP, f"JOB_BACKEND is '{backend}'; serializer not checked")

    serializer = str(settings.get("JOB_SERIALIZER", "pickle")).lower()
    if serializer != "json":
        return Check(
            "job_serializer", WARN,
            f"JOB_BACKEND=rq with JOB_SERIALIZER={serializer}",
            "Set JOB_SERIALIZER=json; pickled payloads execute code when Redis is compromised",
        )
    return Check("job_serializer", PASS, "JOB_BACKEND=rq uses the json serializer")


def check_redis_url(settings: Settings, name: str, key: str) -> Check:
    url = settings.get(key)
    if not url:
        return Check(name, SKIP, f"{key} not set")

    parsed = urlparse(str(url))
    host = (parsed.hostname or "").lower()
    if host in LOCAL_HOSTS or host.endswith(".internal"):
        return Check(name, PASS, f"{key} points at {host or 'localhost'}")
    if parsed.password:
        return Check(name, PASS, f"{key} has credentials")
    return Check(
        name, WARN, f"{key} targets remote host '{host}' with no password",
        f"Use a URL with credentials: {parsed.scheme or 'redis'}://:PASSWORD@{host}:{parsed.port or 6379}",
    )


def check_oauth_callback(settings: Settings, production: bool) -> Check:
    google_configured = settings.is_set("GOOGLE_CLIENT_ID") and settings.is_set("GOOGLE_CLIENT_SECRET")
    if not google_configured:
        return Check("oauth_callback_url", SKIP, "Google auth not configured")
    if not production:
        return Check("oauth_callback_url", SKIP, "Not production; OAUTH_CALLBACK_URL not checked")

    callback = settings.get("OAUTH_CALLBACK_URL")
    if not callback:
        return Check(
            "oauth_callback_url", WARN,
            "Google auth is configured but OAUTH_CALLBACK_URL is not set",
            "Set OAUTH_CALLBACK_URL to the exact https:// redirect URI registered with Google",
        )
    if not str(callback).lower().startswith("https://"):
        return Check(
            "oauth_callback_url", WARN, f"OAUTH_CALLBACK_URL is not https: {callback}",
            "Use an https:// callback URL in production",
        )
    return Check("oauth_callback_url", PASS, "OAUTH_CALLBACK_URL is set")


def check_trusted_hosts(settings: Settings, production: bool) -> Check:
    if not production:
        return Check("trusted_hosts", SKIP, "Not production; TRUSTED_HOSTS not checked")

    hosts = settings.get("TRUSTED_HOSTS")
    if not hosts:
        return Check(
            "trusted_hosts", WARN, "TRUSTED_HOSTS is not set",
            "Set TRUSTED_HOSTS to your domain(s) so forged Host headers cannot poison links",
        )
    return Check("trusted_hosts", PASS, f"TRUSTED_HOSTS is set ({hosts})")


def check_security_headers(settings: Settings, production: bool) -> Check:
    value = as_bool(settings.values.get("FEATHER_SECURITY_HEADERS"))
    if value is False:
        status = FAIL if production else WARN
        return Check(
            "security_headers", status, "FEATHER_SECURITY_HEADERS is disabled",
            "Remove FEATHER_SECURITY_HEADERS=false; it drops CSP, X-Frame-Options and HSTS",
        )
    return Check("security_headers", PASS, "Security headers enabled")


def check_dependencies() -> list:
    checks = []
    for package, minimum in sorted(MIN_DEPENDENCY_VERSIONS.items()):
        name = f"dep_{package}"
        try:
            current = installed_version(package)
        except PackageNotFoundError:
            checks.append(Check(name, SKIP, f"{package} is not installed"))
            continue
        except Exception as e:  # noqa: BLE001
            checks.append(Check(name, SKIP, f"{package} version unreadable ({e})"))
            continue

        if parse_version(current) < parse_version(minimum):
            checks.append(Check(
                name, FAIL, f"{package} {current} is below the minimum {minimum}",
                f"pip install --upgrade '{package}>={minimum}'",
            ))
        else:
            checks.append(Check(name, PASS, f"{package} {current} >= {minimum}"))
    return checks


def check_extras() -> Check:
    """Report which optional extras are installed.

    Informational: a missing extra is only a problem if the app configures
    the feature that needs it, and the other checks catch that (a redis://
    CACHE_URL with no redis extra, for instance).
    """
    from feather._optional import installed_extras

    report = installed_extras()
    present = sorted(name for name, info in report.items() if info["installed"])
    absent = sorted(name for name, info in report.items() if not info["installed"])

    message = f"installed: {', '.join(present) or 'none'}"
    if absent:
        message += f" | not installed: {', '.join(absent)}"
    return Check(
        "extras", PASS, message,
        "Install what the app uses, e.g. pip install 'feather-framework[redis,postgres]'",
    )


def check_env_in_gitignore(project_dir: Path) -> Check:
    gitignore = project_dir / ".gitignore"
    remedy = "Add a line '.env' to .gitignore so secrets never reach the repository"
    if not gitignore.exists():
        return Check("env_in_gitignore", FAIL, "No .gitignore in the project", remedy)

    for raw_line in gitignore.read_text().splitlines():
        line = raw_line.strip()
        if line in (".env", "*.env", ".env*", "/.env", ".env.*"):
            return Check("env_in_gitignore", PASS, f".gitignore lists '{line}'")
    return Check("env_in_gitignore", FAIL, ".env is not listed in .gitignore", remedy)


# =============================================================================
# Runner
# =============================================================================


def run_checks(project_dir: Path, env_file: Optional[str], force_production: bool = False) -> dict:
    """Run every check and return a result dict (also used by --json)."""
    settings = resolve_settings(project_dir, env_file)
    env = detect_environment(settings)
    production = force_production or env == "production"

    checks = [
        check_secret_key(settings),
        check_environment(env) if not force_production
        else Check("environment", PASS, "Production rules forced with --production"),
        check_debug(settings, production),
        check_bool_setting(
            settings, "session_cookie_secure", "SESSION_COOKIE_SECURE", production,
            "Set SESSION_COOKIE_SECURE = True so the session cookie is HTTPS-only",
        ),
        check_bool_setting(
            settings, "session_cookie_httponly", "SESSION_COOKIE_HTTPONLY", production,
            "Set SESSION_COOKIE_HTTPONLY = True so JavaScript cannot read the session cookie",
        ),
        check_bool_setting(
            settings, "remember_cookie_secure", "REMEMBER_COOKIE_SECURE", production,
            "Set REMEMBER_COOKIE_SECURE = True; Flask-Login sets no cookie flags by default",
        ),
        check_bool_setting(
            settings, "remember_cookie_httponly", "REMEMBER_COOKIE_HTTPONLY", production,
            "Set REMEMBER_COOKIE_HTTPONLY = True; Flask-Login sets no cookie flags by default",
        ),
        check_samesite(settings, production),
        check_csrf(settings),
        check_job_serializer(settings),
        check_redis_url(settings, "redis_url", "REDIS_URL"),
        check_redis_url(settings, "cache_url", "CACHE_URL"),
        check_oauth_callback(settings, production),
        check_trusted_hosts(settings, production),
        check_security_headers(settings, production),
        check_env_in_gitignore(project_dir),
        check_extras(),
    ]
    checks.extend(check_dependencies())

    summary = {
        "pass": sum(1 for c in checks if c.status == PASS),
        "warn": sum(1 for c in checks if c.status == WARN),
        "fail": sum(1 for c in checks if c.status == FAIL),
        "skip": sum(1 for c in checks if c.status == SKIP),
    }

    from feather._optional import installed_extras

    return {
        "ok": summary["fail"] == 0,
        "extras": installed_extras(),
        "mode": settings.mode,
        "environment": env,
        "production_rules": production,
        "notes": settings.notes,
        "summary": summary,
        "checks": [c.as_dict() for c in checks],
    }


STATUS_COLORS = {PASS: "green", WARN: "yellow", FAIL: "red", SKIP: "white"}


@click.command(name="security-check")
@click.option("--env-file", default=None, help="Read settings from this env file instead of importing the app.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--production", "force_production", is_flag=True, help="Apply production rules regardless of FLASK_ENV.")
@click.option("--path", "project_path", default=".", help="Project directory to audit (default: current directory).")
def security_check(env_file: Optional[str], as_json: bool, force_production: bool, project_path: str):
    """Audit production security settings.

    Reads the app's effective configuration (importing app.py when possible,
    otherwise the .env file and environment) and reports one line per check.
    Exits 1 if any check FAILs.

    \b
    Examples:
      feather security-check                     Audit the current project
      feather security-check --json              Machine-readable output
      feather security-check --env-file prod.env Audit a deployment env file
      feather security-check --production        Force production rules
    """
    project_dir = Path(project_path).resolve()
    if not project_dir.exists():
        raise click.ClickException(f"Directory not found: {project_path}")

    result = run_checks(project_dir, env_file, force_production)

    if as_json:
        click.echo(json_module.dumps(result, indent=2))
    else:
        name_width = max(len(c["name"]) for c in result["checks"])
        for note in result["notes"]:
            click.echo(click.style(f"note: {note}", fg="cyan"))
        if result["notes"]:
            click.echo()

        for check in result["checks"]:
            status = click.style(f"{check['status']:<4}", fg=STATUS_COLORS[check["status"]], bold=True)
            click.echo(f"{status}  {check['name']:<{name_width}}  {check['message']}")
            if check["remedy"] and check["status"] in (WARN, FAIL):
                click.echo(f"      {' ' * name_width}  remedy: {check['remedy']}")

        summary = result["summary"]
        click.echo()
        click.echo(
            f"{summary['pass']} passed, {summary['warn']} warnings, "
            f"{summary['fail']} failed, {summary['skip']} skipped "
            f"(mode: {result['mode']}, environment: {result['environment'] or 'unset'})"
        )

    if not result["ok"]:
        sys.exit(1)
