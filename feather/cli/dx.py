"""feather routes/shell/test - Developer experience commands."""

import os
import subprocess
import sys
from pathlib import Path

import click


def _get_app():
    """Import and return the Flask app from the current directory."""
    # Add current directory to path
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())

    try:
        from app import app
        return app
    except ImportError as e:
        raise click.ClickException(
            f"Could not import app: {e}\n"
            "Make sure you're in a Feather project directory with app.py"
        )


@click.command()
@click.option("--method", "-m", default=None, help="Filter by HTTP method (GET, POST, etc.)")
@click.option("--path", "-p", default=None, help="Filter by path pattern")
def routes(method: str, path: str):
    """List all registered routes.

    Shows all URL routes registered in the application along with their
    HTTP methods and endpoint names.

    \b
    Examples:
      feather routes           List all routes
      feather routes -m POST   Filter by HTTP method
      feather routes -p /api   Filter by path pattern
    """
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    app = _get_app()

    click.echo(click.style("\nRegistered Routes", fg="cyan", bold=True))
    click.echo(click.style("=" * 70, fg="cyan"))
    click.echo()

    # Collect and sort routes
    route_list = []
    for rule in app.url_map.iter_rules():
        # Skip static endpoint
        if rule.endpoint == "static":
            continue

        methods = ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
        endpoint = rule.endpoint
        rule_path = rule.rule

        # Apply filters
        if method and method.upper() not in methods:
            continue
        if path and path not in rule_path:
            continue

        route_list.append((methods, rule_path, endpoint))

    # Sort by path
    route_list.sort(key=lambda x: x[1])

    if not route_list:
        click.echo("No routes found matching your filters.")
        return

    # Calculate column widths
    method_width = max(len(r[0]) for r in route_list)
    path_width = max(len(r[1]) for r in route_list)

    # Print header
    header = f"{'METHOD':<{method_width}}  {'PATH':<{path_width}}  ENDPOINT"
    click.echo(click.style(header, fg="white", bold=True))
    click.echo("-" * 70)

    # Print routes with color coding
    for methods, rule_path, endpoint in route_list:
        # Color code by method
        if "POST" in methods or "PUT" in methods or "PATCH" in methods:
            method_color = "yellow"
        elif "DELETE" in methods:
            method_color = "red"
        else:
            method_color = "green"

        method_str = click.style(f"{methods:<{method_width}}", fg=method_color)
        path_str = f"{rule_path:<{path_width}}"
        endpoint_str = click.style(endpoint, fg="blue")

        click.echo(f"{method_str}  {path_str}  {endpoint_str}")

    click.echo()
    click.echo(f"Total: {len(route_list)} routes")


@click.command()
def shell():
    """Start an interactive Python shell with app context.

    Launches IPython (if available) or the standard Python shell with
    the Flask application context active and common imports pre-loaded.

    Available variables:
        app     - Flask application instance
        db      - SQLAlchemy database instance
        Models are auto-imported from your models/ directory
    """
    if not Path("app.py").exists():
        raise click.ClickException("Not in a Feather project directory.")

    app = _get_app()

    # Build context with useful imports
    ctx = {"app": app}

    # Try to import db
    try:
        from feather.db import db
        ctx["db"] = db
    except ImportError:
        pass

    # Auto-import models
    models_dir = Path("models")
    if models_dir.exists():
        import importlib
        for model_file in models_dir.glob("*.py"):
            if model_file.name.startswith("_"):
                continue
            module_name = f"models.{model_file.stem}"
            try:
                module = importlib.import_module(module_name)
                # Import all public classes (likely models)
                for name in dir(module):
                    if not name.startswith("_"):
                        obj = getattr(module, name)
                        if isinstance(obj, type):
                            ctx[name] = obj
            except ImportError:
                pass

    # Print banner
    click.echo(click.style("\nFeather Interactive Shell", fg="cyan", bold=True))
    click.echo(click.style("=" * 40, fg="cyan"))
    click.echo()
    click.echo("Available variables:")
    for name in sorted(ctx.keys()):
        click.echo(f"  {click.style(name, fg='green')}: {type(ctx[name]).__name__}")
    click.echo()

    # Push app context
    with app.app_context():
        # Try IPython first
        try:
            from IPython import embed
            embed(user_ns=ctx, colors="neutral")
        except ImportError:
            # Fall back to standard Python shell
            import code
            code.interact(local=ctx, banner="")


