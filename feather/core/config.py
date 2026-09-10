"""Configuration loading utilities."""

import importlib
import os
from datetime import timedelta
from typing import Callable, Optional, Type

from dotenv import find_dotenv, load_dotenv


def _ensure_dotenv_loaded() -> None:
    """Load the project's .env file if it has not been loaded yet.

    The built-in Config below reads os.environ, so the .env file has to be in
    the environment *before* those reads happen. Feather also calls
    load_dotenv() from Feather.__init__, but that runs after this module is
    imported - without this call a project with a .env and no config.py would
    silently get stale defaults.

    Idempotent and non-destructive: override=False means real environment
    variables always win over .env, and usecwd searches from the project
    directory rather than the (possibly editable) framework checkout.
    """
    try:
        load_dotenv(find_dotenv(usecwd=True), override=False)
    except Exception:  # pragma: no cover - dotenv must never break startup
        pass


_ensure_dotenv_loaded()

# Shorthand names for config classes
# Allows FLASK_CONFIG=production instead of FLASK_CONFIG=ProductionConfig
CONFIG_SHORTCUTS = {
    "development": "DevelopmentConfig",
    "dev": "DevelopmentConfig",
    "production": "ProductionConfig",
    "prod": "ProductionConfig",
    "testing": "TestingConfig",
    "test": "TestingConfig",
}


#: Strings that mean "true" in a .env file or the environment.
TRUE_VALUES = ("true", "1", "yes", "on", "y", "t")


