"""feather env - Inspect the environment variables a project depends on.

``feather env check`` reads ``config.py``, collects every ``os.environ``
lookup it performs, and reports which of those keys the environment actually
supplies. It is the thing both production Feather apps ended up writing by
hand, with a hard-coded ``REQUIRED_VARS`` list that drifted from config.py.

A key is *required* when config.py reads it with no fallback
(``os.environ["X"]`` or ``os.environ.get("X")``); it is *optional* when a
default is given (``os.environ.get("X", "...")``). Only missing required keys
fail the command.
"""

import ast
import os
from pathlib import Path
from typing import Optional

import click

from feather.cli._docker_templates import COMPOSE_HOST_KEYS, COMPOSE_PROVIDED_KEYS
from feather.cli.security_check import read_env_file

#: Keys the framework itself reads, worth reporting even when config.py
#: never mentions them.
FRAMEWORK_KEYS = ("FLASK_ENV", "FLASK_CONFIG", "FLASK_DEBUG", "SECRET_KEY")

#: Keys Feather supplies a default for, so a config.py reading them with no
#: fallback is not actually missing anything when they are unset.
FRAMEWORK_DEFAULTED = {"FLASK_ENV", "FLASK_CONFIG", "FLASK_DEBUG"}


class EnvRef:
    """One environment key referenced by the project's config."""

    def __init__(self, key: str, required: bool, default: Optional[str] = None):
        self.key = key
        self.required = required
        self.default = default

    def merge(self, other: "EnvRef") -> None:
        """Widen this reference with another sighting of the same key."""
        # If any read has no fallback, the key is effectively required.
        self.required = self.required or other.required
        if self.default is None:
            self.default = other.default


def _literal(node) -> Optional[str]:
    """Return a str/int/bool literal's text, or None if it is not one."""
    if isinstance(node, ast.Constant) and node.value is not None:
        return str(node.value)
    return None


def collect_env_refs(source: str) -> dict:
    """Return ``{key: EnvRef}`` for every os.environ access in ``source``.

    Recognises ``os.environ["X"]``, ``os.environ.get("X")``,
    ``os.environ.get("X", default)``, ``os.getenv("X")`` and
    ``os.getenv("X", default)``.
    """
    refs: dict = {}

    def add(ref: EnvRef) -> None:
        existing = refs.get(ref.key)
        if existing is None:
            refs[ref.key] = ref
        else:
            existing.merge(ref)

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise click.ClickException(f"Could not parse config.py: {exc}")

    for node in ast.walk(tree):
        # os.environ["KEY"]
        if isinstance(node, ast.Subscript):
            value = node.value
            if (
                isinstance(value, ast.Attribute)
                and value.attr == "environ"
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
            ):
                add(EnvRef(node.slice.value, required=True))
            continue

        if not isinstance(node, ast.Call) or not node.args:
            continue

        func = node.func
        is_environ_get = (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "environ"
        )
        is_getenv = isinstance(func, ast.Attribute) and func.attr == "getenv"

        if not (is_environ_get or is_getenv):
            continue

        key_node = node.args[0]
        if not (isinstance(key_node, ast.Constant) and isinstance(key_node.value, str)):
            continue

        if len(node.args) > 1:
            default = _literal(node.args[1])
            add(EnvRef(key_node.value, required=False, default=default))
        else:
            add(EnvRef(key_node.value, required=True))

    return refs


def resolve_env(project_dir: Path, env_file: Optional[str]) -> tuple:
    """Return ``(values, source_label, env_path)`` for the environment to check.

    ``env_path`` is None when no env file was found.
    """
    path = Path(env_file) if env_file else project_dir / ".env"
    if not path.is_absolute():
        path = project_dir / path

    values = {}
    if path.exists():
        values.update(read_env_file(path))
        label = str(path)
        found = path
    elif env_file:
        raise click.ClickException(f"Env file not found: {env_file}")
    else:
        label = "process environment only (no .env)"
        found = None

    # The real process environment wins, the way python-dotenv loads things.
    for key in os.environ:
        values[key] = os.environ[key]

    return values, label, found


@click.group(name="env")
def env_group():
    """Inspect the environment variables this project needs.

    \b
    Commands:
      check   Report which keys config.py reads and which are missing
    """


@env_group.command(name="check")
@click.option(
    "--env-file", default=None,
    help="Check against this env file instead of .env (e.g. a production copy).",
)
@click.option(
    "--path", "project_path", default=".",
    help="Project directory to inspect (default: the current directory).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def env_check(env_file: Optional[str], project_path: str, as_json: bool):
    """List the environment keys config.py reads and report what is missing.

    Exits 1 when a key config.py reads with no fallback is unset.

    \b
    Examples:
      feather env check                         Check .env plus the environment
      feather env check --env-file prod.env     Check a production env file
      feather env check --json                  Machine-readable output
    """
    import json as json_module

    project_dir = Path(project_path).resolve()
    config_file = project_dir / "config.py"
    if not config_file.exists():
        raise click.ClickException(
            f"No config.py in {project_dir}. Run this from your project root."
        )

    refs = collect_env_refs(config_file.read_text())
    for key in FRAMEWORK_KEYS:
        refs.setdefault(key, EnvRef(key, required=False, default=None))
    for key in FRAMEWORK_DEFAULTED:
        if key in refs:
            refs[key].required = False

    values, source_label, env_path = resolve_env(project_dir, env_file)

    rows = []
    missing_required = []
    for key in sorted(refs):
        ref = refs[key]
        present = key in values and values[key] != ""
        compose = key in COMPOSE_PROVIDED_KEYS
        if present:
            status = "set"
        elif compose:
            status = "compose supplies"
        elif ref.required:
            status = "MISSING"
            missing_required.append(key)
        elif ref.default is not None:
            status = f"unset (default: {ref.default})"
        else:
            status = "unset (optional)"
        rows.append(
            {
                "key": key,
                "required": ref.required,
                "default": ref.default,
                "present": present,
                "status": status,
            }
        )

    # Keys the environment carries that config.py never reads. Not an error -
    # the framework, an extension or a service may read them directly - but
    # a typo in .env shows up here.
    known = set(refs) | set(COMPOSE_PROVIDED_KEYS) | set(COMPOSE_HOST_KEYS)
    file_only = []
    if env_path is not None:
        file_only = sorted(k for k in read_env_file(env_path) if k not in known)

    result = {
        "ok": not missing_required,
        "source": source_label,
        "keys": rows,
        "missing": missing_required,
        "unreferenced": file_only,
    }

    if as_json:
        click.echo(json_module.dumps(result, indent=2))
    else:
        click.echo(click.style(f"Environment keys read by config.py ({source_label})", bold=True))
        click.echo()
        width = max((len(r["key"]) for r in rows), default=3)
        for row in rows:
            if row["status"] == "MISSING":
                color = "red"
            elif row["present"]:
                color = "green"
            else:
                color = "yellow"
            flag = "required" if row["required"] else "optional"
            click.echo(
                f"  {row['key']:<{width}}  {flag:<8}  "
                + click.style(row["status"], fg=color)
            )
        if file_only:
            click.echo()
            click.echo(
                click.style(
                    "Set but not read by config.py: " + ", ".join(file_only), fg="cyan"
                )
            )
        click.echo()
        if missing_required:
            click.echo(
                click.style(
                    f"{len(missing_required)} required key(s) missing: "
                    + ", ".join(missing_required),
                    fg="red",
                    bold=True,
                )
            )
        else:
            click.echo(click.style("All required keys are set.", fg="green"))

    if missing_required:
        raise SystemExit(1)
