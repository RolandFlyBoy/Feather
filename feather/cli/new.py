"""feather new - Create a new Feather project."""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import click


def _extract_db_name(db_url: str) -> str | None:
    """Extract database name from a PostgreSQL URL."""
    try:
        parsed = urlparse(db_url)
        # Path is /dbname, so strip the leading /
        db_name = parsed.path.lstrip("/")
        return db_name if db_name else None
    except Exception:
        return None


@click.command()
@click.argument("name")
@click.option("--template", default="default", help="Project template to use")
@click.option("--no-prompt", is_flag=True, help="Skip prompts, use defaults (simple app, no database)")
def new(name: str, template: str, no_prompt: bool):
    """Create a new Feather project.

    NAME is the name of the project directory to create.
    """
    project_path = Path.cwd() / name

    if project_path.exists():
        raise click.ClickException(f"Directory '{name}' already exists")

    # Default options - minimal app (just pressing Enter through prompts)
    options = {
        "app_type": "simple",  # "simple", "single_tenant", or "multi_tenant"
        "database": "none",  # "none", "sqlite", or "postgresql"
        "db_url": None,
        "include_auth": False,
        "tenant_mode": None,  # None, "single", or "multi"
        "include_cache": False,
        "include_jobs": False,
        "include_storage": False,
        "storage_backend": None,
        "include_email": False,
        "admin_email": None,
    }

    # Interactive prompts
    if not no_prompt:
        click.echo()
        click.echo(click.style("Project Configuration", fg="cyan", bold=True))
        click.echo()

        # App type selection (drives all other options)
        click.echo(click.style("App Type", fg="cyan"))
        click.echo("  Simple       - Static pages, no authentication")
        click.echo("  Single-tenant - One organization, user accounts")
        click.echo("  Multi-tenant  - Multiple organizations (SaaS)")
        click.echo()
        app_type = click.prompt(
            "  Select type",
            type=click.Choice(["simple", "single-tenant", "multi-tenant"]),
            default="simple",
        )
        options["app_type"] = app_type.replace("-", "_")

        # Database options depend on app type
        click.echo()
        click.echo(click.style("Database", fg="cyan"))

        if app_type == "simple":
            # Simple: Ask, default none
            db_choice = click.prompt(
                "  Type",
                type=click.Choice(["none", "sqlite", "postgresql"]),
                default="none",
            )
            options["database"] = db_choice

            if db_choice == "postgresql":
                db_name = click.prompt(
                    "  Database name",
                    default=name,
                )
                options["db_url"] = f"postgresql://localhost/{db_name}"

        elif app_type == "single-tenant":
            # Single-tenant: Ask SQLite or PostgreSQL, default SQLite
            db_choice = click.prompt(
                "  Type",
                type=click.Choice(["sqlite", "postgresql"]),
                default="sqlite",
            )
            options["database"] = db_choice
            options["include_auth"] = True
            options["tenant_mode"] = "single"

            if db_choice == "postgresql":
                db_name = click.prompt(
                    "  Database name",
                    default=name,
                )
                options["db_url"] = f"postgresql://localhost/{db_name}"

        else:  # multi-tenant
            # Multi-tenant: PostgreSQL required, just ask for name
            options["database"] = "postgresql"
            options["include_auth"] = True
            options["tenant_mode"] = "multi"

            db_name = click.prompt(
                "  Database name (PostgreSQL required)",
                default=name,
            )
            options["db_url"] = f"postgresql://localhost/{db_name}"

        # Background jobs: Available for all app types
        click.echo()
        click.echo(click.style("Background Jobs", fg="cyan"))
        options["include_jobs"] = click.confirm(
            "  Include background jobs?",
            default=True,
        )

        # Additional features: Only for authenticated apps
        if options["include_auth"]:
            click.echo()
            click.echo(click.style("Features", fg="cyan") + " (press Enter for defaults):")

            options["include_cache"] = click.confirm(
                "  Include Redis caching?",
                default=True,
            )

            options["include_storage"] = click.confirm(
                "  Include cloud storage (GCS)?",
                default=True,
            )

            if options["include_storage"]:
                options["storage_backend"] = "gcs"

            options["include_email"] = click.confirm(
                "  Include email support (Resend)?",
                default=False,
            )

            # User model field selection
            click.echo()
            click.echo(click.style("User Profile Fields", fg="cyan") + " (optional):")
            options["user_fields"] = {
                "display_name": click.confirm(
                    "  Include display_name?",
                    default=True,
                ),
                "profile_image_url": click.confirm(
                    "  Include profile_image_url?",
                    default=True,
                ),
            }

            # Admin email (required for auth)
            click.echo()
            click.echo(click.style("Admin Setup", fg="cyan"))
            admin_label = "Platform admin email" if app_type == "multi-tenant" else "Admin email"
            email = click.prompt(f"  {admin_label}")
            options["admin_email"] = email

        click.echo()

    # Handle database creation based on type
    if options["database"] == "postgresql":
        # Extract database name from URL and create database
        db_name = _extract_db_name(options["db_url"])
        if not db_name:
            raise click.ClickException(
                f"Could not parse database name from URL: {options['db_url']}\n"
                "Expected format: postgresql://[user:pass@]host[:port]/dbname"
            )

        # Create database first - fail early if it doesn't work
        if not _create_database(db_name):
            raise click.ClickException(
                f"Failed to create database '{db_name}'. "
                "Please ensure PostgreSQL is running and you have permission to create databases.\n"
                "You can create the database manually with: createdb " + db_name
            )
    elif options["database"] == "sqlite":
        # SQLite will be created automatically when app runs
        options["db_url"] = "sqlite:///app.db"
    else:
        # No database
        options["db_url"] = None

    click.echo(f"Creating new Feather project: {name}")

    # Create project structure
    _create_project_structure(project_path, database=options["database"], include_auth=options.get("include_auth", False))

    # Create files from templates
    _create_project_files(project_path, name, **options)

    # Initialize git
    _init_git(project_path)

    # Install dependencies
    _install_dependencies(project_path)

    # Set up Python virtual environment
    _setup_venv(project_path)

    click.echo()
    click.echo(click.style("Project created successfully!", fg="green", bold=True))
    click.echo()

    # Next steps based on configuration
    click.echo("Next steps:")
    click.echo(f"  1. cd {name}")
    click.echo("  2. source venv/bin/activate")

    if options["database"] == "none":
        # No database - simplest case
        click.echo("  3. feather dev")
        click.echo()
        click.echo("Or run it all at once:")
        click.echo(f"  cd {name} && source venv/bin/activate && feather dev")
    elif options.get("include_auth"):
        # Has auth - needs migrations and seeds
        click.echo('  3. feather db migrate -m "Initial migration"')
        click.echo("  4. feather db upgrade")
        click.echo("  5. python seeds.py")
        click.echo("  6. feather dev")
        click.echo()
        click.echo("Or run it all at once:")
        click.echo(f'  cd {name} && source venv/bin/activate && feather db migrate -m "Initial migration" && feather db upgrade && python seeds.py && feather dev')
        click.echo()
        click.echo(f"Admin user will be created for: {options['admin_email']}")
        if options["tenant_mode"] == "multi":
            click.echo("(Platform admin - can create and manage tenants)")
    else:
        # Has database but no auth
        click.echo('  3. feather db migrate -m "Initial migration"')
        click.echo("  4. feather db upgrade")
        click.echo("  5. feather dev")
        click.echo()
        click.echo("Or run it all at once:")
        click.echo(f'  cd {name} && source venv/bin/activate && feather db migrate -m "Initial migration" && feather db upgrade && feather dev')

    # Add infrastructure notes if relevant
    infra_notes = []

    if options.get("include_cache"):
        infra_notes.append("Redis (for caching): redis-server")

    if options.get("include_jobs"):
        infra_notes.append("Background jobs run in thread pool (no setup needed)")
        infra_notes.append("For persistent jobs: set JOB_BACKEND=rq in .env (requires Redis)")

    if options.get("include_storage") and options.get("storage_backend") == "gcs":
        infra_notes.append("Configure GCS credentials in .env (GCS_CREDENTIALS_JSON)")

    if options.get("include_auth"):
        infra_notes.append("Google OAuth: Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env")
        infra_notes.append("  Create credentials at: https://console.cloud.google.com/apis/credentials")

    if options.get("include_email"):
        infra_notes.append("Resend: Set RESEND_API_KEY in .env")
        infra_notes.append("  Get your API key at: https://resend.com/api-keys")

    if infra_notes:
        click.echo()
        click.echo(click.style("Infrastructure requirements:", fg="yellow"))
        for note in infra_notes:
            click.echo(f"  • {note}")

    click.echo()
    click.echo("Then open http://localhost:5173 in your browser")