def as_bool(value) -> bool:
    """Coerce an env/config value to a bool the way Feather always has.

    ``"true"``, ``"1"``, ``"yes"``, ``"on"``, ``"y"``, ``"t"`` (any case)
    are true; everything else, including the empty string and None, is
    false.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in TRUE_VALUES


def get_setting(key: str, default=None, cast: Optional[Callable] = None):
    """Read one setting from the app config, falling back to the environment.

    This is the single path backends use to read their configuration, so
    ``feather.jobs`` and ``feather.cache`` no longer duplicate the same
    ``os.environ.get(..., default)`` chains that :data:`Config` already
    encodes.

    Lookup order:

    1. ``current_app.config[key]``, when there is an app context and the
       value is not ``None``. A ``None`` counts as unset because a
       project's config.py routinely writes
       ``JOB_SERIALIZER = os.environ.get("JOB_SERIALIZER")``, leaving the
       key present but empty - falling back to the framework default there
       used to put the queue and the worker on different serializers.
    2. ``os.environ[key]``, for a script or CLI command with no app, and for
       an app whose config class predates the key.
    3. ``default``.

    Args:
        key: Config/environment key, e.g. ``"JOB_BACKEND"``.
        default: Value when neither source has one.
        cast: Applied to any value that is still a string, e.g. ``int`` or
            :func:`as_bool`. Environment values are always strings; a
            config.py that assigns ``JOB_MAX_WORKERS = "8"`` gets the same
            treatment instead of handing a string to a thread pool. A value
            the cast cannot parse falls back to ``default``.

    Returns:
        The resolved value.

    Example::

        backend = get_setting("JOB_BACKEND", "sync")
        workers = get_setting("JOB_MAX_WORKERS", 4, cast=int)
        monitor = get_setting("JOB_ENABLE_MONITORING", False, cast=as_bool)
    """
    from feather.core.registry import current_app_or_none

    app = current_app_or_none()
    if app is not None:
        value = app.config.get(key)
        if value is not None:
            return _cast(value, cast, default)

    raw = os.environ.get(key)
    if raw is not None and raw != "":
        return _cast(raw, cast, default)

    return default


def _cast(value, cast: Optional[Callable], default):
    """Apply `cast` to a string value; leave already-typed values alone."""
    if cast is None or not isinstance(value, str):
        return value
    try:
        return cast(value)
    except (TypeError, ValueError):
        return default


def _env_config_values() -> dict:
    """Read every environment-derived setting fresh from os.environ.

    Called at import time and again from load_config(), so values picked up
    from a .env file loaded later are never stale.
    """
    return {
        "SECRET_KEY": os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production"),
        "DATABASE_URL": os.environ.get("DATABASE_URL", "sqlite:///app.db"),
        # Session configuration
        "PERMANENT_SESSION_LIFETIME": timedelta(
            days=int(os.environ.get("SESSION_LIFETIME_DAYS", "7"))
        ),
        "REMEMBER_COOKIE_DURATION": timedelta(
            days=int(os.environ.get("REMEMBER_COOKIE_DAYS", "365"))
        ),
        "SESSION_PROTECTION": os.environ.get("SESSION_PROTECTION", "basic"),
        # Google OAuth (optional)
        "GOOGLE_CLIENT_ID": os.environ.get("GOOGLE_CLIENT_ID"),
        "GOOGLE_CLIENT_SECRET": os.environ.get("GOOGLE_CLIENT_SECRET"),
        "OAUTH_CALLBACK_URL": os.environ.get("OAUTH_CALLBACK_URL"),
        # Multi-tenant settings
        "FEATHER_MULTI_TENANT": os.environ.get("FEATHER_MULTI_TENANT", "").lower()
        in ("true", "1", "yes"),
        "FEATHER_ALLOW_PUBLIC_EMAILS": os.environ.get(
            "FEATHER_ALLOW_PUBLIC_EMAILS", ""
        ).lower()
        in ("true", "1", "yes"),
        "FEATHER_POST_LOGIN_CALLBACK": os.environ.get("FEATHER_POST_LOGIN_CALLBACK"),
        # Proxy / host hardening
        "FEATHER_PROXY_FIX": os.environ.get("FEATHER_PROXY_FIX", "true").lower()
        not in ("false", "0", "no"),
        "FEATHER_PROXY_FIX_NUM": int(os.environ.get("FEATHER_PROXY_FIX_NUM", "1")),
        "TRUSTED_HOSTS": parse_trusted_hosts(os.environ.get("TRUSTED_HOSTS")),
        # Discovery
        "FEATHER_LENIENT_DISCOVERY": os.environ.get(
            "FEATHER_LENIENT_DISCOVERY", ""
        ).lower()
        in ("true", "1", "yes"),
        # Vite dev server (used for island scripts in debug mode)
        "VITE_DEV_SERVER": os.environ.get("VITE_DEV_SERVER", "http://localhost:5173"),
        # Storage (optional)
        "STORAGE_BACKEND": os.environ.get("STORAGE_BACKEND", "local"),
        "GCS_BUCKET": os.environ.get("GCS_BUCKET"),
        # Cache (optional)
        "CACHE_BACKEND": os.environ.get("CACHE_BACKEND", "memory"),
        "CACHE_URL": os.environ.get("CACHE_URL"),
        "CACHE_DEFAULT_TTL": int(os.environ.get("CACHE_DEFAULT_TTL", "300")),
        # Background Jobs (optional)
        "JOB_BACKEND": os.environ.get("JOB_BACKEND", "sync"),
        "REDIS_URL": os.environ.get("REDIS_URL"),
        "JOB_MAX_WORKERS": int(os.environ.get("JOB_MAX_WORKERS", "4")),
        "JOB_ENABLE_MONITORING": os.environ.get("JOB_ENABLE_MONITORING", "").lower()
        in ("true", "1", "yes"),
    }


def parse_trusted_hosts(value):
    """Parse TRUSTED_HOSTS from a comma-separated string or a list.

    Returns None when unset, so Flask keeps its "any host" default.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (list, tuple, set)):
        hosts = [str(host).strip() for host in value]
    else:
        hosts = [host.strip() for host in str(value).split(",")]
    hosts = [host for host in hosts if host]
    return hosts or None


#: Backwards-compatible private alias.
_parse_trusted_hosts = parse_trusted_hosts


