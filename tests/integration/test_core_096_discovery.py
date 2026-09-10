"""Regression tests for 0.9.6 discovery strictness.

A broken models/services/routes module used to be printed as a warning and
swallowed, leaving the app running with routes silently missing. Discovery is
now strict by default and lenient only when FEATHER_LENIENT_DISCOVERY is set.
"""

import logging
import os
import sys
from contextlib import contextmanager

import pytest

from feather.core.discovery import discover_models, discover_routes, discover_services

pytestmark = pytest.mark.integration


class AppStub:
    """Minimal stand-in for a Flask app during discovery."""

    def __init__(self, **config):
        self.config = dict(config)
        self.logger = logging.getLogger("feather.test.discovery")
        self.blueprints = {}
        self.registered = []

    def register_blueprint(self, bp, **kwargs):
        self.registered.append(bp)
        self.blueprints[bp.name] = bp


@contextmanager
def project(tmp_path, lenient_env=None):
    """Put a temp project on sys.path and clean up its modules afterwards."""
    saved = os.environ.get("FEATHER_LENIENT_DISCOVERY")
    if lenient_env is None:
        os.environ.pop("FEATHER_LENIENT_DISCOVERY", None)
    else:
        os.environ["FEATHER_LENIENT_DISCOVERY"] = lenient_env

    sys.path.insert(0, str(tmp_path))
    try:
        yield
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        for name in [
            m
            for m in sys.modules
            if m.split(".")[0] in ("models", "services", "routes")
        ]:
            del sys.modules[name]
        if saved is None:
            os.environ.pop("FEATHER_LENIENT_DISCOVERY", None)
        else:
            os.environ["FEATHER_LENIENT_DISCOVERY"] = saved


def make_project(tmp_path, kind):
    """Create a temp project with one healthy and one broken module."""
    if kind == "models":
        pkg = tmp_path / "models"
    elif kind == "services":
        pkg = tmp_path / "services"
    else:
        pkg = tmp_path / "routes" / "api"
        (tmp_path / "routes").mkdir(exist_ok=True)
        (tmp_path / "routes" / "__init__.py").write_text("")

    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "broken.py").write_text("import a_module_that_does_not_exist\n")
    (pkg / "fine.py").write_text("VALUE = 1\n")
    return pkg


# =============================================================================
# Strict by default
# =============================================================================


class TestStrictDiscovery:
    def test_broken_route_module_raises(self, tmp_path):
        make_project(tmp_path, "routes")
        app = AppStub()

        with project(tmp_path):
            with pytest.raises(ImportError):
                discover_routes(app, tmp_path / "routes")

    def test_broken_model_module_raises(self, tmp_path):
        make_project(tmp_path, "models")
        app = AppStub()

        with project(tmp_path):
            with pytest.raises(ImportError):
                discover_models(tmp_path / "models", app=app)

    def test_broken_service_module_raises(self, tmp_path):
        make_project(tmp_path, "services")
        app = AppStub()

        with project(tmp_path):
            with pytest.raises(ImportError):
                discover_services(tmp_path / "services", app=app)

    def test_error_is_logged_with_module_name(self, tmp_path, caplog):
        make_project(tmp_path, "models")
        app = AppStub()

        with project(tmp_path):
            with caplog.at_level(logging.ERROR):
                with pytest.raises(ImportError):
                    discover_models(tmp_path / "models", app=app)

        messages = " ".join(record.getMessage() for record in caplog.records)
        assert "models.broken" in messages


# =============================================================================
# Lenient mode
# =============================================================================


class TestLenientDiscovery:
    def test_env_flag_keeps_going(self, tmp_path, caplog):
        make_project(tmp_path, "routes")
        app = AppStub()

        with project(tmp_path, lenient_env="1"):
            with caplog.at_level(logging.ERROR):
                discover_routes(app, tmp_path / "routes")

        messages = " ".join(record.getMessage() for record in caplog.records)
        assert "routes.api.broken" in messages

    def test_config_flag_keeps_going(self, tmp_path):
        make_project(tmp_path, "models")
        app = AppStub(FEATHER_LENIENT_DISCOVERY=True)

        with project(tmp_path):
            # Must not raise
            discover_models(tmp_path / "models", app=app)

    def test_healthy_modules_still_import(self, tmp_path):
        make_project(tmp_path, "services")
        app = AppStub(FEATHER_LENIENT_DISCOVERY=True)

        with project(tmp_path):
            discover_services(tmp_path / "services", app=app)
            assert "services.fine" in sys.modules


# =============================================================================
# Backwards compatibility
# =============================================================================


class TestDiscoverySignatures:
    def test_discover_models_still_accepts_a_single_argument(self, tmp_path):
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "__init__.py").write_text("")

        with project(tmp_path):
            assert discover_models(tmp_path / "models") == []

    def test_discover_services_still_accepts_a_single_argument(self, tmp_path):
        (tmp_path / "services").mkdir()
        (tmp_path / "services" / "__init__.py").write_text("")

        with project(tmp_path):
            assert discover_services(tmp_path / "services") == {}