def _create_database(db_name: str) -> bool:
    """Create PostgreSQL database. Returns True if successful or already exists."""
    try:
        # Check if database already exists
        result = subprocess.run(
            ["psql", "-lqt"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            # Parse output to check if database exists
            databases = [line.split("|")[0].strip() for line in result.stdout.split("\n") if "|" in line]
            if db_name in databases:
                click.echo(f"  Database '{db_name}' already exists")
                return True

        # Try to create the database
        result = subprocess.run(
            ["createdb", db_name],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            click.echo(click.style(f"  Created database '{db_name}'", fg="green"))
            return True
        else:
            # Check if it failed because it already exists
            if "already exists" in result.stderr:
                click.echo(f"  Database '{db_name}' already exists")
                return True
            click.echo(click.style(f"  Failed to create database: {result.stderr.strip()}", fg="red"))
            return False
    except FileNotFoundError:
        click.echo(click.style("  PostgreSQL tools (psql/createdb) not found in PATH", fg="red"))
        return False
    except Exception as e:
        click.echo(click.style(f"  Database creation error: {e}", fg="red"))
        return False


def _create_project_structure(project_path: Path, database: str = "postgresql", include_auth: bool = False):
    """Create the project directory structure."""
    directories = [
        "logs",
        "services",
        "routes/api",
        "routes/pages",
        "templates/components",
        "templates/partials",
        "templates/pages",
        "templates/errors",
        "static/islands",
        "static/css",
        "static/js",
        "static/dist",
        "tests",
    ]

    # Only create models and migrations if we have a database
    if database != "none":
        directories.extend(["models", "migrations/versions"])

    # Add admin and account directories when auth is enabled
    if include_auth:
        directories.extend([
            "templates/pages/admin",
            "templates/pages/account",
            "templates/partials/admin",
        ])

    for directory in directories:
        (project_path / directory).mkdir(parents=True, exist_ok=True)

    click.echo("  Created directory structure")


def _create_project_files(
    project_path: Path,
    name: str,
    database: str = "postgresql",
    include_auth: bool = False,
    tenant_mode: str = None,
    include_cache: bool = False,
    include_jobs: bool = False,
    include_storage: bool = False,
    storage_backend: str = None,
    include_email: bool = False,
    db_url: str = None,
    admin_email: str = None,
    app_type: str = None,  # "simple", "single_tenant", or "multi_tenant"
    user_fields: dict = None,  # Optional User model field selection
):
    """Create project files from templates.

    Args:
        project_path: Path to the project directory
        name: Project name
        database: Database type ("none", "sqlite", or "postgresql")
        include_auth: Whether to include authentication (Google OAuth + admin panel)
        tenant_mode: Tenant mode ("single" or "multi"), only if include_auth is True
        include_cache: Whether to include Redis caching
        include_jobs: Whether to include background jobs
        include_storage: Whether to include cloud storage
        storage_backend: Storage backend ("gcs" or None)
        include_email: Whether to include email support (Resend)
        db_url: Database URL (for postgresql/sqlite)
        admin_email: Admin email for seeds.py
    """
    # Determine if we have a database
    has_database = database != "none"

    # Admin is always included when auth is enabled
    include_admin = include_auth

    # app.py - Main entry point
    (project_path / "app.py").write_text(
        '''"""Main application entry point."""

from feather import Feather

app = Feather(__name__)

if __name__ == "__main__":
    app.run()
'''
    )

    # config.py - Build conditionally
    (project_path / "config.py").write_text(
        _build_config_content(
            database=database,
            db_url=db_url,
            include_auth=include_auth,
            tenant_mode=tenant_mode,
            include_cache=include_cache,
            include_jobs=include_jobs,
            include_storage=include_storage,
            storage_backend=storage_backend,
            include_email=include_email,
        )
    )

    # .env - Environment variables (works for local development)
    (project_path / ".env").write_text(
        _build_env_content(
            name=name,
            database=database,
            db_url=db_url,
            include_auth=include_auth,
            tenant_mode=tenant_mode,
            include_cache=include_cache,
            include_jobs=include_jobs,
            include_storage=include_storage,
            include_email=include_email,
        )
    )

    # .gitignore
    (project_path / ".gitignore").write_text(
        """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
.venv/

# Environment
.env
*.local

# IDE
.idea/
.vscode/
*.swp
*.swo

# Build
static/dist/
node_modules/
*.egg-info/
dist/
build/

# Testing
.pytest_cache/
.coverage
htmlcov/

# Misc
.DS_Store
*.log
"""
    )

    # requirements.txt - Standalone with all dependencies
    (project_path / "requirements.txt").write_text(
        _build_requirements_content(
            database=database,
            include_auth=include_auth,
            include_cache=include_cache,
            include_jobs=include_jobs,
            include_storage=include_storage,
        )
    )

    # package.json
    (project_path / "package.json").write_text(
        f'''{{
  "name": "{name}",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "engines": {{
    "node": ">=22"
  }},
  "scripts": {{
    "dev": "vite",
    "build": "vite build"
  }},
  "devDependencies": {{
    "vite": "^7.0.0",
    "@tailwindcss/vite": "^4.0.0",
    "tailwindcss": "^4.0.0",
    "terser": "^5.0.0",
    "vite-plugin-full-reload": "^1.2.0"
  }}
}}
'''
    )

    # vite.config.js
    (project_path / "vite.config.js").write_text(
        '''import { defineConfig } from "vite";
import { resolve } from "path";
import { readdirSync, existsSync } from "fs";
import tailwindcss from "@tailwindcss/vite";
import fullReload from "vite-plugin-full-reload";

// Auto-discover islands
function discoverIslands() {
  const islandsDir = resolve(__dirname, "static/islands");
  const entries = {};

  if (existsSync(islandsDir)) {
    readdirSync(islandsDir)
      .filter((file) => file.endsWith(".js"))
      .forEach((file) => {
        const name = file.replace(".js", "");
        entries[`islands/${name}`] = resolve(islandsDir, file);
      });
  }

  return entries;
}

export default defineConfig({
  plugins: [
    tailwindcss(),
    // Watch templates and trigger full page reload
    fullReload(["templates/**/*.html", "static/css/**/*.css"], { delay: 100 }),
  ],
  server: {
    port: 5173,
    proxy: {
      // Proxy everything except Vite internals to Flask
      "^(?!/@vite|/@id|/node_modules|/static).*": {
        target: "http://127.0.0.1:5000",
        changeOrigin: false,  // Keep original Host header for correct cookie domain
        configure: (proxy) => {
          // Add X-Forwarded headers for OAuth redirect URI detection
          // Pass through existing proto header (from ngrok/tunnels) or default to http
          proxy.on("proxyReq", (proxyReq, req) => {
            proxyReq.setHeader("X-Forwarded-Host", req.headers.host);
            const proto = req.headers["x-forwarded-proto"] || "http";
            proxyReq.setHeader("X-Forwarded-Proto", proto);
          });
        },
      },
    },
    watch: {
      // Ignore non-frontend files to prevent unnecessary reloads
      ignored: [
        "**/node_modules/**",
        "**/.git/**",
        "**/venv/**",
        "**/__pycache__/**",
        "**/migrations/**",
        "**/*.py",
        "**/*.pyc",
      ],
    },
  },
  build: {
    outDir: "static/dist",
    manifest: true,
    rollupOptions: {
      input: {
        // Styles
        styles: resolve(__dirname, "static/css/app.css"),
        // Islands (auto-discovered)
        ...discoverIslands(),
      },
      output: {
        entryFileNames: "[name]-[hash].js",
        chunkFileNames: "[name]-[hash].js",
        assetFileNames: "[name]-[hash][extname]",
      },
    },
    minify: "terser",
    terserOptions: {
      mangle: { toplevel: false },
      compress: { keep_classnames: true, keep_fnames: true },
    },
  },
});
'''
    )

    # static/css/app.css
    # Find feather templates path for Tailwind scanning
    import feather
    feather_templates_path = Path(feather.__file__).parent / "templates"

    (project_path / "static/css/app.css").write_text(
        f'@import "tailwindcss";\n\n/* Scan Feather framework templates for Tailwind classes */\n@source "{feather_templates_path}/**/*.html";\n\n'
        + """/* Sensible defaults */
@layer base {
  /* Interactive elements get pointer cursor */
  button, [role="button"], [type="submit"], [type="button"] {
    cursor: pointer;
  }

  a {
    cursor: pointer;
  }

  /* Disabled elements */
  button:disabled, [disabled] {
    cursor: not-allowed;
    opacity: 0.5;
  }
}

/* Material Icons - use: <span class="icon">home</span> */
@layer components {
  .icon {
    font-family: 'Material Symbols Outlined';
    font-weight: normal;
    font-style: normal;
    font-size: 24px;
    line-height: 1;
    letter-spacing: normal;
    text-transform: none;
    display: inline-block;
    white-space: nowrap;
    word-wrap: normal;
    direction: ltr;
    -webkit-font-smoothing: antialiased;
    vertical-align: middle;
  }

  /* Icon sizes */
  .icon-sm { font-size: 18px; }
  .icon-md { font-size: 24px; }
  .icon-lg { font-size: 36px; }
  .icon-xl { font-size: 48px; }

  /* Drag and drop styles */
  .dragging {
    opacity: 0.5;
  }

  .drag-over {
    background-color: rgba(59, 130, 246, 0.1);
  }

  .feather-drop-placeholder {
    height: 2px;
    background: #3b82f6;
    border-radius: 2px;
    margin: 4px 0;
  }

  /* Admin Panel Styles - CHRP-inspired */

  /* Header - 80px (h-20) fixed black header */
  .admin-header {
    background: #000;
  }

  /* Tab Navigation */
  .admin-nav-item {
    transition: background-color 0.15s;
    border-bottom: 2px solid transparent;
  }

  .admin-nav-item:hover {
    background-color: #f3f4f6;
  }

  .admin-nav-item.active {
    background: #f3f4f6;
    font-weight: 600;
    border-bottom-color: #000;
  }

  /* Table styles */
  .admin-table-header {
    background: #f9fafb;
    border-bottom: 2px solid #e5e7eb;
  }

  .admin-table-row {
    transition: background-color 0.1s;
  }

  .admin-table-row:hover {
    background-color: #f9fafb;
  }

  /* Status badges */
  .admin-badge {
    display: inline-flex;
    align-items: center;
    padding: 0.125rem 0.5rem;
    font-size: 0.75rem;
    font-weight: 500;
    border-radius: 9999px;
  }

  .admin-badge-active {
    background-color: #dcfce7;
    color: #166534;
  }

  .admin-badge-suspended {
    background-color: #fee2e2;
    color: #991b1b;
  }

  .admin-badge-admin {
    background-color: #000;
    color: #fff;
  }

  .admin-badge-pending {
    background-color: #fef3c7;
    color: #92400e;
  }

  /* Buttons */
  .admin-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
    font-weight: 500;
    border-radius: 0.5rem;
    transition: background-color 0.15s;
    cursor: pointer;
  }

  .admin-btn-primary {
    background: #000;
    color: #fff;
  }

  .admin-btn-primary:hover {
    background: #374151;
  }

  .admin-btn-secondary {
    background: #fff;
    color: #374151;
    border: 1px solid #d1d5db;
  }

  .admin-btn-secondary:hover {
    background: #f9fafb;
  }

  .admin-btn-danger {
    background: #dc2626;
    color: #fff;
  }

  .admin-btn-danger:hover {
    background: #b91c1c;
  }

  /* Cards */
  .admin-card {
    background: #fff;
    border-radius: 0.5rem;
    box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1);
  }

  .admin-card-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
  }

  .admin-card-icon {
    width: 3rem;
    height: 3rem;
    border-radius: 0.5rem;
    background: #000;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
  }

  .admin-card-body {
    padding: 1.5rem;
  }

  /* Fixed layout with scrollable content */
  /* Header: 80px (h-20), Nav: 49px */
  .admin-content-scroll {
    height: calc(100vh - 5rem - 49px);
    overflow-y: auto;
    padding-bottom: 2rem;
  }

  /* Avatar dropdown */
  .admin-avatar-dropdown {
    display: none;
    position: absolute;
    right: 0;
    top: calc(100% + 0.5rem);
    min-width: 240px;
    background: #fff;
    border-radius: 0.5rem;
    box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
    z-index: 50;
  }

  .admin-avatar-dropdown.show {
    display: block;
  }

  /* Input styles */
  .admin-input {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid #d1d5db;
    border-radius: 0.5rem;
    font-size: 0.875rem;
  }

  .admin-input:focus {
    outline: none;
    box-shadow: 0 0 0 2px #000;
    border-color: transparent;
  }

  /* Search input with icon */
  .admin-search-input {
    padding-left: 2.5rem;
  }

  /* Stats grid for detail page */
  .admin-stats-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
  }

  @media (min-width: 768px) {
    .admin-stats-grid {
      grid-template-columns: repeat(4, 1fr);
    }
  }

  @media (min-width: 1024px) {
    .admin-stats-grid {
      grid-template-columns: repeat(7, 1fr);
    }
  }

  .admin-stat-item {
    text-align: center;
  }

  .admin-stat-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #111827;
  }

  .admin-stat-label {
    font-size: 0.75rem;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  /* Page layouts */
  .auth-page {
    min-height: 100vh;
    background: #f9fafb;
  }

  .page-header {
    background: #000;
    height: 5rem;
    display: flex;
    align-items: center;
  }

  .page-header-container {
    max-width: 80rem;
    margin: 0 auto;
    padding: 0 1rem;
    width: 100%;
  }

  .page-header-title {
    color: #fff;
    font-size: 1.25rem;
    font-weight: 600;
  }

  .page-content {
    max-width: 42rem;
    margin: 0 auto;
    padding: 2rem 1rem;
  }

  .page-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: #111827;
    margin-bottom: 0.5rem;
  }

  .page-subtitle {
    color: #4b5563;
    margin-bottom: 1.5rem;
  }

  /* Card title/subtitle - extends admin-card */
  .admin-card-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: #111827;
  }

  .admin-card-subtitle {
    font-size: 0.875rem;
    color: #4b5563;
  }

  /* Step indicators */
  .steps {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  .step-number {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 9999px;
    background: #000;
    color: #fff;
    font-size: 0.75rem;
    font-weight: 700;
    flex-shrink: 0;
  }

  .step-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .step-title {
    font-size: 0.875rem;
    font-weight: 600;
    color: #111827;
  }

  .step-content {
    margin-left: 2rem;
  }

  .step-text {
    font-size: 0.875rem;
    color: #4b5563;
  }

  .step-text-margin {
    margin-bottom: 0.5rem;
  }

  .step-link {
    color: #000;
    font-weight: 500;
    text-decoration: underline;
  }

  .step-link:hover {
    text-decoration: none;
  }

  /* Code blocks */
  .code-section {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .code-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.25rem;
  }

  .code-block {
    font-size: 0.875rem;
    background: #f3f4f6;
    color: #1f2937;
    padding: 0.75rem;
    border-radius: 0.5rem;
    overflow-x: auto;
    font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
  }

  .code-block-dark {
    background: #111827;
    color: #f3f4f6;
    padding: 1rem;
  }

  .code-inline {
    background: #f3f4f6;
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
    color: #1f2937;
    font-size: 0.75rem;
    font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
  }

  /* Custom Dropdown Component */
  .dropdown-button {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 0.5rem;
    font-size: 0.875rem;
    cursor: pointer;
    transition: border-color 0.15s, box-shadow 0.15s;
  }

  .dropdown-button:focus {
    outline: none;
    border-color: #6366f1;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
  }

  .dropdown-block {
    width: 100%;
    padding: 0.5rem 0.75rem;
  }

  .dropdown-inline {
    padding: 0.375rem 0.625rem;
    font-size: 0.8125rem;
  }

  .dropdown-chevron {
    flex-shrink: 0;
    margin-left: 0.5rem;
  }

  .dropdown-options {
    position: absolute;
    z-index: 50;
    margin-top: 0.25rem;
    width: 100%;
    min-width: 12rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.5rem;
    box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
    max-height: 16rem;
    overflow-y: auto;
  }

  .dropdown-option {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0.75rem;
    font-size: 0.875rem;
    color: #374151;
    cursor: pointer;
    transition: background-color 0.1s;
  }

  .dropdown-option:hover,
  .dropdown-option-focused {
    background: #f3f4f6;
  }

  .dropdown-option-selected {
    font-weight: 500;
    color: #111827;
  }

  .dropdown-check {
    color: #6366f1;
    flex-shrink: 0;
    margin-left: 0.5rem;
  }

  /* Dark mode support */
  .dark .dropdown-button {
    background: #1f2937;
    border-color: #374151;
    color: #f9fafb;
  }

  .dark .dropdown-button:focus {
    border-color: #818cf8;
    box-shadow: 0 0 0 3px rgba(129, 140, 248, 0.2);
  }

  .dark .dropdown-options {
    background: #1f2937;
    border-color: #374151;
  }

  .dark .dropdown-option {
    color: #e5e7eb;
  }

  .dark .dropdown-option:hover,
  .dark .dropdown-option-focused {
    background: #374151;
  }

  .dark .dropdown-option-selected {
    color: #f9fafb;
  }

  .dark .dropdown-check {
    color: #818cf8;
  }

  /* Page loader spinner - pure CSS, no font dependency */
  .spinner {
    width: 2rem;
    height: 2rem;
    border: 3px solid #e5e7eb;
    border-top-color: #6366f1;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .spinner-sm {
    width: 1rem;
    height: 1rem;
    border-width: 2px;
  }

  .spinner-lg {
    width: 3rem;
    height: 3rem;
    border-width: 4px;
  }

  /* Dark mode spinner */
  .dark .spinner {
    border-color: #374151;
    border-top-color: #818cf8;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Admin Feather logo font */
  .admin-logo-text {
    font-family: 'Lobster', cursive;
  }

  /* Admin chart container */
  .admin-chart-container {
    height: 250px;
  }
}

/* Add your custom styles below */
"""
    )

    # Example island
    (project_path / "static/islands/counter.js").write_text(
        '''/**
 * Counter island - Example interactive component
 *
 * Demonstrates:
 * - Reactive state
 * - localStorage persistence (refresh the page - count is remembered!)
 * - Action handlers
 * - DOM updates via render()
 */
island("counter", {
  // Enable localStorage persistence - state survives page refresh
  persist: true,

  state: {
    count: 0,
  },

  init() {
    // Only set from data attribute if no persisted value
    // (persisted state is automatically loaded before init)
    if (this.state.count === 0 && this.data.initial) {
      this.state.count = parseInt(this.data.initial);
    }
  },

  actions: {
    increment() {
      this.state.count++;
    },
    decrement() {
      this.state.count--;
    },
    reset() {
      this.state.count = 0;
      // Optionally clear localStorage too
      // this.clearPersisted();
    },
  },

  render(state) {
    return {
      ".count": state.count,
    };
  },
});
'''
    )

    # App JS - shared utilities and initialization
    (project_path / "static/js/app.js").write_text(
        '''/**
 * App Initialization
 * ===================
 * Common utilities and initialization for the application.
 *
 * Usage:
 *   Include in base.html:
 *   <script src="http://localhost:5173/static/js/app.js"></script>
 */

(function() {
  "use strict";

  // Custom confirm modal handler for hx-confirm
  (function() {
    const modal = document.getElementById("confirm-modal");
    const message = document.getElementById("confirm-message");
    if (!modal || !message) return;

    let issueRequest = null;

    document.body.addEventListener("htmx:confirm", (e) => {
      // Only intercept if there is an hx-confirm attribute with a message
      if (!e.detail.question) return;

      e.preventDefault();
      message.textContent = e.detail.question;
      issueRequest = e.detail.issueRequest;
      modal.classList.remove("hidden");
    });

    modal.addEventListener("click", (e) => {
      const action = e.target.dataset.action;
      if (action === "confirm") {
        issueRequest(true);
      }
      if (action === "confirm" || action === "cancel") {
        modal.classList.add("hidden");
      }
    });

    // Close on Escape key
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !modal.classList.contains("hidden")) {
        modal.classList.add("hidden");
      }
    });
  })();

  /**
   * Initialize all components on page load and after HTMX swaps.
   * Add your initialization code here.
   */
  function initComponents(container = document) {
    // Dropdowns are auto-initialized by dropdown.js
    // Add any app-specific initialization here

    // Example: Initialize tooltips
    // initTooltips(container);
  }

  // Initialize on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => initComponents());
  } else {
    initComponents();
  }

  // Re-initialize after HTMX swaps
  document.addEventListener("htmx:afterSwap", (e) => {
    initComponents(e.detail.target);
  });

  // Expose for manual initialization
  window.initComponents = initComponents;
})();
'''
    )

    # Models - only create if we have a database
    if has_database:
        # Models __init__.py - export models based on configuration
        if include_auth and tenant_mode == "multi":
            # Multi-tenant with auth: Tenant, User, Log, Account, AccountUser
            # Import order matters for migrations - tables with FKs must come after their dependencies
            (project_path / "models/__init__.py").write_text(
                '''"""SQLAlchemy models - Auto-discovered by Feather."""

from feather.db import db, Model
from models.tenant import Tenant
from models.user import User
from models.log import Log
from models.account import Account, AccountUser

__all__ = ["db", "Model", "Account", "AccountUser", "Log", "Tenant", "User"]
'''
            )
        elif include_auth:
            # Single-tenant with auth: User, Log, Account, AccountUser (no Tenant)
            # Import order matters for migrations - tables with FKs must come after their dependencies
            (project_path / "models/__init__.py").write_text(
                '''"""SQLAlchemy models - Auto-discovered by Feather."""

from feather.db import db, Model
from models.user import User
from models.log import Log
from models.account import Account, AccountUser

__all__ = ["db", "Model", "Account", "AccountUser", "Log", "User"]
'''
            )
        else:
            # No auth: just base imports
            (project_path / "models/__init__.py").write_text(
                '''"""SQLAlchemy models - Auto-discovered by Feather."""

from feather.db import db, Model

# Import your models here for easy access
# from models.user import User
'''
            )

        # Tenant model - only for multi-tenant mode
        if tenant_mode == "multi":
            (project_path / "models/tenant.py").write_text(
                _build_tenant_model_content()
            )

        # User model - only created when auth is enabled
        if include_auth:
            (project_path / "models/user.py").write_text(
                _build_user_model_content(include_auth=include_auth, tenant_mode=tenant_mode, user_fields=user_fields)
            )

        # Account model - for multi-profile support (when auth is enabled)
        if include_auth:
            (project_path / "models/account.py").write_text(
                _build_account_model_content()
            )

        # Log model - for admin panel event and error logging
        if include_admin:
            (project_path / "models/log.py").write_text(
                _build_log_model_content(tenant_mode=tenant_mode)
            )

    # Services __init__.py
    services_init_content = '''"""Business logic services - Auto-discovered by Feather."""

# Import your services here for easy access
# from services.user_service import UserService
'''
    if include_email:
        services_init_content += '''from services.email_service import EmailService

__all__ = ["EmailService"]
'''
    (project_path / "services/__init__.py").write_text(services_init_content)

    # Routes __init__.py
    (project_path / "routes/__init__.py").write_text(
        '''"""Route blueprints - Auto-discovered by Feather."""
'''
    )

    (project_path / "routes/api/__init__.py").write_text(
        '''"""API routes - Mounted at /api/*"""
'''
    )

    # Example API route - demonstrates auth protection if enabled
    (project_path / "routes/api/health.py").write_text(
        _build_api_routes_content(include_auth)
    )

    (project_path / "routes/pages/__init__.py").write_text(
        '''"""Page routes - Mounted at /*"""
'''
    )

    # Example page route
    (project_path / "routes/pages/home.py").write_text(
        '''"""Home page route."""

from flask import render_template

from feather import page


@page.get("/")
def home():
    """Home page."""
    return render_template("pages/home.html")
'''
    )

    # Base template
    (project_path / "templates/base.html").write_text(
        '''{% from "components/confirm_modal.html" import confirm_modal %}
{% from "components/prompt_modal.html" import prompt_modal %}
{% from "components/toast.html" import toast %}
{% from "components/page_loader.html" import page_loader %}
{% from "components/htmx_indicator.html" import htmx_indicator %}
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <meta name="theme-color" content="#000000">
    <link rel="icon" type="image/svg+xml" href="/feather-static/favicon.svg">
    <link rel="apple-touch-icon" href="/feather-static/apple-touch-icon.png">
    <title>{% block title %}My App{% endblock %}</title>

    <!-- Google Material Icons -->
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200">

    {% if config.DEBUG %}
    <!-- Development: Vite serves assets with HMR -->
    <script type="module" src="http://localhost:5173/@vite/client"></script>
    <link rel="stylesheet" href="http://localhost:5173/static/css/app.css">
    {% else %}
    <!-- Production: Use built assets from manifest -->
    <link rel="stylesheet" href="{{ feather_asset('styles') }}">
    {% endif %}

    {% block extra_head %}{% endblock %}
</head>
<body class="min-h-screen bg-gray-50" hx-headers='{"X-CSRFToken": "{{ csrf_token() }}"}'>
    {{ page_loader() }}
    {{ htmx_indicator() }}
    {% block content %}{% endblock %}

    <!-- HTMX -->
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    <!-- Idiomorph - morphing for HTMX polling without flicker -->
    <script src="https://unpkg.com/idiomorph@0.3.0/dist/idiomorph-ext.min.js"></script>

    <!-- Framework JS (served from feather package) -->
    <script src="/feather-static/api.js"></script>
    <script src="/feather-static/feather.js"></script>
    <script src="/feather-static/dropdown.js"></script>

    <!-- App JS (shared utilities) -->
    {% if config.DEBUG %}
    <script type="module" src="http://localhost:5173/static/js/app.js"></script>
    {% else %}
    <script src="{{ url_for('static', filename='js/app.js') }}"></script>
    {% endif %}

    <!-- Page islands -->
    {% block islands %}{% endblock %}

    <!-- Confirm Modal -->
    {{ confirm_modal() }}

    <!-- Prompt Modal -->
    {{ prompt_modal() }}

    <!-- Toast Notifications -->
    {{ toast() }}

    <!-- Pending Toast (shown after redirect) -->
    {% if pending_toast %}
    <div id="pending-toast-data" data-message="{{ pending_toast.message }}" data-type="{{ pending_toast.type }}" style="display:none;"></div>
    <script>
      document.addEventListener("DOMContentLoaded", function() {
        var el = document.getElementById("pending-toast-data");
        if (el && window.showToast) {
          window.showToast(el.dataset.message, el.dataset.type || "info");
        }
      });
    </script>
    {% endif %}

    {% block scripts %}{% endblock %}
</body>
</html>
'''
    )

    # Component: README.md - Guide for adding Tailwind Plus components
    (project_path / "templates/components/README.md").write_text(
        '''# Components

Jinja2 macro components for your UI. Designed to work with [Tailwind Plus](https://tailwindcss.com/plus).

## Icons

Feather includes [Google Material Icons](https://fonts.google.com/icons) out of the box.

```jinja2
{% from "components/icon.html" import icon %}

{{ icon("home") }}
{{ icon("settings", size="lg") }}
{{ icon("favorite", class="text-red-500") }}
```

**Sizes:** `sm` (18px), `md` (24px), `lg` (36px), `xl` (48px)

Browse icons at: https://fonts.google.com/icons

### Icon with Button

```jinja2
{% from "components/button.html" import button %}
{% from "components/icon.html" import icon %}
{{ button("Save", icon=icon("save", size="sm")) }}
```

## Tailwind Plus Components

### Quick Start

1. Copy HTML from Tailwind Plus
2. Wrap in a Jinja2 macro
3. Import and use in templates

### Example: Button Component

**Step 1: Copy from Tailwind Plus**

```html
<button class="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500">
  Button text
</button>
```

**Step 2: Create macro in `button.html`**

```jinja2
{% macro button(text, variant="primary", class="") %}
{% set base = "rounded-md px-3 py-2 text-sm font-semibold shadow-sm" %}
{% set variants = {
    "primary": "bg-indigo-600 text-white hover:bg-indigo-500",
    "secondary": "bg-white text-gray-900 ring-1 ring-gray-300 hover:bg-gray-50"
} %}
<button class="{{ base }} {{ variants[variant] }} {{ class }}">{{ text }}</button>
{% endmacro %}
```

**Step 3: Use in templates**

```jinja2
{% from "components/button.html" import button %}

{{ button("Save") }}
{{ button("Cancel", variant="secondary") }}
```

## Tips

- Use `class=""` parameter for additional Tailwind classes
- Add explicit parameters for HTML attributes you need (e.g., `disabled=false`, `placeholder=""`)
- Use `caller()` for components with children (cards, modals)

## Component Pattern

```jinja2
{# component_name.html #}
{% macro component_name(required_param, optional="default", class="") %}
<element class="{{ class }}">
    Content here
</element>
{% endmacro %}
```

## Components with Children

For components that wrap content (cards, modals), use `caller()`:

```jinja2
{# card.html #}
{% macro card(title="", class="") %}
<div class="bg-white shadow rounded-lg {{ class }}">
    {% if title %}<h3 class="font-bold p-4">{{ title }}</h3>{% endif %}
    <div class="p-4">{{ caller() }}</div>
</div>
{% endmacro %}
```

Usage:

```jinja2
{% from "components/card.html" import card %}

{% call card(title="My Card") %}
    <p>This is the card content.</p>
{% endcall %}
```
'''
    )

    # HTMX Partial: like_button.html - Example server-driven interaction
    (project_path / "templates/partials/like_button.html").write_text(
        '''{#
Like Button Partial
===================
An HTMX-powered like button that updates without page reload.

This template is returned by the server after a like/unlike action.
HTMX swaps this HTML into the page, updating the button state.

Usage in a page template:
    {% include "partials/like_button.html" %}

Flask route example:
    @api.post("/posts/<post_id>/like")
    def like_post(post_id):
        post = Post.query.get_or_404(post_id)
        post.toggle_like(current_user)
        return render_template("partials/like_button.html", post=post, liked=True)
#}
{% from "components/icon.html" import icon %}

<button hx-post="/api/posts/{{ post.id }}/{% if liked %}unlike{% else %}like{% endif %}"
        hx-swap="outerHTML"
        class="flex items-center gap-2 px-4 py-2 rounded-lg transition-colors
               {% if liked %}bg-red-50 text-red-600 hover:bg-red-100{% else %}bg-gray-100 text-gray-600 hover:bg-gray-200{% endif %}">
    {{ icon("favorite", size="sm") }}
    <span>{{ post.like_count if post else 0 }}</span>
</button>
'''
    )

    # HTMX Partial: load_more.html - Example infinite scroll pattern
    (project_path / "templates/partials/load_more.html").write_text(
        '''{#
Load More Button Partial
========================
HTMX-powered "load more" pattern for pagination.

Usage:
    {% include "partials/load_more.html" %}

Flask route example:
    @page.get("/posts")
    def posts():
        page = request.args.get('page', 1, type=int)
        posts = Post.query.paginate(page=page, per_page=10)

        if request.headers.get('HX-Request'):
            # HTMX request - return just the posts HTML
            return render_template("partials/posts_list.html", posts=posts.items, page=page)

        return render_template("pages/posts.html", posts=posts.items, page=page)
#}

{% if has_more %}
<div hx-get="{{ next_url }}"
     hx-trigger="revealed"
     hx-swap="outerHTML"
     class="flex justify-center py-8">
    <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
</div>
{% endif %}
'''
    )

    # Home page template - different versions for auth vs no-auth
    if include_auth:
        # Full template with Google OAuth login
        (project_path / "templates/pages/home.html").write_text(
            '''{% extends "base.html" %}
{% from "components/icon.html" import icon %}

{% block title %}Welcome - My App{% endblock %}

{% block content %}
<div class="container mx-auto px-4 py-12">
    <div class="max-w-2xl mx-auto text-center">
        <h1 class="text-3xl font-bold text-gray-900 mb-3 flex items-center justify-center gap-3">
            <svg class="w-14 h-14" viewBox="0 0 72 72" xmlns="http://www.w3.org/2000/svg">
                <path fill="#b399c8" d="M42.3339,49.147a29.9446,29.9446,0,0,1-19.3378-8.1514h0c-8.0137-7.3643-8.378-18.0752-8.5332-22.6484l-.0215-.627a2.9039,2.9039,0,0,1,3.457-2.9512c17.0049,3.3555,21.6943,16.3243,22.0557,17.4a49.5426,49.5426,0,0,1,3.5742,15.9219,1,1,0,0,1-.9668,1.0518C42.5322,49.144,42.455,49.147,42.3339,49.147Z"/>
                <path fill="#61b2e4" d="M44.4355,55.3159c-11.6455,0-17.3757-6.9734-17.6521-7.3542a1,1,0,0,1,.2617-1.4239,11.1031,11.1031,0,0,1,12.7742-1.5734c-1.4648-9.0782,1.877-13.5684,2.0312-13.77a.9982.9982,0,0,1,.75-.39.9705.9705,0,0,1,.78.3242c8.9434,9.7715,8.793,16.5322,7.9072,19.6914-.0341.1406-1.0615,4.0918-4.7714,4.4063C45.8046,55.2876,45.1113,55.3159,44.4355,55.3159Z"/>
                <path fill="none" stroke="#1f2937" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M55.1837,57.69S34.96,45.877,23.0974,24.2062"/>
                <path fill="none" stroke="#1f2937" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M45.2281,54.3024C33.2973,54.7629,27.6,47.4216,27.6,47.4216"/>
                <path fill="none" stroke="#1f2937" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M40.528,42.4827c-.5595-7.1945,2.1157-10.6784,2.1157-10.6784,8.8346,9.6533,8.4063,16.1616,7.6813,18.7468"/>
                <path fill="none" stroke="#1f2937" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M37.0138,47.4216A30.15,30.15,0,0,1,23.673,40.26c-8.0725-7.4186-8.0674-18.2414-8.2321-22.5774a1.9032,1.9032,0,0,1,2.2642-1.9314C34.6938,19.1027,39.02,32.5284,39.02,32.5284"/>
            </svg>
            Welcome to Feather
        </h1>
        <p class="text-lg text-gray-600 mb-6">
            An AI-native web framework for server-rendered apps using HTMX and vanilla JavaScript islands.
        </p>

        <!-- Interactive counter island demo -->
        <div data-island="counter" data-initial="0"
             class="inline-flex items-center gap-4 p-4 bg-white rounded-xl shadow-lg mb-6">
            <button data-action="decrement"
                    class="w-10 h-10 flex items-center justify-center bg-gray-100 text-gray-600 rounded-full hover:bg-gray-200 transition-colors">
                {{ icon("remove", size="sm") }}
            </button>
            <span class="count text-2xl font-bold text-gray-900 w-12 text-center">0</span>
            <button data-action="increment"
                    class="w-10 h-10 flex items-center justify-center bg-indigo-500 text-white rounded-full hover:bg-indigo-600 transition-colors">
                {{ icon("add", size="sm") }}
            </button>
        </div>

        {% if current_user.is_authenticated %}
        <!-- Logged in: Show profile card -->
        <div class="bg-white rounded-xl shadow-lg p-6 text-left">
            <div class="flex items-start justify-between">
                <div class="flex items-center gap-4">
                    {% if current_user.profile_image_url %}
                    <img src="{{ current_user.profile_image_url }}"
                         alt="Profile"
                         class="w-14 h-14 rounded-full"
                         referrerpolicy="no-referrer">
                    {% else %}
                    <div class="w-14 h-14 rounded-full bg-gray-100 flex items-center justify-center">
                        {{ icon("person", size="md", class="text-gray-400") }}
                    </div>
                    {% endif %}
                    <div>
                        <h2 class="text-lg font-semibold text-gray-900">
                            {{ current_user.display_name or current_user.email }}
                        </h2>
                        <p class="text-sm text-gray-500">{{ current_user.email }}</p>
                    </div>
                </div>
                <a href="{{ url_for('auth.logout') }}"
                   class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors">
                    {{ icon("logout", size="sm") }}
                    Sign Out
                </a>
            </div>

            {% if not current_user.active %}
            {% set is_suspended = current_user.approved_at is defined and current_user.approved_at %}
            <div class="mt-4 rounded-lg p-4 {% if is_suspended %}bg-red-50 border border-red-200{% else %}bg-gray-100{% endif %}">
                <div class="flex items-center gap-2 {% if is_suspended %}text-red-800{% else %}text-gray-700{% endif %}">
                    {{ icon("block" if is_suspended else "hourglass_empty", class="text-red-600" if is_suspended else "text-gray-500") }}
                    <span class="font-medium">{% if is_suspended %}Account Suspended{% else %}Pending Approval{% endif %}</span>
                </div>
                <p class="text-sm {% if is_suspended %}text-red-700{% else %}text-gray-600{% endif %} mt-1">
                    {% if is_suspended %}
                    Your account has been suspended. Please contact your administrator.
                    {% else %}
                    Your account is awaiting administrator approval.
                    {% endif %}
                </p>
            </div>
            {% endif %}
        </div>
        {% else %}
        <!-- Not logged in: Show sign in card -->
        <div class="bg-white rounded-xl shadow-lg p-6">
            <p class="text-gray-600 mb-4 text-sm">Try Google OAuth with automatic user creation and admin approval workflow.</p>
            <a href="{{ url_for('google_auth.login') }}"
               class="inline-flex items-center gap-3 px-6 py-3 text-sm font-medium text-white bg-black rounded-lg hover:bg-gray-800">
                <svg class="w-5 h-5" viewBox="0 0 24 24">
                    <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                    <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                    <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                    <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                Sign in with Google
            </a>
        </div>
        {% endif %}

        <p class="mt-6 text-sm text-gray-500">
            Edit <code class="bg-gray-100 px-2 py-1 rounded">templates/pages/home.html</code> to get started.
        </p>
    </div>
</div>
{% endblock %}

{% block islands %}
{% if config.DEBUG %}
<script type="module" src="http://localhost:5173/static/islands/counter.js"></script>
{% else %}
<script src="{{ feather_asset('islands/counter') }}"></script>
{% endif %}
{% endblock %}
'''
        )
    else:
        # Simple template without auth references
        (project_path / "templates/pages/home.html").write_text(
            '''{% extends "base.html" %}
{% from "components/icon.html" import icon %}

{% block title %}Welcome - My App{% endblock %}

{% block content %}
<div class="container mx-auto px-4 py-12">
    <div class="max-w-2xl mx-auto text-center">
        <h1 class="text-3xl font-bold text-gray-900 mb-3 flex items-center justify-center gap-3">
            <svg class="w-14 h-14" viewBox="0 0 72 72" xmlns="http://www.w3.org/2000/svg">
                <path fill="#b399c8" d="M42.3339,49.147a29.9446,29.9446,0,0,1-19.3378-8.1514h0c-8.0137-7.3643-8.378-18.0752-8.5332-22.6484l-.0215-.627a2.9039,2.9039,0,0,1,3.457-2.9512c17.0049,3.3555,21.6943,16.3243,22.0557,17.4a49.5426,49.5426,0,0,1,3.5742,15.9219,1,1,0,0,1-.9668,1.0518C42.5322,49.144,42.455,49.147,42.3339,49.147Z"/>
                <path fill="#61b2e4" d="M44.4355,55.3159c-11.6455,0-17.3757-6.9734-17.6521-7.3542a1,1,0,0,1,.2617-1.4239,11.1031,11.1031,0,0,1,12.7742-1.5734c-1.4648-9.0782,1.877-13.5684,2.0312-13.77a.9982.9982,0,0,1,.75-.39.9705.9705,0,0,1,.78.3242c8.9434,9.7715,8.793,16.5322,7.9072,19.6914-.0341.1406-1.0615,4.0918-4.7714,4.4063C45.8046,55.2876,45.1113,55.3159,44.4355,55.3159Z"/>
                <path fill="none" stroke="#1f2937" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M55.1837,57.69S34.96,45.877,23.0974,24.2062"/>
                <path fill="none" stroke="#1f2937" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M45.2281,54.3024C33.2973,54.7629,27.6,47.4216,27.6,47.4216"/>
                <path fill="none" stroke="#1f2937" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M40.528,42.4827c-.5595-7.1945,2.1157-10.6784,2.1157-10.6784,8.8346,9.6533,8.4063,16.1616,7.6813,18.7468"/>
                <path fill="none" stroke="#1f2937" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M37.0138,47.4216A30.15,30.15,0,0,1,23.673,40.26c-8.0725-7.4186-8.0674-18.2414-8.2321-22.5774a1.9032,1.9032,0,0,1,2.2642-1.9314C34.6938,19.1027,39.02,32.5284,39.02,32.5284"/>
            </svg>
            Welcome to Feather
        </h1>
        <p class="text-lg text-gray-600 mb-6">
            An AI-native web framework for server-rendered apps using HTMX and vanilla JavaScript islands.
        </p>

        <!-- Interactive counter island demo -->
        <div data-island="counter" data-initial="0"
             class="inline-flex items-center gap-4 p-4 bg-white rounded-xl shadow-lg mb-6">
            <button data-action="decrement"
                    class="w-10 h-10 flex items-center justify-center bg-gray-100 text-gray-600 rounded-full hover:bg-gray-200 transition-colors">
                {{ icon("remove", size="sm") }}
            </button>
            <span class="count text-2xl font-bold text-gray-900 w-12 text-center">0</span>
            <button data-action="increment"
                    class="w-10 h-10 flex items-center justify-center bg-indigo-500 text-white rounded-full hover:bg-indigo-600 transition-colors">
                {{ icon("add", size="sm") }}
            </button>
        </div>

        <div class="bg-white rounded-xl shadow-lg p-6">
            <h2 class="text-lg font-semibold text-gray-900 mb-3">Your app is running!</h2>
            <ul class="text-left text-sm text-gray-600 space-y-2">
                <li class="flex items-center gap-2">
                    {{ icon("check_circle", size="sm", class="text-green-500") }}
                    Edit <code class="bg-gray-100 px-1.5 py-0.5 rounded">routes/pages/home.py</code> to change this page
                </li>
                <li class="flex items-center gap-2">
                    {{ icon("check_circle", size="sm", class="text-green-500") }}
                    Create new routes in <code class="bg-gray-100 px-1.5 py-0.5 rounded">routes/pages/</code>
                </li>
                <li class="flex items-center gap-2">
                    {{ icon("check_circle", size="sm", class="text-green-500") }}
                    Add templates in <code class="bg-gray-100 px-1.5 py-0.5 rounded">templates/pages/</code>
                </li>
            </ul>
        </div>

        <p class="mt-6 text-sm text-gray-500">
            Edit <code class="bg-gray-100 px-2 py-1 rounded">templates/pages/home.html</code> to get started.
        </p>
    </div>
</div>
{% endblock %}

{% block islands %}
{% if config.DEBUG %}
<script type="module" src="http://localhost:5173/static/islands/counter.js"></script>
{% else %}
<script src="{{ feather_asset('islands/counter') }}"></script>
{% endif %}
{% endblock %}
'''
        )

    # Alembic config - only if we have a database
    if has_database:
        (project_path / "migrations/alembic.ini").write_text(
            """[alembic]
script_location = migrations
prepend_sys_path = .

[post_write_hooks]

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""
        )

        (project_path / "migrations/env.py").write_text(
            '''"""Alembic migration environment."""

from logging.config import fileConfig

from alembic import context
from flask import current_app

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = current_app.extensions["migrate"].db.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = current_app.extensions["migrate"].db.engine

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
'''
        )

        (project_path / "migrations/script.py.mako").write_text(
            '''"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
'''
        )

    # Tests
    (project_path / "tests/__init__.py").write_text("")

    if has_database:
        (project_path / "tests/conftest.py").write_text(
            '''"""Pytest configuration for Feather apps."""

import pytest

from app import app as flask_app
from feather.db import db


# =============================================================================
# CSRF-Aware Test Client
# =============================================================================

class CsrfTestClient:
    """Test client wrapper that automatically handles CSRF tokens.

    Use this for POST/PUT/DELETE requests that require CSRF protection.

    Usage:
        def test_something(csrf_client):
            response = csrf_client.post('/api/items', json={'name': 'test'})
    """

    def __init__(self, flask_client):
        self._client = flask_client
        self._csrf_token = None

    def _get_csrf_token(self):
        if self._csrf_token is None:
            response = self._client.get('/_test_csrf_token')
            self._csrf_token = response.get_json()['token']
        return self._csrf_token

    def _add_csrf_header(self, kwargs):
        headers = dict(kwargs.get('headers', {}))
        headers['X-CSRFToken'] = self._get_csrf_token()
        kwargs['headers'] = headers
        return kwargs

    def get(self, *args, **kwargs):
        return self._client.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        return self._client.post(*args, **self._add_csrf_header(kwargs))

    def put(self, *args, **kwargs):
        return self._client.put(*args, **self._add_csrf_header(kwargs))

    def delete(self, *args, **kwargs):
        return self._client.delete(*args, **self._add_csrf_header(kwargs))

    def patch(self, *args, **kwargs):
        return self._client.patch(*args, **self._add_csrf_header(kwargs))

    def __getattr__(self, name):
        return getattr(self._client, name)


def _register_csrf_endpoint(app):
    """Register CSRF token endpoint for testing.

    Must be called BEFORE any requests are made to the app.
    """
    # Only register once per app
    if '/_test_csrf_token' in [rule.rule for rule in app.url_map.iter_rules()]:
        return

    from flask import jsonify
    from flask_wtf.csrf import generate_csrf

    @app.route('/_test_csrf_token')
    def _get_csrf_token():
        return jsonify({'token': generate_csrf()})


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def app():
    """Create application for testing."""
    flask_app.config["TESTING"] = True
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    # Register CSRF endpoint BEFORE any requests
    _register_csrf_endpoint(flask_app)

    with flask_app.app_context():
        db.create_all()

    yield flask_app

    # Cleanup
    with flask_app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(app):
    """Create raw test client (no CSRF handling)."""
    return app.test_client()


@pytest.fixture
def csrf_client(app):
    """Create CSRF-aware test client for POST/PUT/DELETE."""
    return CsrfTestClient(app.test_client())
'''
        )
    else:
        (project_path / "tests/conftest.py").write_text(
            '''"""Pytest configuration for Feather apps."""

import pytest

from app import app as flask_app


@pytest.fixture
def app():
    """Create application for testing."""
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()
'''
        )

    (project_path / "tests/test_home.py").write_text(
        '''"""Test home page."""


def test_home_page(client):
    """Test home page returns 200."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Welcome to Feather" in response.data
'''
    )

    # CLAUDE.md - Compact guide for AI coding assistants
    (project_path / "CLAUDE.md").write_text(
        _build_claude_md_content(
            database=database,
            include_auth=include_auth,
            tenant_mode=tenant_mode,
            include_cache=include_cache,
            include_jobs=include_jobs,
        )
    )

    # Admin panel scaffolding (when auth enabled)
    if include_auth:
        # Admin routes
        (project_path / "routes/pages/admin.py").write_text(
            _build_admin_routes(tenant_mode, include_email)
        )

        # Account routes (pending/suspended pages)
        (project_path / "routes/pages/account.py").write_text(
            _build_account_routes()
        )

        # Admin service
        (project_path / "services/admin_service.py").write_text(
            _build_admin_service(tenant_mode)
        )

        # Email service (when email enabled)
        if include_email:
            (project_path / "services/email_service.py").write_text(
                _build_email_service_content()
            )

        # Admin Chart JS - Chart.js rendering for analytics
        (project_path / "static/js/admin-chart.js").write_text(
            '''/**
 * Admin Analytics Chart
 * ======================
 * Chart.js rendering for user growth analytics.
 */

(function() {
  "use strict";

  const container = document.getElementById("chart-container");
  const apiUrl = container?.dataset.apiUrl;
  let chart = null;

  async function loadAndRender(days) {
    if (!apiUrl) return;

    try {
      const result = await ApiUtility.get(`${apiUrl}?days=${days}`);
      if (result.success && result.data) {
        renderChart(result.data);
      } else {
        console.error("Chart data error:", result.error);
      }
    } catch (error) {
      console.error("Failed to load user growth data:", error);
    }
  }

  function renderChart(data) {
    const ctx = document.getElementById("user-growth-canvas");
    if (!ctx) return;

    if (chart) chart.destroy();

    chart = new Chart(ctx, {
      type: "line",
      data: {
        labels: data.map(d => {
          const date = new Date(d.date);
          return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
        }),
        datasets: [{
          label: "New Users",
          data: data.map(d => d.count),
          borderColor: "#000",
          backgroundColor: "rgba(0, 0, 0, 0.1)",
          fill: true,
          tension: 0.4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, ticks: { stepSize: 1, precision: 0 } }
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const selector = document.getElementById("time-range-select");
    if (selector) {
      selector.addEventListener("change", (e) => loadAndRender(parseInt(e.target.value)));
    }
    loadAndRender(30);
  });
})();
'''
        )

        # Admin JS - scripts for admin panel
        (project_path / "static/js/admin.js").write_text(
            '''/**
 * Admin Panel Scripts
 * ====================
 * JavaScript for the admin panel functionality.
 */

(function() {
  "use strict";

  // Avatar dropdown toggle
  function initAvatarDropdown() {
    const avatarBtn = document.getElementById("admin-avatar-btn");
    const dropdown = document.getElementById("admin-avatar-dropdown");
    const avatarImg = document.getElementById("admin-avatar-img");

    if (avatarImg) {
      avatarImg.addEventListener("error", () => {
        const fallback = avatarImg.dataset.fallback;
        if (fallback && avatarImg.src !== fallback) avatarImg.src = fallback;
      });
    }

    if (avatarBtn && dropdown) {
      avatarBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        dropdown.classList.toggle("show");
      });

      document.addEventListener("click", (e) => {
        if (!dropdown.contains(e.target) && !avatarBtn.contains(e.target)) {
          dropdown.classList.remove("show");
        }
      });
    }
  }

  // Custom confirm modal for admin
  let confirmCallback = null;

  function initConfirmModal() {
    const modal = document.getElementById("confirm-modal");
    const message = document.getElementById("confirm-message");
    const confirmBtn = document.getElementById("confirm-button");
    if (!modal || !message) return;

    // Handle htmx:confirm events
    document.body.addEventListener("htmx:confirm", (evt) => {
      const question = evt.detail.question;
      if (!question) return;

      evt.preventDefault();
      message.textContent = question;
      modal.classList.remove("hidden");
      confirmCallback = () => evt.detail.issueRequest(true);
    });

    // Confirm button click
    if (confirmBtn) {
      confirmBtn.addEventListener("click", () => {
        if (confirmCallback) confirmCallback();
        closeConfirmModal();
      });
    }

    // Modal backdrop and cancel clicks
    modal.addEventListener("click", (e) => {
      const action = e.target.dataset.action;
      if (action === "cancel" || e.target === modal.querySelector(".absolute.inset-0")) {
        closeConfirmModal();
      }
    });
  }

  function closeConfirmModal() {
    const modal = document.getElementById("confirm-modal");
    if (modal) modal.classList.add("hidden");
    confirmCallback = null;
  }

  // Expose closeConfirmModal globally for the modal backdrop
  window.closeConfirmModal = closeConfirmModal;

  // Handle escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeConfirmModal();
      document.getElementById("admin-avatar-dropdown")?.classList.remove("show");
    }
  });

  // Show pending toast on page load (if set by server)
  function initPendingToast() {
    const pendingToast = document.getElementById("pending-toast-data");
    if (pendingToast && window.showToast) {
      const message = pendingToast.dataset.message;
      const type = pendingToast.dataset.type || "success";
      if (message) {
        window.showToast(message, type);
      }
    }
  }

  // Handle email selection in admin tools
  function initEmailSelector() {
    document.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-action='select-email']");
      if (btn) {
        const email = btn.dataset.email;
        const input = document.querySelector("[name='to']");
        const dropdown = document.getElementById("user-dropdown");
        if (input) input.value = email;
        if (dropdown) dropdown.innerHTML = "";
      }
    });
  }

  // Handle clickable rows (navigation)
  function initClickableRows() {
    document.addEventListener("click", (e) => {
      const row = e.target.closest("[data-href]");
      if (row && !e.target.closest("a, button")) {
        window.location = row.dataset.href;
      }
    });
  }

  // Handle admin avatar image fallbacks
  function initAvatarFallbacks() {
    document.querySelectorAll(".admin-avatar-img").forEach((img) => {
      img.addEventListener("error", () => {
        const fallback = img.dataset.fallback;
        if (fallback && img.src !== fallback) img.src = fallback;
      });
    });
  }

  // Handle tenant modal
  function initTenantModal() {
    const modal = document.getElementById("create-tenant-modal");
    if (!modal) return;

    document.addEventListener("click", (e) => {
      const action = e.target.dataset.action;
      if (action === "show-create-tenant") {
        modal.classList.remove("hidden");
      } else if (action === "hide-create-tenant") {
        modal.classList.add("hidden");
      }
    });
  }

  // Initialize on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      initAvatarDropdown();
      initConfirmModal();
      initPendingToast();
      initEmailSelector();
      initClickableRows();
      initAvatarFallbacks();
      initTenantModal();
    });
  } else {
    initAvatarDropdown();
    initConfirmModal();
    initPendingToast();
    initEmailSelector();
    initClickableRows();
    initAvatarFallbacks();
    initTenantModal();
  }
})();
'''
        )

        # Admin templates - pages
        (project_path / "templates/pages/admin/base.html").write_text(
            _build_admin_base_template(tenant_mode)
        )
        (project_path / "templates/pages/admin/users.html").write_text(
            _build_admin_users_template()
        )
        (project_path / "templates/pages/admin/user_detail.html").write_text(
            _build_admin_user_detail_template()
        )
        (project_path / "templates/pages/admin/tools.html").write_text(
            _build_admin_tools_template(include_email)
        )
        (project_path / "templates/pages/admin/analytics.html").write_text(
            _build_admin_analytics_template()
        )
        (project_path / "templates/pages/admin/logs.html").write_text(
            _build_admin_logs_template()
        )

        # Admin templates - partials
        (project_path / "templates/partials/admin/users_table.html").write_text(
            _build_admin_users_table_partial()
        )
        (project_path / "templates/partials/admin/user_actions.html").write_text(
            _build_admin_user_actions_partial()
        )
        if include_email:
            (project_path / "templates/partials/admin/email_result.html").write_text(
                _build_admin_email_result_partial()
            )
        (project_path / "templates/partials/admin/logs_table.html").write_text(
            _build_admin_logs_table_partial()
        )

        # Multi-tenant admin templates
        if tenant_mode == "multi":
            (project_path / "templates/pages/admin/tenants.html").write_text(
                _build_admin_tenants_template()
            )
            (project_path / "templates/pages/admin/tenant_detail.html").write_text(
                _build_admin_tenant_detail_template()
            )
            (project_path / "templates/partials/admin/tenants_table.html").write_text(
                _build_admin_tenants_table_partial()
            )
            (project_path / "templates/partials/admin/tenant_actions.html").write_text(
                _build_admin_tenant_actions_partial()
            )

        # Account status pages (pending approval, suspended)
        (project_path / "templates/pages/account/pending.html").write_text(
            _build_account_pending_template()
        )
        (project_path / "templates/pages/account/suspended.html").write_text(
            _build_account_suspended_template()
        )

    # seeds.py - Database seed file (only when auth enabled)
    if include_auth:
        (project_path / "seeds.py").write_text(
            _build_seeds_content(admin_email=admin_email, tenant_mode=tenant_mode)
        )

        # Auth tests
        (project_path / "tests/test_auth.py").write_text(
            '''"""Tests for authentication flows."""

