"""Discovery is strict.

A broken models/services/routes module stops startup, rather than leaving the
app running with routes silently missing.
"""

import logging
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
def project(tmp_path):
    """Put a temp project on sys.path and clean up its modules afterwards."""
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
# Signatures
# =============================================================================


class TestDiscoverySignatures:
    def test_discover_models_accepts_a_single_argument(self, tmp_path):
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "__init__.py").write_text("")

        with project(tmp_path):
            assert discover_models(tmp_path / "models") == []

    def test_discover_services_accepts_a_single_argument(self, tmp_path):
        (tmp_path / "services").mkdir()
        (tmp_path / "services" / "__init__.py").write_text("")

        with project(tmp_path):
            assert discover_services(tmp_path / "services") == {}
