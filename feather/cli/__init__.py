"""Feather CLI - Command line interface for Feather framework."""

import click

from feather.cli.new import new
from feather.cli.dev import dev
from feather.cli.db import db_group
from feather.cli.generate import generate
from feather.cli.build import build, start
from feather.cli.deploy import deploy
from feather.cli.dx import routes, shell, test
from feather.cli.platform_admin import platform_admin
from feather.cli.jobs import jobs


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


@click.group(cls=FeatherGroup)
@click.version_option(package_name="feather-framework")
def cli():
    pass


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
cli.add_command(platform_admin)


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
