"""feather new - Create a new Feather project.

Every question the prompts ask also has a flag, so the command can be driven
from arguments alone. That is what lets a server-side agent scaffold an app:
it has no terminal to answer prompts on, and it needs the result as data
rather than as the "Next steps" text a person reads.
"""

import contextlib
import importlib.metadata
import io
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


#: The app types, in the spelling the ``--app-type`` flag and the prompt use.
#: ``options["app_type"]`` carries the underscored form the scaffold expects.
APP_TYPES = ("simple", "single-tenant", "multi-tenant")

#: The database each app type gets when nothing answers the question.
DEFAULT_DATABASE = {
    "simple": "none",
    "single-tenant": "sqlite",
    "multi-tenant": "postgresql",
}

#: Flags the prompts only ever ask about for an app with user accounts, and
#: the option key each one answers. Used to refuse them on a simple app, the
#: way the prompt flow never offers them there.
AUTH_ONLY_FLAGS = {
    "auto_approve_users": "--auto-approve-users/--no-auto-approve-users",
    "cache": "--cache/--no-cache",
    "storage": "--storage/--no-storage",
    "email": "--email/--no-email",
    "admin_email": "--admin-email",
    "sign_in": "--sign-in",
}


def _has_auth(app_type: str) -> bool:
    """Whether this app type comes with user accounts."""
    return app_type in ("single-tenant", "multi-tenant")


def _questions_for(app_type: str) -> tuple[str, ...]:
    """The flags that have to be given for this app type to skip the prompts.

    The database is not among them for multi-tenant (PostgreSQL is the only
    answer), and neither the database name nor the User profile fields are
    ever among them: both have a default that needs no terminal.
    """
    questions = () if app_type == "multi-tenant" else ("database",)
    questions += ("jobs",)
    if _has_auth(app_type):
        questions += ("auto_approve_users", "cache", "storage", "email", "admin_email")
    return questions


def _fully_specified(given: dict) -> bool:
    """Whether the flags answer every question the prompts would ask."""
    app_type = given["app_type"]
    if app_type is None:
        return False
    return all(given[question] is not None for question in _questions_for(app_type))


def _validate_flags(given: dict) -> None:
    """Refuse flag combinations the prompt flow could never produce.

    Called with the flags as given, and again once the app type and the
    database are settled, so an answer that came from a default or a prompt
    cannot slip through a combination an explicit flag is refused for.
    """
    app_type = given["app_type"]
    database = given["database"]

    if app_type == "multi-tenant" and database not in (None, "postgresql"):
        raise click.ClickException(
            "--app-type multi-tenant requires --database postgresql "
            f"(got --database {database}); tenants are rows in one PostgreSQL database"
        )

    if app_type is not None and _has_auth(app_type) and database == "none":
        raise click.ClickException(
            f"--app-type {app_type} stores user accounts, so it needs a database: "
            "pass --database sqlite or --database postgresql"
        )

    if app_type is not None and not _has_auth(app_type):
        for key, flag in AUTH_ONLY_FLAGS.items():
            if given.get(key) is not None:
                raise click.ClickException(
                    f"{flag} applies to an app with user accounts: "
                    "pass --app-type single-tenant or --app-type multi-tenant"
                )

    if given["db_name"] is not None and database not in (None, "postgresql"):
        raise click.ClickException(
            "--db-name names the PostgreSQL database to create, so it applies "
            f"only with --database postgresql (got --database {database})"
        )