import pytest
from models.user import User
from feather.db import db


class TestPublicAccess:
    """Test public route access."""

    def test_home_page_accessible(self, client):
        """Home page is accessible without authentication."""
        response = client.get("/")
        assert response.status_code == 200

    def test_health_check_accessible(self, client):
        """Health check is accessible without authentication."""
        response = client.get("/health")
        assert response.status_code == 200


class TestProtectedRoutes:
    """Test that protected routes require authentication."""

    def test_admin_requires_auth(self, client):
        """Admin panel requires authentication."""
        response = client.get("/admin/")
        # Should redirect to login or return 401
        assert response.status_code in [302, 401, 403]

    def test_admin_users_requires_auth(self, client):
        """Admin users page requires authentication."""
        response = client.get("/admin/users")
        assert response.status_code in [302, 401, 403]


class TestLoginFlow:
    """Test login behavior."""

    def test_google_login_route_exists(self, client):
        """Google login route is registered."""
        response = client.get("/auth/google/login")
        # 302 = OAuth configured and redirecting
        # 503 = OAuth not configured (expected in tests without credentials)
        assert response.status_code in [302, 503]

    def test_logout_route_exists(self, client):
        """Logout route is registered and redirects."""
        response = client.get("/auth/logout")
        # Should redirect to home
        assert response.status_code == 302
'''
        )

        # Admin panel tests
        (project_path / "tests/test_admin.py").write_text(
            '''"""Tests for admin panel functionality."""

import pytest
from models.user import User
from feather.db import db


@pytest.fixture
def admin_user(app):
    """Create an admin user for testing."""
    with app.app_context():
        user = User(
            email="admin@test.com",
            display_name="Test Admin",
            active=True,
            role="admin",
        )
        db.session.add(user)
        db.session.commit()
        yield user


@pytest.fixture
def regular_user(app):
    """Create a regular user for testing."""
    with app.app_context():
        user = User(
            email="user@test.com",
            display_name="Test User",
            active=True,
            role="user",
        )
        db.session.add(user)
        db.session.commit()
        yield user


class TestAdminAccess:
    """Test admin panel access control."""

    def test_unauthenticated_blocked(self, client):
        """Unauthenticated users cannot access admin."""
        response = client.get("/admin/users")
        assert response.status_code in [302, 401, 403]

    # Note: Testing authenticated admin access requires simulating login,
    # which depends on your session handling. You can add tests like:
    #
    # def test_admin_can_view_users(self, admin_client):
    #     response = admin_client.get("/admin/users")
    #     assert response.status_code == 200


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_returns_status(self, client):
        """Health endpoint returns status."""
        response = client.get("/health")
        data = response.get_json()
        assert "status" in data

    def test_health_live_always_ok(self, client):
        """Liveness probe always returns 200."""
        response = client.get("/health/live")
        assert response.status_code == 200
'''
        )

    click.echo("  Created project files")


def _build_claude_md_content(
    database: str,
    include_auth: bool,
    tenant_mode: str,
    include_cache: bool,
    include_jobs: bool,
) -> str:
    """Build CLAUDE.md content with conditional sections.

    Args:
        database: Database type ("none", "sqlite", or "postgresql")
        include_auth: Whether authentication is enabled (includes admin panel)
        tenant_mode: Tenant mode ("single" or "multi"), None if no auth
        include_cache: Whether Redis caching is enabled
        include_jobs: Whether background jobs are enabled
    """
    has_database = database != "none"
    is_multi_tenant = tenant_mode == "multi"

    # Build feature list for header
    features = []
    if has_database:
        features.append(f"Database: {database}")
    if include_auth:
        features.append(f"Auth: {'multi-tenant' if is_multi_tenant else 'single-tenant'}")
    if include_cache:
        features.append("Cache: yes")
    if include_jobs:
        features.append("Jobs: yes")

    content = f'''# CLAUDE.md - Feather Project

Guide for AI coding assistants working on this Feather project.

**App Configuration:** {', '.join(features) if features else 'Minimal (no database)'}

---

## ⚠️ Critical Rules (MUST FOLLOW)

These rules are mandatory. Violating them will cause bugs, security issues, or poor UX.

### 1. No Inline Styles or Scripts
- **Never use inline Tailwind classes** in templates
- **Never use inline `<script>` blocks** in templates
- **Never use inline event handlers** (`onclick`, `onchange`, etc.)
- Put CSS in `static/css/app.css` using `@apply`
- Put JS in `static/js/` (shared) or `static/islands/` (components)
- Attach handlers with `addEventListener` in JS files

### 2. Never Use Native Browser Dialogs
- **Never use `alert()`** - Use modal components with X close button
- **Never use `confirm()`** - Use `hx-confirm` (styled modal) or custom modal
- **Never use `prompt()`** - Use `window.showPrompt()` (styled modal)
- All modals must close with ESC key and have visible X button

### 3. Never Use Raw fetch()
- **Always use `ApiUtility`** from `/feather-static/api.js`
- It provides: automatic CSRF tokens, retry logic, error handling
- Example: `ApiUtility.post('/api/items', data)` not `fetch('/api/items', ...)`

### 4. Progressive Enhancement Order
- Try **Components** first (server-rendered Jinja2 macros)
- Then **HTMX** (server interactions without page reload)
- Only use **Islands** when client-side state is truly needed
- 90% of features should work with Components + HTMX

### 5. Keep Routes Thin, Services Fat
- Routes: validate input, call services, return response
- Services: all business logic, database operations, validation rules
- Never put complex logic in route handlers
'''

    # Add auth rule only if auth is enabled
    if include_auth:
        content += '''
### 6. Always Protect Routes
- Use `@auth_required` on all routes that need authentication
- Use `@admin_required` for admin-only routes
- Check `current_user.is_active` for suspended user handling
'''

    # Add multi-tenant rule only if multi-tenant
    if is_multi_tenant:
        content += '''
### 7. Never Bypass Tenant Isolation
- Always filter queries by `tenant_id`
- Use `get_current_tenant_id()` or `require_same_tenant()`
- Never trust user input for tenant identification
'''

    # Add Google image rule if auth enabled
    if include_auth:
        content += '''
### 8. Google Profile Images Need referrerpolicy
- Always add `referrerpolicy="no-referrer"` to `<img>` tags with Google URLs
- Without this, browsers block the images
'''

    content += '''
---

## Project Structure

```
'''

    if has_database:
        content += '''models/          # SQLAlchemy models (auto-discovered)
'''

    content += '''services/        # Business logic (auto-discovered)
routes/
  api/           # API routes → /api/*
  pages/         # Page routes → /*
templates/
  components/    # Custom/override components
  partials/      # HTMX response fragments
  pages/         # Full page templates
static/
  css/app.css    # Tailwind styles (use @apply)
  islands/       # Interactive JS components
```

## Development Commands

```bash
feather dev              # Start dev server (port 5173)
feather routes           # List all routes
feather shell            # Python shell with app context
'''

    if has_database:
        content += '''feather db migrate       # Create migration
feather db upgrade       # Apply migrations
'''

    if include_auth:
        content += '''python seeds.py          # Create admin user (first time)
'''

    content += '''```

## Quick Reference

### Three-Layer UI

| Need | Use |
|------|-----|
| Static UI | **Component** (Jinja2 macro) |
| Server interaction | **HTMX** (returns HTML partial) |
| Complex client state | **Island** (JS with reactive state) |

### Routes
```python
@api.get("/users")
@inject(UserService)
def list_users(user_service):
    return {"users": user_service.list_all()}
```

