"""feather build/start - Production commands."""

import os
import subprocess
import sys
from pathlib import Path

import click


@click.command()
def build():
    """Build the application for production.

    This runs Vite build to minify and hash CSS/JS assets.
    """
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    click.echo(click.style("Building for production...", fg="cyan", bold=True))
    click.echo()

    # Run Vite build
    if Path("package.json").exists():
        click.echo("Building CSS/JS assets...")
        result = subprocess.run(
            ["npm", "run", "build"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            click.echo(result.stderr)
            raise click.ClickException("Vite build failed")

        click.echo(click.style("Assets built successfully!", fg="green"))
    else:
        click.echo("No package.json found, skipping asset build")

    click.echo()
    click.echo(click.style("Build complete!", fg="green", bold=True))
    click.echo()
    click.echo("To start the production server:")
    click.echo("  feather start")


@click.command()
@click.option("--port", default=8000, help="Port to run the server on")
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--workers", default=4, help="Number of worker processes")
@click.option(
    "--worker-class", "worker_class",
    default="sync",
    type=click.Choice(["sync", "gevent", "uvicorn.workers.UvicornWorker"]),
    help="Worker class (sync, gevent, or uvicorn)"
)
@click.option("--timeout", default=30, help="Worker timeout in seconds")
@click.option("--keep-alive", "keep_alive", default=5, help="Keep-alive timeout in seconds")
@click.option("--max-requests", "max_requests", default=1000, help="Max requests per worker before restart")
@click.option("--preload/--no-preload", default=False, help="Preload application code")
def start(
    port: int,
    host: str,
    workers: int,
    worker_class: str,
    timeout: int,
    keep_alive: int,
    max_requests: int,
    preload: bool,
):
    """Start the production server using Gunicorn.

    \b
    Examples:
      feather start                                         Basic start
      feather start --workers 8 --worker-class gevent       Async workers
      feather start --worker-class uvicorn.workers.UvicornWorker  ASGI mode
      feather start --timeout 120                           Long requests
      feather start --max-requests 500                      Memory optimization
    """
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    click.echo(click.style(f"Starting production server on {host}:{port}", fg="cyan", bold=True))
    click.echo(f"Workers: {workers} ({worker_class})")
    click.echo(f"Timeout: {timeout}s | Keep-alive: {keep_alive}s")
    click.echo()

    env = os.environ.copy()
    env["FLASK_ENV"] = "production"

    cmd = [
        "gunicorn",
        "app:app",
        "--bind", f"{host}:{port}",
        "--workers", str(workers),
        "--worker-class", worker_class,
        "--timeout", str(timeout),
        "--keep-alive", str(keep_alive),
        "--max-requests", str(max_requests),
        "--max-requests-jitter", str(max_requests // 10),  # Add jitter to prevent thundering herd
        "--access-logfile", "-",
        "--error-logfile", "-",
    ]

    if preload:
        cmd.append("--preload")

    # Check for required dependencies
    if worker_class == "gevent":
        try:
            import gevent  # noqa: F401
        except ImportError:
            raise click.ClickException(
                "gevent not installed. Install with: pip install gevent"
            )
    elif worker_class == "uvicorn.workers.UvicornWorker":
        try:
            import uvicorn  # noqa: F401
        except ImportError:
            raise click.ClickException(
                "uvicorn not installed. Install with: pip install uvicorn"
            )

    try:
        subprocess.run(cmd, env=env)
    except FileNotFoundError:
        raise click.ClickException(
            "Gunicorn not found. Install it with: pip install gunicorn"
        )
    except KeyboardInterrupt:
        click.echo()
        click.echo("Server stopped")