def _resolve_options(name: str, given: dict, no_prompt: bool) -> dict:
    """Settle every scaffolding question from the flags, a prompt or a default.

    A flag answers its question outright, which is what lets an orchestrator
    drive the command from arguments. Whatever is left over is prompted for,
    unless the caller passed --no-prompt or the flags already answer every
    question, in which case the default answer stands and nothing is asked.
    """
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
        "sign_in": "google",
    }

    prompting = not no_prompt and not _fully_specified(given)
    shown = []

    def section(title: str, suffix: str = "") -> None:
        """Head a group of questions, separated from the group before it.

        The separator is tracked rather than printed with the group above
        because a flag can remove any group, and a section the caller
        answered by flag should leave no gap behind.
        """
        if shown:
            click.echo()
        click.echo(click.style(title, fg="cyan") + suffix)
        shown.append(title)

    if prompting:
        click.echo()
        click.echo(click.style("Project Configuration", fg="cyan", bold=True))
        click.echo()

    # App type selection (drives all other options)
    app_type = given["app_type"]
    if app_type is None:
        if prompting:
            section("App Type")
            click.echo("  Simple       - Static pages, no authentication")
            click.echo("  Single-tenant - One organization, user accounts")
            click.echo("  Multi-tenant  - Multiple organizations (SaaS)")
            click.echo()
            app_type = click.prompt(
                "  Select type",
                type=click.Choice(list(APP_TYPES)),
                default="simple",
            )
        else:
            app_type = "simple"

    options["app_type"] = app_type.replace("-", "_")
    if _has_auth(app_type):
        options["include_auth"] = True
        options["tenant_mode"] = "multi" if app_type == "multi-tenant" else "single"

    # Database options depend on app type. Multi-tenant has no choice to make,
    # so its only question is the name of the database to create.
    database = given["database"]
    if database is None and app_type == "multi-tenant":
        database = "postgresql"

    asks_database = prompting and database is None
    asks_db_name = prompting and given["db_name"] is None and (
        database == "postgresql" or asks_database
    )
    if asks_database or asks_db_name:
        section("Database")

    if asks_database:
        choices = ["none", "sqlite", "postgresql"] if app_type == "simple" else ["sqlite", "postgresql"]
        database = click.prompt(
            "  Type",
            type=click.Choice(choices),
            default=DEFAULT_DATABASE[app_type],
        )
    elif database is None:
        database = DEFAULT_DATABASE[app_type]

    options["database"] = database
    _validate_flags({**given, "app_type": app_type, "database": database})

    if database == "postgresql":
        db_name = given["db_name"]
        if db_name is None and prompting:
            label = "Database name (PostgreSQL required)" if app_type == "multi-tenant" else "Database name"
            db_name = click.prompt(f"  {label}", default=name)
        options["db_url"] = f"postgresql://localhost/{db_name or name}"

    # Background jobs: Available for all app types
    if given["jobs"] is not None:
        options["include_jobs"] = given["jobs"]
    elif prompting:
        section("Background Jobs")
        options["include_jobs"] = click.confirm(
            "  Include background jobs?",
            default=True,
        )

    # Additional features: Only for authenticated apps
    if options["include_auth"]:
        features = (
            ("auto_approve_users", "auto_approve_users", "  Auto-approve new user signups?", False),
            ("include_cache", "cache", "  Include Redis caching?", True),
            ("include_storage", "storage", "  Include cloud storage (S3 or GCS)?", True),
            ("include_email", "email", "  Include email support (Resend)?", False),
        )
        if prompting and any(given[flag] is None for _, flag, _, _ in features):
            section("Features", " (press Enter for defaults):")

        for key, flag, question, default in features:
            if given[flag] is not None:
                options[key] = given[flag]
            elif prompting:
                options[key] = click.confirm(question, default=default)

        if options["include_storage"]:
            options["storage_backend"] = "gcs"

        # User model field selection. Only ever asked: an app driven by flags
        # keeps the model's own default, which is every field.
        if prompting:
            section("User Profile Fields", " (optional):")
            options["user_fields"] = {
                "display_name": click.confirm(
                    "  Include display_name?",
                    default=True,
                ),
                # profile_image_url is always included (needed for OAuth profile pics)
                "profile_image_url": True,
            }

        # How people sign in. Not asked: Google unless the flag says email.
        options["sign_in"] = given.get("sign_in") or "google"

        # Admin email (required for auth)
        if given["admin_email"] is not None:
            options["admin_email"] = given["admin_email"]
        elif prompting:
            section("Admin Setup")
            admin_label = "Platform admin email" if app_type == "multi-tenant" else "Admin email"
            options["admin_email"] = click.prompt(f"  {admin_label}")
        else:
            # Nothing else can supply it: seeds.py has no admin to create, so
            # the app would have no way in.
            raise click.ClickException(
                f"--admin-email is required for --app-type {app_type} when running "
                "without prompts; it is the account seeds.py makes an admin"
            )

    if prompting:
        click.echo()

    return options


