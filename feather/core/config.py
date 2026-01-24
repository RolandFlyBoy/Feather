"""Configuration loading utilities."""

import importlib
import os
from datetime import timedelta
from typing import Optional, Type

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


class Config:
    """Base configuration class."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///app.db")

    # SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session configuration
    # How long before the session expires (browser close = session end if not permanent)
    PERMANENT_SESSION_LIFETIME = timedelta(days=int(os.environ.get("SESSION_LIFETIME_DAYS", "7")))

    # How long "remember me" cookies last
    REMEMBER_COOKIE_DURATION = timedelta(days=int(os.environ.get("REMEMBER_COOKIE_DAYS", "365")))

    # Session protection: None, 'basic', or 'strong'
    # 'strong' regenerates session on IP/user-agent change (more secure but can log out mobile users)
    SESSION_PROTECTION = os.environ.get("SESSION_PROTECTION", "strong")

    # Google OAuth (optional)
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    OAUTH_CALLBACK_URL = os.environ.get("OAUTH_CALLBACK_URL")  # Override OAuth redirect URI

    # Multi-tenant settings
    # Enable multi-tenant mode with domain-based tenant assignment
    FEATHER_MULTI_TENANT = os.environ.get("FEATHER_MULTI_TENANT", "").lower() in ("true", "1", "yes")

    # Allow public email domains (Gmail, Outlook, etc.) in multi-tenant mode
    # When True, users with public emails can sign up; app handles account creation via callback
    FEATHER_ALLOW_PUBLIC_EMAILS = os.environ.get("FEATHER_ALLOW_PUBLIC_EMAILS", "").lower() in (
        "true",
        "1",
        "yes",
    )

    # Post-login callback (optional)
    # Dotted path to function called after OAuth login: "myapp.auth:handle_login"
    # Receives (user, token) and can return redirect URL or None for default behavior
    FEATHER_POST_LOGIN_CALLBACK = os.environ.get("FEATHER_POST_LOGIN_CALLBACK")

    # Storage (optional)
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")
    GCS_BUCKET = os.environ.get("GCS_BUCKET")

    # Cache (optional)
    CACHE_BACKEND = os.environ.get("CACHE_BACKEND", "memory")  # 'memory' or 'redis'
    CACHE_URL = os.environ.get("CACHE_URL")  # Redis URL for cache
    CACHE_DEFAULT_TTL = int(os.environ.get("CACHE_DEFAULT_TTL", "300"))

    # Background Jobs (optional)
    JOB_BACKEND = os.environ.get("JOB_BACKEND", "sync")  # 'sync', 'thread', or 'rq'
    REDIS_URL = os.environ.get("REDIS_URL")  # Redis URL for jobs and cache

    # Thread pool job settings (JOB_BACKEND=thread)
    JOB_MAX_WORKERS = int(os.environ.get("JOB_MAX_WORKERS", "4"))  # Thread pool size
    JOB_ENABLE_MONITORING = os.environ.get("JOB_ENABLE_MONITORING", "").lower() in (
        "true",
        "1",
        "yes",
    )  # Enable psutil resource tracking


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False


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

    # Fall back to default
    env = os.environ.get("FLASK_ENV", "development")
    if env == "production":
        return ProductionConfig
    elif env == "testing":
        return TestingConfig
    return DevelopmentConfig


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
        # Assume it's in the default config module
        try:
            config_module = importlib.import_module("config")
            return getattr(config_module, path)
        except (ImportError, AttributeError):
            raise ValueError(f"Could not load config class: {path}")
