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
def seed():
    """Run database seed data."""
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    seed_file = Path("seeds.py")
    if not seed_file.exists():
        raise click.ClickException("No seeds.py file found. Create one with your seed data.")

    click.echo("Running seed data...")

    result = subprocess.run(
        [sys.executable, "seeds.py"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        click.echo(result.stdout)
        click.echo(click.style("Seed data applied!", fg="green"))
    else:
        if result.stdout:
            click.echo(result.stdout)
        if result.stderr:
            click.echo(result.stderr)
        raise click.ClickException("Failed to run seed data")