def _find_feather_root() -> Path | None:
    """Find the Feather framework root directory by looking for setup.py/pyproject.toml with feather."""
    current = Path.cwd()

    # Check if we're in the Feather framework directory
    pyproject = current / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        if "feather-framework" in content or 'name = "feather"' in content:
            return current

    # Check parent directories (in case we're in a subdirectory)
    for parent in current.parents:
        pyproject = parent / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text()
            if "feather-framework" in content or 'name = "feather"' in content:
                return parent

    return None


def _clean_test_artifacts(root: Path, include_venv: bool = False):
    """Remove test artifacts from a directory."""
    import shutil

    artifacts = [
        ".pytest_cache",
        ".coverage",
        "htmlcov",
        ".ruff_cache",
        "feather_framework.egg-info",
    ]

    removed = []

    # Remove top-level artifacts
    for artifact in artifacts:
        artifact_path = root / artifact
        if artifact_path.exists():
            if artifact_path.is_dir():
                shutil.rmtree(artifact_path)
            else:
                artifact_path.unlink()
            removed.append(artifact)

    # Remove all __pycache__ directories
    pycache_count = 0
    for pycache in root.rglob("__pycache__"):
        if pycache.exists():
            shutil.rmtree(pycache)
            pycache_count += 1
    if pycache_count:
        removed.append(f"__pycache__ ({pycache_count} dirs)")

    # Remove .pyc files
    pyc_count = 0
    for pyc in root.rglob("*.pyc"):
        pyc.unlink()
        pyc_count += 1
    if pyc_count:
        removed.append(f"*.pyc ({pyc_count} files)")

    # Optionally remove venv
    if include_venv:
        venv_path = root / "venv"
        if venv_path.exists():
            shutil.rmtree(venv_path)
            removed.append("venv")

    return removed