### Services
```python
class UserService(Service):
    def create(self, email: str) -> User:
        user = User(email=email)
        self.save(user)
        return user
```

### HTMX Cross-Element Updates
```python
def with_trigger(content, trigger="dataUpdated"):
    response = make_response(content)
    response.headers["HX-Trigger"] = trigger
    return response
```

### Islands
```javascript
island("counter", {
  state: { count: 0 },
  actions: {
    increment() { this.state.count++; }
  },
  render(state) {
    return { ".count": state.count };
  }
});
```
'''

    if include_auth:
        content += '''
### Auth Decorators
```python
@auth_required      # Any logged-in user
@admin_required     # User with role="admin"
@role_required("editor")  # Specific role
```
'''

    if is_multi_tenant:
        content += '''
### Tenant Scoping
```python
users = User.query.filter_by(tenant_id=current_user.tenant_id).all()
```
'''

    content += '''
---

## Full Documentation

For comprehensive patterns, architecture, and advanced features:
https://github.com/RolandFlyBoy/Feather/blob/main/README.md
'''

    return content


def _init_git(project_path: Path):
    """Initialize git repository."""
    try:
        subprocess.run(
            ["git", "init"],
            cwd=project_path,
            capture_output=True,
            check=True,
        )
        click.echo("  Initialized git repository")
    except (subprocess.CalledProcessError, FileNotFoundError):
        click.echo("  Skipped git init (git not available)")


def _install_dependencies(project_path: Path):
    """Install npm dependencies."""
    try:
        subprocess.run(
            ["npm", "install"],
            cwd=project_path,
            capture_output=True,
            check=True,
        )
        click.echo("  Installed npm dependencies")
    except (subprocess.CalledProcessError, FileNotFoundError):
        click.echo("  Skipped npm install (npm not available)")
        click.echo("  Run 'npm install' manually to install frontend dependencies")


def _setup_venv(project_path: Path):
    """Create virtual environment and install dependencies."""
    venv_path = project_path / "venv"

    try:
        # Create venv
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            capture_output=True,
            check=True,
        )
        click.echo("  Created virtual environment")

        # Determine pip path
        if sys.platform == "win32":
            pip_path = venv_path / "Scripts" / "pip"
        else:
            pip_path = venv_path / "bin" / "pip"

        # Install requirements.txt
        subprocess.run(
            [str(pip_path), "install", "-r", "requirements.txt"],
            cwd=project_path,
            capture_output=True,
            check=True,
        )
        click.echo("  Installed Python dependencies")

        # Install Feather in editable mode from the framework location
        feather_path = Path(__file__).parent.parent.parent
        subprocess.run(
            [str(pip_path), "install", "-e", str(feather_path)],
            capture_output=True,
            check=True,
        )
        click.echo("  Linked Feather framework")

    except subprocess.CalledProcessError as e:
        click.echo(f"  Warning: Could not set up venv ({e})")
        click.echo("  Run manually: python -m venv venv && venv/bin/pip install -r requirements.txt")
    except FileNotFoundError:
        click.echo("  Skipped venv setup (Python not available)")


# =============================================================================
# Content Builders - Generate file contents based on options
# =============================================================================


def _build_config_content(
    database: str,
    db_url: str,
    include_auth: bool,
    tenant_mode: str,
    include_cache: bool,
    include_jobs: bool,
    include_storage: bool,
    storage_backend: str,
    include_email: bool = False,
) -> str:
    """Build config.py content based on options.

    Args:
        database: Database type ("none", "sqlite", or "postgresql")
        db_url: Database URL (None if database is "none")
        include_auth: Whether authentication is enabled
        tenant_mode: Tenant mode ("single" or "multi"), None if no auth
        include_cache: Whether Redis caching is enabled
        include_jobs: Whether background jobs are enabled
        include_storage: Whether cloud storage is enabled
        storage_backend: Storage backend ("gcs" or None)
        include_email: Whether email support (Resend) is enabled
    """
    has_database = database != "none"

    config = '''"""Application configuration."""

import os


class Config:
    """Base configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
'''

    # Database config - only if we have a database
    if has_database:
        config += f'''
    # Database
    DATABASE_URL = os.environ.get("DATABASE_URL", "{db_url}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Connection pool settings (keep minimal for development)
    SQLALCHEMY_POOL_SIZE = 2
    SQLALCHEMY_MAX_OVERFLOW = 2
'''

    # Session cookie settings - only if we have auth
    if include_auth:
        config += '''
    # Session cookie settings (required for OAuth through Vite proxy)
    SESSION_COOKIE_SAMESITE = "Lax"   # Allow redirects from Google OAuth
    SESSION_COOKIE_HTTPONLY = True     # Prevent JS access (security)
'''

    # Multi-tenancy config - based on tenant_mode
    if include_auth:
        is_multi = tenant_mode == "multi"
        config += f'''
    # Multi-tenancy
    FEATHER_MULTI_TENANT = {is_multi}
'''

    # Admin config - always enabled when auth is enabled
    if include_auth:
        config += '''
    # Admin Panel
    ADMIN_ENABLED = True

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
'''

    # Cache config
    if include_cache:
        config += '''
    # Caching (Redis)
    CACHE_BACKEND = os.environ.get("CACHE_BACKEND", "redis")
    CACHE_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CACHE_DEFAULT_TTL = 300  # 5 minutes
'''
    else:
        config += '''
    # Caching (in-memory for development)
    CACHE_BACKEND = os.environ.get("CACHE_BACKEND", "memory")
    CACHE_DEFAULT_TTL = 300  # 5 minutes
'''

    # Jobs config
    if include_jobs:
        config += '''
    # Background Jobs (thread pool for background execution)
    JOB_BACKEND = os.environ.get("JOB_BACKEND", "thread")
    JOB_MAX_WORKERS = int(os.environ.get("JOB_MAX_WORKERS", "2"))
'''
    else:
        config += '''
    # Background Jobs (synchronous - no background execution)
    JOB_BACKEND = os.environ.get("JOB_BACKEND", "sync")
'''

    # Storage config
    if include_storage:
        backend = storage_backend or "local"
        config += f'''
    # File Storage (Google Cloud Storage)
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "{backend}")
    GCS_BUCKET = os.environ.get("GCS_BUCKET")
    GCS_CREDENTIALS_JSON = os.environ.get("GCS_CREDENTIALS_JSON")
'''

    # Email config (Resend)
    if include_email:
        config += '''
    # Email (Resend)
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
    RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "noreply@example.com")
'''

    # Dev/Prod configs
    config += '''

class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
'''

    if include_auth:
        config += '''    SESSION_COOKIE_SECURE = False      # Allow HTTP in development
    SESSION_PROTECTION = None          # Disabled for Vite proxy (prevents session invalidation during OAuth)
'''

    config += '''

class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
'''

    if include_auth:
        config += '''    SESSION_COOKIE_SECURE = True       # HTTPS only
    SESSION_PROTECTION = "strong"      # Strict session protection
'''

    config += '''

# Map environment names to config classes
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
'''

    return config


def _build_env_content(
    name: str,
    database: str,
    db_url: str,
    include_auth: bool,
    tenant_mode: str,
    include_cache: bool,
    include_jobs: bool,
    include_storage: bool,
    include_email: bool = False,
) -> str:
    """Build .env content based on options.

    Args:
        name: Project name
        database: Database type ("none", "sqlite", or "postgresql")
        db_url: Database URL (None if database is "none")
        include_auth: Whether authentication is enabled
        tenant_mode: Tenant mode ("single" or "multi"), None if no auth
        include_cache: Whether Redis caching is enabled
        include_jobs: Whether background jobs are enabled
        include_storage: Whether cloud storage is enabled
        include_email: Whether email support (Resend) is enabled
    """
    has_database = database != "none"

    env = f"""# {name} Environment Variables

# Core
SECRET_KEY=dev-secret-key-change-in-production
# Set FLASK_DEBUG=0 when using the thread job backend
# Or use JOB_BACKEND=sync during development if you need debug mode
FLASK_DEBUG=1
"""

    # Database URL - only if we have a database
    if has_database:
        env += f"""
# Database
DATABASE_URL={db_url}
"""

    # Google OAuth - only when auth is enabled
    if include_auth:
        env += """
# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
"""

    # Background Jobs configuration
    if include_jobs:
        env += """
# Background Jobs
# thread = runs in background threads (default, no setup needed)
# sync = runs immediately, blocks request (for debugging)
# rq = Redis workers (for production with job persistence)
JOB_BACKEND=thread
JOB_MAX_WORKERS=2              # Max concurrent background jobs
# JOB_ENABLE_MONITORING=true   # Uncomment for memory/CPU tracking on failures
"""

    # Redis - for caching and/or RQ job backend
    if include_cache and include_jobs:
        env += """
# Redis (for caching, and RQ if JOB_BACKEND=rq)
REDIS_URL=redis://localhost:6379/0
"""
    elif include_cache:
        env += """
# Redis (for caching)
REDIS_URL=redis://localhost:6379/0
"""
    elif include_jobs:
        env += """
# Redis (only needed if JOB_BACKEND=rq)
# REDIS_URL=redis://localhost:6379/0
"""

    # GCS - bucket name first, then credentials
    if include_storage:
        env += """
# Google Cloud Storage (optional - local storage used if not configured)
GCS_BUCKET=
GCS_CREDENTIALS_JSON=
"""

    # Email (Resend)
    if include_email:
        env += """
# Email (Resend)
# Get your API key from https://resend.com/api-keys
RESEND_API_KEY=
# Default "from" address (must be verified in Resend)
RESEND_FROM_EMAIL=noreply@yourdomain.com
"""

    return env


def _build_seeds_content(admin_email: str = None, tenant_mode: str = "single") -> str:
    """Build seeds.py based on tenant mode.

    Args:
        admin_email: The admin's email (from CLI prompt).
        tenant_mode: "single" or "multi" tenant mode.
    """
    email_line = f'"{admin_email}"' if admin_email else 'None  # Set your admin email here'

    if tenant_mode == "multi":
        # Multi-tenant: Create platform admin with Account and Tenant
        return f'''"""Database seeds - Run with: python seeds.py"""

from datetime import datetime, timezone

from sqlalchemy import func

from app import app
from feather.db import db
from models import User, Tenant, Account, AccountUser

# Platform admin email (set during project creation)
ADMIN_EMAIL = {email_line}


def _create_tenant_from_email(email):
    """Create a tenant from an email domain.

    E.g., admin@acme.com -> Tenant(name="Acme", slug="acme", domain="acme.com")
    Returns existing tenant if one already exists for the domain.
    """
    domain = email.split("@")[1]
    name = domain.split(".")[0].title()  # acme.com -> Acme
    slug = name.lower()

    # Check if tenant already exists
    tenant = Tenant.query.filter_by(domain=domain).first()
    if tenant:
        return tenant

    # Create new tenant
    tenant = Tenant(
        name=name,
        slug=slug,
        domain=domain,
        status="active",
    )
    db.session.add(tenant)
    db.session.flush()  # Get tenant.id
    return tenant


def _create_account_for_user(user):
    """Create an Account and AccountUser for a user.

    This sets up the multi-profile system:
    - Creates an Account owned by the user
    - Creates an AccountUser linking user to account as admin
    - Sets user.subscription_owner_account_id
    """
    # Check if user already has an account
    if user.subscription_owner_account_id:
        return

    # Create account
    account = Account(
        name=user.display_name or user.email.split("@")[0],
        avatar_url=Account.random_avatar(),
        owner_user_id=user.id,
    )
    db.session.add(account)
    db.session.flush()  # Get account.id

    # Create account membership
    account_user = AccountUser(
        user_id=user.id,
        account_id=account.id,
        role="admin",
    )
    db.session.add(account_user)

    # Set subscription owner
    user.subscription_owner_account_id = account.id


def seed():
    """Create initial platform admin user with tenant and account.

    The platform admin:
    - Is assigned to a tenant created from their email domain
    - Has is_platform_admin=True so they can manage all tenants
    - Can use tenant-scoped features (which require a tenant_id)

    The admin can log in with Google OAuth.
    """
    if not ADMIN_EMAIL:
        print("Set ADMIN_EMAIL at the top of this file first")
        return

    email = ADMIN_EMAIL

    # Create or get tenant from admin's email domain
    tenant = _create_tenant_from_email(email)

    # Create or update admin user (case-insensitive email lookup)
    existing = User.query.filter(func.lower(User.email) == email.lower()).first()
    if existing:
        # Update existing user to be platform admin
        changed = False
        if existing.role != "admin":
            existing.role = "admin"
            changed = True
        if not existing.is_platform_admin:
            existing.is_platform_admin = True
            changed = True
        if not existing.active:
            existing.active = True
            existing.approved_at = datetime.now(timezone.utc)
            changed = True
        # Ensure they have a tenant
        if not existing.tenant_id:
            existing.tenant_id = tenant.id
            changed = True
        # Ensure they have an account
        if not existing.subscription_owner_account_id:
            _create_account_for_user(existing)
            changed = True
        if changed:
            db.session.commit()
            print(f"Granted platform admin access to: {{email}} (tenant: {{tenant.name}})")
        else:
            print(f"Platform admin already exists: {{email}}")
        return

    # Create new platform admin with tenant
    admin = User(
        email=email,
        username=email.split("@")[0],
        tenant_id=tenant.id,  # Platform admin belongs to a tenant for tenant-scoped features
        role="admin",
        is_platform_admin=True,  # But can still manage all tenants
        active=True,  # Initial admin is pre-approved
        approved_at=datetime.now(timezone.utc)
    )
    db.session.add(admin)
    db.session.flush()  # Get admin.id for account creation

    # Create account for admin
    _create_account_for_user(admin)

    db.session.commit()
    print(f"Created platform admin: {{email}} (tenant: {{tenant.name}})")


if __name__ == "__main__":
    with app.app_context():
        seed()
'''
    else:
        # Single-tenant: Create regular admin with Account (no platform admin concept)
        return f'''"""Database seeds - Run with: python seeds.py"""

from datetime import datetime, timezone

from sqlalchemy import func

from app import app
from feather.db import db
from models import User, Account, AccountUser

# Admin email (set during project creation)
ADMIN_EMAIL = {email_line}


def _create_account_for_user(user):
    """Create an Account and AccountUser for a user.

    This sets up the multi-profile system:
    - Creates an Account owned by the user
    - Creates an AccountUser linking user to account as admin
    - Sets user.subscription_owner_account_id
    """
    # Check if user already has an account
    if user.subscription_owner_account_id:
        return

    # Create account
    account = Account(
        name=user.display_name or user.email.split("@")[0],
        avatar_url=Account.random_avatar(),
        owner_user_id=user.id,
    )
    db.session.add(account)
    db.session.flush()  # Get account.id

    # Create account membership
    account_user = AccountUser(
        user_id=user.id,
        account_id=account.id,
        role="admin",
    )
    db.session.add(account_user)

    # Set subscription owner
    user.subscription_owner_account_id = account.id


def seed():
    """Create initial admin user with account.

    The admin can manage all users in the application.
    The admin can log in with Google OAuth.
    """
    if not ADMIN_EMAIL:
        print("Set ADMIN_EMAIL at the top of this file first")
        return

    email = ADMIN_EMAIL

    # Create or update admin user (case-insensitive email lookup)
    existing = User.query.filter(func.lower(User.email) == email.lower()).first()
    if existing:
        # Update existing user to be admin
        changed = False
        if existing.role != "admin":
            existing.role = "admin"
            changed = True
        if not existing.active:
            existing.active = True
            existing.approved_at = datetime.now(timezone.utc)
            changed = True
        # Ensure they have an account
        if not existing.subscription_owner_account_id:
            _create_account_for_user(existing)
            changed = True
        if changed:
            db.session.commit()
            print(f"Granted admin access to: {{email}}")
        else:
            print(f"Admin already exists: {{email}}")
        return

    # Create new admin
    admin = User(
        email=email,
        username=email.split("@")[0],
        role="admin",
        active=True,  # Initial admin is pre-approved
        approved_at=datetime.now(timezone.utc)
    )
    db.session.add(admin)
    db.session.flush()  # Get admin.id for account creation

    # Create account for admin
    _create_account_for_user(admin)

    db.session.commit()
    print(f"Created admin: {{email}}")


if __name__ == "__main__":
    with app.app_context():
        seed()
'''


def _build_email_service_content() -> str:
    """Build email service using Resend."""
    return '''"""Email service using Resend."""

import resend
from flask import current_app


class EmailService:
    """Service for sending emails via Resend."""

    def __init__(self):
        api_key = current_app.config.get("RESEND_API_KEY")
        if api_key:
            resend.api_key = api_key

    def send(self, to: str, subject: str, body: str, html: bool = False) -> dict:
        """Send an email to a single recipient.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text or HTML)
            html: If True, body is treated as HTML

        Returns:
            dict with 'success' and 'message' or 'error' keys
        """
        api_key = current_app.config.get("RESEND_API_KEY")
        if not api_key:
            return {"success": False, "error": "RESEND_API_KEY not configured"}

        from_email = current_app.config.get("RESEND_FROM_EMAIL", "noreply@example.com")

        try:
            params = {
                "from": from_email,
                "to": [to],
                "subject": subject,
            }
            if html:
                params["html"] = body
            else:
                params["text"] = body

            result = resend.Emails.send(params)
            return {"success": True, "message": f"Email sent to {to}", "id": result.get("id")}
        except Exception as e:
            return {"success": False, "error": str(e)}
'''


def _build_requirements_content(
    database: str,
    include_auth: bool,
    include_cache: bool,
    include_jobs: bool,
    include_storage: bool,
) -> str:
    """Build requirements.txt referencing Feather framework.

    ALL dependencies are defined in Feather's pyproject.toml:
    - Flask, SQLAlchemy, Flask-Login, Flask-WTF, alembic
    - authlib, requests (OAuth)
    - psycopg2-binary (PostgreSQL)
    - google-cloud-storage, reportlab (storage/PDF)
    - redis, rq (caching/jobs)
    - gunicorn (production server)
    - pytest, pytest-cov (testing)

    This file is just deployment instructions.
    The parameters are kept for API compatibility but no longer used.
    """
    return """# Project Dependencies
# ALL deps come from Feather framework:
# Flask, SQLAlchemy, authlib, redis, GCS, reportlab, gunicorn, pytest, etc.

# For local development, Feather is linked via:
#   pip install -e /path/to/feather

# For deployment, uncomment this:
# feather-framework

