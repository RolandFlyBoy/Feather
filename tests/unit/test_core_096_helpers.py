"""Regression tests for 0.9.6 template helper fixes.

Island script URLs in debug mode were hard-coded to http://localhost:5173.
They now follow VITE_DEV_SERVER and fall back to built assets when Vite is
not running.
"""

import os
from contextlib import contextmanager

import pytest

from feather.core.helpers import feather_island_scripts

pytestmark = pytest.mark.unit


@contextmanager
def env(**values):
    saved = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture
def debug_app():
    from feather import Feather

    app = Feather(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    app.debug = True
    return app


HTML = '<div data-island="counter">Count</div>'


class TestViteDevServerUrl:
    def test_default_is_localhost_5173(self, debug_app):
        with env(VITE_DEV_SERVER=None, FEATHER_VITE=None, FEATHER_NO_VITE=None):
            with debug_app.app_context():
                result = str(feather_island_scripts(HTML))

        assert "http://localhost:5173/static/islands/counter.js" in result

    def test_config_value_is_used(self, debug_app):
        debug_app.config["VITE_DEV_SERVER"] = "http://vite.internal:4000"

        with env(FEATHER_VITE=None, FEATHER_NO_VITE=None):
            with debug_app.app_context():
                result = str(feather_island_scripts(HTML))

        assert "http://vite.internal:4000/static/islands/counter.js" in result

    def test_env_value_is_used(self):
        """VITE_DEV_SERVER from the environment reaches the island URLs."""
        from feather import Feather

        with env(VITE_DEV_SERVER="http://127.0.0.1:6001", FEATHER_VITE=None, FEATHER_NO_VITE=None):
            app = Feather(__name__)
            app.config["TESTING"] = True
            app.config["SECRET_KEY"] = "test-secret"
            app.debug = True
            with app.app_context():
                result = str(feather_island_scripts(HTML))

        assert "http://127.0.0.1:6001/static/islands/counter.js" in result

    def test_trailing_slash_is_normalised(self, debug_app):
        with env(VITE_DEV_SERVER="http://localhost:5173/", FEATHER_VITE=None, FEATHER_NO_VITE=None):
            with debug_app.app_context():
                result = str(feather_island_scripts(HTML))

        assert "http://localhost:5173/static/islands/counter.js" in result


class TestViteDisabled:
    def test_feather_vite_zero_uses_built_asset(self, debug_app):
        with env(FEATHER_VITE="0", FEATHER_NO_VITE=None, VITE_DEV_SERVER=None):
            with debug_app.app_context():
                result = str(feather_island_scripts(HTML))

        assert "5173" not in result
        assert "/static/islands/counter.js" in result

    def test_feather_no_vite_uses_built_asset(self, debug_app):
        """feather dev --no-vite sets FEATHER_NO_VITE=1 for the Flask process."""
        with env(FEATHER_NO_VITE="1", FEATHER_VITE=None, VITE_DEV_SERVER=None):
            with debug_app.app_context():
                result = str(feather_island_scripts(HTML))

        assert "5173" not in result
        assert "/static/islands/counter.js" in result

    def test_config_flag_disables_vite(self, debug_app):
        debug_app.config["FEATHER_VITE"] = False

        with env(FEATHER_VITE=None, FEATHER_NO_VITE=None, VITE_DEV_SERVER=None):
            with debug_app.app_context():
                result = str(feather_island_scripts(HTML))

        assert "5173" not in result

    def test_production_mode_unchanged(self, debug_app):
        debug_app.debug = False

        with env(FEATHER_VITE=None, FEATHER_NO_VITE=None, VITE_DEV_SERVER=None):
            with debug_app.app_context():
                result = str(feather_island_scripts(HTML))

        assert "5173" not in result
        assert "counter.js" in result


class TestDevCommandSignalsNoVite:
    def test_dev_sets_feather_no_vite(self):
        """feather dev must tell the Flask process that Vite is not running."""
        from pathlib import Path

        source = Path("feather/cli/dev.py").read_text()
        assert "FEATHER_NO_VITE" in source
