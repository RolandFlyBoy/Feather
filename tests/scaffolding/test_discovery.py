"""Tests for route discovery - verifies blueprints are registered correctly."""

import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.scaffolding


class TestBlueprintDiscovery:
    """Test that custom blueprints in route modules are auto-registered."""

    def test_custom_blueprint_is_registered(self, temp_project_dir):
        """Custom blueprints in route modules should be auto-registered."""
        from flask import Flask, Blueprint
        from feather.core.discovery import _discover_route_modules

        # Create a route module with a custom blueprint
        routes_dir = temp_project_dir / "routes" / "pages"
        routes_dir.mkdir(parents=True)

        # Create __init__.py files
        (temp_project_dir / "routes" / "__init__.py").write_text("")
        (routes_dir / "__init__.py").write_text("")

        # Create a route module with a custom blueprint (like admin.py)
        admin_routes = '''
from flask import Blueprint

page = Blueprint("admin", __name__, url_prefix="/admin")

@page.route("/")
def admin_index():
    return "Admin"

@page.route("/users")
def admin_users():
    return "Users"
'''
        (routes_dir / "admin.py").write_text(admin_routes)

        # Add temp dir to path so imports work
        sys.path.insert(0, str(temp_project_dir))

        try:
            # Create a Flask app
            app = Flask(__name__)

            # Run discovery
            _discover_route_modules(app, routes_dir, "routes.pages")

            # Verify the admin blueprint was registered
            assert "admin" in app.blueprints, "Admin blueprint should be registered"

            # Verify routes are accessible
            with app.test_client() as client:
                response = client.get("/admin/")
                assert response.status_code == 200
                assert response.data == b"Admin"

                response = client.get("/admin/users")
                assert response.status_code == 200
                assert response.data == b"Users"

        finally:
            # Clean up sys.path and modules
            sys.path.remove(str(temp_project_dir))
            # Remove imported modules to avoid polluting other tests
            mods_to_remove = [k for k in sys.modules if k.startswith("routes")]
            for mod in mods_to_remove:
                del sys.modules[mod]

    def test_custom_blueprint_not_registered_twice(self, temp_project_dir):
        """Custom blueprints with same name as existing should not be registered again."""
        from flask import Flask, Blueprint
        from feather.core.discovery import _discover_route_modules

        # Create a route module with a custom blueprint
        routes_dir = temp_project_dir / "routes" / "pages"
        routes_dir.mkdir(parents=True)

        (temp_project_dir / "routes" / "__init__.py").write_text("")
        (routes_dir / "__init__.py").write_text("")

        admin_routes = '''
from flask import Blueprint

page = Blueprint("admin", __name__, url_prefix="/admin")

@page.route("/")
def admin_index():
    return "Admin"
'''
        (routes_dir / "admin.py").write_text(admin_routes)

        sys.path.insert(0, str(temp_project_dir))

        try:
            app = Flask(__name__)

            # Pre-register a blueprint with name "admin" at different prefix
            existing_admin = Blueprint("admin", __name__, url_prefix="/existing")

            @existing_admin.route("/test")
            def existing_test():
                return "Existing"

            app.register_blueprint(existing_admin)

            # Run discovery - should NOT re-register "admin" since name already exists
            _discover_route_modules(app, routes_dir, "routes.pages")

            # The original admin blueprint should still be there with original routes
            with app.test_client() as client:
                # The pre-registered route should work
                response = client.get("/existing/test")
                assert response.status_code == 200
                assert response.data == b"Existing"

                # The discovered /admin/ route should NOT exist (blueprint not re-registered)
                response = client.get("/admin/")
                assert response.status_code == 404

        finally:
            sys.path.remove(str(temp_project_dir))
            mods_to_remove = [k for k in sys.modules if k.startswith("routes")]
            for mod in mods_to_remove:
                del sys.modules[mod]

    def test_global_blueprints_not_auto_registered(self, temp_project_dir):
        """Global api/page blueprints should not be registered by discovery."""
        from flask import Flask
        from feather.core.discovery import _discover_route_modules
        from feather.core.decorators import api, page

        # Create an empty routes directory (no modules)
        routes_dir = temp_project_dir / "routes" / "pages"
        routes_dir.mkdir(parents=True)

        (temp_project_dir / "routes" / "__init__.py").write_text("")
        (routes_dir / "__init__.py").write_text("")

        sys.path.insert(0, str(temp_project_dir))

        try:
            app = Flask(__name__)

            # Run discovery with empty routes
            _discover_route_modules(app, routes_dir, "routes.pages")

            # Global blueprints should NOT be registered by discovery
            # (they are registered explicitly by Feather after discovery)
            assert "api" not in app.blueprints
            assert "page" not in app.blueprints

        finally:
            sys.path.remove(str(temp_project_dir))


@pytest.fixture
def temp_project_dir():
    """Create a temporary directory for test route modules."""
    import shutil

    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