class Config:
    """Base configuration class.

    Environment-derived values (SECRET_KEY, DATABASE_URL, ...) are applied by
    reload_from_env() at import time and re-applied by load_config() after the
    project's .env file has been loaded.
    """

    @classmethod
    def reload_from_env(cls) -> None:
        """Re-read environment-derived settings from os.environ."""
        for key, value in _env_config_values().items():
            setattr(cls, key, value)

    # SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # CSRF token lifetime.
    # Flask-WTF expires tokens after one hour by default, on top of the session
    # lifetime. A form left open (a long write-up, a slow interview) then fails
    # with a confusing generic error. The session already bounds the token, so
    # None is the safer default; apps can still set their own limit.
    WTF_CSRF_TIME_LIMIT = None

    # Cookie hardening. Secure is set per environment (ProductionConfig);
    # HttpOnly and SameSite=Lax are safe everywhere. Flask-Login sets none
    # of the REMEMBER_COOKIE_* flags by default.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"

    # Session protection ('basic'), Google OAuth, multi-tenant, storage, cache,
    # job and proxy settings all come from _env_config_values() above.


# Populate the environment-derived settings for the first time.
Config.reload_from_env()


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


def load_config(config_class: Optional[str] = None) -> Type[Config]:
    """Load configuration class.

    Priority:
    1. Explicit config_class parameter
    2. FLASK_CONFIG environment variable
    3. Project's config.py file
    4. Default DevelopmentConfig

    Args:
        config_class: Optional config class name or path.

    Returns:
        Configuration class.
    """
    # Make sure a project .env has been applied, then refresh the built-in
    # config values so they reflect it (they were read at import time).
    _ensure_dotenv_loaded()
    Config.reload_from_env()

    # If explicit config class provided
    if config_class:
        return _import_config_class(config_class)

    # Check FLASK_CONFIG environment variable
    env_config = os.environ.get("FLASK_CONFIG")
    if env_config:
        return _import_config_class(env_config)

    # Try to load from project's config.py
    try:
        config_module = importlib.import_module("config")

        # Look for config dict mapping
        if hasattr(config_module, "config"):
            env = os.environ.get("FLASK_ENV", "development")
            config_map = config_module.config
            if env in config_map:
                return config_map[env]
            if "default" in config_map:
                return config_map["default"]

        # Look for specific config classes
        env = os.environ.get("FLASK_ENV", "development")
        class_name = f"{env.capitalize()}Config"
        if hasattr(config_module, class_name):
            return getattr(config_module, class_name)

        # Fall back to Config class
        if hasattr(config_module, "Config"):
            return config_module.Config

    except ImportError:
        pass

    # Fall back to the built-in config for this environment
    return _builtin_config_for(os.environ.get("FLASK_ENV", "development"))


def _builtin_config_for(name: str) -> Type[Config]:
    """Resolve an environment or class name to a built-in config class.

    Accepts both shorthands ('production', 'prod') and class names
    ('ProductionConfig'). Unknown names fall back to DevelopmentConfig.
    """
    class_name = CONFIG_SHORTCUTS.get((name or "").lower(), name)
    return {
        "ProductionConfig": ProductionConfig,
        "TestingConfig": TestingConfig,
        "DevelopmentConfig": DevelopmentConfig,
        "Config": Config,
    }.get(class_name, DevelopmentConfig)


def _import_config_class(path: str) -> Type[Config]:
    """Import a config class from a dotted path or shorthand name.

    Args:
        path: Dotted path like 'config.ProductionConfig', class name like 'ProductionConfig',
              or shorthand like 'production', 'prod', 'dev', 'test'.

    Returns:
        Configuration class.
    """
    # Expand shorthand names (e.g., "production" → "ProductionConfig")
    path = CONFIG_SHORTCUTS.get(path.lower(), path)

    if "." in path:
        module_path, class_name = path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    else:
        # Assume it's in the project's config module
        try:
            config_module = importlib.import_module("config")
            return getattr(config_module, path)
        except (ImportError, AttributeError):
            # No project config.py (or it doesn't define this class): fall back
            # to the framework's own config classes so FLASK_CONFIG=production
            # works in a project without a config.py.
            builtin = {
                "ProductionConfig": ProductionConfig,
                "TestingConfig": TestingConfig,
                "DevelopmentConfig": DevelopmentConfig,
                "Config": Config,
            }.get(path)
            if builtin is not None:
                return builtin
            raise ValueError(f"Could not load config class: {path}")
