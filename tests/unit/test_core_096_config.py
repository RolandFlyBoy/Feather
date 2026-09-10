"""Regression tests for 0.9.6 configuration fixes.

Covers:
- .env values reaching the built-in Config (dotenv load ordering).
- FLASK_CONFIG shorthands falling back to built-in config classes.
- The startup warning when the development config is used by default.
- WTF_CSRF_TIME_LIMIT defaulting to None.
"""

import logging
import os
import sys
from contextlib import contextmanager

import pytest

from feather.core import config as config_module
from feather.core.config import (
    Config,
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    load_config,
)

pytestmark = pytest.mark.unit


BUILTIN_CONFIGS = (Config, DevelopmentConfig, ProductionConfig, TestingConfig)


@contextmanager
def clean_config_state(**env):
    """Isolate env vars and built-in config class attributes."""
    snapshots = [(cls, dict(cls.__dict__)) for cls in BUILTIN_CONFIGS]
    saved_env = dict(os.environ)
    cwd = os.getcwd()
    try:
        for key in ("FLASK_ENV", "FLASK_CONFIG", "SECRET_KEY"):
            os.environ.pop(key, None)
        os.environ.update(env)
        yield
    finally:
        os.chdir(cwd)
        os.environ.clear()
        os.environ.update(saved_env)
        for cls, snapshot in snapshots:
            for key in list(cls.__dict__):
                if key not in snapshot and not key.startswith("__"):
                    delattr(cls, key)
            for key, value in snapshot.items():
                if key.startswith("__"):
                    continue
                try:
                    setattr(cls, key, value)
                except (AttributeError, TypeError):
                    pass


# =============================================================================
# .env is loaded before the built-in config is read
# =============================================================================


class TestDotenvOrdering:
    def test_env_file_secret_key_reaches_app_config(self, tmp_path):
        """A .env SECRET_KEY must win over the built-in placeholder."""
        from feather import Feather

        (tmp_path / ".env").write_text("SECRET_KEY=from-dotenv-secret\n")

        with clean_config_state():
            os.chdir(tmp_path)
            app = Feather(__name__)
            assert app.config["SECRET_KEY"] == "from-dotenv-secret"

    def test_real_environment_beats_dotenv(self, tmp_path):
        """An exported variable is not overridden by .env (override=False)."""
        from feather import Feather

        (tmp_path / ".env").write_text("SECRET_KEY=from-dotenv-secret\n")

        with clean_config_state(SECRET_KEY="from-real-env"):
            os.chdir(tmp_path)
            app = Feather(__name__)
            assert app.config["SECRET_KEY"] == "from-real-env"


# =============================================================================
# FLASK_CONFIG shorthands without a project config.py
# =============================================================================


class TestConfigShorthands:
    @pytest.mark.parametrize(
        "shorthand,expected",
        [
            ("production", ProductionConfig),
            ("prod", ProductionConfig),
            ("development", DevelopmentConfig),
            ("dev", DevelopmentConfig),
            ("testing", TestingConfig),
            ("test", TestingConfig),
        ],
    )
    def test_shorthand_falls_back_to_builtin(self, shorthand, expected):
        """With no project config.py, shorthands resolve to built-ins."""
        assert "config" not in sys.modules or not hasattr(
            sys.modules.get("config"), shorthand
        )
        with clean_config_state(FLASK_CONFIG=shorthand):
            assert load_config() is expected

    def test_explicit_class_name_falls_back_to_builtin(self):
        """'ProductionConfig' with no project config.py resolves too."""
        with clean_config_state(FLASK_CONFIG="ProductionConfig"):
            assert load_config() is ProductionConfig

    def test_unknown_config_name_still_raises(self):
        """A genuinely unknown config name is still an error."""
        with clean_config_state(FLASK_CONFIG="NoSuchConfig"):
            with pytest.raises(ValueError):
                load_config()


# =============================================================================
# Development config warning
# =============================================================================


class TestDevelopmentConfigWarning:
    def test_warns_when_defaulting_to_development(self, tmp_path, caplog):
        """No FLASK_ENV/FLASK_CONFIG => warn that dev config was chosen."""
        from feather import Feather

        with clean_config_state():
            os.chdir(tmp_path)
            with caplog.at_level(logging.WARNING):
                Feather(__name__)

        messages = " ".join(record.getMessage() for record in caplog.records)
        assert "DevelopmentConfig" in messages
        assert "FLASK_ENV" in messages or "FLASK_CONFIG" in messages

    def test_no_warning_when_env_is_explicit(self, tmp_path, caplog):
        """An explicit FLASK_ENV means the developer chose; stay quiet."""
        from feather import Feather

        with clean_config_state(FLASK_ENV="development"):
            os.chdir(tmp_path)
            with caplog.at_level(logging.WARNING):
                Feather(__name__)

        messages = " ".join(record.getMessage() for record in caplog.records)
        assert "DevelopmentConfig" not in messages

    def test_production_secret_key_still_required(self, tmp_path):
        """The production SECRET_KEY refusal is unchanged."""
        from feather import Feather

        with clean_config_state(FLASK_CONFIG="production"):
            os.chdir(tmp_path)
            with pytest.raises(RuntimeError, match="SECRET_KEY"):
                Feather(__name__)


# =============================================================================
# CSRF token lifetime
# =============================================================================


class CustomCsrfConfig(Config):
    """Project config that pins its own CSRF token lifetime."""

    TESTING = True
    SECRET_KEY = "custom-csrf-secret"
    WTF_CSRF_TIME_LIMIT = 3600


class TestCsrfTimeLimit:
    def test_default_is_none(self, test_app):
        """The framework default lets the session bound the token."""
        assert test_app.config["WTF_CSRF_TIME_LIMIT"] is None

    def test_builtin_config_declares_it(self):
        """The built-in Config carries the default too."""
        assert Config.WTF_CSRF_TIME_LIMIT is None

    def test_app_config_can_override(self):
        """An app that sets its own limit keeps it."""
        from feather import Feather

        app = Feather(
            __name__,
            config_class="tests.unit.test_core_096_config.CustomCsrfConfig",
        )
        assert app.config["WTF_CSRF_TIME_LIMIT"] == 3600
