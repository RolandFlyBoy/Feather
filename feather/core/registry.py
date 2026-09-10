"""Per-app storage for Feather's backends.

Before 0.9.8 the queue, the cache, the Vite manifest and the rate limiter
were module-level singletons, so two Feather apps in one process (a test
suite creating several apps, a WSGI file mounting two apps, an admin app
beside the public one) silently shared them: the first app's configuration
won and the second app's cache entries leaked into the first.

Everything now lives in ``app.extensions["feather"]``, the standard Flask
place for extension state, and ``get_queue()`` / ``get_cache()`` /
``get_rate_limiter()`` are thin facades that resolve the current app.

Outside an app context the facades keep working against a **process-level
default** store, which is what a script, a CLI command or a module-level
``@job`` registration hits. That store is shared by everything with no app
context; it is a compatibility fallback, not a second app.

Example::

    from feather.core.registry import feather_state, get_backend

    def _make_thing(app):
        return Thing(app.config["THING_URL"] if app else "default")

    def get_thing():
        return get_backend("thing", _make_thing)
"""

from typing import Any, Callable

#: State for code running without an app context. Documented fallback, not
#: a hidden second app: `feather worker` and module-level @job registration
#: both land here.
_PROCESS_STATE: dict[str, Any] = {}

#: The key Feather owns in ``app.extensions``.
EXTENSION_KEY = "feather"


def current_app_or_none():
    """The current Flask app object, or None when there is no app context.

    Returns the real application, not the ``current_app`` proxy, so it can
    be stored and compared.
    """
    try:
        from flask import current_app

        return current_app._get_current_object()
    except RuntimeError:
        return None
    except ImportError:  # pragma: no cover - flask is a hard dependency
        return None


def feather_state(app=None) -> dict[str, Any]:
    """The mutable state dict for ``app`` (or the current app).

    Args:
        app: A Flask application. Defaults to the current app, and to the
            process-level default store when there is no app context.

    Returns:
        The dict Feather stores its backends in. For a real app this is
        ``app.extensions["feather"]``, created on first use.
    """
    if app is None:
        app = current_app_or_none()
    if app is None:
        return _PROCESS_STATE
    extensions = getattr(app, "extensions", None)
    if extensions is None:  # pragma: no cover - Flask always sets this
        app.extensions = extensions = {}
    return extensions.setdefault(EXTENSION_KEY, {})


def get_backend(name: str, factory: Callable[[Any], Any], app=None) -> Any:
    """Return the named backend for this app, creating it once.

    Args:
        name: Registry key, e.g. ``"queue"`` or ``"cache"``.
        factory: Called with the app (which may be ``None`` outside an app
            context) to build the backend the first time it is needed.
        app: Explicit app; defaults to the current app.

    Returns:
        The backend instance, the same object for every call within one app.
    """
    if app is None:
        app = current_app_or_none()
    state = feather_state(app)
    existing = state.get(name)
    if existing is not None:
        return existing
    created = factory(app)
    state[name] = created
    return created


def set_backend(name: str, value: Any, app=None) -> Any:
    """Store a backend explicitly (used by ``init_cache`` / ``init_jobs``)."""
    feather_state(app)[name] = value
    return value


def reset_backends(app=None, *names: str) -> None:
    """Drop cached backends so the next call rebuilds them.

    Args:
        app: The app to clear. Pass ``None`` for the process-level store.
        *names: Keys to clear; all of them when omitted.

    Note:
        Passing ``None`` clears only the process-level store, never a real
        app's state - that is what makes per-app isolation testable.
    """
    state = feather_state(app) if app is not None else _PROCESS_STATE
    if not names:
        state.clear()
        return
    for name in names:
        state.pop(name, None)


__all__ = [
    "EXTENSION_KEY",
    "current_app_or_none",
    "feather_state",
    "get_backend",
    "reset_backends",
    "set_backend",
]
