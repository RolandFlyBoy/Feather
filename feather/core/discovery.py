"""Auto-discovery utilities for models, services, and routes."""

import importlib
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


def discover_models(models_path: Path) -> list:
    """Discover and import all models from the models directory.

    Args:
        models_path: Path to the models directory.

    Returns:
        List of discovered model classes.
    """
    models = []

    for file_path in models_path.glob("*.py"):
        if file_path.name.startswith("_"):
            continue

        module_name = f"models.{file_path.stem}"

        try:
            module = importlib.import_module(module_name)

            # Find all Model subclasses in the module
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and hasattr(obj, "__tablename__")
                    and name != "Model"
                ):
                    models.append(obj)

        except ImportError as e:
            print(f"Warning: Could not import {module_name}: {e}")

    return models


def discover_services(services_path: Path) -> dict:
    """Discover and register all services from the services directory.

    Args:
        services_path: Path to the services directory.

    Returns:
        Dict mapping service names to classes.
    """
    services = {}

    for file_path in services_path.glob("*.py"):
        if file_path.name.startswith("_"):
            continue

        module_name = f"services.{file_path.stem}"

        try:
            module = importlib.import_module(module_name)

            # Find all Service subclasses
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and hasattr(obj, "__mro__")
                    and any(c.__name__ == "Service" for c in obj.__mro__[1:])
                ):
                    services[name] = obj

        except ImportError as e:
            print(f"Warning: Could not import {module_name}: {e}")

    return services


def discover_routes(app: "Flask", routes_path: Path) -> None:
    """Discover and register all routes from the routes directory.

    Routes are organized as:
    - routes/api/*.py -> Mounted at /api/*
    - routes/pages/*.py -> Mounted at /*

    Custom blueprints in route modules are auto-registered.

    Args:
        app: Flask application instance.
        routes_path: Path to the routes directory.
    """
    # Discover API routes
    api_path = routes_path / "api"
    if api_path.exists():
        _discover_route_modules(app, api_path, "routes.api")

    # Discover page routes
    pages_path = routes_path / "pages"
    if pages_path.exists():
        _discover_route_modules(app, pages_path, "routes.pages")


def _discover_route_modules(app: "Flask", path: Path, base_module: str) -> None:
    """Import all route modules from a directory and register custom blueprints.

    Args:
        app: Flask application instance.
        path: Path to the routes directory.
        base_module: Base module name (e.g., 'routes.api').
    """
    from flask import Blueprint
    from feather.core.decorators import api, page as global_page

    for file_path in path.glob("*.py"):
        if file_path.name.startswith("_"):
            continue

        module_name = f"{base_module}.{file_path.stem}"

        try:
            module = importlib.import_module(module_name)

            # Look for custom blueprints to register (not the global api/page)
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, Blueprint)
                    and obj is not api
                    and obj is not global_page
                    and obj.name not in app.blueprints  # Not already registered
                ):
                    app.register_blueprint(obj)

        except ImportError as e:
            print(f"Warning: Could not import {module_name}: {e}")
