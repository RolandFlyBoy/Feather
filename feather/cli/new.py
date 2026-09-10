"""feather new - Create a new Feather project."""

import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import click

from feather.scaffold import render_fragment, write_project


def _get_local_source_path():
    """Get the local source directory if feather was installed from a local path.

    Works for both `pipx install .` and `pipx install -e .` — either way,
    PEP 610 records a file:// URL in direct_url.json pointing to the source.
    """
    try:
        dist = importlib.metadata.distribution("feather-framework")
        direct_url = dist.read_text("direct_url.json")
        if direct_url:
            data = json.loads(direct_url)
            url = data.get("url", "")
            if url.startswith("file://"):
                path = Path(url[7:])
                if (path / "pyproject.toml").exists():
                    return path
    except Exception:
        pass
    return None


def _get_feather_version():
    """Get the installed feather-framework version."""
    try:
        return importlib.metadata.version("feather-framework")
    except importlib.metadata.PackageNotFoundError:
        import feather
        return feather.__version__


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
@click.option("--no-prompt", is_flag=True, help="Skip prompts, use defaults (simple app, no database)")
def new(name: str, no_prompt: bool):
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
        "auto_approve_users": False,  # Auto-approve signups (no admin approval needed)
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

            options["auto_approve_users"] = click.confirm(
                "  Auto-approve new user signups?",
                default=False,
            )

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
                # profile_image_url is always included (needed for OAuth profile pics)
                "profile_image_url": True,
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

    click.echo()
    click.echo(click.style("Deployment:", fg="yellow"))
    click.echo("  Dockerfile, docker-compose.yml, docker-compose.dev.yml, deploy/ and")
    click.echo("  .env.example are already written. On a server: cp .env.example .env,")
    click.echo("  fill it in, then ./deploy/deploy.sh. See the Deployment section of")
    click.echo("  CLAUDE.md, and `feather docker init --help` to regenerate the files.")


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


def _create_docker_files(
    project_path: Path,
    name: str,
    database: str = "postgresql",
    include_cache: bool = False,
    include_jobs: bool = False,
    env_body: str = None,
    domain: str = None,
) -> list:
    """Write the Docker deployment layout into a freshly scaffolded project.

    Shares every file body with ``feather docker init`` via
    :mod:`feather.cli._docker_templates`, so an app scaffolded today and an
    app that runs ``feather docker init`` later get identical files.
    """
    from feather.cli._docker_templates import docker_files, slugify, write_docker_files

    files = docker_files(
        name,
        app_slug=slugify(name),
        database=database != "none",
        redis=include_cache or include_jobs,
        worker=include_jobs,
        domain=domain,
        base_env=env_body,
    )
    return write_docker_files(project_path, files, force=True)


def _create_project_files(
    project_path: Path,
    name: str,
    database: str = "postgresql",
    include_auth: bool = False,
    tenant_mode: str = None,
    auto_approve_users: bool = False,
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

    The file bodies are not in this module. They live in
    :mod:`feather.scaffold` as real files - ``app.css`` is CSS, ``base.html``
    is HTML - grouped into overlays that are applied in order according to the
    options below. See that package's docstring for the layout and for how
    ``__FEATHER_..__`` tokens are substituted.

    Args:
        project_path: Path to the project directory
        name: Project name
        database: Database type ("none", "sqlite", or "postgresql")
        include_auth: Whether to include authentication (Google OAuth + admin panel)
        tenant_mode: Tenant mode ("single" or "multi"), only if include_auth is True
        auto_approve_users: Whether new signups are active without admin approval
        include_cache: Whether to include Redis caching
        include_jobs: Whether to include background jobs
        include_storage: Whether to include cloud storage
        storage_backend: Storage backend ("gcs" or None)
        include_email: Whether to include email support (Resend)
        db_url: Database URL (for postgresql/sqlite)
        admin_email: Admin email for seeds.py
        app_type: Recorded by the prompt flow; the overlays key off the
            individual options rather than off this label.
        user_fields: Optional User model field selection
    """
    options = {
        "name": name,
        "database": database,
        "include_auth": include_auth,
        "tenant_mode": tenant_mode,
        "auto_approve_users": auto_approve_users,
        "include_cache": include_cache,
        "include_jobs": include_jobs,
        "include_storage": include_storage,
        "storage_backend": storage_backend,
        "include_email": include_email,
        "db_url": db_url,
        "admin_email": admin_email,
        "app_type": app_type,
        "user_fields": user_fields,
    }

    write_project(project_path, options)

    # Docker deployment layout (Dockerfile, compose files, Caddyfile, deploy
    # scripts, .env.example). The bodies live in _docker_templates so
    # `feather docker init` writes exactly the same thing into an app that
    # was scaffolded before this release. It seeds .env.example from the .env
    # the overlays just wrote, so it has to run after them.
    _create_docker_files(
        project_path,
        name=name,
        database=database,
        include_cache=include_cache,
        include_jobs=include_jobs,
        env_body=(project_path / ".env").read_text(),
    )

    # Guidance for AI coding assistants.
    #
    # AGENTS.md carries the rules because every assistant reads that name;
    # CLAUDE.md points at it so the two can never drift apart. The rules are
    # also checkable rather than merely stated: `feather check` enforces them
    # and `feather components` answers "what arguments does this macro take"
    # from the macros themselves. The body is one file in the scaffold
    # overlays, written into both names by _agent_files.
    from feather.cli._agent_files import agent_files

    for relative, content in agent_files(
        name, render_fragment(options, "agents_body")
    ).items():
        target = project_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    click.echo("  Created project files")


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


def _pip_install_feather(pip_path):
    """Install feather-framework from PyPI into a scaffolded app's venv."""
    version = _get_feather_version()
    package_spec = f"feather-framework=={version}"
    try:
        subprocess.run(
            [str(pip_path), "install", package_spec],
            capture_output=True,
            check=True,
        )
        click.echo(f"  Installed Feather framework ({version})")
    except subprocess.CalledProcessError:
        # Version may not be on PyPI yet — try without pinning
        click.echo(f"  Note: {package_spec} not found on PyPI, trying latest...")
        subprocess.run(
            [str(pip_path), "install", "feather-framework"],
            capture_output=True,
            check=True,
        )
        click.echo("  Installed Feather framework (latest)")


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

        # Install Feather into the scaffolded app's venv
        source_path = _get_local_source_path()
        if source_path:
            # Installed from local source (pipx install . or pip install -e .)
            subprocess.run(
                [str(pip_path), "install", str(source_path)],
                capture_output=True,
                check=True,
            )
            click.echo("  Installed Feather framework (from source)")
        else:
            # Installed from PyPI
            _pip_install_feather(pip_path)

    except subprocess.CalledProcessError as e:
        click.echo(f"  Warning: Could not set up venv ({e})")
        click.echo("  Run manually: python -m venv venv && venv/bin/pip install feather-framework")
    except FileNotFoundError:
        click.echo("  Skipped venv setup (Python not available)")

