"""feather dev - Run development server with Vite HMR."""

import os
import subprocess
import sys
import time
from pathlib import Path

import click


@click.command()
@click.option("--port", default=5000, help="Flask port (Vite proxies to this)")
@click.option("--host", default="127.0.0.1", help="Host to bind Flask to")
@click.option("--no-vite", is_flag=True, help="Run Flask only without Vite")
def dev(port: int, host: str, no_vite: bool):
    """Run the development server with Vite HMR.

    Vite serves as the main development server with hot module replacement.
    Flask runs in the background, and Vite proxies requests to it.

    Open http://localhost:5173 in your browser.
    """
    # Check we're in a Feather project
    if not Path("app.py").exists():
        raise click.ClickException(
            "Not in a Feather project directory. Run this from your project root."
        )

    click.echo(click.style("Starting Feather development server...", fg="cyan", bold=True))
    click.echo()

    env = os.environ.copy()
    env["FLASK_ENV"] = "development"
    # Let FLASK_DEBUG come from .env (Flask loads it automatically)
    # If not set, Flask defaults to debug mode in development

    flask_cmd = [sys.executable, "-m", "flask", "run", "--host", host, "--port", str(port)]

    processes = []

    try:
        if no_vite or not Path("package.json").exists():
            # No Vite mode - Flask runs directly in foreground
            click.echo(click.style(f"  Server running at http://{host}:{port}", fg="green", bold=True))
            click.echo("  Press Ctrl+C to stop")
            click.echo()

            flask_process = subprocess.Popen(flask_cmd, env=env)
            processes.append(("Flask", flask_process))
            flask_process.wait()
        else:
            # Vite mode - Flask in background, Vite in foreground
            click.echo("  Starting Flask server...")
            flask_process = subprocess.Popen(flask_cmd, env=env)
            processes.append(("Flask", flask_process))

            # Wait for Flask to be ready
            time.sleep(1.5)

            # Check Flask is running
            if flask_process.poll() is not None:
                raise click.ClickException("Flask failed to start.")

            click.echo()
            click.echo(click.style("  Open http://localhost:5173 in your browser", fg="green", bold=True))
            click.echo()
            click.echo("  Vite serves assets with HMR (instant updates)")
            click.echo("  Flask runs in background (proxied by Vite)")
            click.echo("  Template changes trigger automatic reload")
            click.echo()
            click.echo("  Press Ctrl+C to stop")
            click.echo()

            # Start Vite in foreground (user-facing)
            vite_process = subprocess.Popen(["npm", "run", "dev"])
            processes.append(("Vite", vite_process))

            # Wait for Vite
            vite_process.wait()

    except KeyboardInterrupt:
        click.echo()
        click.echo("Shutting down...")

    finally:
        # Clean up all processes
        for name, process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                click.echo(f"  Stopped {name}")

        click.echo("Goodbye!")
