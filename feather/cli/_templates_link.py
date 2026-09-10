"""Keep ``.feather-templates`` pointing at the installed package's templates.

Tailwind only emits a utility class it has seen in a scanned file, so a
project's ``static/css/app.css`` has to list Feather's own component
templates as a ``@source``. Those templates live wherever pip installed the
package, which is a different absolute path on every machine and inside
every image - baking that path into app.css silently drops every framework
component class from the production CSS.

The fix is one indirection: app.css scans ``../../.feather-templates``, a
project-relative path, and ``feather dev`` / ``feather build`` point that
name at the installed package before the frontend build runs.

In a Docker image there is no Python in the Node stage, so the Dockerfile
COPYs the templates in as a real directory. A real directory therefore always
wins: this module leaves it alone.
"""

from pathlib import Path

#: Name of the link in the project root. Also in .gitignore and .dockerignore.
LINK_NAME = ".feather-templates"


def feather_templates_dir() -> Path:
    """Absolute path of the installed Feather package's templates directory."""
    import feather

    return Path(feather.__file__).resolve().parent / "templates"


def ensure_templates_link(project_path: Path = None) -> tuple:
    """Create or refresh ``.feather-templates`` in the project root.

    Idempotent, and safe to call when the target is already correct or when
    something real is sitting there.

    Returns:
        ``(status, detail)`` where status is one of ``"created"``,
        ``"updated"``, ``"current"``, ``"directory"`` (a real directory is
        present and was left alone) or ``"error"``.
    """
    project_path = Path(project_path or Path.cwd())
    link = project_path / LINK_NAME
    target = feather_templates_dir()

    if not target.is_dir():
        return ("error", f"Feather's templates directory is missing: {target}")

    # A real directory is what the Docker build puts here. Never touch it.
    if link.is_dir() and not link.is_symlink():
        return ("directory", str(link))

    if link.is_symlink():
        try:
            if link.resolve() == target:
                return ("current", str(target))
        except OSError:
            pass  # dangling symlink - fall through and replace it
        try:
            link.unlink()
        except OSError as exc:
            return ("error", f"Could not replace {LINK_NAME}: {exc}")
        status = "updated"
    elif link.exists():
        # A regular file called .feather-templates. Not ours to delete.
        return ("error", f"{link} exists and is not a directory or symlink")
    else:
        status = "created"

    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        return ("error", f"Could not create {LINK_NAME}: {exc}")

    return (status, str(target))
