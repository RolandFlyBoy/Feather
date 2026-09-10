"""feather build/start - Production commands."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

from feather.cli._templates_link import LINK_NAME, ensure_templates_link


def refresh_templates_link(quiet: bool = False) -> None:
    """Point ``.feather-templates`` at the installed package's templates.

    Tailwind scans that path (``static/css/app.css`` lists it as a
    ``@source``) for the class names Feather's own components use. Without
    it the production CSS silently lacks every framework component style.
    """
    status, detail = ensure_templates_link(Path.cwd())

    if status == "error":
        click.echo(
            click.style(
                f"Warning: {detail}\n"
                "Tailwind will not see Feather's component classes.",
                fg="yellow",
            ),
            err=True,
        )
    elif status == "directory" and not quiet:
        click.echo(f"  {LINK_NAME} is a real directory; leaving it alone")
    elif status in ("created", "updated") and not quiet:
        click.echo(f"  {LINK_NAME} -> {detail}")


@click.command()
def build():
    """Build the application for production.

    This runs Vite build to minify and hash CSS/JS assets.
    """
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    click.echo(click.style("Building for production...", fg="cyan", bold=True))
    click.echo()

    refresh_templates_link()

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


def _run_security_check() -> dict:
    """Run the security audit in-process and return its result dict."""
    from feather.cli.security_check import run_checks

    return run_checks(Path.cwd(), env_file=None, force_production=True)


@click.command()
@click.option(
    "--port", envvar="PORT", default=8000, type=int, show_default=True,
    help="Port to run the server on (env: PORT)",
)
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option(
    "--workers", envvar="WEB_CONCURRENCY", default=4, type=int, show_default=True,
    help="Number of worker processes (env: WEB_CONCURRENCY)",
)
@click.option(
    "--worker-class", "worker_class",
    default="sync",
    type=click.Choice(["sync", "gthread", "gevent", "uvicorn.workers.UvicornWorker"]),
    help="Worker class (sync, gthread, gevent, or uvicorn)"
)
@click.option("--threads", default=None, type=int, help="Threads per worker (gthread)")
@click.option("--timeout", default=30, help="Worker timeout in seconds")
@click.option("--keep-alive", "keep_alive", default=5, help="Keep-alive timeout in seconds")
@click.option(
    "--graceful-timeout", "graceful_timeout", default=30,
    help="Seconds to let a worker finish in-flight requests after SIGTERM",
)
@click.option("--max-requests", "max_requests", default=1000, help="Max requests per worker before restart")
@click.option("--preload/--no-preload", default=False, help="Preload application code")
@click.option(
    "--skip-security-check", "skip_security_check", is_flag=True,
    help="Start even if `feather security-check` reports a failure.",
)
def start(
    port: int,
    host: str,
    workers: int,
    worker_class: str,
    threads: int,
    timeout: int,
    keep_alive: int,
    graceful_timeout: int,
    max_requests: int,
    preload: bool,
    skip_security_check: bool,
):
    """Start the production server using Gunicorn.

    ``PORT`` and ``WEB_CONCURRENCY`` are read from the environment, which is
    how the generated Dockerfile and docker-compose.yml configure the web
    container. Explicit flags win over both.

    The production security audit (``feather security-check``) runs first and
    a FAIL refuses to start; ``--skip-security-check`` overrides that.

    Gunicorn replaces this process (``execvp``) so it is PID 1 in a
    container and receives ``docker stop``'s SIGTERM directly.

    \b
    Examples:
      feather start                                         Basic start
      feather start --workers 8 --worker-class gevent       Async workers
      feather start --worker-class gthread --threads 4      Threaded workers
      feather start --timeout 120                           Long requests
      feather start --max-requests 500                      Memory optimization
      feather start --graceful-timeout 60                   Slow shutdown drain
    """
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    # Gunicorn is about to serve production traffic, so audit against
    # production rules regardless of what FLASK_ENV happens to say.
    os.environ["FLASK_ENV"] = "production"

    if skip_security_check:
        click.echo(click.style("Skipping the security check (--skip-security-check)", fg="yellow"))
    else:
        result = _run_security_check()
        failures = [c for c in result["checks"] if c["status"] == "FAIL"]
        if failures:
            lines = "\n".join(
                f"  FAIL  {c['name']}: {c['message']}"
                + (f"\n        remedy: {c['remedy']}" if c["remedy"] else "")
                for c in failures
            )
            raise click.ClickException(
                "Refusing to start: the production security check failed.\n"
                f"{lines}\n"
                "Run `feather security-check` for the full report, or start with "
                "--skip-security-check once you have accepted the risk."
            )
        summary = result["summary"]
        click.echo(
            click.style(
                f"Security check: {summary['pass']} passed, {summary['warn']} warnings",
                fg="green",
            )
        )

    click.echo(click.style(f"Starting production server on {host}:{port}", fg="cyan", bold=True))
    click.echo(f"Workers: {workers} ({worker_class})")
    click.echo(f"Timeout: {timeout}s | Keep-alive: {keep_alive}s | Graceful: {graceful_timeout}s")
    click.echo()

    cmd = [
        "gunicorn",
        "app:app",
        "--bind", f"{host}:{port}",
        "--workers", str(workers),
        "--worker-class", worker_class,
        "--timeout", str(timeout),
        "--keep-alive", str(keep_alive),
        "--graceful-timeout", str(graceful_timeout),
        "--max-requests", str(max_requests),
        "--max-requests-jitter", str(max(1, max_requests // 10)),  # avoid a thundering herd
        "--access-logfile", "-",
        "--error-logfile", "-",
    ]

    if threads:
        cmd += ["--threads", str(threads)]

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

    if shutil.which("gunicorn") is None:
        raise click.ClickException(
            "Gunicorn not found. Install it with: "
            "pip install 'feather-framework[prod]' (or: pip install gunicorn)"
        )

    # Replace this process. In a container that makes gunicorn PID 1, so
    # `docker stop` delivers SIGTERM to gunicorn itself and the graceful
    # shutdown above actually happens instead of the runtime killing a
    # click wrapper after ten seconds.
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        os.execvp(cmd[0], cmd)
    except OSError as exc:  # pragma: no cover - execvp only returns on failure
        raise click.ClickException(f"Could not start gunicorn: {exc}")
