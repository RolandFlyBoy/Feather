"""Optional dependencies and the extras that install them.

From 0.9.8 the heavy packages are optional extras rather than hard
dependencies of every app, so a minimal app no longer installs a PDF
renderer and a cloud SDK it never imports::

    pip install feather-framework            # core only
    pip install 'feather-framework[redis]'   # + redis, rq
    pip install 'feather-framework[all]'     # everything

Every module that imports one of those packages goes through
:func:`require`, so a missing package produces one actionable line naming
the exact install command instead of an ImportError traceback::

    >>> from feather.storage.gcs import GCSStorage
    >>> GCSStorage('bucket')
    feather.MissingDependencyError: GCS storage requires the
    'google-cloud-storage' package, which is not installed.
      pip install 'feather-framework[gcs]'
      (or: pip install google-cloud-storage)

:class:`MissingDependencyError` subclasses ``ImportError``, so code that
already catches ``ImportError`` keeps working.
"""

from collections.abc import Iterable
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version as _installed_version
from types import ModuleType
from typing import Optional

#: Extra name -> the distributions that extra installs. Kept in step with
#: ``[project.optional-dependencies]`` in pyproject.toml (a test asserts it).
EXTRAS: dict[str, tuple[str, ...]] = {
    "pdf": ("weasyprint",),
    "gcs": ("google-cloud-storage",),
    "postgres": ("psycopg2-binary",),
    "redis": ("redis", "rq"),
    "email": ("resend",),
    "prod": ("gunicorn",),
    "test": ("pytest", "pytest-cov"),
}

#: One-line description of what each extra is for (used by `feather
#: security-check` and by the error messages).
EXTRA_DESCRIPTIONS: dict[str, str] = {
    "pdf": "PDF rendering (WeasyPrint)",
    "gcs": "Google Cloud Storage backend",
    "postgres": "PostgreSQL driver",
    "redis": "Redis cache and the RQ job backend",
    "email": "Transactional email (Resend)",
    "prod": "Production WSGI server (gunicorn)",
    "test": "pytest for the app's own test suite",
}

#: Import name -> (distribution name, extra). Import names and distribution
#: names differ often enough (psycopg2 / psycopg2-binary, google.cloud.storage
#: / google-cloud-storage) that both are spelled out.
MODULE_PACKAGES: dict[str, tuple[str, Optional[str]]] = {
    "weasyprint": ("weasyprint", "pdf"),
    "google.cloud": ("google-cloud-storage", "gcs"),
    "google.cloud.storage": ("google-cloud-storage", "gcs"),
    "psycopg2": ("psycopg2-binary", "postgres"),
    "redis": ("redis", "redis"),
    "rq": ("rq", "redis"),
    "rq.job": ("rq", "redis"),
    "rq.registry": ("rq", "redis"),
    "rq.serializers": ("rq", "redis"),
    # rq-scheduler is not part of any extra: it is only needed by the
    # optional `feather.jobs.scheduler` helper, so the message names the
    # package directly.
    "rq_scheduler": ("rq-scheduler", None),
    "resend": ("resend", "email"),
    "gunicorn": ("gunicorn", "prod"),
    "pytest": ("pytest", "test"),
}

#: Distributions that satisfy an extra even though they are not the pinned
#: one (a hand-built psycopg2 is as good as psycopg2-binary).
_EQUIVALENT_PACKAGES: dict[str, tuple[str, ...]] = {
    "psycopg2-binary": ("psycopg2",),
}


class MissingDependencyError(ImportError):
    """An optional dependency is needed but not installed.

    Subclasses ``ImportError`` so existing ``except ImportError`` handlers
    (in apps and in the framework's own backends) keep catching it.
    """


def package_for(module: str) -> tuple[Optional[str], Optional[str]]:
    """Return ``(distribution, extra)`` for an import name.

    Falls back to the longest registered prefix, so ``google.cloud.storage``
    resolves through ``google.cloud``. Returns ``(None, None)`` for a module
    Feather does not know about.
    """
    if module in MODULE_PACKAGES:
        return MODULE_PACKAGES[module]
    parts = module.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        prefix = ".".join(parts[:cut])
        if prefix in MODULE_PACKAGES:
            return MODULE_PACKAGES[prefix]
    return None, None


def install_command(extra: Optional[str], package: Optional[str] = None) -> str:
    """The exact command that installs the dependency."""
    if extra:
        return f"pip install 'feather-framework[{extra}]'"
    return f"pip install {package}"


def missing_message(
    module: str,
    feature: Optional[str] = None,
    package: Optional[str] = None,
    extra: Optional[str] = None,
) -> str:
    """Build the actionable "this is missing, here is the fix" message."""
    known_package, known_extra = package_for(module)
    package = package or known_package or module
    extra = extra or known_extra

    what = feature or f"feather.{module}"
    lines = [f"{what} requires the '{package}' package, which is not installed."]
    if extra:
        lines.append(f"  {install_command(extra)}")
        lines.append(f"  (or: pip install {package})")
    else:
        lines.append(f"  pip install {package}")
    return "\n".join(lines)


