"""feather db - Database management commands."""

import subprocess
import sys
from pathlib import Path

import click


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

    result = subprocess.run(
        [sys.executable, "-m", "flask", "db", "init"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        click.echo(click.style("Migrations initialized!", fg="green"))
    else:
        if result.stdout:
            click.echo(result.stdout)
        if result.stderr:
            click.echo(result.stderr)
        raise click.ClickException("Failed to initialize migrations")


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

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        click.echo(result.stdout)
        click.echo(click.style("Migration generated!", fg="green"))
        click.echo("Run 'feather db upgrade' to apply it.")
    else:
        if result.stdout:
            click.echo(result.stdout)
        if result.stderr:
            click.echo(result.stderr)
        raise click.ClickException("Failed to generate migration")


@db_group.command()
def upgrade():
    """Apply pending migrations."""
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    click.echo("Applying migrations...")

    result = subprocess.run(
        [sys.executable, "-m", "flask", "db", "upgrade"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        click.echo(result.stdout)
        click.echo(click.style("Migrations applied!", fg="green"))
    else:
        if result.stdout:
            click.echo(result.stdout)
        if result.stderr:
            click.echo(result.stderr)
        raise click.ClickException("Failed to apply migrations")


@db_group.command()
def downgrade():
    """Rollback the last migration."""
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    click.echo("Rolling back migration...")

    result = subprocess.run(
        [sys.executable, "-m", "flask", "db", "downgrade"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        click.echo(result.stdout)
        click.echo(click.style("Migration rolled back!", fg="green"))
    else:
        if result.stdout:
            click.echo(result.stdout)
        if result.stderr:
            click.echo(result.stderr)
        raise click.ClickException("Failed to rollback migration")


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

        result = subprocess.run(
            [sys.executable, "seeds.py"],
            capture_output=True,
            text=True,
        )

        if result.stdout:
            click.echo(result.stdout)
        if result.returncode != 0:
            if result.stderr:
                click.echo(result.stderr)
            raise click.ClickException("Failed to run seeds.py")

    # Run extra seed files from seeds/ directory
    if seeds_dir.exists():
        seed_files = sorted(
            f for f in seeds_dir.glob("*.py") if not f.name.startswith("_")
        )
        for sf in seed_files:
            click.echo(f"Running {sf}...")

            result = subprocess.run(
                [sys.executable, str(sf)],
                capture_output=True,
                text=True,
            )

            if result.stdout:
                click.echo(result.stdout)
            if result.returncode != 0:
                if result.stderr:
                    click.echo(result.stderr)
                raise click.ClickException(f"Failed to run {sf}")

    click.echo(click.style("Seed data applied!", fg="green"))