# Python 3.13+ compatibility (audioop removed from stdlib)
audioop-lts>=0.2.1; python_version >= "3.13"
"""


def _build_user_model_content(include_auth: bool, tenant_mode: str = None, user_fields: dict = None) -> str:
    """Build User model content based on auth and tenant mode.

    Args:
        include_auth: Whether authentication is enabled
        tenant_mode: "single" or "multi" (None if no auth)
        user_fields: Optional dict of field flags (e.g., {"display_name": True, "profile_image_url": False})
    """
    # Default to including all optional fields
    if user_fields is None:
        user_fields = {"display_name": True, "profile_image_url": True}

    # Build optional field definitions
    optional_field_defs = ""
    if user_fields.get("display_name", True):
        optional_field_defs += "    display_name = db.Column(db.String(100))\n"
    if user_fields.get("profile_image_url", True):
        optional_field_defs += "    profile_image_url = db.Column(db.String(500))\n"

    # Build optional attribute docstrings
    optional_attr_docs = ""
    if user_fields.get("display_name", True):
        optional_attr_docs += "        display_name: Display name for UI\n"
    if user_fields.get("profile_image_url", True):
        optional_attr_docs += "        profile_image_url: URL to profile image (from Google OAuth)\n"

    if include_auth and tenant_mode == "multi":
        # Multi-tenant User model with tenant_id and is_platform_admin
        return f'''"""User model with authentication and multi-tenant support."""

import uuid
from datetime import datetime, timezone

from flask_login import UserMixin

from feather.db import db, Model


class User(UserMixin, Model):
    """User model with authentication and role-based access.

    Authentication is handled by Google OAuth - no password storage needed.

    Feather uses a two-axis authority model:
    - Tenant role (role): Authority within a tenant (admin, editor, user)
    - Platform authority (is_platform_admin): Cross-tenant operator power

    Inherits from:
        - UserMixin: Flask-Login integration (is_authenticated, get_id, etc.)
        - Model: SQLAlchemy base model

    Attributes:
        id: UUID primary key
        tenant_id: Foreign key to tenant (required for multi-tenancy)
        email: Unique email address (from Google OAuth)
        username: Unique username
{optional_attr_docs}        active: Whether the user account is active (not suspended)
        approved_at: When user was first approved (None = pending, set = was approved)
        role: Tenant role (user, editor, moderator, admin)
        is_platform_admin: Whether user can manage tenants
        subscription_owner_account_id: The account that owns this user's subscription
        created_at: Timestamp of creation
        updated_at: Timestamp of last update
    """

    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = db.Column(db.String(36), db.ForeignKey("tenants.id"), nullable=True, index=True)  # Nullable for platform admins

    email = db.Column(db.String(255), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
{optional_field_defs}

    # Authorization
    active = db.Column(db.Boolean, default=False, nullable=False)  # Suspended until approved
    approved_at = db.Column(db.DateTime, nullable=True)  # Set when first approved (None=pending, set=was approved)
    role = db.Column(db.String(50), default="user", nullable=False)  # user, editor, moderator, admin
    is_platform_admin = db.Column(db.Boolean, default=False, nullable=False)

    # Account relationship - the account that owns this user's subscription
    # use_alter=True defers FK creation to handle circular dependency with Account model
    subscription_owner_account_id = db.Column(db.String(36), db.ForeignKey("accounts.id", use_alter=True), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))

    @property
    def is_active(self):
        """Check if user account is active (not suspended).

        Flask-Login requires this to be a @property, not a method.
        When is_active returns False, the user has a valid session but
        is blocked with 403 "Account suspended" on protected routes.
        """
        return bool(self.active)

    @property
    def is_admin(self):
        """Check if user is a tenant admin (derived from role)."""
        return self.role == "admin"

    @property
    def is_authenticated(self):
        """Check if user is authenticated.

        Flask-Login requires this. We override explicitly because SQLAlchemy 2.0's
        DeclarativeBase metaclass can shadow the UserMixin.is_authenticated property.
        Returns True for any user loaded from the database.
        """
        return True

    @property
    def is_anonymous(self):
        """Check if this is an anonymous user.

        Flask-Login requires this. We override explicitly because SQLAlchemy 2.0's
        DeclarativeBase metaclass can shadow the UserMixin.is_anonymous property.
        Returns False for real users loaded from the database.
        """
        return False

    def __repr__(self):
        return f"<User {{self.username}}>"
'''
    elif include_auth:
        # Single-tenant User model (no tenant_id, no is_platform_admin)
        return f'''"""User model with authentication."""

import uuid
from datetime import datetime, timezone

from flask_login import UserMixin

from feather.db import db, Model


class User(UserMixin, Model):
    """User model with authentication and role-based access.

    Authentication is handled by Google OAuth - no password storage needed.

    Inherits from:
        - UserMixin: Flask-Login integration (is_authenticated, get_id, etc.)
        - Model: SQLAlchemy base model

    Attributes:
        id: UUID primary key
        email: Unique email address (from Google OAuth)
        username: Unique username
{optional_attr_docs}        active: Whether the user account is active (not suspended)
        approved_at: When user was first approved (None = pending, set = was approved)
        role: User role (user, editor, moderator, admin)
        subscription_owner_account_id: The account that owns this user's subscription
        created_at: Timestamp of creation
        updated_at: Timestamp of last update
    """

    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    email = db.Column(db.String(255), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
{optional_field_defs}

    # Authorization
    active = db.Column(db.Boolean, default=False, nullable=False)  # Suspended until approved
    approved_at = db.Column(db.DateTime, nullable=True)  # Set when first approved (None=pending, set=was approved)
    role = db.Column(db.String(50), default="user", nullable=False)  # user, editor, moderator, admin

    # Account relationship - the account that owns this user's subscription
    # use_alter=True defers FK creation to handle circular dependency with Account model
    subscription_owner_account_id = db.Column(db.String(36), db.ForeignKey("accounts.id", use_alter=True), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))

    @property
    def is_active(self):
        """Check if user account is active (not suspended).

        Flask-Login requires this to be a @property, not a method.
        When is_active returns False, the user has a valid session but
        is blocked with 403 "Account suspended" on protected routes.
        """
        return bool(self.active)

    @property
    def is_admin(self):
        """Check if user is an admin (derived from role)."""
        return self.role == "admin"

    @property
    def is_authenticated(self):
        """Check if user is authenticated.

        Flask-Login requires this. We override explicitly because SQLAlchemy 2.0's
        DeclarativeBase metaclass can shadow the UserMixin.is_authenticated property.
        Returns True for any user loaded from the database.
        """
        return True

    @property
    def is_anonymous(self):
        """Check if this is an anonymous user.

        Flask-Login requires this. We override explicitly because SQLAlchemy 2.0's
        DeclarativeBase metaclass can shadow the UserMixin.is_anonymous property.
        Returns False for real users loaded from the database.
        """
        return False

    def __repr__(self):
        return f"<User {{self.username}}>"
'''
    else:
        # Simple User model without auth features
        # Build simpler optional fields for no-auth case (only display_name)
        simple_field_defs = ""
        simple_attr_docs = ""
        if user_fields.get("display_name", True):
            simple_field_defs = "    display_name = db.Column(db.String(100))\n"
            simple_attr_docs = "        display_name: Display name for UI\n"

        return f'''"""User model."""

import uuid
from datetime import datetime, timezone

from feather.db import db, Model


class User(Model):
    """Basic User model.

    Attributes:
        id: UUID primary key
        email: Unique email address
        username: Unique username
{simple_attr_docs}        created_at: Timestamp of creation
        updated_at: Timestamp of last update
    """

    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(255), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
{simple_field_defs}
    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<User {{self.username}}>"
'''


def _build_tenant_model_content() -> str:
    """Build Tenant model content for multi-tenancy."""
    return '''"""Tenant model for multi-tenancy support."""

import uuid
from datetime import datetime, timezone

from feather.db import db, Model


class Tenant(Model):
    """Tenant model for multi-tenant applications.

    Tenants can be identified by email domain (B2B) or created individually (B2C).
    Set FEATHER_ALLOW_PUBLIC_EMAILS=True to allow B2C patterns with public emails.

    Attributes:
        id: UUID primary key
        slug: URL-friendly identifier (e.g., "acme")
        domain: Email domain (e.g., "acme.com"), nullable for B2C tenants
        name: Display name (e.g., "Acme Corp")
        type: Tenant type (e.g., "company", "individual"), optional
        status: Tenant status (pending, active, suspended)
        created_at: Timestamp of creation
        updated_at: Timestamp of last update
    """

    __tablename__ = "tenants"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug = db.Column(db.String(64), unique=True, nullable=False, index=True)
    domain = db.Column(db.String(255), unique=True, nullable=True, index=True)  # Nullable for B2C tenants
    name = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(50), nullable=True, index=True)  # e.g., "company", "individual"
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)  # pending, active, suspended

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))

    # Relationship to users
    users = db.relationship("User", backref="tenant", lazy="dynamic")

    def __repr__(self):
        return f"<Tenant {self.slug}>"
'''


def _build_log_model_content(tenant_mode: str = "single") -> str:
    """Build Log model content based on tenant mode.

    Args:
        tenant_mode: "single" or "multi" tenant mode
    """
    if tenant_mode == "multi":
        # Multi-tenant: include tenant_id for scoping
        return '''"""Log model for admin panel event and error logging."""

import uuid
from datetime import datetime, timezone

from feather.db import db, Model


class Log(Model):
    """Log model for tracking application events and errors.

    Logs are scoped by tenant_id so admins only see logs from their tenant.
    Platform admins can see all logs across tenants.

    Attributes:
        id: UUID primary key
        level: Log level (INFO, WARNING, ERROR)
        event_type: Type of event (e.g., NotFoundError, ValidationError, UserLogin)
        message: Human-readable message
        path: URL path where the event occurred
        method: HTTP method (GET, POST, etc.)
        user_id: ID of user who triggered the event (if authenticated)
        tenant_id: ID of tenant for scoping (nullable for platform-level events)
        stack_trace: Full stack trace for debugging (errors only)
        request_data: Sanitized request data (JSON string)
        created_at: Timestamp of when the event occurred
    """

    __tablename__ = "logs"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Log level and event type
    level = db.Column(db.String(20), default="ERROR", nullable=False, index=True)
    event_type = db.Column(db.String(100), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    path = db.Column(db.String(500))
    method = db.Column(db.String(10))

    # User context
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    tenant_id = db.Column(db.String(36), db.ForeignKey("tenants.id"), nullable=True, index=True)

    # Debug info (for errors)
    stack_trace = db.Column(db.Text)
    request_data = db.Column(db.Text)

    # Timestamp
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    user = db.relationship("User", backref="logs")

    def __repr__(self):
        return f"<Log {self.level} {self.event_type}: {self.path}>"
'''
    else:
        # Single-tenant: no tenant_id
        return '''"""Log model for admin panel event and error logging."""

import uuid
from datetime import datetime, timezone

from feather.db import db, Model


class Log(Model):
    """Log model for tracking application events and errors.

    Attributes:
        id: UUID primary key
        level: Log level (INFO, WARNING, ERROR)
        event_type: Type of event (e.g., NotFoundError, ValidationError, UserLogin)
        message: Human-readable message
        path: URL path where the event occurred
        method: HTTP method (GET, POST, etc.)
        user_id: ID of user who triggered the event (if authenticated)
        stack_trace: Full stack trace for debugging (errors only)
        request_data: Sanitized request data (JSON string)
        created_at: Timestamp of when the event occurred
    """

    __tablename__ = "logs"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Log level and event type
    level = db.Column(db.String(20), default="ERROR", nullable=False, index=True)
    event_type = db.Column(db.String(100), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    path = db.Column(db.String(500))
    method = db.Column(db.String(10))

    # User context
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)

    # Debug info (for errors)
    stack_trace = db.Column(db.Text)
    request_data = db.Column(db.Text)

    # Timestamp
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    user = db.relationship("User", backref="logs")

    def __repr__(self):
        return f"<Log {self.level} {self.event_type}: {self.path}>"
'''


def _build_account_model_content() -> str:
    """Build Account and AccountUser models for multi-profile support.

    This creates:
    - Account: An organization/workspace that users can belong to
    - AccountUser: Join table linking users to accounts with roles

    Users can belong to multiple accounts. Each user has a primary
    "subscription owner" account (user.subscription_owner_account_id).
    """
    return '''"""Account models for multi-profile support."""

import random
import uuid
from datetime import datetime, timezone

from feather.db import db, Model


class Account(Model):
    """Account model - represents an organization/workspace.

    Users can belong to multiple accounts via AccountUser.
    Each account has an owner user who created it.

    Attributes:
        id: UUID primary key
        name: Display name for the account
        avatar_url: URL to account avatar/logo
        owner_user_id: The user who owns/created this account
        created_at: Timestamp of creation
        updated_at: Timestamp of last update
    """

    __tablename__ = "accounts"

    # Default avatar options for new accounts
    AVATAR_OPTIONS = [
        "https://api.dicebear.com/7.x/shapes/svg?seed=1",
        "https://api.dicebear.com/7.x/shapes/svg?seed=2",
        "https://api.dicebear.com/7.x/shapes/svg?seed=3",
        "https://api.dicebear.com/7.x/shapes/svg?seed=4",
        "https://api.dicebear.com/7.x/shapes/svg?seed=5",
    ]

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False)
    avatar_url = db.Column(db.String(500))
    # use_alter=True defers FK creation to handle circular dependency with User model
    owner_user_id = db.Column(db.String(36), db.ForeignKey("users.id", use_alter=True), nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    owner = db.relationship("User", foreign_keys=[owner_user_id], backref="owned_accounts")
    members = db.relationship("AccountUser", back_populates="account", cascade="all, delete-orphan")

    @classmethod
    def random_avatar(cls):
        """Get a random avatar URL for new accounts."""
        return random.choice(cls.AVATAR_OPTIONS)

    def __repr__(self):
        return f"<Account {self.name}>"


class AccountUser(Model):
    """Join table linking users to accounts with roles.

    Attributes:
        id: UUID primary key
        user_id: Foreign key to user
        account_id: Foreign key to account
        role: User's role within this account (admin, member)
        created_at: Timestamp of when user joined account
    """

    __tablename__ = "account_users"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    account_id = db.Column(db.String(36), db.ForeignKey("accounts.id"), nullable=False)
    role = db.Column(db.String(50), default="member", nullable=False)  # admin, member

    # Timestamp
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = db.relationship("User", backref="account_memberships")
    account = db.relationship("Account", back_populates="members")

    # Unique constraint - user can only be in an account once
    __table_args__ = (
        db.UniqueConstraint("user_id", "account_id", name="uq_user_account"),
    )

    def __repr__(self):
        return f"<AccountUser {self.user_id} in {self.account_id}>"
'''


def _build_api_routes_content(include_auth: bool) -> str:
    """Build example API routes based on auth option."""
    if include_auth:
        return '''"""Example API routes with authentication."""

from feather import api, auth_required


@api.get("/health")
def health():
    """Public health check endpoint."""
    return {"status": "ok"}


@api.get("/me")
@auth_required
def get_current_user():
    """Get current user (requires authentication).

    This endpoint demonstrates the @auth_required decorator.
    Only authenticated users can access this endpoint.
    """
    from flask_login import current_user

    return {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "username": current_user.username,
        }
    }
'''
    else:
        return '''"""Example API routes."""

from feather import api


@api.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}
'''


# =============================================================================
# Account Status Pages (Pending/Suspended)
# =============================================================================


def _build_account_routes() -> str:
    """Build account status routes for pending approval and suspended users.

    Returns:
        Python code string for routes/pages/account.py
    """
    return '''"""Account status routes for pending/suspended users."""

from flask import redirect, render_template, url_for
from flask_login import current_user, logout_user

from feather import page
from feather.auth import login_only


@page.get("/account/pending")
@login_only
def account_pending():
    """Show pending approval page for users awaiting admin approval."""
    # If user is active, redirect to home
    if current_user.active:
        return redirect(url_for("page.home"))
    # If user was approved before (suspended), show suspended page instead
    if getattr(current_user, "approved_at", None):
        return redirect(url_for("page.account_suspended"))
    return render_template("pages/account/pending.html")


@page.get("/account/suspended")
@login_only
def account_suspended():
    """Show suspended page for users whose accounts have been deactivated."""
    # If user is active, redirect to home
    if current_user.active:
        return redirect(url_for("page.home"))
    return render_template("pages/account/suspended.html")


@page.post("/account/logout")
@login_only
def account_logout():
    """Log out the current user and redirect to home."""
    logout_user()
    return redirect(url_for("page.home"))
'''


def _build_account_pending_template() -> str:
    """Build the pending approval page template.

    Returns:
        HTML template string for templates/pages/account/pending.html
    """
    return '''{% extends "base.html" %}

{% block title %}Account Pending - My App{% endblock %}

{% block content %}
<div class="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4">
    <div class="max-w-md w-full text-center">
        <!-- Icon -->
        <div class="mx-auto w-16 h-16 bg-yellow-100 rounded-full flex items-center justify-center mb-6">
            <span class="material-symbols-outlined text-3xl text-yellow-600">hourglass_top</span>
        </div>

        <!-- Heading -->
        <h1 class="text-2xl font-bold text-gray-900 mb-2">Account Pending Approval</h1>
        <p class="text-gray-600 mb-8">
            Your account has been created and is awaiting approval from an administrator.
            You'll receive access once your account has been reviewed.
        </p>

        <!-- Info Card -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6 text-left">
            <h2 class="font-medium text-gray-900 mb-3">What happens next?</h2>
            <ul class="space-y-2 text-sm text-gray-600">
                <li class="flex items-start gap-2">
                    <span class="material-symbols-outlined text-green-500 text-lg flex-shrink-0">check_circle</span>
                    <span>An administrator will review your account</span>
                </li>
                <li class="flex items-start gap-2">
                    <span class="material-symbols-outlined text-green-500 text-lg flex-shrink-0">check_circle</span>
                    <span>Once approved, you'll have full access to the application</span>
                </li>
                <li class="flex items-start gap-2">
                    <span class="material-symbols-outlined text-blue-500 text-lg flex-shrink-0">info</span>
                    <span>This usually takes 1-2 business days</span>
                </li>
            </ul>
        </div>

        <!-- User Info -->
        <div class="bg-gray-100 rounded-lg p-4 mb-6 text-sm text-gray-600">
            <p>Logged in as: <strong>{{ current_user.email }}</strong></p>
        </div>

        <!-- Actions -->
        <div class="space-y-3">
            <form action="{{ url_for('page.account_logout') }}" method="post">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <button type="submit" class="w-full px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg transition-colors">
                    Sign Out
                </button>
            </form>
            <p class="text-xs text-gray-500">
                Questions? Contact your administrator for help.
            </p>
        </div>
    </div>
</div>
{% endblock %}
'''


def _build_account_suspended_template() -> str:
    """Build the suspended account page template.

    Returns:
        HTML template string for templates/pages/account/suspended.html
    """
    return '''{% extends "base.html" %}

{% block title %}Account Suspended - My App{% endblock %}

{% block content %}
<div class="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4">
    <div class="max-w-md w-full text-center">
        <!-- Icon -->
        <div class="mx-auto w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-6">
            <span class="material-symbols-outlined text-3xl text-red-600">block</span>
        </div>

        <!-- Heading -->
        <h1 class="text-2xl font-bold text-gray-900 mb-2">Account Suspended</h1>
        <p class="text-gray-600 mb-8">
            Your account has been suspended by an administrator.
            If you believe this is an error, please contact your administrator.
        </p>

        <!-- Info Card -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6 text-left">
            <h2 class="font-medium text-gray-900 mb-3">Why was my account suspended?</h2>
            <p class="text-sm text-gray-600 mb-3">
                Account suspensions can occur for various reasons, including:
            </p>
            <ul class="space-y-2 text-sm text-gray-600">
                <li class="flex items-start gap-2">
                    <span class="material-symbols-outlined text-gray-400 text-lg flex-shrink-0">remove_circle_outline</span>
                    <span>Violation of terms of service</span>
                </li>
                <li class="flex items-start gap-2">
                    <span class="material-symbols-outlined text-gray-400 text-lg flex-shrink-0">remove_circle_outline</span>
                    <span>Security concerns</span>
                </li>
                <li class="flex items-start gap-2">
                    <span class="material-symbols-outlined text-gray-400 text-lg flex-shrink-0">remove_circle_outline</span>
                    <span>Administrative action</span>
                </li>
            </ul>
        </div>

        <!-- User Info -->
        <div class="bg-gray-100 rounded-lg p-4 mb-6 text-sm text-gray-600">
            <p>Logged in as: <strong>{{ current_user.email }}</strong></p>
        </div>

        <!-- Actions -->
        <div class="space-y-3">
            <form action="{{ url_for('page.account_logout') }}" method="post">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <button type="submit" class="w-full px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg transition-colors">
                    Sign Out
                </button>
            </form>
            <p class="text-xs text-gray-500">
                Questions? Contact your administrator for help.
            </p>
        </div>
    </div>
</div>
{% endblock %}
'''


# =============================================================================
# Admin Panel Scaffolding
# =============================================================================


def _build_admin_routes(tenant_mode: str, include_email: bool = False) -> str:
    """Build admin routes - base routes for all, tenant routes for multi-tenant.

    Args:
        tenant_mode: "single" or "multi"
        include_email: Whether email support (Resend) is enabled

    Returns:
        Python code string for routes/pages/admin.py
    """
    base_routes = '''"""Admin panel routes."""

import json

from flask import abort, Blueprint, jsonify, make_response, redirect, render_template, request, session, url_for
from flask_login import current_user

from feather.auth import admin_required
from services.admin_service import AdminService


page = Blueprint("admin", __name__, url_prefix="/admin")


# =============================================================================
# Helpers
# =============================================================================


def redirect_with_toast(url: str, message: str, toast_type: str = "success"):
    """Redirect with a pending toast message stored in session."""
    session["_pending_toast"] = {"message": message, "type": toast_type}
    return redirect(url)


def with_toast(html_content: str, message: str, toast_type: str = "success"):
    """Wrap HTML response with HX-Trigger header for toast notification."""
    response = make_response(html_content)
    response.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": message, "type": toast_type}
    })
    return response


@page.context_processor
def inject_admin_context():
    """Inject common admin context into all templates."""
    pending_toast = session.pop("_pending_toast", None)
    return {
        "fallback_avatar": AdminService.fallback_avatar,
        "pending_toast": pending_toast,
    }


# =============================================================================
# User Management Routes
# =============================================================================


@page.route("/")
@admin_required
def index():
    """Admin index - redirect to users page."""
    return redirect(url_for("admin.users_page"))


@page.route("/users")
@admin_required
def users_page():
    """Users list with search and pagination."""
    search = request.args.get("q", "").strip()
    page_num = request.args.get("page", 1, type=int)
    per_page = 50
    offset = (page_num - 1) * per_page

    service = AdminService()
    if search:
        result = service.search_users(search, limit=per_page, offset=offset)
    else:
        result = service.get_all_users(limit=per_page, offset=offset)

    return render_template(
        "pages/admin/users.html",
        users=result["users"],
        pagination=result["pagination"],
        search=search,
    )


@page.route("/users/<user_id>")
@admin_required
def user_detail_page(user_id: str):
    """User detail page."""
    service = AdminService()
    user = service.get_user_detail(user_id)
    if not user:
        abort(404, "User not found")

    return render_template("pages/admin/user_detail.html", user=user)


@page.route("/users/<user_id>/toggle-status", methods=["POST"])
@admin_required
def toggle_user_status(user_id: str):
    """Toggle user active status. Returns partial for HTMX."""
    service = AdminService()
    user = service.toggle_user_status(user_id)
    if not user:
        abort(404, "User not found")

    status = "activated" if user.active else "suspended"

    # Build status pill HTML for OOB swap
    if user.active:
        pill_html = '<span class="px-2 py-1 text-xs bg-green-100 text-green-800 rounded">Active</span>'
    elif hasattr(user, 'approved_at') and user.approved_at:
        pill_html = '<span class="px-2 py-1 text-xs bg-red-100 text-red-800 rounded">Suspended</span>'
    else:
        pill_html = '<span class="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">Pending</span>'

    # Include OOB swap for the status pill in the profile card
    oob_pill = f'<span id="status-pill" hx-swap-oob="true">{pill_html}</span>'
    html = render_template("partials/admin/user_actions.html", user=user) + oob_pill
    return with_toast(html, f"{user.email} has been {status}.")


@page.route("/users/<user_id>/update-role", methods=["POST"])
@admin_required
def update_user_role(user_id: str):
    """Update user role. Returns partial for HTMX."""
    role = request.form.get("role", "user")
    service = AdminService()
    user = service.update_user_role(user_id, role)
    if not user:
        abort(404, "User not found")

    html = render_template("partials/admin/user_actions.html", user=user)
    return with_toast(html, f"Updated {user.email} role to {role}.")


# =============================================================================
# Tools Routes
# =============================================================================


@page.route("/tools")
@admin_required
def tools_page():
    """Admin tools page."""
    return render_template("pages/admin/tools.html")


# =============================================================================
# Analytics Routes
# =============================================================================


@page.route("/analytics")
@admin_required
def analytics_page():
    """Analytics dashboard page."""
    service = AdminService()
    stats = service.get_user_stats()
    return render_template("pages/admin/analytics.html", stats=stats)


@page.route("/api/stats/user-growth")
@admin_required
def api_user_growth():
    """Get user growth data for analytics chart."""
    days = request.args.get("days", 30, type=int)
    service = AdminService()
    data = service.get_user_growth(days)
    return jsonify({"success": True, "data": data})


# =============================================================================
# Error Logs Routes
# =============================================================================


@page.route("/logs")
@admin_required
def logs_page():
    """Logs page with search and filtering."""
    search = request.args.get("search", "").strip()
    filter_code = request.args.get("filter", "")
    page_num = request.args.get("page", 1, type=int)

    service = AdminService()
    logs_result = service.get_logs(
        limit=50,
        page=page_num,
        status_code=filter_code if filter_code else None,
        search=search if search else None,
    )
    stats = service.get_log_stats(days=7)

    return render_template(
        "pages/admin/logs.html",
        logs=logs_result["items"],
        pagination=logs_result["pagination"],
        stats=stats,
        search=search,
        filter=filter_code,
    )
'''

    # Add email routes when email support is enabled
    if include_email:
        base_routes += '''

# =============================================================================
# Email Routes (Resend)
# =============================================================================


@page.route("/tools/send-email", methods=["POST"])
@admin_required
def send_email():
    """Send email to a user."""
    to = request.form.get("to", "").strip()
    subject = request.form.get("subject", "").strip()
    body = request.form.get("body", "").strip()

    if not to or not subject or not body:
        return render_template(
            "partials/admin/email_result.html",
            success=False,
            message="All fields are required.",
        )

    from services.email_service import EmailService
    email_service = EmailService()
    result = email_service.send(to, subject, body)

    return render_template(
        "partials/admin/email_result.html",
        success=result.get("success", False),
        message=result.get("message") or result.get("error", "Unknown error"),
    )


@page.route("/tools/search-users")
@admin_required
def search_users_dropdown():
    """Search users for dropdown (HTMX endpoint)."""
    query = request.args.get("to", "").strip()
    if len(query) < 2:
        return ""

    service = AdminService()
    result = service.search_users(query, limit=5, offset=0)
    users = result["users"]

    if not users:
        return '<div class="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg"><div class="p-3 text-sm text-gray-500">No users found</div></div>'

    html = '<div class="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg">'
    for user in users:
        display_name = getattr(user, "display_name", None) or user.email
        profile_url = getattr(user, "profile_image_url", None)
        avatar_url = profile_url if profile_url and profile_url.strip() else AdminService.fallback_avatar(user)
        fallback_url = AdminService.fallback_avatar(user)
        html += f"""
        <button type="button"
                data-action="select-email"
                data-email="{user.email}"
                class="w-full px-3 py-2 text-left text-sm hover:bg-gray-50 flex items-center gap-2">
            <img src="{avatar_url}"
                 data-fallback="{fallback_url}"
                 referrerpolicy="no-referrer"
                 crossorigin="anonymous"
                 class="w-6 h-6 rounded-full admin-avatar-img">
            <div>
                <span class="font-medium">{display_name}</span>
                <span class="text-gray-500"> - {user.email}</span>
            </div>
        </button>
        """
    html += '</div>'
    return html
'''

    # Add tenant routes for multi-tenant mode
    if tenant_mode == "multi":
        base_routes += '''

# =============================================================================
# Tenant Management Routes (Platform Admin Only)
# =============================================================================


from feather.auth import platform_admin_required


@page.route("/tenants")
@platform_admin_required
def tenants_page():
    """Tenants list with status filtering."""
    status_filter = request.args.get("status", "").strip()
    page_num = request.args.get("page", 1, type=int)
    per_page = 50
    offset = (page_num - 1) * per_page

    service = AdminService()
    result = service.get_all_tenants(
        limit=per_page,
        offset=offset,
        status=status_filter if status_filter else None,
    )
    stats = service.get_tenant_stats()

    return render_template(
        "pages/admin/tenants.html",
        tenants=result["tenants"],
        pagination=result["pagination"],
        stats=stats,
        status_filter=status_filter,
    )


@page.route("/tenants/<tenant_id>")
@platform_admin_required
def tenant_detail_page(tenant_id: str):
    """Tenant detail page with users list."""
    service = AdminService()
    tenant = service.get_tenant_detail(tenant_id)
    if not tenant:
        abort(404, "Tenant not found")

    users_result = service.get_tenant_users(tenant_id, limit=50, offset=0)

    return render_template(
        "pages/admin/tenant_detail.html",
        tenant=tenant,
        users=users_result["users"],
        users_pagination=users_result["pagination"],
    )


@page.route("/tenants", methods=["POST"])
@platform_admin_required
def create_tenant():
    """Create a new tenant with an auto-approved admin user."""
    name = request.form.get("name", "").strip()
    domain = request.form.get("domain", "").strip()
    admin_email = request.form.get("admin_email", "").strip()

    if not name or not domain or not admin_email:
        return redirect_with_toast(url_for("admin.tenants_page"), "All fields are required.", "error")

    service = AdminService()
    tenant, admin_user = service.create_tenant(name, domain, admin_email)
    if tenant:
        return redirect_with_toast(
            url_for("admin.tenants_page"),
            f"Created tenant '{name}' with admin {admin_email}.",
            "success"
        )
    else:
        return redirect_with_toast(
            url_for("admin.tenants_page"),
            "Failed to create tenant. Check for duplicate slug, domain, or email.",
            "error"
        )


@page.route("/tenants/<tenant_id>/toggle-status", methods=["POST"])
@platform_admin_required
def toggle_tenant_status(tenant_id: str):
    """Toggle tenant active/suspended status. Returns partial for HTMX."""
    service = AdminService()
    tenant = service.toggle_tenant_status(tenant_id)
    if not tenant:
        abort(404, "Tenant not found")

    status = "activated" if tenant.status == "active" else "suspended"
    html = render_template("partials/admin/tenant_actions.html", tenant=tenant)
    return with_toast(html, f"Tenant '{tenant.name}' has been {status}.")
'''

    return base_routes


def _build_admin_service(tenant_mode: str) -> str:
    """Build admin service - base functions for all, tenant functions for multi-tenant.

    Args:
        tenant_mode: "single" or "multi"

    Returns:
        Python code string for services/admin_service.py
    """
    base_service = '''"""Admin panel services."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import re
