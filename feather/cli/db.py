"""feather db - Database management commands."""

import subprocess
import sys
from pathlib import Path

import click


def _run_streaming(cmd: list, failure_message: str) -> int:
    """Run a subprocess with its output streamed to the terminal.

    Alembic/Flask-Migrate print progress as they work; capturing it would hide
    everything until the command finished (and hide it entirely on success).

    Args:
        cmd: Command to run.
        failure_message: Message for the ClickException raised on failure.

    Returns:
        The process exit code (0 on success).

    Raises:
        click.ClickException: If the command exits non-zero.
    """
    result = subprocess.run(cmd)

    if result.returncode != 0:
        click.echo(
            click.style(
                f"Command failed (exit code {result.returncode}): {' '.join(str(c) for c in cmd)}",
                fg="red",
            )
        )
        raise click.ClickException(failure_message)

    return result.returncode


@click.group(name="db")
def db_group():
    """Database management commands."""
    pass


@db_group.command()
def init():
    """Initialize the migrations directory."""
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    click.echo("Initializing migrations...")

    _run_streaming(
        [sys.executable, "-m", "flask", "db", "init"],
        "Failed to initialize migrations",
    )

    click.echo(click.style("Migrations initialized!", fg="green"))


@db_group.command()
@click.option("-m", "--message", default=None, help="Migration message")
def migrate(message: str):
    """Generate a new migration from model changes."""
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    click.echo("Generating migration...")

    cmd = [sys.executable, "-m", "flask", "db", "migrate"]
    if message:
        cmd.extend(["-m", message])

    _run_streaming(cmd, "Failed to generate migration")

    click.echo(click.style("Migration generated!", fg="green"))
    click.echo("Run 'feather db upgrade' to apply it.")


@db_group.command()
def upgrade():
    """Apply pending migrations."""
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    click.echo("Applying migrations...")

    _run_streaming(
        [sys.executable, "-m", "flask", "db", "upgrade"],
        "Failed to apply migrations",
    )

    click.echo(click.style("Migrations applied!", fg="green"))


@db_group.command()
def downgrade():
    """Rollback the last migration."""
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    click.echo("Rolling back migration...")

    _run_streaming(
        [sys.executable, "-m", "flask", "db", "downgrade"],
        "Failed to rollback migration",
    )

    click.echo(click.style("Migration rolled back!", fg="green"))


@db_group.command()
@click.option("--extra-only", is_flag=True, help="Run only extra seed files from seeds/ directory")
def seed(extra_only):
    """Run database seed data.

    Runs seeds.py first, then any .py files in seeds/ directory (alphabetically).
    Use --extra-only to skip seeds.py and only run seeds/ directory files.
    """
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    seed_file = Path("seeds.py")
    seeds_dir = Path("seeds")

    if not seed_file.exists() and not seeds_dir.exists():
        raise click.ClickException(
            "No seeds.py file or seeds/ directory found. Create one with your seed data."
        )

    # Run main seeds.py
    if seed_file.exists() and not extra_only:
        click.echo("Running seeds.py...")

        _run_streaming([sys.executable, "seeds.py"], "Failed to run seeds.py")

    # Run extra seed files from seeds/ directory
    if seeds_dir.exists():
        seed_files = sorted(
            f for f in seeds_dir.glob("*.py") if not f.name.startswith("_")
        )
        for sf in seed_files:
            click.echo(f"Running {sf}...")

            _run_streaming([sys.executable, str(sf)], f"Failed to run {sf}")

    click.echo(click.style("Seed data applied!", fg="green"))
