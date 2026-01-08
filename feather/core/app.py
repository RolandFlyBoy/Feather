"""
Feather Application Class
=========================

The main entry point for Feather applications. Extends Flask with automatic
discovery of models, services, and routes plus batteries-included features.

Getting Started
---------------
Create a minimal application in app.py::

    from feather import Feather

    app = Feather(__name__)

    if __name__ == "__main__":
        app.run()

That's it! Feather will automatically:

1. Load configuration from .env and config.py
2. Initialize the database (SQLAlchemy + migrations)
3. Discover and register models from models/
4. Discover and register services from services/
5. Discover and register routes from routes/

Project Structure
-----------------
Feather expects this directory structure::

    myapp/
    ├── app.py              # Your entry point (3 lines)
    ├── config.py           # Configuration classes
    ├── .env                # Environment variables
    ├── models/             # SQLAlchemy models (auto-discovered)
    ├── services/           # Business logic services (auto-discovered)
    ├── routes/
    │   ├── api/            # API routes → /api/*
    │   └── pages/          # Page routes → /*
    ├── templates/          # Jinja2 templates
    └── static/             # Static files + islands

Configuration
-------------
Configuration is loaded in this priority:

1. Explicit config_class parameter to Feather()
2. FLASK_CONFIG environment variable
3. config.py file in your project
4. Built-in defaults

See feather.core.config for details.
"""

import importlib
import os
from pathlib import Path
from typing import Optional

from flask import Flask
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from jinja2 import ChoiceLoader, FileSystemLoader

from feather.core.config import load_config
from feather.core.discovery import discover_models, discover_routes, discover_services
from feather.core.decorators import api, page
from feather.core.helpers import setup_template_helpers
from feather.core.error_handlers import register_error_handlers
from feather.core.middleware import init_request_id, setup_logging
from feather.core.health import init_health
from feather.db import db, migrate