def require(
    module: str,
    feature: Optional[str] = None,
    package: Optional[str] = None,
    extra: Optional[str] = None,
) -> ModuleType:
    """Import ``module``, or raise :class:`MissingDependencyError`.

    Args:
        module: Import name, e.g. ``"rq"`` or ``"google.cloud.storage"``.
        feature: What needed it, used to open the message ("GCS storage
            requires ..."). Defaults to the module name.
        package: Distribution name, when it differs from the import name and
            is not in :data:`MODULE_PACKAGES`.
        extra: Feather extra that installs it, when not in
            :data:`MODULE_PACKAGES`.

    Returns:
        The imported module.

    Example::

        rq = require("rq", feature="The RQ job backend")
        queue = rq.Queue(...)
    """
    try:
        return import_module(module)
    except ImportError as exc:
        raise MissingDependencyError(
            missing_message(module, feature=feature, package=package, extra=extra)
        ) from exc


def require_attr(
    module: str,
    *names: str,
    feature: Optional[str] = None,
):
    """Import ``module`` and return the named attributes.

    Convenience for the common ``from rq import Queue, Retry`` shape::

        Queue, Retry = require_attr("rq", "Queue", "Retry", feature="RQ jobs")
    """
    imported = require(module, feature=feature)
    values = tuple(getattr(imported, name) for name in names)
    return values[0] if len(values) == 1 else values


def requirement_spec(version: Optional[str] = None, extras: "Iterable[str]" = ()) -> str:
    """The requirements.txt line for feather-framework with these extras.

    From 0.9.8 a bare ``feather-framework==X.Y.Z`` no longer installs
    weasyprint, google-cloud-storage, psycopg2, redis/rq, resend, gunicorn
    or pytest, so anything that generates a requirements.txt (``feather
    new``) must name the extras the app actually enabled.

    Args:
        version: Pin to this exact version; unpinned when None.
        extras: Extra names, in any order. Unknown names raise ValueError so
            a typo fails at generation time rather than at pip install time.

    Returns:
        e.g. ``"feather-framework[email,postgres]==0.9.8"``.

    Example::

        requirement_spec("0.9.8", ["email", "redis"])
        'feather-framework[email,redis]==0.9.8'
    """
    names = sorted(set(extras))
    unknown = [name for name in names if name not in EXTRAS and name != "all"]
    if unknown:
        raise ValueError(
            f"Unknown Feather extra(s): {', '.join(unknown)}. "
            f"Known extras: {', '.join(sorted(EXTRAS))}, all"
        )
    spec = "feather-framework"
    if names:
        spec += f"[{','.join(names)}]"
    if version:
        spec += f"=={version}"
    return spec


def package_version(package: str) -> Optional[str]:
    """Installed version of a distribution, or None when absent."""
    for candidate in (package, *_EQUIVALENT_PACKAGES.get(package, ())):
        try:
            return _installed_version(candidate)
        except PackageNotFoundError:
            continue
        except Exception:  # noqa: BLE001 - a broken dist must not crash a check
            return None
    return None


def installed_extras() -> dict[str, dict]:
    """Report which extras are installed.

    Returns:
        ``{extra: {"installed": bool, "description": str,
        "packages": {name: version or None}}}``. An extra counts as installed
        only when every package it ships is importable.

    Example::

        >>> installed_extras()["redis"]
        {'installed': True, 'description': 'Redis cache and the RQ job
         backend', 'packages': {'redis': '7.0.0', 'rq': '2.6.0'}}
    """
    report: dict[str, dict] = {}
    for extra, packages in EXTRAS.items():
        versions = {name: package_version(name) for name in packages}
        report[extra] = {
            "installed": all(value is not None for value in versions.values()),
            "description": EXTRA_DESCRIPTIONS.get(extra, ""),
            "packages": versions,
        }
    return report


def extras_summary() -> str:
    """One line per extra, for CLI output.

    Example::

        pdf       missing    PDF rendering (WeasyPrint)
        redis     installed  redis 7.0.0, rq 2.6.0
    """
    report = installed_extras()
    width = max(len(name) for name in report)
    lines = []
    for extra, info in report.items():
        if info["installed"]:
            detail = ", ".join(f"{n} {v}" for n, v in info["packages"].items())
            state = "installed"
        else:
            missing = [n for n, v in info["packages"].items() if v is None]
            detail = f"{info['description']} - {install_command(extra)}"
            state = "missing"
            if len(missing) != len(info["packages"]):
                state = "partial"
        lines.append(f"{extra:<{width}}  {state:<9}  {detail}")
    return "\n".join(lines)


__all__ = [
    "EXTRAS",
    "EXTRA_DESCRIPTIONS",
    "MODULE_PACKAGES",
    "MissingDependencyError",
    "extras_summary",
    "install_command",
    "installed_extras",
    "missing_message",
    "package_for",
    "package_version",
    "require",
    "requirement_spec",
    "require_attr",
]
