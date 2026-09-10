"""Feather CLI - Command line interface for Feather framework."""

import json
import os
import urllib.request

import click

from feather import __version__
from feather.cli.new import new
from feather.cli.dev import dev
from feather.cli.db import db_group
from feather.cli.generate import generate
from feather.cli.build import build, start
from feather.cli.deploy import deploy
from feather.cli.dx import routes, shell, test
from feather.cli.platform_admin import platform_admin
from feather.cli.jobs import jobs
from feather.cli.worker import worker
from feather.cli.security_check import security_check


class FeatherGroup(click.Group):
    """Custom group that shows organized help without duplicating commands."""

    def format_help(self, ctx, formatter):
        """Write the help into the formatter."""
        formatter.write_paragraph()
        formatter.write_text("Feather - A Flask-based web framework for AI-era development.")
        formatter.write_paragraph()

        # Project Commands
        formatter.write_text(click.style("Project Commands:", bold=True))
        with formatter.indentation():
            formatter.write_dl([
                ("new", "Create a new Feather project"),
                ("dev", "Run development server (Vite + Flask)"),
                ("build", "Build assets for production"),
                ("start", "Start production server (Gunicorn)"),
            ])

        formatter.write_paragraph()
        formatter.write_text(click.style("Deployment Commands:", bold=True))
        with formatter.indentation():
            formatter.write_dl([
                ("deploy render", "Generate Dockerfile, render.yaml, .dockerignore for Render.com"),
            ])

        formatter.write_paragraph()
        formatter.write_text(click.style("Development Commands:", bold=True))
        with formatter.indentation():
            formatter.write_dl([
                ("routes", "List all registered routes"),
                ("shell", "Interactive Python shell with app context"),
            ])

        formatter.write_paragraph()
        formatter.write_text(click.style("Testing Commands:", bold=True))
        with formatter.indentation():
            formatter.write_dl([
                ("test", "Run project tests with pytest"),
                ("test --framework", "Run Feather framework tests"),
                ("test --framework -v", "Verbose framework test output"),
                ("test --framework -m MARKER", "Run tests by marker (unit, integration, e2e, scaffolding, jobs)"),
                ("test --framework --fast", "Skip slow tests (e2e, scaffolding)"),
                ("test --framework --clean", "Remove test artifacts (venv, cache, etc.)"),
                ("test --list-markers", "Show available test markers"),
            ])

        formatter.write_paragraph()
        formatter.write_text(click.style("Security:", bold=True))
        with formatter.indentation():
            formatter.write_dl([
                ("security-check", "Audit production security settings (exit 1 on any FAIL)"),
                ("security-check --json", "Machine-readable audit output"),
                ("security-check --env-file FILE", "Audit an env file without importing the app"),
                ("security-check --production", "Apply production rules regardless of FLASK_ENV"),
            ])

        formatter.write_paragraph()
        formatter.write_text(click.style("Database Commands:", bold=True))
        with formatter.indentation():
            formatter.write_dl([
                ("db init", "Initialize migrations directory"),
                ("db migrate", "Generate a new migration"),
                ("db upgrade", "Apply pending migrations"),
                ("db downgrade", "Revert the last migration"),
                ("db seed", "Run seeds.py to populate data"),
            ])

        formatter.write_paragraph()
        formatter.write_text(click.style("Code Generation:", bold=True))
        with formatter.indentation():
            formatter.write_dl([
                ("generate model", "Create a SQLAlchemy model"),
                ("generate service", "Create a service class"),
                ("generate route", "Create API or page routes"),
                ("generate island", "Create a JavaScript island"),
                ("generate serializer", "Create a JSON serializer"),
            ])

        formatter.write_paragraph()
        formatter.write_text(click.style("Job Commands:", bold=True))
        with formatter.indentation():
            formatter.write_dl([
                ("jobs list", "List jobs in the queue"),
                ("jobs status", "Show queue status"),
                ("jobs info", "Show job details"),
                ("jobs failed", "List failed jobs"),
                ("jobs retry", "Retry a failed job"),
                ("jobs clear", "Clear job history"),
            ])

        formatter.write_paragraph()
        formatter.write_text(click.style("Worker Commands:", bold=True))
        with formatter.indentation():
            formatter.write_dl([
                ("worker", "Start an RQ background job worker"),
                ("worker high default low", "Process specific queues (priority order)"),
            ])

        formatter.write_paragraph()
        formatter.write_text(click.style("Admin Commands:", bold=True))
        with formatter.indentation():
            formatter.write_dl([
                ("platform-admin", "Grant/revoke platform admin status"),
            ])

        formatter.write_paragraph()
        formatter.write_text("Run 'feather COMMAND --help' for more info on a command.")

        # Options section
        formatter.write_paragraph()
        formatter.write_text(click.style("Options:", bold=True))
        with formatter.indentation():
            formatter.write_dl([
                ("--version", "Show the version and exit"),
                ("--help", "Show this message and exit"),
            ])


PYPI_JSON_URL = "https://pypi.org/pypi/feather-framework/json"
UPDATE_CHECK_TIMEOUT = 2.0

#: Commands that check PyPI for a newer release before running.
UPDATE_CHECK_COMMANDS = {"new"}


def _fetch_latest_version() -> str:
    """Return the latest feather-framework version published on PyPI.

    A single short GET; callers must handle any exception (offline, DNS
    failure, PyPI outage) themselves.
    """
    with urllib.request.urlopen(PYPI_JSON_URL, timeout=UPDATE_CHECK_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["info"]["version"]


def _version_tuple(text: str) -> tuple:
    """Comparable tuple of leading integers ('1.2.3rc1' -> (1, 2, 3))."""
    import re

    parts = []
    for chunk in re.split(r"[.\-+]", str(text)):
        match = re.match(r"^(\d+)", chunk)
        if not match:
            break
        parts.append(int(match.group(1)))
    return tuple(parts) or (0,)


def _warn_if_outdated() -> None:
    """Print a one-line notice when a newer release exists on PyPI.

    Never raises and never blocks for long: skipped entirely when
    ``FEATHER_NO_UPDATE_CHECK=1`` is set, and any network failure is
    swallowed so offline use is unaffected.
    """
    if os.environ.get("FEATHER_NO_UPDATE_CHECK", "").strip().lower() in ("1", "true", "yes", "on"):
        return

    try:
        latest = _fetch_latest_version()
        if _version_tuple(latest) > _version_tuple(__version__):
            click.echo(
                click.style(
                    f"A newer Feather is available: {__version__} -> {latest}. "
                    f"Upgrade with: pip install --upgrade feather-framework=={latest}",
                    fg="yellow",
                ),
                err=True,
            )
    except Exception:  # noqa: BLE001 - an update check must never break the CLI
        pass


def _print_version(ctx, param, value):
    """--version callback that also reports newer releases."""
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"feather-framework, version {__version__}")
    _warn_if_outdated()
    ctx.exit()


@click.group(cls=FeatherGroup)
@click.option(
    "--version",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=_print_version,
    help="Show the version and exit.",
)
@click.pass_context
def cli(ctx):
    if ctx.invoked_subcommand in UPDATE_CHECK_COMMANDS:
        _warn_if_outdated()


# Register commands
cli.add_command(new)
cli.add_command(dev)
cli.add_command(db_group, name="db")
cli.add_command(generate)
cli.add_command(build)
cli.add_command(start)
cli.add_command(deploy)
cli.add_command(routes)
cli.add_command(shell)
cli.add_command(test)
cli.add_command(jobs)
cli.add_command(worker)
cli.add_command(platform_admin)
cli.add_command(security_check)


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