class Feather(Flask):
    """The Feather application class - your starting point.

    Extends Flask with auto-discovery of components and batteries-included
    features for rapid development. Most Flask features work identically.

    What Feather Does Automatically:
        - Loads configuration from .env and config.py
        - Sets up database (SQLAlchemy + Flask-Migrate)
        - Discovers models from models/
        - Discovers services from services/
        - Discovers routes from routes/api/ and routes/pages/
        - Sets up template helpers for Vite asset resolution
        - Registers error handlers for consistent API responses

    Example:
        Minimal application (app.py)::

            from feather import Feather

            app = Feather(__name__)

            if __name__ == "__main__":
                app.run()

        With custom configuration::

            app = Feather(__name__, config_class='config.ProductionConfig')

        Flask features work normally::

            @app.before_request
            def before_request():
                # Your code here
                pass

    Attributes:
        All standard Flask attributes are available. Key additions:
        - api blueprint: Mounted at /api/* for REST endpoints
        - page blueprint: Mounted at /* for HTML pages
        - db: SQLAlchemy database instance (via feather.db)

    See Also:
        - :class:`feather.Service`: Base class for business logic
        - :mod:`feather.exceptions`: Error handling
        - :func:`feather.dispatch`: Event system
    """

    def __init__(
        self,
        import_name: str,
        config_class: Optional[str] = None,
        **kwargs,
    ):
        """Initialize a Feather application.

        Args:
            import_name: The name of the application package. Usually pass
                ``__name__`` from your app.py file.
            config_class: Optional dotted path to a configuration class, e.g.,
                ``'config.ProductionConfig'``. If not provided, Feather will
                auto-detect based on FLASK_ENV environment variable.
            **kwargs: Additional arguments passed to Flask.__init__(). Common
                options include ``static_folder``, ``template_folder``, etc.

        Example:
            Standard usage::

                app = Feather(__name__)

            With custom configuration::

                app = Feather(__name__, config_class='config.ProductionConfig')

            With Flask options::

                app = Feather(
                    __name__,
                    static_folder='assets',
                    template_folder='views'
                )
        """
        super().__init__(import_name, **kwargs)

        # Register framework templates and static files
        # This allows Flask to find templates in feather/templates/ (components, errors)
        # and static files in feather/static/ (api.js, feather.js, favicon.svg)
        self._setup_framework_assets()

        # Step 1: Load .env file (if present) before any config loading
        load_dotenv()

        # Step 2: Load configuration from config.py or environment
        self._setup_config(config_class)

        # Step 2.5: Enable ProxyFix for reverse proxy support
        # Needed for both production (Render, Heroku, AWS ALB, nginx) and development (ngrok, localtunnel).
        # Without ProxyFix, Flask doesn't see the true protocol and secure cookies/OAuth break.
        # Safe to enable unconditionally - only reads X-Forwarded-* headers if they exist.
        from werkzeug.middleware.proxy_fix import ProxyFix
        self.wsgi_app = ProxyFix(self.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

        # Step 3: Initialize database and migrations
        self._setup_database()

        # Step 4: Initialize CSRF protection
        # Token is available in templates via {{ csrf_token() }}
        csrf = CSRFProtect()
        csrf.init_app(self)

        # Step 5: Auto-discover models, services, and routes
        # (Must happen BEFORE blueprint registration so routes are added first)
        self._discover_components()

        # Step 6: Register route blueprints
        # @api.get('/users') → GET /api/users
        # @page.get('/') → GET /
        self.register_blueprint(api, url_prefix="/api")
        self.register_blueprint(page)

        # Step 6.5: Register CSRF exemptions
        # Must happen AFTER route registration so view_functions is populated
        self._register_csrf_exemptions(csrf)

        # Step 7: Setup template helpers (feather_asset for Vite manifest)
        setup_template_helpers(self)

        # Step 8: Register error handlers for consistent JSON responses
        register_error_handlers(self)

        # Step 9: Initialize request ID tracking
        init_request_id(self)

        # Step 10: Setup logging (JSON format in production)
        json_logging = os.environ.get("FLASK_ENV") == "production"
        setup_logging(self, json_format=json_logging)

        # Step 11: Register health check endpoints (/health, /health/live, /health/ready)
        init_health(self)

        # Step 12: Initialize authentication (if User model exists)
        self._setup_auth()

    def _setup_config(self, config_class: Optional[str] = None):
        """Load configuration from config.py and environment.

        Configuration priority:
        1. Explicit config_class parameter
        2. FLASK_CONFIG environment variable
        3. Project's config.py file
        4. Built-in DevelopmentConfig

        Args:
            config_class: Optional dotted path to config class.
        """
        config = load_config(config_class)
        self.config.from_object(config)

        # Disable SQLAlchemy modification tracking for performance
        self.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)

    def _setup_database(self):
        """Initialize SQLAlchemy and Flask-Migrate.

        Reads DATABASE_URL from config and sets up:
        - SQLAlchemy for ORM queries
        - Flask-Migrate for database migrations

        After setup, use db.session for queries::

            from feather import db
            users = db.session.query(User).all()
        """
        # Support DATABASE_URL (common in deployment platforms)
        database_url = self.config.get("DATABASE_URL")
        if database_url:
            self.config["SQLALCHEMY_DATABASE_URI"] = database_url

        # Only initialize database if configured (skip for minimal apps)
        if self.config.get("SQLALCHEMY_DATABASE_URI"):
            db.init_app(self)
            migrate.init_app(self, db)

    def _discover_components(self):
        """Auto-discover and register models, services, and routes.

        Looks for components in standard directories:

        - models/*.py → SQLAlchemy models are imported and registered
        - services/*.py → Service classes become available for @inject
        - routes/api/*.py → API routes mounted at /api/*
        - routes/pages/*.py → Page routes mounted at /*

        Files starting with underscore (_) are skipped.
        """
        app_root = Path(self.root_path)

        # Discover models - imports all Model subclasses from models/
        models_path = app_root / "models"
        if models_path.exists():
            discover_models(models_path)

        # Discover services - imports all Service subclasses from services/
        services_path = app_root / "services"
        if services_path.exists():
            discover_services(services_path)

        # Discover routes - imports and registers all route modules
        routes_path = app_root / "routes"
        if routes_path.exists():
            discover_routes(self, routes_path)

    def _register_csrf_exemptions(self, csrf):
        """Register CSRF exemptions from config and decorated views.

        Called after routes are registered so view_functions is populated.
        Supports two methods of exemption:

        1. Config-based: WTF_CSRF_EXEMPT_VIEWS list of "module.function" strings
        2. Decorator-based: Views decorated with @csrf_exempt

        Args:
            csrf: The CSRFProtect instance to register exemptions with.
        """
        # Method 1: Config-based exemptions
        exempt_views = self.config.get("WTF_CSRF_EXEMPT_VIEWS", [])
        for view_name in exempt_views:
            csrf.exempt(view_name)

        # Method 2: Scan view functions for @csrf_exempt decorator
        for endpoint, view_func in self.view_functions.items():
            exempt_location = getattr(view_func, "_csrf_exempt_location", None)
            if exempt_location:
                csrf.exempt(exempt_location)

    def run(self, host: str = "127.0.0.1", port: int = 5000, debug: bool = None, **kwargs):
        """Run the development server.

        This is for local development only. For production, use Gunicorn
        via ``feather start``.

        Args:
            host: Hostname to listen on. Default: '127.0.0.1' (localhost only).
                Use '0.0.0.0' to make server publicly accessible.
            port: Port to listen on. Default: 5000.
            debug: Enable debug mode with auto-reload. Defaults to True if
                FLASK_DEBUG=1 in environment.
            **kwargs: Additional arguments passed to Flask.run().

        Example:
            Default (localhost:5000 with debug)::

                app.run()

            Custom host and port::

                app.run(host='0.0.0.0', port=8080)

            Production-like (no debug)::

                app.run(debug=False)

        Note:
            For production, use::

                feather build  # Build assets
                feather start  # Run with Gunicorn
        """
        if debug is None:
            debug = os.environ.get("FLASK_DEBUG", "1") == "1"

        super().run(host=host, port=port, debug=debug, **kwargs)

    def _setup_auth(self):
        """Initialize authentication if a User model is discovered.

        This is called automatically during app initialization. It will:

        1. Try to import a User model from the models/ directory
        2. If found, initialize Flask-Login with the User model
        3. If GOOGLE_CLIENT_ID is configured, also initialize Google OAuth

        The User model must:
        - Inherit from flask_login.UserMixin
        - Have a get_by_id(id) class method

        Example User model::

            from flask_login import UserMixin
            from feather.db import db, Model
            from feather.db.mixins import UUIDMixin, TimestampMixin

            class User(UserMixin, UUIDMixin, TimestampMixin, Model):
                __tablename__ = 'users'
                email = db.Column(db.String(255), unique=True, nullable=False)
                # ...

        Configuration (in .env or config.py):
            GOOGLE_CLIENT_ID: Optional. If set, Google OAuth is enabled.
            GOOGLE_CLIENT_SECRET: Required if GOOGLE_CLIENT_ID is set.
        """
        try:
            # Try to import User model from application
            from models import User

            # Initialize Flask-Login
            from feather.auth import init_auth
            from feather.auth.routes import auth_bp

            init_auth(self, user_model=User)

            # Register auth routes (logout, etc.)
            self.register_blueprint(auth_bp)

            # Always initialize Google OAuth blueprint (route checks for config)
            from feather.auth.google import init_google_oauth

            init_google_oauth(self)

        except ImportError:
            # No User model found - authentication not enabled
            # This is normal for apps that don't need auth
            pass
        except Exception as e:
            # Log but don't fail - auth is optional
            self.logger.warning(f"Failed to initialize auth: {e}")

    def _setup_framework_assets(self):
        """Register framework templates and static files.

        Configures Flask to find:
        - Framework templates in feather/templates/ (components, errors)
        - Framework static files in feather/static/ (api.js, feather.js, favicon.svg)

        Template resolution order:
        1. App's templates/ folder (user can override)
        2. Framework's feather/templates/ folder (defaults)

        This allows users to override any framework template by creating
        their own version in templates/. For example, creating
        templates/components/button.html will override the framework's version.
        """
        # Get the feather package directory
        feather_dir = Path(__file__).parent.parent

        # Framework template and static paths
        framework_templates = feather_dir / "templates"
        framework_static = feather_dir / "static"

        # Add framework templates as a fallback loader
        # User templates (self.jinja_loader) take priority
        if framework_templates.exists():
            framework_loader = FileSystemLoader(str(framework_templates))
            self.jinja_loader = ChoiceLoader([
                self.jinja_loader,  # App templates first (user overrides)
                framework_loader,   # Framework templates as fallback
            ])

        # Register framework static files route
        # Files served at /feather-static/ to avoid conflicts with app's /static/
        if framework_static.exists():
            from flask import send_from_directory

            @self.route("/feather-static/<path:filename>")
            def feather_static(filename):
                return send_from_directory(str(framework_static), filename)