@click.command()
@click.option("--coverage/--no-coverage", default=True, help="Run with coverage reporting")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--path", "-p", default="tests", help="Test path or file")
@click.option("--framework", "-f", is_flag=True, help="Run Feather framework tests")
@click.option("--clean", "-c", is_flag=True, help="Clean test artifacts (venv, .coverage, cache)")
@click.option(
    "--marker", "-m",
    type=click.Choice(["unit", "integration", "e2e", "scaffolding", "jobs", "api_contract", "all"]),
    default="all",
    help="Run tests by marker (framework tests only)"
)
@click.option("--fast", is_flag=True, help="Skip slow tests (e2e, scaffolding)")
@click.option("--list-markers", is_flag=True, help="List available test markers")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def test(
    coverage: bool,
    verbose: bool,
    path: str,
    framework: bool,
    clean: bool,
    marker: str,
    fast: bool,
    list_markers: bool,
    args: tuple
):
    """Run tests with pytest.

    Runs the test suite using pytest. By default, includes coverage reporting.

    \b
    Examples:
      feather test                      Run all project tests
      feather test -v                   Verbose output
      feather test --no-coverage        Skip coverage reporting
      feather test -p tests/test_api.py Run specific test file
      feather test -- -k "test_user"    Pass args to pytest
      feather test --framework          Run Feather framework tests
      feather test --framework --clean  Clean test artifacts

    \b
    Framework test markers:
      feather test -f -m unit           Fast isolated tests (no I/O)
      feather test -f -m integration    Component integration tests
      feather test -f -m e2e            End-to-end workflow tests
      feather test -f -m scaffolding    CLI scaffolding tests
      feather test -f -m jobs           Background job tests
      feather test -f -m api_contract   Public API contract tests
      feather test -f --fast            Skip slow tests (e2e, scaffolding)
      feather test -f --list-markers    Show all available markers
    """
    if list_markers:
        click.echo(click.style("\nAvailable test markers:", fg="cyan", bold=True))
        click.echo()
        markers = [
            ("unit", "Fast isolated tests (< 10ms, no I/O)"),
            ("integration", "Component integration tests (< 500ms, may use test DB)"),
            ("e2e", "End-to-end workflow tests (full workflows)"),
            ("scaffolding", "CLI generation tests"),
            ("jobs", "Background job tests"),
            ("api_contract", "Public API contract tests (breaking change detection)"),
        ]
        for name, desc in markers:
            click.echo(f"  {click.style(name, fg='green'):20} {desc}")
        click.echo()
        click.echo("Run with: feather test --framework -m <marker>")
        return
    if clean:
        # Clean mode - remove artifacts and exit
        if framework:
            root = _find_feather_root()
            if not root:
                raise click.ClickException("Not in the Feather framework directory.")
            click.echo(click.style("\nCleaning framework test artifacts...", fg="cyan", bold=True))
        else:
            if not Path("app.py").exists():
                raise click.ClickException("Not in a Feather project directory.")
            root = Path.cwd()
            click.echo(click.style("\nCleaning project test artifacts...", fg="cyan", bold=True))

        removed = _clean_test_artifacts(root, include_venv=framework)

        if removed:
            for item in removed:
                click.echo(f"  Removed: {click.style(item, fg='yellow')}")
            click.echo(click.style("\nClean complete!", fg="green"))
        else:
            click.echo("  Nothing to clean.")
        return

    if framework:
        # Running framework tests
        feather_root = _find_feather_root()
        if not feather_root:
            raise click.ClickException(
                "Not in the Feather framework directory.\n"
                "Run this from the Feather repo root, or use 'feather test' without --framework for project tests."
            )

        click.echo(click.style("\nRunning Feather framework tests...", fg="cyan", bold=True))
        click.echo(f"  Framework root: {feather_root}")

        # Check for venv and pytest availability
        venv_path = feather_root / "venv"
        venv_python = venv_path / "bin" / "python"
        venv_pytest = venv_path / "bin" / "pytest"

        # Determine which pytest to use
        pytest_cmd = None
        created_venv = False

        if venv_pytest.exists():
            # Use existing venv's pytest
            pytest_cmd = str(venv_pytest)
            click.echo(f"  Using venv: {venv_path}")
        else:
            # Check if pytest is available globally
            try:
                subprocess.run(["pytest", "--version"], capture_output=True, check=True)
                pytest_cmd = "pytest"
                click.echo("  Using system pytest")
            except (FileNotFoundError, subprocess.CalledProcessError):
                # No pytest available - create venv and install deps
                click.echo("  No pytest found. Setting up test environment...")
                click.echo()

                # Create venv
                click.echo("  Creating virtual environment...")
                subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)

                # Install dev dependencies
                click.echo("  Installing dev dependencies...")
                pip_cmd = str(venv_path / "bin" / "pip")
                result = subprocess.run(
                    [pip_cmd, "install", "-e", ".[dev]"],
                    cwd=feather_root,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    click.echo(click.style(f"  Failed to install: {result.stderr}", fg="red"))
                    sys.exit(1)

                pytest_cmd = str(venv_pytest)
                created_venv = True
                click.echo(click.style("  Environment ready!", fg="green"))

        click.echo()

        # Build pytest command
        test_path = feather_root / path
        cmd = [pytest_cmd, str(test_path)]

        if verbose:
            cmd.append("-v")

        if coverage:
            cmd.extend([f"--cov={feather_root / 'feather'}", "--cov-report=term-missing"])

        # Add marker filtering
        if fast:
            # Skip slow tests
            cmd.extend(["-m", "not e2e and not scaffolding"])
            click.echo(click.style("  Mode: fast (skipping e2e and scaffolding)", fg="yellow"))
        elif marker != "all":
            cmd.extend(["-m", marker])
            click.echo(click.style(f"  Marker: {marker}", fg="yellow"))

        cmd.extend(args)

        result = subprocess.run(cmd, cwd=feather_root)

        # Clean up test artifacts
        import shutil
        for cleanup_dir in [".pytest_cache", "__pycache__"]:
            cleanup_path = feather_root / cleanup_dir
            if cleanup_path.exists():
                shutil.rmtree(cleanup_path)

        # Clean up __pycache__ in subdirectories
        for pycache in feather_root.rglob("__pycache__"):
            if pycache.exists():
                shutil.rmtree(pycache)

        sys.exit(result.returncode)
    else:
        # Running project tests
        if not Path("app.py").exists():
            raise click.ClickException("Not in a Feather project directory.")

        click.echo(click.style("\nRunning tests...", fg="cyan", bold=True))
        click.echo()

        # Build pytest command
        cmd = ["pytest", path]

        if verbose:
            cmd.append("-v")

        if coverage:
            cmd.extend(["--cov=.", "--cov-report=term-missing"])

        # Add any extra args passed after --
        cmd.extend(args)

        try:
            result = subprocess.run(cmd)
            sys.exit(result.returncode)
        except FileNotFoundError:
            raise click.ClickException(
                "pytest not found. Install it with: pip install pytest pytest-cov"
            )