@contextlib.contextmanager
def _quiet(enabled: bool):
    """Swallow the progress narration while ``--json`` is on.

    The helpers below say what they are doing as they go, which is what a
    person wants to watch. A caller that asked for JSON has to be able to
    parse the whole of stdout, so for them it goes nowhere.
    """
    if not enabled:
        yield
        return
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _result(project_path: Path, name: str, options: dict, migrated: bool) -> dict:
    """What ``--json`` prints: the choices made, and what came of them."""
    return {
        "path": str(project_path),
        "name": name,
        "app_type": options["app_type"].replace("_", "-"),
        "database": options["database"],
        "database_url": options["db_url"],
        "jobs": bool(options["include_jobs"]),
        "cache": bool(options["include_cache"]),
        "storage": bool(options["include_storage"]),
        "email": bool(options["include_email"]),
        "auto_approve_users": bool(options["auto_approve_users"]),
        "admin_email": options["admin_email"],
        "sign_in": (options.get("sign_in") or "google") if options.get("include_auth") else None,
        "migration_created": bool(migrated),
    }


@click.command()
@click.argument("name")
@click.option("--no-prompt", is_flag=True, help="Skip prompts, use defaults for anything no flag answers")
@click.option(
    "--app-type",
    type=click.Choice(list(APP_TYPES)),
    default=None,
    help="App type (default: simple)",
)
@click.option(
    "--database",
    type=click.Choice(["none", "sqlite", "postgresql"]),
    default=None,
    help="Database (default: none for simple, sqlite for single-tenant, postgresql for multi-tenant)",
)
@click.option("--db-name", default=None, help="PostgreSQL database to create (default: the project name)")
@click.option("--jobs/--no-jobs", default=None, help="Background jobs")
@click.option("--cache/--no-cache", default=None, help="Redis caching (apps with user accounts)")
@click.option("--storage/--no-storage", default=None, help="Cloud storage (apps with user accounts)")
@click.option("--email/--no-email", default=None, help="Email support via Resend (apps with user accounts)")
@click.option(
    "--auto-approve-users/--no-auto-approve-users",
    default=None,
    help="New signups are active without admin approval",
)
@click.option("--admin-email", default=None, help="Admin account seeds.py creates; required for an app with user accounts")
@click.option(
    "--sign-in",
    "sign_in",
    type=click.Choice(["google", "email"]),
    default=None,
    help="How people sign in: google (default), or email sign-in links, which need no Google Cloud project",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Print the result as one JSON object instead of the next steps, and never prompt",
)
@click.option(
    "--files-only",
    is_flag=True,
    help="Write the project's files and nothing else: no database, git, venv, npm or migration",
)
def new(
    name: str,
    no_prompt: bool,
    app_type: str,
    database: str,
    db_name: str,
    jobs: bool,
    cache: bool,
    storage: bool,
    email: bool,
    auto_approve_users: bool,
    admin_email: str,
    sign_in: str,
    as_json: bool,
    files_only: bool,
):
    """Create a new Feather project.

    NAME is the name of the project directory to create.

    Every prompt has a flag, so the command runs without a terminal once the
    flags answer the questions the chosen app type needs:

    \b
        feather new shop --app-type single-tenant --database postgresql \\
            --jobs --cache --storage --no-email --no-auto-approve-users \\
            --admin-email you@example.com --json
    """
    project_path = (Path.cwd() / name).resolve()

    # A directory holding only dotfiles is a fresh clone (just .git), which is
    # what a platform scaffolding into its own repository has. Anything else
    # is someone's work, and is never written over.
    fresh_clone = project_path.is_dir() and all(p.name.startswith(".") for p in project_path.iterdir())
    if project_path.exists() and not (files_only and fresh_clone):
        raise click.ClickException(f"Directory '{name}' already exists")
    if name in (".", "./"):
        name = project_path.name

    given = {
        "app_type": app_type,
        "database": database,
        "db_name": db_name,
        "jobs": jobs,
        "cache": cache,
        "storage": storage,
        "email": email,
        "auto_approve_users": auto_approve_users,
        "admin_email": admin_email,
        "sign_in": sign_in,
    }
    _validate_flags(given)

    # A caller reading JSON off stdout has no terminal to answer a prompt on.
    options = _resolve_options(name, given, no_prompt or as_json)

    with _quiet(as_json):
        migrated = _build_project(project_path, name, options, files_only=files_only)

    if as_json:
        click.echo(json.dumps(_result(project_path, name, options, migrated)))
        return

    _print_next_steps(name, options, migrated)