import uuid

from sqlalchemy import func, or_

from feather.db import db
from feather.services import Service
from models import User, Log


class AdminService(Service):
    """Service for admin panel operations."""

    # =========================================================================
    # Static Helpers
    # =========================================================================

    @staticmethod
    def fallback_avatar(user) -> str:
        """Generate fallback avatar URL for user."""
        name = getattr(user, "display_name", None) or getattr(user, "email", "User")
        return f"https://ui-avatars.com/api/?name={name}&background=random&color=fff&size=128"

    @staticmethod
    def _empty_pagination() -> dict[str, Any]:
        """Return an empty pagination dict."""
        return {
            "page": 1,
            "pages": 1,
            "per_page": 50,
            "total": 0,
            "start": 0,
            "end": 0,
            "has_prev": False,
            "has_next": False,
        }

    # =========================================================================
    # User Management
    # =========================================================================

    def get_all_users(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Get paginated list of all users."""
        query = User.query

        # Exclude platform admins from results
        if hasattr(User, "is_platform_admin"):
            query = query.filter(or_(User.is_platform_admin == False, User.is_platform_admin == None))

        total = query.count()
        users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()

        page = (offset // limit) + 1 if limit > 0 else 1
        pages = (total + limit - 1) // limit if limit > 0 else 1

        return {
            "users": users,
            "total": total,
            "has_more": offset + limit < total,
            "pagination": {
                "page": page,
                "pages": pages,
                "per_page": limit,
                "total": total,
                "start": offset + 1 if total > 0 else 0,
                "end": min(offset + limit, total),
                "has_prev": page > 1,
                "has_next": page < pages,
            }
        }

    def search_users(self, query: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Search users by email, display_name, or username."""
        search_filter = User.email.ilike(f"%{query}%")

        if hasattr(User, "display_name"):
            search_filter = or_(search_filter, User.display_name.ilike(f"%{query}%"))
        if hasattr(User, "username"):
            search_filter = or_(search_filter, User.username.ilike(f"%{query}%"))

        base_query = User.query.filter(search_filter)

        # Exclude platform admins
        if hasattr(User, "is_platform_admin"):
            base_query = base_query.filter(or_(User.is_platform_admin == False, User.is_platform_admin == None))

        total = base_query.count()
        users = base_query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()

        page = (offset // limit) + 1 if limit > 0 else 1
        pages = (total + limit - 1) // limit if limit > 0 else 1

        return {
            "users": users,
            "total": total,
            "has_more": offset + limit < total,
            "pagination": {
                "page": page,
                "pages": pages,
                "per_page": limit,
                "total": total,
                "start": offset + 1 if total > 0 else 0,
                "end": min(offset + limit, total),
                "has_prev": page > 1,
                "has_next": page < pages,
            }
        }

    def get_user_detail(self, user_id: str) -> Optional[Any]:
        """Get user by ID for detail page."""
        return User.query.get(user_id)

    def toggle_user_status(self, user_id: str) -> Optional[Any]:
        """Toggle user active status."""
        user = User.query.get(user_id)
        if not user:
            return None

        user.active = not user.active
        if user.active and hasattr(user, "approved_at") and not user.approved_at:
            user.approved_at = datetime.now(timezone.utc)
        db.session.commit()
        return user

    def update_user_role(self, user_id: str, role: str) -> Optional[Any]:
        """Update user role."""
        valid_roles = ["user", "editor", "moderator", "admin"]
        if role not in valid_roles:
            return None

        user = User.query.get(user_id)
        if not user:
            return None

        user.role = role
        db.session.commit()
        return user

    # =========================================================================
    # Analytics
    # =========================================================================

    def get_user_stats(self) -> dict[str, int]:
        """Get user statistics for analytics dashboard."""
        query = User.query

        # Exclude platform admins
        if hasattr(User, "is_platform_admin"):
            query = query.filter(or_(User.is_platform_admin == False, User.is_platform_admin == None))

        total_users = query.count()
        active_users = query.filter(User.active == True).count()

        first_of_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        new_this_month = query.filter(User.created_at >= first_of_month).count()

        return {
            "total_users": total_users,
            "active_users": active_users,
            "new_this_month": new_this_month,
        }

    def get_user_growth(self, days: int = 30) -> list[dict[str, Any]]:
        """Get daily user registration counts for analytics chart."""
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        query = db.session.query(
            func.date(User.created_at).label("date"),
            func.count(User.id).label("count")
        ).filter(User.created_at >= start_date)

        # Exclude platform admins
        if hasattr(User, "is_platform_admin"):
            query = query.filter(or_(User.is_platform_admin == False, User.is_platform_admin == None))

        results = query.group_by(func.date(User.created_at)).order_by(func.date(User.created_at)).all()

        # Convert to dict
        date_counts = {str(r.date): r.count for r in results}

        # Fill in missing dates with 0
        filled_data = []
        current = start_date.date()
        end = datetime.now(timezone.utc).date()

        while current <= end:
            date_str = str(current)
            filled_data.append({"date": date_str, "count": date_counts.get(date_str, 0)})
            current += timedelta(days=1)

        return filled_data

    # =========================================================================
    # Logs
    # =========================================================================

    def get_logs(
        self,
        limit: int = 50,
        offset: int = 0,
        status_code: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
    ) -> dict[str, Any]:
        """Get paginated logs with optional filtering."""
        if page > 1:
            offset = (page - 1) * limit

        query = Log.query

        # Filter by event type category
        if status_code:
            if hasattr(Log, "event_type"):
                if status_code in ("4", "client"):
                    query = query.filter(
                        Log.event_type.in_(["NotFoundError", "ValidationError", "AuthenticationError", "AuthorizationError"])
                    )
                elif status_code in ("5", "server"):
                    query = query.filter(Log.event_type.in_(["InternalError", "ServerError"]))

        # Search path/message
        if search:
            search_filters = []
            if hasattr(Log, "path"):
                search_filters.append(Log.path.ilike(f"%{search}%"))
            if hasattr(Log, "message"):
                search_filters.append(Log.message.ilike(f"%{search}%"))
            if search_filters:
                query = query.filter(or_(*search_filters))

        total = query.count()
        items = query.order_by(Log.created_at.desc()).offset(offset).limit(limit).all()

        pages = (total + limit - 1) // limit if limit > 0 else 1

        return {
            "items": items,
            "total": total,
            "pagination": {
                "page": page,
                "pages": pages,
                "per_page": limit,
                "total": total,
                "start": offset + 1 if total > 0 else 0,
                "end": min(offset + limit, total),
                "has_prev": page > 1,
                "has_next": page < pages,
            }
        }

    def get_log_stats(self, days: int = 7) -> dict[str, int]:
        """Get log statistics for the last N days."""
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        base_query = Log.query.filter(Log.created_at >= start_date)

        if hasattr(Log, "event_type"):
            errors_4xx = base_query.filter(
                Log.event_type.in_(["NotFoundError", "ValidationError", "AuthenticationError", "AuthorizationError"])
            ).count()
            errors_5xx = base_query.filter(Log.event_type.in_(["InternalError", "ServerError"])).count()
        else:
            errors_4xx = 0
            errors_5xx = base_query.count()

        return {
            "errors_4xx": errors_4xx,
            "errors_5xx": errors_5xx,
            "total": errors_4xx + errors_5xx,
        }
'''

    # Add tenant functions for multi-tenant mode
    if tenant_mode == "multi":
        # Import Tenant model and current_user for tenant isolation
        base_service = base_service.replace(
            "from models import User, Log",
            "from models import User, Log, Tenant"
        )
        base_service = base_service.replace(
            "from feather.db import db",
            "from flask_login import current_user\nfrom feather.db import db"
        )

        # Add tenant isolation helper methods after Static Helpers section
        base_service = base_service.replace(
            '''    # =========================================================================
    # User Management
    # =========================================================================''',
            '''    # =========================================================================
    # Tenant Isolation Helpers
    # =========================================================================

    @staticmethod
    def _is_platform_admin() -> bool:
        """Check if current user is a platform admin (can see all tenants)."""
        return getattr(current_user, "is_platform_admin", False)

    @staticmethod
    def _get_tenant_id():
        """Get current user's tenant_id. Returns None for platform admins."""
        if AdminService._is_platform_admin():
            return None
        return getattr(current_user, "tenant_id", None)

    # =========================================================================
    # User Management
    # ========================================================================='''
        )

        # Replace get_all_users with tenant-aware version
        base_service = base_service.replace(
            '''    def get_all_users(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Get paginated list of all users."""
        query = User.query

        # Exclude platform admins from results
        if hasattr(User, "is_platform_admin"):
            query = query.filter(or_(User.is_platform_admin == False, User.is_platform_admin == None))

        total = query.count()
        users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()''',
            '''    def get_all_users(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Get paginated list of users (tenant-scoped for non-platform-admins)."""
        query = User.query

        # Tenant isolation: non-platform-admins only see their tenant's users
        tenant_id = self._get_tenant_id()
        if tenant_id:
            query = query.filter(User.tenant_id == tenant_id)

        # Exclude platform admins from results
        if hasattr(User, "is_platform_admin"):
            query = query.filter(or_(User.is_platform_admin == False, User.is_platform_admin == None))

        total = query.count()
        users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()'''
        )

        # Replace search_users with tenant-aware version
        base_service = base_service.replace(
            '''    def search_users(self, query: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Search users by email, display_name, or username."""
        search_filter = User.email.ilike(f"%{query}%")

        if hasattr(User, "display_name"):
            search_filter = or_(search_filter, User.display_name.ilike(f"%{query}%"))
        if hasattr(User, "username"):
            search_filter = or_(search_filter, User.username.ilike(f"%{query}%"))

        base_query = User.query.filter(search_filter)

        # Exclude platform admins
        if hasattr(User, "is_platform_admin"):
            base_query = base_query.filter(or_(User.is_platform_admin == False, User.is_platform_admin == None))

        total = base_query.count()
        users = base_query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()''',
            '''    def search_users(self, query: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Search users by email, display_name, or username (tenant-scoped)."""
        search_filter = User.email.ilike(f"%{query}%")

        if hasattr(User, "display_name"):
            search_filter = or_(search_filter, User.display_name.ilike(f"%{query}%"))
        if hasattr(User, "username"):
            search_filter = or_(search_filter, User.username.ilike(f"%{query}%"))

        base_query = User.query.filter(search_filter)

        # Tenant isolation: non-platform-admins only see their tenant's users
        tenant_id = self._get_tenant_id()
        if tenant_id:
            base_query = base_query.filter(User.tenant_id == tenant_id)

        # Exclude platform admins
        if hasattr(User, "is_platform_admin"):
            base_query = base_query.filter(or_(User.is_platform_admin == False, User.is_platform_admin == None))

        total = base_query.count()
        users = base_query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()'''
        )

        # Replace get_user_detail with tenant-aware version
        base_service = base_service.replace(
            '''    def get_user_detail(self, user_id: str) -> Optional[Any]:
        """Get user by ID for detail page."""
        return User.query.get(user_id)''',
            '''    def get_user_detail(self, user_id: str) -> Optional[Any]:
        """Get user by ID for detail page (tenant-scoped)."""
        user = User.query.get(user_id)
        if not user:
            return None

        # Tenant isolation: non-platform-admins can only view users in their tenant
        tenant_id = self._get_tenant_id()
        if tenant_id and user.tenant_id != tenant_id:
            return None  # Not authorized to view this user

        return user'''
        )

        # Replace toggle_user_status with tenant-aware version
        base_service = base_service.replace(
            '''    def toggle_user_status(self, user_id: str) -> Optional[Any]:
        """Toggle user active status."""
        user = User.query.get(user_id)
        if not user:
            return None

        user.active = not user.active
        if user.active and hasattr(user, "approved_at") and not user.approved_at:
            user.approved_at = datetime.now(timezone.utc)
        db.session.commit()
        return user''',
            '''    def toggle_user_status(self, user_id: str) -> Optional[Any]:
        """Toggle user active status (tenant-scoped)."""
        user = User.query.get(user_id)
        if not user:
            return None

        # Tenant isolation: non-platform-admins can only modify users in their tenant
        tenant_id = self._get_tenant_id()
        if tenant_id and user.tenant_id != tenant_id:
            return None  # Not authorized to modify this user

        user.active = not user.active
        if user.active and hasattr(user, "approved_at") and not user.approved_at:
            user.approved_at = datetime.now(timezone.utc)
        db.session.commit()
        return user'''
        )

        # Replace update_user_role with tenant-aware version
        base_service = base_service.replace(
            '''    def update_user_role(self, user_id: str, role: str) -> Optional[Any]:
        """Update user role."""
        valid_roles = ["user", "editor", "moderator", "admin"]
        if role not in valid_roles:
            return None

        user = User.query.get(user_id)
        if not user:
            return None

        user.role = role
        db.session.commit()
        return user''',
            '''    def update_user_role(self, user_id: str, role: str) -> Optional[Any]:
        """Update user role (tenant-scoped)."""
        valid_roles = ["user", "editor", "moderator", "admin"]
        if role not in valid_roles:
            return None

        user = User.query.get(user_id)
        if not user:
            return None

        # Tenant isolation: non-platform-admins can only modify users in their tenant
        tenant_id = self._get_tenant_id()
        if tenant_id and user.tenant_id != tenant_id:
            return None  # Not authorized to modify this user

        user.role = role
        db.session.commit()
        return user'''
        )

        # Replace get_user_stats with tenant-aware version
        base_service = base_service.replace(
            '''    def get_user_stats(self) -> dict[str, int]:
        """Get user statistics for analytics dashboard."""
        query = User.query

        # Exclude platform admins
        if hasattr(User, "is_platform_admin"):
            query = query.filter(or_(User.is_platform_admin == False, User.is_platform_admin == None))

        total_users = query.count()
        active_users = query.filter(User.active == True).count()

        first_of_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        new_this_month = query.filter(User.created_at >= first_of_month).count()

        return {
            "total_users": total_users,
            "active_users": active_users,
            "new_this_month": new_this_month,
        }''',
            '''    def get_user_stats(self) -> dict[str, int]:
        """Get user statistics for analytics dashboard (tenant-scoped)."""
        query = User.query

        # Tenant isolation: non-platform-admins only see their tenant's stats
        tenant_id = self._get_tenant_id()
        if tenant_id:
            query = query.filter(User.tenant_id == tenant_id)

        # Exclude platform admins
        if hasattr(User, "is_platform_admin"):
            query = query.filter(or_(User.is_platform_admin == False, User.is_platform_admin == None))

        total_users = query.count()
        active_users = query.filter(User.active == True).count()

        first_of_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        new_this_month = query.filter(User.created_at >= first_of_month).count()

        return {
            "total_users": total_users,
            "active_users": active_users,
            "new_this_month": new_this_month,
        }'''
        )

        # Replace get_user_growth with tenant-aware version
        base_service = base_service.replace(
            '''    def get_user_growth(self, days: int = 30) -> list[dict[str, Any]]:
        """Get daily user registration counts for analytics chart."""
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        query = db.session.query(
            func.date(User.created_at).label("date"),
            func.count(User.id).label("count")
        ).filter(User.created_at >= start_date)

        # Exclude platform admins
        if hasattr(User, "is_platform_admin"):
            query = query.filter(or_(User.is_platform_admin == False, User.is_platform_admin == None))

        results = query.group_by(func.date(User.created_at)).order_by(func.date(User.created_at)).all()''',
            '''    def get_user_growth(self, days: int = 30) -> list[dict[str, Any]]:
        """Get daily user registration counts for analytics chart (tenant-scoped)."""
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        query = db.session.query(
            func.date(User.created_at).label("date"),
            func.count(User.id).label("count")
        ).filter(User.created_at >= start_date)

        # Tenant isolation: non-platform-admins only see their tenant's growth
        tenant_id = self._get_tenant_id()
        if tenant_id:
            query = query.filter(User.tenant_id == tenant_id)

        # Exclude platform admins
        if hasattr(User, "is_platform_admin"):
            query = query.filter(or_(User.is_platform_admin == False, User.is_platform_admin == None))

        results = query.group_by(func.date(User.created_at)).order_by(func.date(User.created_at)).all()'''
        )

        base_service += '''
    # =========================================================================
    # Tenant Management (Multi-tenant only)
    # =========================================================================

    def get_all_tenants(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get paginated list of all tenants."""
        query = Tenant.query

        if status and hasattr(Tenant, "status"):
            query = query.filter(Tenant.status == status)

        total = query.count()
        tenants = query.order_by(Tenant.created_at.desc()).offset(offset).limit(limit).all()

        page = (offset // limit) + 1 if limit > 0 else 1
        pages = (total + limit - 1) // limit if limit > 0 else 1

        return {
            "tenants": tenants,
            "total": total,
            "has_more": offset + limit < total,
            "pagination": {
                "page": page,
                "pages": pages,
                "per_page": limit,
                "total": total,
                "start": offset + 1 if total > 0 else 0,
                "end": min(offset + limit, total),
                "has_prev": page > 1,
                "has_next": page < pages,
            }
        }

    def get_tenant_detail(self, tenant_id: str) -> Optional[Any]:
        """Get tenant by ID for detail page."""
        return Tenant.query.get(tenant_id)

    def get_tenant_stats(self) -> dict[str, int]:
        """Get tenant statistics for dashboard."""
        total = Tenant.query.count()

        if hasattr(Tenant, "status"):
            active = Tenant.query.filter(Tenant.status == "active").count()
            pending = Tenant.query.filter(Tenant.status == "pending").count()
            suspended = Tenant.query.filter(Tenant.status == "suspended").count()
        else:
            active = total
            pending = 0
            suspended = 0

        return {
            "total": total,
            "active": active,
            "pending": pending,
            "suspended": suspended,
        }

    def create_tenant(
        self,
        name: str,
        domain: str,
        admin_email: Optional[str] = None
    ) -> tuple[Optional[Any], Optional[Any]]:
        """Create a new tenant and optionally its admin user."""
        # Auto-generate slug from domain
        slug = domain.split(".")[0].lower()
        slug = re.sub(r"[^a-z0-9-]", "", slug)

        tenant = Tenant(
            id=str(uuid.uuid4()),
            name=name,
            slug=slug,
            domain=domain,
        )

        if hasattr(Tenant, "status"):
            tenant.status = "active"

        db.session.add(tenant)

        admin_user = None
        if admin_email:
            existing = User.query.filter_by(email=admin_email).first()
            if existing:
                db.session.rollback()
                return None, None

            username = admin_email.split("@")[0]
            admin_user = User(
                id=str(uuid.uuid4()),
                tenant_id=tenant.id,
                email=admin_email,
            )

            if hasattr(User, "username"):
                admin_user.username = username
            if hasattr(User, "display_name"):
                admin_user.display_name = username.title()
            if hasattr(User, "role"):
                admin_user.role = "admin"
            if hasattr(User, "active"):
                admin_user.active = True
            if hasattr(User, "is_platform_admin"):
                admin_user.is_platform_admin = False

            db.session.add(admin_user)

        try:
            db.session.commit()
            return tenant, admin_user
        except Exception:
            db.session.rollback()
            return None, None

    def toggle_tenant_status(self, tenant_id: str) -> Optional[Any]:
        """Toggle tenant between active and suspended status."""
        tenant = Tenant.query.get(tenant_id)
        if tenant and hasattr(tenant, "status"):
            tenant.status = "suspended" if tenant.status == "active" else "active"
            db.session.commit()
        return tenant

    def get_tenant_users(
        self,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> dict[str, Any]:
        """Get users belonging to a specific tenant."""
        query = User.query.filter(User.tenant_id == tenant_id)

        if hasattr(User, "is_platform_admin"):
            query = query.filter(or_(User.is_platform_admin == False, User.is_platform_admin == None))

        total = query.count()
        users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()

        page = (offset // limit) + 1 if limit > 0 else 1
        pages = (total + limit - 1) // limit if limit > 0 else 1

        return {
            "users": users,
            "total": total,
            "has_more": offset + limit < total,
            "pagination": {
                "page": page,
                "pages": pages,
                "per_page": limit,
                "total": total,
                "start": offset + 1 if total > 0 else 0,
                "end": min(offset + limit, total),
                "has_prev": page > 1,
                "has_next": page < pages,
            }
        }
'''

    return base_service


def _build_admin_base_template(tenant_mode: str) -> str:
    """Build admin base template with navigation."""
    # Build navigation tabs
    tenant_tab = ""
    if tenant_mode == "multi":
        tenant_tab = '''
                    {% if current_user.is_platform_admin is defined and current_user.is_platform_admin %}
                    <a href="{{ url_for('admin.tenants_page') }}"
                       class="admin-nav-item px-4 py-3 text-sm {% if request.endpoint in ['admin.tenants_page', 'admin.tenant_detail_page'] %}active{% else %}text-gray-600 hover:text-gray-900{% endif %}">
                        Tenants
                    </a>
                    {% endif %}'''

    return '''{% extends "base.html" %}

{% block title %}{% block admin_title %}Admin{% endblock %} - Admin{% endblock %}

{% block content %}
<!-- Admin panel always uses light theme -->
<div class="admin-page bg-white text-gray-900 min-h-screen">
<!-- Fixed Header -->
<header class="admin-header fixed top-0 left-0 right-0 z-40 h-20">
    <div class="max-w-7xl mx-auto px-4 h-full flex items-center justify-between">
        <!-- Left: Admin branding -->
        <a href="{{ url_for('admin.index') }}" class="flex items-center gap-3 hover:opacity-80 transition-opacity">
            <svg class="w-12 h-12" viewBox="0 0 72 72" xmlns="http://www.w3.org/2000/svg">
                <g id="color">
                    <path fill="#b399c8" d="M42.3339,49.147a29.9446,29.9446,0,0,1-19.3378-8.1514h0c-8.0137-7.3643-8.378-18.0752-8.5332-22.6484l-.0215-.627a2.9039,2.9039,0,0,1,3.457-2.9512c17.0049,3.3555,21.6943,16.3243,22.0557,17.4a49.5426,49.5426,0,0,1,3.5742,15.9219,1,1,0,0,1-.9668,1.0518C42.5322,49.144,42.455,49.147,42.3339,49.147Z"/>
                    <path fill="#61b2e4" d="M44.4355,55.3159c-11.6455,0-17.3757-6.9734-17.6521-7.3542a1,1,0,0,1,.2617-1.4239,11.1031,11.1031,0,0,1,12.7742-1.5734c-1.4648-9.0782,1.877-13.5684,2.0312-13.77a.9982.9982,0,0,1,.75-.39.9705.9705,0,0,1,.78.3242c8.9434,9.7715,8.793,16.5322,7.9072,19.6914-.0341.1406-1.0615,4.0918-4.7714,4.4063C45.8046,55.2876,45.1113,55.3159,44.4355,55.3159Z"/>
                </g>
                <g id="line">
                    <path fill="none" stroke="#fff" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M55.1837,57.69S34.96,45.877,23.0974,24.2062"/>
                    <path fill="none" stroke="#fff" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M45.2281,54.3024C33.2973,54.7629,27.6,47.4216,27.6,47.4216"/>
                    <path fill="none" stroke="#fff" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M40.528,42.4827c-.5595-7.1945,2.1157-10.6784,2.1157-10.6784,8.8346,9.6533,8.4063,16.1616,7.6813,18.7468"/>
                    <path fill="none" stroke="#fff" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M37.0138,47.4216A30.15,30.15,0,0,1,23.673,40.26c-8.0725-7.4186-8.0674-18.2414-8.2321-22.5774a1.9032,1.9032,0,0,1,2.2642-1.9314C34.6938,19.1027,39.02,32.5284,39.02,32.5284"/>
                </g>
            </svg>
            <div class="flex flex-col">
                <span class="text-white text-[32px] leading-none admin-logo-text">Feather</span>
                <span class="text-white/70 text-sm font-normal">Admin</span>
            </div>
        </a>

        <!-- Right: Avatar dropdown -->
        <div class="relative">
            <button id="admin-avatar-btn" class="flex items-center gap-3 hover:opacity-80 transition-opacity cursor-pointer">
                {% if current_user and current_user.is_authenticated %}
                {% set display_name = current_user.display_name or current_user.username or current_user.email or 'Admin' %}
                {% set fallback_url = 'https://ui-avatars.com/api/?name=' ~ display_name|urlencode ~ '&background=000&color=fff&size=128' %}
                <img id="admin-avatar-img"
                     src="{{ current_user.profile_image_url or fallback_url }}"
                     alt="{{ display_name }}"
                     class="w-10 h-10 rounded-full ring-2 ring-white ring-opacity-50"
                     referrerpolicy="no-referrer"
                     crossorigin="anonymous"
                     data-fallback="{{ fallback_url }}">
                {% else %}
                <div class="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
                    <span class="material-symbols-outlined text-white text-[20px]">person</span>
                </div>
                {% endif %}
                <span class="material-symbols-outlined text-white text-[20px]">expand_more</span>
            </button>

            <!-- Avatar Dropdown Menu -->
            <div id="admin-avatar-dropdown" class="admin-avatar-dropdown">
                {% if current_user and current_user.is_authenticated %}
                <div class="p-4 border-b border-gray-200">
                    <p class="font-semibold text-gray-900">{{ current_user.display_name or current_user.username or 'Admin' }}</p>
                    <p class="text-sm text-gray-600">{{ current_user.email }}</p>
                </div>
                {% endif %}
                <div class="py-2">
                    <a href="/" class="flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors cursor-pointer">
                        <span class="material-symbols-outlined text-[20px]">home</span>
                        <span>Back to Site</span>
                    </a>
                    <a href="{{ url_for('auth.logout') }}" class="flex items-center gap-3 px-4 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors cursor-pointer">
                        <span class="material-symbols-outlined text-[20px]">logout</span>
                        <span>Sign Out</span>
                    </a>
                </div>
            </div>
        </div>
    </div>
</header>

<!-- Main Content Area -->
<div class="pt-20">
    <!-- Tab Navigation -->
    <nav class="bg-white border-b border-gray-200 fixed top-20 left-0 right-0 z-30">
        <div class="max-w-7xl mx-auto px-4">
            <div class="flex gap-8">
                <a href="{{ url_for('admin.users_page') }}"
                   class="admin-nav-item px-4 py-3 text-sm {% if request.endpoint in ['admin.users_page', 'admin.user_detail_page', 'admin.index'] %}active{% else %}text-gray-600 hover:text-gray-900{% endif %}">
                    Users
                </a>''' + tenant_tab + '''
                <a href="{{ url_for('admin.tools_page') }}"
                   class="admin-nav-item px-4 py-3 text-sm {% if request.endpoint == 'admin.tools_page' %}active{% else %}text-gray-600 hover:text-gray-900{% endif %}">
                    Tools
                </a>
                <a href="{{ url_for('admin.analytics_page') }}"
                   class="admin-nav-item px-4 py-3 text-sm {% if request.endpoint == 'admin.analytics_page' %}active{% else %}text-gray-600 hover:text-gray-900{% endif %}">
                    Analytics
                </a>
                <a href="{{ url_for('admin.logs_page') }}"
                   class="admin-nav-item px-4 py-3 text-sm {% if request.endpoint == 'admin.logs_page' %}active{% else %}text-gray-600 hover:text-gray-900{% endif %}">
                    Logs
                </a>
            </div>
        </div>
    </nav>

    <!-- Scrollable Content Area -->
    <div class="admin-content-scroll pt-[49px]">
        <main class="max-w-7xl mx-auto px-4 py-6">
            {% block admin_content %}{% endblock %}
        </main>
    </div>
</div>

<!-- Confirm Modal -->
<div id="confirm-modal" class="fixed inset-0 z-50 hidden">
    <div class="absolute inset-0 bg-black/50" data-action="cancel"></div>
    <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-lg shadow-xl w-full max-w-md overflow-hidden">
        <div class="p-6">
            <h3 class="text-lg font-semibold text-gray-900 mb-2">Confirm</h3>
            <p id="confirm-message" class="text-gray-600">Are you sure?</p>
        </div>
        <div class="flex items-center justify-end gap-3 px-6 py-4 bg-gray-50 border-t border-gray-200">
            <button data-action="cancel"
                    class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 cursor-pointer">
                Cancel
            </button>
            <button id="confirm-button"
                    class="px-4 py-2 text-sm font-medium text-white bg-black rounded-lg hover:bg-gray-800 cursor-pointer">
                Confirm
            </button>
        </div>
    </div>
</div>

<!-- Toast Container -->
<div id="toast-container"></div>
</div><!-- /.admin-page -->
{% endblock %}

{% block scripts %}
{{ super() }}
{% if pending_toast %}
<div id="pending-toast-data" data-message="{{ pending_toast.message }}" data-type="{{ pending_toast.type }}"></div>
{% endif %}
{% if config.DEBUG %}
<script type="module" src="http://localhost:5173/static/js/admin.js"></script>
{% else %}
<script src="{{ url_for('static', filename='js/admin.js') }}"></script>
{% endif %}
{% block admin_scripts %}{% endblock %}
{% endblock %}
'''


def _build_admin_users_template() -> str:
    """Build admin users list template."""
    return '''{% extends "pages/admin/base.html" %}

{% block admin_title %}Users{% endblock %}

{% block admin_content %}
<div class="space-y-6">

    <!-- Search Bar -->
    <div class="bg-white rounded-lg shadow p-4">
        <div class="flex items-center gap-4">
            <span class="material-symbols-outlined text-gray-400">search</span>
            <input type="text"
                   name="q"
                   value="{{ search }}"
                   placeholder="Search by username, name, or email..."
                   hx-get="{{ url_for('admin.users_page') }}"
                   hx-trigger="input changed delay:500ms"
                   hx-target="#users-table-container"
                   hx-select="#users-table-container"
                   class="flex-1 outline-none text-sm">
            {% if search %}
            <a href="{{ url_for('admin.users_page') }}"
               class="text-gray-400 hover:text-gray-600">
                <span class="material-symbols-outlined">close</span>
            </a>
            {% endif %}
        </div>
    </div>

    <!-- Table Container (HTMX target) -->
    <div id="users-table-container">
        {% include "partials/admin/users_table.html" %}
    </div>

</div>
{% endblock %}
'''


def _build_admin_users_table_partial() -> str:
    """Build admin users table partial."""
    return '''<div class="bg-white rounded-lg shadow overflow-hidden">
    <table class="w-full">
        <thead class="admin-table-header">
            <tr>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">User</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">Email</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">Role</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">Status</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">Joined</th>
            </tr>
        </thead>
        <tbody class="divide-y divide-gray-200">
            {% for user in users %}
            <tr class="hover:bg-gray-50 cursor-pointer"
                data-href="{{ url_for('admin.user_detail_page', user_id=user.id) }}">
                <td class="px-4 py-3">
                    <div class="flex items-center gap-3">
                        {% set avatar_url = user.profile_image_url if user.profile_image_url is defined and user.profile_image_url else fallback_avatar(user) %}
                        <img src="{{ avatar_url }}"
                             alt="{{ user.display_name or user.email }}"
                             class="w-10 h-10 rounded-full"
                             referrerpolicy="no-referrer"
                             crossorigin="anonymous">
                        <div>
                            <p class="font-medium">{{ user.display_name or user.email }}</p>
                            {% if user.username is defined and user.username %}
                            <p class="text-sm text-gray-600">@{{ user.username }}</p>
                            {% endif %}
                        </div>
                    </div>
                </td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ user.email }}</td>
                <td class="px-4 py-3">
                    {% if user.role == 'admin' %}
                    <span class="px-2 py-1 text-xs bg-black text-white rounded">Admin</span>
                    {% elif user.role == 'editor' %}
                    <span class="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded">Editor</span>
                    {% elif user.role == 'moderator' %}
                    <span class="px-2 py-1 text-xs bg-purple-100 text-purple-800 rounded">Moderator</span>
                    {% else %}
                    <span class="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded">{{ (user.role or 'user')|title }}</span>
                    {% endif %}
                </td>
                <td class="px-4 py-3">
                    {% if user.active %}
                    <span class="px-2 py-1 text-xs bg-green-100 text-green-800 rounded">Active</span>
                    {% elif user.approved_at is defined and user.approved_at %}
                    <span class="px-2 py-1 text-xs bg-red-100 text-red-800 rounded">Suspended</span>
                    {% else %}
                    <span class="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">Pending</span>
                    {% endif %}
                </td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ user.created_at.strftime('%b %d, %Y') }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    {% if not users %}
    <div class="p-8 text-center text-gray-500">
        <span class="material-symbols-outlined text-4xl mb-2">search_off</span>
        <p class="text-sm">No users found</p>
    </div>
    {% endif %}
</div>

<!-- Pagination -->
{% if pagination.pages > 1 %}
<div class="flex items-center justify-between mt-4">
    <div class="text-sm text-gray-600">
        Showing {{ pagination.start }}-{{ pagination.end }} of {{ pagination.total }}
    </div>
    <div class="flex gap-2">
        {% if pagination.has_prev %}
        <a href="?page={{ pagination.page - 1 }}"
           hx-get="{{ url_for('admin.users_page', page=pagination.page - 1) }}"
           hx-target="#users-table-container"
           hx-select="#users-table-container"
           class="px-4 py-2 text-sm bg-white border border-gray-300 rounded hover:bg-gray-50">
            Previous
        </a>
        {% else %}
        <button disabled class="px-4 py-2 text-sm bg-white border border-gray-300 rounded opacity-50 cursor-not-allowed">
            Previous
        </button>
        {% endif %}
        {% if pagination.has_next %}
        <a href="?page={{ pagination.page + 1 }}"
           hx-get="{{ url_for('admin.users_page', page=pagination.page + 1) }}"
           hx-target="#users-table-container"
           hx-select="#users-table-container"
           class="px-4 py-2 text-sm bg-white border border-gray-300 rounded hover:bg-gray-50">
            Next
        </a>
        {% else %}
        <button disabled class="px-4 py-2 text-sm bg-white border border-gray-300 rounded opacity-50 cursor-not-allowed">
            Next
        </button>
        {% endif %}
    </div>
</div>
{% endif %}
'''


def _build_admin_user_detail_template() -> str:
    """Build admin user detail template."""
    return '''{% extends "pages/admin/base.html" %}

{% block admin_title %}{{ user.display_name or user.email }}{% endblock %}

{% block admin_content %}
<div class="space-y-6">
    <!-- Back button -->
    <a href="{{ url_for('admin.users_page') }}" class="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900">
        <span class="material-symbols-outlined text-[20px]">arrow_back</span>
        Back to Users
    </a>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- User Profile Card (Left Column) -->
        <div class="bg-white rounded-lg shadow">
            <div class="p-6 text-center">
                {% set avatar_url = user.profile_image_url if user.profile_image_url is defined and user.profile_image_url else fallback_avatar(user) %}
                <img src="{{ avatar_url }}"
                     alt="{{ user.display_name or user.email }}"
                     class="w-24 h-24 rounded-full mx-auto mb-4"
                     referrerpolicy="no-referrer"
                     crossorigin="anonymous">
                <h2 class="text-xl font-semibold text-gray-900">{{ user.display_name or user.email }}</h2>
                {% if user.username is defined and user.username %}
                <p class="text-gray-600">@{{ user.username }}</p>
                {% endif %}
                <p class="text-sm text-gray-500 mt-1">{{ user.email }}</p>
            </div>

            <div class="border-t border-gray-200 p-6 space-y-4">
                <div class="flex justify-between text-sm">
                    <span class="text-gray-600">Joined</span>
                    <span class="font-medium">{{ user.created_at.strftime('%b %d, %Y') }}</span>
                </div>
                <div class="flex justify-between text-sm">
                    <span class="text-gray-600">Status</span>
                    <span id="status-pill">
                    {% if user.active %}
                    <span class="px-2 py-1 text-xs bg-green-100 text-green-800 rounded">Active</span>
                    {% elif user.approved_at is defined and user.approved_at %}
                    <span class="px-2 py-1 text-xs bg-red-100 text-red-800 rounded">Suspended</span>
                    {% else %}
                    <span class="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">Pending</span>
                    {% endif %}
                    </span>
                </div>
                <div class="flex justify-between text-sm">
                    <span class="text-gray-600">Role</span>
                    <span class="font-medium">{{ (user.role or 'user')|title }}</span>
                </div>
            </div>
        </div>

        <!-- Actions Column (Right, spans 2 columns) -->
        <div class="lg:col-span-2 space-y-6" id="user-actions">
            {% include "partials/admin/user_actions.html" %}
        </div>
    </div>
</div>
{% endblock %}
'''


def _build_admin_user_actions_partial() -> str:
    """Build admin user actions partial."""
    return '''<!-- User Actions Card -->
<div class="bg-white rounded-lg shadow">
    <div class="p-6 border-b border-gray-200">
        <div class="flex items-center gap-3">
            <div class="w-12 h-12 rounded-lg bg-black flex items-center justify-center">
                <span class="material-symbols-outlined text-white text-[28px]">badge</span>
            </div>
            <div>
                <h3 class="text-lg font-semibold text-gray-900">User Management</h3>
                <p class="text-sm text-gray-600">Manage user status and role</p>
            </div>
        </div>
    </div>

    <div class="p-6 space-y-4">
        <!-- Account Status Toggle -->
        <label class="flex items-center justify-between cursor-pointer">
            <div>
                <p class="font-medium text-gray-900">Account Status</p>
                <p class="text-sm text-gray-600">
                    {% if user.active %}
                    User can access the application
                    {% elif user.approved_at is defined and user.approved_at %}
                    User account is suspended
                    {% else %}
                    User is pending approval
                    {% endif %}
                </p>
            </div>
            <div class="relative flex-shrink-0">
                <input type="checkbox"
                       class="sr-only peer"
                       {% if user.active %}checked{% endif %}
                       hx-post="{{ url_for('admin.toggle_user_status', user_id=user.id) }}"
                       hx-target="#user-actions"
                       hx-swap="innerHTML"
                       hx-trigger="change">
                <div class="w-11 h-6 bg-gray-300 rounded-full peer-checked:bg-black transition-colors"></div>
                <div class="absolute left-1 top-1 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-5 shadow-sm"></div>
            </div>
        </label>

        <!-- Role Dropdown -->
        <div class="flex items-center justify-between pt-4 border-t border-gray-200">
            <div>
                <p class="font-medium text-gray-900">Role</p>
                <p class="text-sm text-gray-600">User's access level</p>
            </div>
            <div class="grid grid-cols-1">
                <select name="role"
                        hx-post="{{ url_for('admin.update_user_role', user_id=user.id) }}"
                        hx-target="#user-actions"
                        hx-swap="innerHTML"
                        hx-trigger="change"
                        class="col-start-1 row-start-1 appearance-none rounded-md bg-white py-1.5 pr-8 pl-3 text-sm text-gray-900 outline-1 -outline-offset-1 outline-gray-300 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-black cursor-pointer">
                    <option value="user" {% if user.role == 'user' or not user.role %}selected{% endif %}>User</option>
                    <option value="editor" {% if user.role == 'editor' %}selected{% endif %}>Editor</option>
                    <option value="moderator" {% if user.role == 'moderator' %}selected{% endif %}>Moderator</option>
                    <option value="admin" {% if user.role == 'admin' %}selected{% endif %}>Admin</option>
                </select>
                <svg viewBox="0 0 16 16" fill="currentColor" class="pointer-events-none col-start-1 row-start-1 mr-2 size-4 self-center justify-self-end text-gray-500">
                    <path d="M4.22 6.22a.75.75 0 0 1 1.06 0L8 8.94l2.72-2.72a.75.75 0 1 1 1.06 1.06l-3.25 3.25a.75.75 0 0 1-1.06 0L4.22 7.28a.75.75 0 0 1 0-1.06Z" fill-rule="evenodd" clip-rule="evenodd" />
                </svg>
            </div>
        </div>
    </div>
</div>
'''


def _build_admin_tools_template(include_email: bool = False) -> str:
    """Build admin tools template.

    Args:
        include_email: Whether email support is enabled
    """
    if include_email:
        return '''{% extends "pages/admin/base.html" %}

{% block admin_title %}Tools{% endblock %}

{% block admin_content %}
<div class="space-y-6">

    <h2 class="text-2xl font-bold">Tools</h2>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">

    <!-- Email Card -->
    <div class="bg-white rounded-lg shadow">
        <div class="p-6 border-b border-gray-200">
            <div class="flex items-center gap-3">
                <div class="w-12 h-12 rounded-lg bg-black flex items-center justify-center">
                    <span class="material-symbols-outlined text-white text-[28px]">mail</span>
                </div>
                <div>
                    <h3 class="text-lg font-semibold">Send Email</h3>
                    <p class="text-sm text-gray-600">Send an email to a user</p>
                </div>
            </div>
        </div>
        <div class="p-6">
            <form hx-post="{{ url_for('admin.send_email') }}"
                  hx-target="#email-result"
                  hx-swap="innerHTML"
                  class="space-y-4">

                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Recipient</label>
                    <input type="text"
                           id="email-to-input"
                           name="to"
                           placeholder="Search users or enter email..."
                           hx-get="{{ url_for('admin.search_users_dropdown') }}"
                           hx-trigger="input changed delay:300ms"
                           hx-target="#user-dropdown"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-black focus:border-black">
                    <div id="user-dropdown" class="relative"></div>
                </div>

                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Subject</label>
                    <input type="text"
                           name="subject"
                           required
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-black focus:border-black">
                </div>

                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Message</label>
                    <textarea name="body"
                              rows="6"
                              required
                              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-black focus:border-black"></textarea>
                </div>

                <div class="flex justify-end">
                    <button type="submit"
                            class="px-4 py-2 bg-black text-white rounded-lg hover:bg-gray-800 cursor-pointer">
                        Send Email
                    </button>
                </div>
            </form>
            <div id="email-result" class="mt-4"></div>
        </div>
    </div>

    </div>

</div>

<script>
// Handle user selection from dropdown
document.addEventListener('click', function(e) {
    if (e.target.closest('[data-action="select-email"]')) {
        var btn = e.target.closest('[data-action="select-email"]');
        var email = btn.dataset.email;
        var input = document.getElementById('email-to-input');
        if (input) {
            input.value = email;
        }
        // Clear the dropdown
        document.getElementById('user-dropdown').innerHTML = '';
    }
});

// Close dropdown when clicking outside
document.addEventListener('click', function(e) {
    var dropdown = document.getElementById('user-dropdown');
    var input = document.getElementById('email-to-input');
    if (dropdown && input && !dropdown.contains(e.target) && e.target !== input) {
        dropdown.innerHTML = '';
    }
});
</script>
{% endblock %}
'''
    else:
        # No tools configured - show placeholder
        return '''{% extends "pages/admin/base.html" %}

{% block admin_title %}Tools{% endblock %}

{% block admin_content %}
<div class="space-y-6">

    <h2 class="text-2xl font-bold">Tools</h2>

    <div class="bg-white rounded-lg shadow p-12 text-center">
        <span class="material-symbols-outlined text-gray-300 text-5xl">build</span>
        <h3 class="text-lg font-medium text-gray-900 mt-4">No tools configured</h3>
        <p class="text-sm text-gray-500 mt-2">Admin tools will appear here when enabled.</p>
    </div>

</div>
{% endblock %}
'''


def _build_admin_email_result_partial() -> str:
    """Build admin email result partial."""
    return '''{% if success %}
<div class="p-4 bg-green-50 border border-green-200 rounded-lg text-green-800 text-sm">
    {{ message }}
</div>
{% else %}
<div class="p-4 bg-red-50 border border-red-200 rounded-lg text-red-800 text-sm">
    {{ message }}
</div>
{% endif %}
'''


def _build_admin_analytics_template() -> str:
    """Build admin analytics template."""
    return '''{% extends "pages/admin/base.html" %}

{% block admin_title %}Analytics{% endblock %}

{% block admin_content %}
<div class="space-y-6">

    <div class="flex items-center justify-between">
        <h2 class="text-2xl font-bold">Analytics</h2>

        <div class="grid grid-cols-1">
            <select id="time-range-select"
                    class="col-start-1 row-start-1 appearance-none rounded-md bg-white py-1.5 pr-8 pl-3 text-sm text-gray-900 outline-1 -outline-offset-1 outline-gray-300 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-black cursor-pointer">
                <option value="7">Last 7 Days</option>
                <option value="30" selected>Last 30 Days</option>
                <option value="90">Last 90 Days</option>
            </select>
            <svg viewBox="0 0 16 16" fill="currentColor" class="pointer-events-none col-start-1 row-start-1 mr-2 size-4 self-center justify-self-end text-gray-500">
                <path d="M4.22 6.22a.75.75 0 0 1 1.06 0L8 8.94l2.72-2.72a.75.75 0 1 1 1.06 1.06l-3.25 3.25a.75.75 0 0 1-1.06 0L4.22 7.28a.75.75 0 0 1 0-1.06Z" fill-rule="evenodd" clip-rule="evenodd" />
            </svg>
        </div>
    </div>

    <!-- Stats Grid -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="bg-white rounded-lg shadow p-6">
            <div class="flex items-center justify-between">
                <div>
                    <p class="text-sm text-gray-600">Total Users</p>
                    <p class="text-2xl font-bold text-gray-900">{{ stats.total_users }}</p>
                </div>
                <div class="w-12 h-12 rounded-lg bg-black flex items-center justify-center">
                    <span class="material-symbols-outlined text-white text-[28px]">group</span>
                </div>
            </div>
        </div>
        <div class="bg-white rounded-lg shadow p-6">
            <div class="flex items-center justify-between">
                <div>
                    <p class="text-sm text-gray-600">Active Users</p>
                    <p class="text-2xl font-bold text-gray-900">{{ stats.active_users }}</p>
                </div>
                <div class="w-12 h-12 rounded-lg bg-green-600 flex items-center justify-center">
                    <span class="material-symbols-outlined text-white text-[28px]">check_circle</span>
                </div>
            </div>
        </div>
        <div class="bg-white rounded-lg shadow p-6">
            <div class="flex items-center justify-between">
                <div>
                    <p class="text-sm text-gray-600">New This Month</p>
                    <p class="text-2xl font-bold text-gray-900">{{ stats.new_this_month }}</p>
                </div>
                <div class="w-12 h-12 rounded-lg bg-blue-600 flex items-center justify-center">
                    <span class="material-symbols-outlined text-white text-[28px]">person_add</span>
                </div>
            </div>
        </div>
    </div>

    <!-- Charts Grid -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <!-- User Growth Chart -->
        <div class="bg-white rounded-lg shadow">
            <div class="p-6 border-b border-gray-200">
                <div class="flex items-center gap-3">
                    <div class="w-12 h-12 rounded-lg bg-black flex items-center justify-center">
                        <span class="material-symbols-outlined text-white text-[28px]">trending_up</span>
                    </div>
                    <div>
                        <h3 class="text-lg font-semibold">User Growth</h3>
                        <p class="text-sm text-gray-600">New registrations</p>
                    </div>
                </div>
            </div>
            <div class="p-6">
                <div id="chart-container"
                     data-api-url="{{ url_for('admin.api_user_growth') }}"
                     class="admin-chart-container">
                    <canvas id="user-growth-canvas"></canvas>
                </div>
            </div>
        </div>
    </div>

</div>
{% endblock %}

{% block admin_scripts %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
{% if config.DEBUG %}
<script type="module" src="http://localhost:5173/static/js/admin-chart.js"></script>
{% else %}
<script src="{{ url_for('static', filename='js/admin-chart.js') }}"></script>
{% endif %}
{% endblock %}
'''


def _build_admin_logs_template() -> str:
    """Build admin logs template."""
    return '''{% extends "pages/admin/base.html" %}

{% block admin_title %}Logs{% endblock %}

{% block admin_content %}
<div class="space-y-6">

    <h2 class="text-2xl font-bold">Error Logs</h2>

    <!-- Error Stats Cards -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="bg-white rounded-lg shadow p-6">
            <div class="flex items-center justify-between">
                <div>
                    <p class="text-sm text-gray-600">Client Errors (4xx)</p>
                    <p class="text-2xl font-bold text-yellow-600">{{ stats.errors_4xx }}</p>
                </div>
                <div class="w-12 h-12 rounded-lg bg-yellow-100 flex items-center justify-center">
                    <span class="material-symbols-outlined text-yellow-600 text-[28px]">warning</span>
                </div>
            </div>
        </div>
        <div class="bg-white rounded-lg shadow p-6">
            <div class="flex items-center justify-between">
                <div>
                    <p class="text-sm text-gray-600">Server Errors (5xx)</p>
                    <p class="text-2xl font-bold text-red-600">{{ stats.errors_5xx }}</p>
                </div>
                <div class="w-12 h-12 rounded-lg bg-red-100 flex items-center justify-center">
                    <span class="material-symbols-outlined text-red-600 text-[28px]">error</span>
                </div>
            </div>
        </div>
        <div class="bg-white rounded-lg shadow p-6">
            <div class="flex items-center justify-between">
                <div>
                    <p class="text-sm text-gray-600">Total Errors (7d)</p>
                    <p class="text-2xl font-bold text-gray-900">{{ stats.total }}</p>
                </div>
                <div class="w-12 h-12 rounded-lg bg-gray-100 flex items-center justify-center">
                    <span class="material-symbols-outlined text-gray-900 text-[28px]">bug_report</span>
                </div>
            </div>
        </div>
    </div>

    <!-- Error Log Table -->
    <div class="bg-white rounded-lg shadow">
        <div class="p-6 border-b border-gray-200">
            <div class="flex items-center justify-between">
                <h4 class="font-semibold text-gray-900">Recent Errors</h4>
                <div class="flex items-center gap-3">
                    <!-- Search -->
                    <input type="text"
                           id="logs-search"
                           name="search"
                           value="{{ search }}"
                           placeholder="Search errors..."
                           hx-get="{{ url_for('admin.logs_page') }}"
                           hx-trigger="input changed delay:500ms"
                           hx-target="#logs-table-container"
                           hx-select="#logs-table-container"
                           hx-include="#logs-filter"
                           class="w-64 px-3 py-1.5 text-sm border border-gray-300 rounded-lg">

                    <!-- Filter -->
                    <div class="grid grid-cols-1">
                        <select id="logs-filter"
                                name="filter"
                                hx-get="{{ url_for('admin.logs_page') }}"
                                hx-trigger="change"
                                hx-target="#logs-table-container"
                                hx-select="#logs-table-container"
                                hx-include="#logs-search"
                                class="col-start-1 row-start-1 appearance-none rounded-md bg-white py-1.5 pr-8 pl-3 text-sm text-gray-900 outline-1 -outline-offset-1 outline-gray-300 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-black cursor-pointer">
                            <option value="">All Errors</option>
                            <option value="client" {% if filter == 'client' %}selected{% endif %}>Client Errors</option>
                            <option value="server" {% if filter == 'server' %}selected{% endif %}>Server Errors</option>
                        </select>
                        <svg viewBox="0 0 16 16" fill="currentColor" class="pointer-events-none col-start-1 row-start-1 mr-2 size-4 self-center justify-self-end text-gray-500">
                            <path d="M4.22 6.22a.75.75 0 0 1 1.06 0L8 8.94l2.72-2.72a.75.75 0 1 1 1.06 1.06l-3.25 3.25a.75.75 0 0 1-1.06 0L4.22 7.28a.75.75 0 0 1 0-1.06Z" fill-rule="evenodd" clip-rule="evenodd" />
                        </svg>
                    </div>
                </div>
            </div>
        </div>

        <div class="p-6">
            <div id="logs-table-container">
                {% include "partials/admin/logs_table.html" %}
            </div>
        </div>
    </div>

</div>
{% endblock %}
'''


def _build_admin_logs_table_partial() -> str:
    """Build admin logs table partial."""
    return '''<table class="w-full">
    <thead class="admin-table-header">
        <tr>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">Type</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">Message</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">Path</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">Time</th>
        </tr>
    </thead>
    <tbody class="divide-y divide-gray-200">
        {% for log in logs %}
        <tr class="hover:bg-gray-50">
            <td class="px-4 py-3">
                {% set event_type = log.event_type if log.event_type is defined else 'Error' %}
                {% if event_type in ['NotFoundError', 'ValidationError', 'AuthenticationError', 'AuthorizationError'] %}
                <span class="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">{{ event_type }}</span>
                {% else %}
                <span class="px-2 py-1 text-xs bg-red-100 text-red-800 rounded">{{ event_type }}</span>
                {% endif %}
            </td>
            <td class="px-4 py-3 text-sm text-gray-600 max-w-md truncate">{{ log.message }}</td>
            <td class="px-4 py-3 text-sm text-gray-600 font-mono">{{ log.path or '-' }}</td>
            <td class="px-4 py-3 text-sm text-gray-600">{{ log.created_at.strftime('%b %d, %H:%M') }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>

{% if not logs %}
<div class="p-8 text-center text-gray-500">
    <span class="material-symbols-outlined text-4xl mb-2">check_circle</span>
    <p class="text-sm">No errors found</p>
</div>
{% endif %}

<!-- Pagination -->
{% if pagination.pages > 1 %}
<div class="flex items-center justify-between mt-4 pt-4 border-t border-gray-200">
    <div class="text-sm text-gray-600">
        Showing {{ pagination.start }}-{{ pagination.end }} of {{ pagination.total }}
    </div>
    <div class="flex gap-2">
        {% if pagination.has_prev %}
        <a href="?page={{ pagination.page - 1 }}{% if search %}&search={{ search }}{% endif %}{% if filter %}&filter={{ filter }}{% endif %}"
           hx-get="{{ url_for('admin.logs_page', page=pagination.page - 1, search=search, filter=filter) }}"
           hx-target="#logs-table-container"
           hx-select="#logs-table-container"
           class="px-4 py-2 text-sm bg-white border border-gray-300 rounded hover:bg-gray-50">
            Previous
        </a>
        {% else %}
        <button disabled class="px-4 py-2 text-sm bg-white border border-gray-300 rounded opacity-50 cursor-not-allowed">
            Previous
        </button>
        {% endif %}
        {% if pagination.has_next %}
        <a href="?page={{ pagination.page + 1 }}{% if search %}&search={{ search }}{% endif %}{% if filter %}&filter={{ filter }}{% endif %}"
           hx-get="{{ url_for('admin.logs_page', page=pagination.page + 1, search=search, filter=filter) }}"
           hx-target="#logs-table-container"
           hx-select="#logs-table-container"
           class="px-4 py-2 text-sm bg-white border border-gray-300 rounded hover:bg-gray-50">
            Next
        </a>
        {% else %}
        <button disabled class="px-4 py-2 text-sm bg-white border border-gray-300 rounded opacity-50 cursor-not-allowed">
            Next
        </button>
        {% endif %}
    </div>
</div>
{% endif %}
'''


def _build_admin_tenants_template() -> str:
    """Build admin tenants list template (multi-tenant only)."""
    return '''{% extends "pages/admin/base.html" %}

{% block admin_content %}
<div class="space-y-6">
    <!-- Header with Create Button -->
    <div class="flex items-center justify-between">
        <div>
            <h2 class="text-2xl font-semibold text-gray-900">Tenants</h2>
            <p class="text-sm text-gray-600">Manage organizations in the platform</p>
        </div>
        <button data-action="show-create-tenant"
                class="px-4 py-2 text-sm font-medium text-white bg-black rounded-lg hover:bg-gray-800">
            <span class="material-symbols-outlined text-sm align-middle mr-1">add</span>
            New Tenant
        </button>
    </div>

    <!-- Stats Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div class="bg-white rounded-lg shadow p-6">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-black flex items-center justify-center">
                    <span class="material-symbols-outlined text-white text-xl">business</span>
                </div>
                <div>
                    <p class="text-2xl font-semibold">{{ stats.total }}</p>
                    <p class="text-sm text-gray-600">Total Tenants</p>
                </div>
            </div>
        </div>
        <div class="bg-white rounded-lg shadow p-6">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                    <span class="material-symbols-outlined text-green-600 text-xl">check_circle</span>
                </div>
                <div>
                    <p class="text-2xl font-semibold">{{ stats.active }}</p>
                    <p class="text-sm text-gray-600">Active</p>
                </div>
            </div>
        </div>
        <div class="bg-white rounded-lg shadow p-6">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-yellow-100 flex items-center justify-center">
                    <span class="material-symbols-outlined text-yellow-600 text-xl">schedule</span>
                </div>
                <div>
                    <p class="text-2xl font-semibold">{{ stats.pending }}</p>
                    <p class="text-sm text-gray-600">Pending</p>
                </div>
            </div>
        </div>
        <div class="bg-white rounded-lg shadow p-6">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center">
                    <span class="material-symbols-outlined text-red-600 text-xl">block</span>
                </div>
                <div>
                    <p class="text-2xl font-semibold">{{ stats.suspended }}</p>
                    <p class="text-sm text-gray-600">Suspended</p>
                </div>
            </div>
        </div>
    </div>

    <!-- Status Filter -->
    <div class="flex items-center gap-2">
        <span class="text-sm text-gray-600">Filter:</span>
        <a href="{{ url_for('admin.tenants_page') }}"
           class="px-3 py-1.5 text-sm rounded-lg {% if not status_filter %}bg-black text-white{% else %}bg-gray-100 text-gray-700 hover:bg-gray-200{% endif %}">
            All
        </a>
        <a href="{{ url_for('admin.tenants_page', status='active') }}"
           class="px-3 py-1.5 text-sm rounded-lg {% if status_filter == 'active' %}bg-black text-white{% else %}bg-gray-100 text-gray-700 hover:bg-gray-200{% endif %}">
            Active
        </a>
        <a href="{{ url_for('admin.tenants_page', status='pending') }}"
           class="px-3 py-1.5 text-sm rounded-lg {% if status_filter == 'pending' %}bg-black text-white{% else %}bg-gray-100 text-gray-700 hover:bg-gray-200{% endif %}">
            Pending
        </a>
        <a href="{{ url_for('admin.tenants_page', status='suspended') }}"
           class="px-3 py-1.5 text-sm rounded-lg {% if status_filter == 'suspended' %}bg-black text-white{% else %}bg-gray-100 text-gray-700 hover:bg-gray-200{% endif %}">
            Suspended
        </a>
    </div>

    <!-- Tenants Table -->
    <div id="tenants-table-container">
        {% include "partials/admin/tenants_table.html" %}
    </div>
</div>

<!-- Create Tenant Modal -->
<div id="create-tenant-modal" class="hidden fixed inset-0 z-50 overflow-y-auto">
    <div class="flex items-center justify-center min-h-screen px-4">
        <div class="fixed inset-0 bg-black/50" data-action="hide-create-tenant"></div>
        <div class="relative bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <div class="flex items-center justify-between mb-4">
                <h3 class="text-lg font-semibold text-gray-900">Create New Tenant</h3>
                <button data-action="hide-create-tenant"
                        class="text-gray-400 hover:text-gray-600">
                    <span class="material-symbols-outlined">close</span>
                </button>
            </div>

            <form action="{{ url_for('admin.create_tenant') }}" method="POST" class="space-y-4">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Tenant Name</label>
                    <input type="text" name="name" required
                           placeholder="Acme Corporation"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-black">
                </div>

                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Email Domain</label>
                    <input type="text" name="domain" required
                           placeholder="acme.com"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-black">
                    <p class="text-xs text-gray-500 mt-1">Users with this email domain can join</p>
                </div>

                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Admin Email</label>
                    <input type="email" name="admin_email" required
                           placeholder="admin@acme.com"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-black">
                    <p class="text-xs text-gray-500 mt-1">This user will be the tenant admin</p>
                </div>

                <div class="flex justify-end gap-3 pt-4">
                    <button type="button"
                            data-action="hide-create-tenant"
                            class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200">
                        Cancel
                    </button>
                    <button type="submit"
                            class="px-4 py-2 text-sm font-medium text-white bg-black rounded-lg hover:bg-gray-800">
                        Create Tenant
                    </button>
                </div>
            </form>
        </div>
    </div>
</div>
{% endblock %}
'''


def _build_admin_tenants_table_partial() -> str:
    """Build admin tenants table partial (multi-tenant only)."""
    return '''<div class="bg-white rounded-lg shadow overflow-hidden">
    <table class="w-full">
        <thead class="admin-table-header">
            <tr>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">Tenant</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">Domain</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">Users</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">Status</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">Created</th>
            </tr>
        </thead>
        <tbody class="divide-y divide-gray-200">
            {% for tenant in tenants %}
            <tr class="hover:bg-gray-50 cursor-pointer"
                data-href="{{ url_for('admin.tenant_detail_page', tenant_id=tenant.id) }}">
                <td class="px-4 py-3">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center">
                            <span class="material-symbols-outlined text-gray-600">business</span>
                        </div>
                        <div>
                            <p class="font-medium">{{ tenant.name }}</p>
                            <p class="text-sm text-gray-600">{{ tenant.slug }}</p>
                        </div>
                    </div>
                </td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ tenant.domain }}</td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ tenant.user_count if tenant.user_count is defined else '-' }}</td>
                <td class="px-4 py-3">
                    {% if tenant.status == 'active' %}
                    <span class="px-2 py-1 text-xs bg-green-100 text-green-800 rounded">Active</span>
                    {% elif tenant.status == 'pending' %}
                    <span class="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">Pending</span>
                    {% else %}
                    <span class="px-2 py-1 text-xs bg-red-100 text-red-800 rounded">Suspended</span>
                    {% endif %}
                </td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ tenant.created_at.strftime('%b %d, %Y') }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    {% if not tenants %}
    <div class="p-8 text-center text-gray-500">
        <span class="material-symbols-outlined text-4xl mb-2">business</span>
        <p class="text-sm">No tenants found</p>
    </div>
    {% endif %}
</div>

<!-- Pagination -->
{% if pagination.pages > 1 %}
<div class="flex items-center justify-between mt-4">
    <div class="text-sm text-gray-600">
        Showing {{ pagination.start }}-{{ pagination.end }} of {{ pagination.total }}
    </div>
    <div class="flex gap-2">
        {% if pagination.has_prev %}
        <a href="?page={{ pagination.page - 1 }}{% if status_filter %}&status={{ status_filter }}{% endif %}"
           class="px-4 py-2 text-sm bg-white border border-gray-300 rounded hover:bg-gray-50">
            Previous
        </a>
        {% else %}
        <button disabled class="px-4 py-2 text-sm bg-white border border-gray-300 rounded opacity-50 cursor-not-allowed">
            Previous
        </button>
        {% endif %}
        {% if pagination.has_next %}
        <a href="?page={{ pagination.page + 1 }}{% if status_filter %}&status={{ status_filter }}{% endif %}"
           class="px-4 py-2 text-sm bg-white border border-gray-300 rounded hover:bg-gray-50">
            Next
        </a>
        {% else %}
        <button disabled class="px-4 py-2 text-sm bg-white border border-gray-300 rounded opacity-50 cursor-not-allowed">
            Next
        </button>
        {% endif %}
    </div>
</div>
{% endif %}
'''


def _build_admin_tenant_detail_template() -> str:
    """Build admin tenant detail template (multi-tenant only)."""
    return '''{% extends "pages/admin/base.html" %}

{% block admin_content %}
<div class="space-y-6">
    <!-- Back link and header -->
    <div>
        <a href="{{ url_for('admin.tenants_page') }}"
           class="inline-flex items-center text-sm text-gray-600 hover:text-gray-900 mb-4">
            <span class="material-symbols-outlined text-sm mr-1">arrow_back</span>
            Back to Tenants
        </a>
        <h2 class="text-2xl font-semibold text-gray-900">{{ tenant.name }}</h2>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Left Column: Tenant Info -->
        <div class="lg:col-span-2">
            <!-- Tenant Profile Card -->
            <div class="bg-white rounded-lg shadow">
                <div class="p-6 border-b border-gray-200">
                    <div class="flex items-center gap-4">
                        <div class="w-16 h-16 rounded-xl bg-gray-100 flex items-center justify-center">
                            <span class="material-symbols-outlined text-gray-600 text-3xl">business</span>
                        </div>
                        <div>
                            <h3 class="text-xl font-semibold text-gray-900">{{ tenant.name }}</h3>
                            <p class="text-gray-600">{{ tenant.slug }}</p>
                        </div>
                    </div>
                </div>
                <div class="p-6">
                    <dl class="grid grid-cols-2 gap-4">
                        <div>
                            <dt class="text-sm text-gray-600">Domain</dt>
                            <dd class="font-medium">{{ tenant.domain }}</dd>
                        </div>
                        <div>
                            <dt class="text-sm text-gray-600">Status</dt>
                            <dd>
                                {% if tenant.status == 'active' %}
                                <span class="px-2 py-1 text-xs bg-green-100 text-green-800 rounded">Active</span>
                                {% elif tenant.status == 'pending' %}
                                <span class="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">Pending</span>
                                {% else %}
                                <span class="px-2 py-1 text-xs bg-red-100 text-red-800 rounded">Suspended</span>
                                {% endif %}
                            </dd>
                        </div>
                        <div>
                            <dt class="text-sm text-gray-600">Created</dt>
                            <dd class="font-medium">{{ tenant.created_at.strftime('%B %d, %Y') }}</dd>
                        </div>
                        <div>
                            <dt class="text-sm text-gray-600">Users</dt>
                            <dd class="font-medium">{{ users|length }}</dd>
                        </div>
                    </dl>
                </div>
            </div>
        </div>

        <!-- Right Column: Actions -->
        <div id="tenant-actions">
            {% include "partials/admin/tenant_actions.html" %}
        </div>
    </div>

    <!-- Users in Tenant (Full Width) -->
    <div class="bg-white rounded-lg shadow">
        <div class="p-6 border-b border-gray-200">
            <h4 class="font-semibold text-gray-900">Users in {{ tenant.name }}</h4>
        </div>
        <div class="divide-y divide-gray-200">
            {% for user in users %}
            <a href="{{ url_for('admin.user_detail_page', user_id=user.id) }}"
               class="flex items-center gap-3 p-4 hover:bg-gray-50">
                {% set avatar_url = user.profile_image_url if user.profile_image_url is defined and user.profile_image_url else fallback_avatar(user) %}
                <img src="{{ avatar_url }}"
                     alt="{{ user.display_name or user.email }}"
                     class="w-10 h-10 rounded-full"
                     referrerpolicy="no-referrer">
                <div class="flex-1">
                    <p class="font-medium">{{ user.display_name or user.email }}</p>
                    <p class="text-sm text-gray-600">{{ user.email }}</p>
                </div>
                <div class="flex items-center gap-2">
                    {% if user.role == 'admin' %}
                    <span class="px-2 py-1 text-xs bg-black text-white rounded">Admin</span>
                    {% endif %}
                    {% if user.active %}
                    <span class="px-2 py-1 text-xs bg-green-100 text-green-800 rounded">Active</span>
                    {% else %}
                    <span class="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">Pending</span>
                    {% endif %}
                </div>
            </a>
            {% endfor %}

            {% if not users %}
            <div class="p-8 text-center text-gray-500">
                <span class="material-symbols-outlined text-4xl mb-2">group</span>
                <p class="text-sm">No users in this tenant</p>
            </div>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}
'''


def _build_admin_tenant_actions_partial() -> str:
    """Build admin tenant actions partial (multi-tenant only)."""
    return '''<!-- Tenant Status Card -->
<div class="bg-white rounded-lg shadow">
    <div class="p-6 border-b border-gray-200">
        <div class="flex items-center gap-3">
            <div class="w-12 h-12 rounded-lg bg-black flex items-center justify-center">
                <span class="material-symbols-outlined text-white text-[28px]">settings</span>
            </div>
            <div>
                <h3 class="text-lg font-semibold text-gray-900">Tenant Status</h3>
                <p class="text-sm text-gray-600">Manage tenant access</p>
            </div>
        </div>
    </div>

    <div class="p-6 space-y-4">
        <!-- Status Toggle -->
        <label class="flex items-center justify-between cursor-pointer">
            <div>
                <p class="font-medium text-gray-900">Active Status</p>
                <p class="text-sm text-gray-600">
                    {% if tenant.status == 'active' %}
                    Tenant users can access the application
                    {% elif tenant.status == 'pending' %}
                    Tenant is pending approval
                    {% else %}
                    Tenant is suspended
                    {% endif %}
                </p>
            </div>
            <div class="relative flex-shrink-0">
                <input type="checkbox"
                       class="sr-only peer"
                       {% if tenant.status == 'active' %}checked{% endif %}
                       hx-post="{{ url_for('admin.toggle_tenant_status', tenant_id=tenant.id) }}"
                       hx-target="#tenant-actions"
                       hx-swap="innerHTML"
                       hx-trigger="change">
                <div class="w-11 h-6 bg-gray-300 rounded-full peer-checked:bg-black transition-colors"></div>
                <div class="absolute left-1 top-1 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-5 shadow-sm"></div>
            </div>
        </label>

        <!-- Info Section -->
        <div class="pt-4 border-t border-gray-200">
            <p class="text-sm text-gray-600">
                {% if tenant.status == 'active' %}
                <span class="material-symbols-outlined text-green-600 text-sm align-middle mr-1">check_circle</span>
                Users from <strong>{{ tenant.domain }}</strong> can sign up and access the app.
                {% elif tenant.status == 'pending' %}
                <span class="material-symbols-outlined text-yellow-600 text-sm align-middle mr-1">schedule</span>
                Activate to allow users from <strong>{{ tenant.domain }}</strong> to join.
                {% else %}
                <span class="material-symbols-outlined text-red-600 text-sm align-middle mr-1">block</span>
                Users from this tenant cannot access the application.
                {% endif %}
            </p>
        </div>
    </div>
</div>
'''
