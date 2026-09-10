"""feather docker - Generate the Docker deployment layout for a project.

Feather deploys as containers on a host you control: Caddy terminates TLS,
``web`` runs gunicorn, ``worker`` runs background jobs, Postgres and Valkey
sit on the internal compose network. ``feather new`` writes these files for
new projects; ``feather docker init`` adds them to an existing one.

The file bodies live in :mod:`feather.cli._docker_templates` so both paths
generate exactly the same thing.
"""

import re
from pathlib import Path

import click

from feather.cli._docker_templates import (
    HEALTH_PATH,
    docker_files,
    slugify,
    write_docker_files,
)


def _read_text(path: Path) -> str:
    """Return a file's text, or '' when it is missing or unreadable."""
    try:
        return path.read_text()
    except OSError:
        return ""


def detect_features(project_path: Path) -> dict:
    """Guess which services this project needs from what is in it.

    Looks at ``.env``, ``config.py``, ``worker.py`` and the ``models``
    directory. Every value can be overridden by a CLI flag.

    Returns:
        ``{"database": bool, "redis": bool, "worker": bool}``
    """
    env_text = _read_text(project_path / ".env")
    config_text = _read_text(project_path / "config.py")
    haystack = env_text + "\n" + config_text

    database = bool(
        re.search(r"\bDATABASE_URL\b", haystack)
        or re.search(r"\bSQLALCHEMY_DATABASE_URI\b", haystack)
        or (project_path / "models").is_dir()
        or (project_path / "migrations").is_dir()
    )

    redis = bool(
        re.search(r"\bREDIS_URL\b", haystack)
        or re.search(r"CACHE_BACKEND\s*[=:]\s*[\"']?redis", haystack)
        or re.search(r"\bCACHE_URL\b", haystack)
    )

    worker = bool(
        re.search(r"\bJOB_BACKEND\b", haystack)
        or (project_path / "worker.py").exists()
        or (project_path / "jobs").is_dir()
    )
    if worker:
        # A worker container is only useful with Redis behind it.
        redis = True

    return {"database": database, "redis": redis, "worker": worker}


@click.group()
def docker():
    """Generate and inspect the Docker deployment layout.

    \b
    Commands:
      init    Write the Dockerfile, compose files and deploy scripts
    """


@docker.command()
@click.option("--force", is_flag=True, help="Overwrite files that already exist.")
@click.option(
    "--worker/--no-worker",
    "worker",
    default=None,
    help="Include (or omit) the background-job worker service. "
    "Detected from the project when not given.",
)
@click.option(
    "--domain", default=None, help="Public hostname, written into .env.example as DOMAIN."
)
@click.option(
    "--name",
    "-n",
    default=None,
    help="Application name used in comments and as the compose project name "
    "(default: the directory name).",
)
@click.option(
    "--path",
    "project_path",
    default=".",
    help="Project directory to write into (default: the current directory).",
)
def init(force: bool, worker, domain: str, name: str, project_path: str):
    """Write the Docker deployment files into this project.

    \b
    Creates:
      Dockerfile              Multi-stage build (base / frontend / worker / web)
      .dockerignore           Keeps secrets and build output out of the image
      docker-compose.yml      Production: caddy, web, worker, db, redis
      docker-compose.dev.yml  Local Postgres and Valkey for `feather dev`
      deploy/Caddyfile        TLS termination and the proxy header contract
      deploy/deploy.sh        Build, migrate once, swap containers, gate on health
      deploy/backup.sh        Nightly pg_dump, for cron
      .env.example            Every key this app reads, and who supplies it

    Existing files are never overwritten without --force.

    \b
    Examples:
      feather docker init
      feather docker init --domain app.example.com
      feather docker init --no-worker
      feather docker init --force
    """
    project = Path(project_path).resolve()

    if not (project / "app.py").exists():
        raise click.ClickException(
            "Not in a Feather project directory. "
            "Run this command from the root of your project (where app.py is)."
        )

    app_name = name or project.name
    detected = detect_features(project)
    if worker is not None:
        detected["worker"] = worker
        if worker:
            detected["redis"] = True

    files = docker_files(
        app_name,
        app_slug=slugify(app_name),
        database=detected["database"],
        redis=detected["redis"],
        worker=detected["worker"],
        domain=domain,
        base_env=_read_text(project / ".env") or None,
    )
    results = write_docker_files(project, files, force=force)

    click.echo(click.style(f"Docker deployment files for {app_name}:", fg="cyan", bold=True))
    for path, action in results:
        color = {"written": "green", "overwritten": "yellow", "skipped": "white"}[action]
        marker = {"written": "+", "overwritten": "~", "skipped": "="}[action]
        click.echo(f"  {click.style(marker, fg=color)} {path:<24} {action}")

    skipped = [path for path, action in results if action == "skipped"]
    click.echo()
    services = ", ".join(
        s for s, on in (
            ("web", True),
            ("worker", detected["worker"]),
            ("db", detected["database"]),
            ("redis", detected["redis"]),
        ) if on
    )
    click.echo(f"Services: caddy, {services}")
    if skipped:
        click.echo(
            click.style(
                f"{len(skipped)} file(s) already existed and were left alone. "
                "Re-run with --force to replace them.",
                fg="yellow",
            )
        )

    click.echo()
    click.echo("Next steps:")
    click.echo("  1. cp .env.example .env  and fill in SECRET_KEY, DOMAIN, POSTGRES_PASSWORD")
    click.echo("  2. Add .feather-templates to .gitignore, and make sure")
    click.echo('     static/css/app.css scans "../../.feather-templates/**/*.html"')
    click.echo("  3. Commit package-lock.json so the image build can use `npm ci`")
    click.echo("  4. Point DNS at the host, then run ./deploy/deploy.sh")
    click.echo()
    click.echo(f"Health endpoint used by every generated check: {HEALTH_PATH}")