def _build_project(project_path: Path, name: str, options: dict, files_only: bool = False) -> bool:
    """Create the project on disk. Returns whether the first migration ran.

    ``files_only`` writes the project's files and stops. It is for a caller
    that installs and migrates somewhere else: a platform that scaffolds on one
    machine and runs the app on another has no database, git identity or Node
    where the files are written, and needs none of them there.
    """
    if files_only:
        if options["database"] == "sqlite":
            options["db_url"] = "sqlite:///app.db"
        elif options["database"] == "none":
            options["db_url"] = None
        click.echo(f"Creating new Feather project: {name}")
        _create_project_structure(project_path, database=options["database"], include_auth=options.get("include_auth", False))
        _create_project_files(project_path, name, **options)
        return False

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

    # The first migration, so the app is deployable straight from the repo.
    return options["database"] != "none" and _create_initial_migration(project_path)


def _print_next_steps(name: str, options: dict, migrated: bool):
    """The closing text a person reads: what to run, and what it needs."""
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
        if migrated:
            click.echo("  3. python seeds.py")
            click.echo("  4. feather dev")
            click.echo()
            click.echo("Or run it all at once:")
            click.echo(f"  cd {name} && source venv/bin/activate && python seeds.py && feather dev")
        else:
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
    elif migrated:
        # Has database, and its first migration is already applied
        click.echo("  3. feather dev")
        click.echo()
        click.echo("Or run it all at once:")
        click.echo(f"  cd {name} && source venv/bin/activate && feather dev")
    else:
        # Has database but no migration yet
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
    sign_in: str = "google",  # "google", or "email" for sign-in links
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
        sign_in: How people sign in, "google" or "email"
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
        "sign_in": sign_in or "google",
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


def _venv_python(project_path: Path) -> Path:
    """The scaffolded project's own interpreter."""
    if sys.platform == "win32":
        return project_path / "venv" / "Scripts" / "python.exe"
    return project_path / "venv" / "bin" / "python"


def _create_initial_migration(project_path: Path) -> bool:
    """Generate the project's first migration and apply it.

    Without this, migrations/versions stays empty. Git does not track an empty
    directory, so the app reaches a server with no migrations, `feather db
    upgrade` has nothing to apply, and the app starts against an empty
    database. Needs the database to be reachable; when it isn't, the caller
    prints the two commands instead.
    """
    python = _venv_python(project_path)
    if not python.exists():
        return False
    steps = (
        (["-m", "flask", "db", "migrate", "-m", "Initial migration"], "  Generated migrations/versions"),
        (["-m", "flask", "db", "upgrade"], "  Applied it to the database"),
    )
    for args, done in steps:
        result = subprocess.run(
            [str(python), *args], cwd=project_path, capture_output=True, text=True
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            click.echo(f"  Could not create the first migration ({detail[-1][:120] if detail else 'unknown error'})")
            return False
        click.echo(done)
    return True


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

