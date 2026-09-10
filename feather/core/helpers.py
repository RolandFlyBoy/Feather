"""Template helpers and context processors."""

import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from flask import make_response, Response
from markupsafe import Markup

if TYPE_CHECKING:
    from flask import Flask


def htmx_redirect(url: str, status_code: int = 200) -> Response:
    """Create an HTMX-compatible redirect response.

    When an HTMX request needs to redirect the full page (e.g., after deleting
    a resource from its detail page), use this helper to send the HX-Redirect
    header that HTMX understands.

    Args:
        url: URL to redirect to.
        status_code: HTTP status code (default 200, HTMX requires 2xx for redirect).

    Returns:
        Flask Response with HX-Redirect header.

    Example::

        from feather.core.helpers import htmx_redirect
        from flask import url_for

        @api.delete('/stories/<story_id>')
        @auth_required
        def delete_story(story_id):
            story = Story.query.get_or_404(story_id)
            db.session.delete(story)
            db.session.commit()

            # Redirect to stories list after deletion
            return htmx_redirect(url_for('page.stories'))

    Note:
        HTMX processes HX-Redirect only for 2xx responses. The default 200
        is intentional - using 3xx would cause the browser to follow the
        redirect before HTMX can process it.

        For non-HTMX requests, use Flask's standard redirect() function.
    """
    response = make_response("", status_code)
    response.headers["HX-Redirect"] = url
    return response


def htmx_refresh() -> Response:
    """Create an HTMX response that triggers a full page refresh.

    Use this when you want HTMX to refresh the entire page after an action,
    rather than swapping a specific element.

    Returns:
        Flask Response with HX-Refresh header.

    Example::

        @api.post('/settings/reset')
        @auth_required
        def reset_settings():
            reset_user_settings(current_user.id)
            return htmx_refresh()
    """
    response = make_response("", 200)
    response.headers["HX-Refresh"] = "true"
    return response


def with_trigger(content: str, trigger: str = "dataUpdated") -> Response:
    """Wrap HTML response with HX-Trigger header for cross-element updates.

    Use this when an HTMX action should trigger updates in other elements
    that are listening for the trigger event.

    Args:
        content: HTML content to return.
        trigger: Event name to trigger (default: "dataUpdated").

    Returns:
        Flask Response with HX-Trigger header.

    Example::

        # In Python:
        @api.post('/todos/<todo_id>/toggle')
        def toggle_todo(todo_id):
            todo = toggle_complete(todo_id)
            return with_trigger(
                render_template("partials/todo_item.html", todo=todo)
            )

        # In HTML (other elements listen for the trigger):
        <div hx-get="/htmx/stats"
             hx-trigger="load, dataUpdated from:body"
             hx-swap="innerHTML">
            <!-- Stats refresh when dataUpdated fires -->
        </div>
    """
    response = make_response(content)
    response.headers["HX-Trigger"] = trigger
    return response


def feather_island_scripts(content: str) -> Markup:
    """Generate script tags for islands used in the page content.

    Scans the rendered content for data-island attributes and generates
    the appropriate script tags for auto-discovery.

    Args:
        content: The rendered HTML content to scan.

    Returns:
        Markup containing script tags for discovered islands.

    Example (in base.html)::

        {% set page_content %}{% block content %}{% endblock %}{% endset %}
        {{ page_content }}
        {{ feather_island_scripts(page_content) }}

    Note:
        This is a convenience helper. You can still manually include
        island scripts in the {% block islands %} block for more control.
    """
    from flask import current_app

    # Find all data-island attributes in the content
    islands = set(re.findall(r'data-island="([^"]+)"', content))

    if not islands:
        return Markup("")

    use_vite = current_app.debug and _vite_enabled(current_app)
    dev_server = _vite_dev_server(current_app)

    scripts = []
    for island in sorted(islands):
        if use_vite:
            # Debug mode with Vite running: load from the dev server (HMR).
            url = f"{dev_server}/static/islands/{island}.js"
        else:
            # Built asset (production, or `feather dev --no-vite`).
            url = _resolve_asset(current_app, f"islands/{island}")
        scripts.append(f'<script type="module" src="{url}"></script>')

    return Markup("\n".join(scripts))


#: Default Vite dev server used for island scripts in debug mode.
DEFAULT_VITE_DEV_SERVER = "http://localhost:5173"


def _vite_dev_server(app: "Flask") -> str:
    """Base URL of the Vite dev server.

    Reads VITE_DEV_SERVER from app config, then the environment, and falls
    back to http://localhost:5173.
    """
    value = app.config.get("VITE_DEV_SERVER") or os.environ.get("VITE_DEV_SERVER")
    return (value or DEFAULT_VITE_DEV_SERVER).rstrip("/")


def _vite_enabled(app: "Flask") -> bool:
    """Whether the Vite dev server is expected to be serving assets.

    Disabled by FEATHER_VITE=0 (config or environment) or by FEATHER_NO_VITE=1,
    which `feather dev --no-vite` sets for the Flask process. When disabled,
    island scripts point at the built assets under /static instead of a dev
    server that isn't listening.
    """
    if os.environ.get("FEATHER_NO_VITE", "").lower() in ("true", "1", "yes"):
        return False

    value = app.config.get("FEATHER_VITE", None)
    if value is None:
        value = os.environ.get("FEATHER_VITE")
    if value is None:
        return True
    if isinstance(value, str):
        return value.lower() not in ("false", "0", "no", "")
    return bool(value)


def setup_template_helpers(app: "Flask") -> None:
    """Set up template helpers and context processors.

    Args:
        app: Flask application instance.
    """

    @app.context_processor
    def inject_helpers():
        """Inject helper functions into template context."""
        return {
            "feather_asset": feather_asset,
            "feather_island": feather_island,
            "feather_island_scripts": feather_island_scripts,
            "htmx_redirect": htmx_redirect,
            "htmx_refresh": htmx_refresh,
            "with_trigger": with_trigger,
        }

    @app.template_global()
    def feather_island(name: str) -> str:
        """Get the URL for an island JS file.

        Args:
            name: Island name (e.g., 'story_form', 'audio_player')

        Returns:
            URL path to the island JS file.
        """
        return _resolve_asset(app, f"islands/{name}")

    @app.template_global()
    def feather_asset(name: str) -> str:
        """Get the URL for a Vite-built asset.

        Args:
            name: Asset name (e.g., 'feather', 'styles', 'islands/counter')

        Returns:
            URL path to the asset.
        """
        return _resolve_asset(app, name)


#: Registry key for the parsed Vite manifest. Per app: two apps in one
#: process have different static folders, and a module-level cache served
#: the first app's hashed filenames to the second.
_MANIFEST_KEY = "vite_manifest"


def _resolve_asset(app: "Flask", name: str) -> str:
    """Resolve an asset name to its built URL.

    Args:
        app: Flask application instance.
        name: Asset name.

    Returns:
        URL path to the asset.
    """
    from feather.core.registry import feather_state

    state = feather_state(app)

    # In debug mode, reload manifest each time
    if app.debug or state.get(_MANIFEST_KEY) is None:
        state[_MANIFEST_KEY] = _load_manifest(app)

    manifest = state.get(_MANIFEST_KEY)

    # If no manifest (dev mode or not built), return source path
    if manifest is None:
        return _fallback_asset_path(name)

    # Look up in manifest
    source_path = _name_to_source_path(name)
    entry = manifest.get(source_path)

    if entry:
        return f"/static/dist/{entry['file']}"

    # Try alternate paths
    for alt_path in _alternate_source_paths(name):
        entry = manifest.get(alt_path)
        if entry:
            return f"/static/dist/{entry['file']}"

    # Fallback
    return _fallback_asset_path(name)


def _load_manifest(app: "Flask") -> dict | None:
    """Load the Vite manifest file.

    Args:
        app: Flask application instance.

    Returns:
        Manifest dict or None if not found.
    """
    manifest_path = Path(app.static_folder) / "dist" / ".vite" / "manifest.json"

    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _name_to_source_path(name: str) -> str:
    """Convert asset name to source path.

    Examples:
        'feather' -> 'static/feather.js'
        'styles' -> 'static/css/app.css'
        'islands/counter' -> 'static/islands/counter.js'
    """
    if name == "styles":
        return "static/css/app.css"

    if "/" in name:
        return f"static/{name}.js"

    return f"static/{name}.js"


def _alternate_source_paths(name: str) -> list[str]:
    """Generate alternate source paths to try.

    Args:
        name: Asset name.

    Returns:
        List of alternate paths.
    """
    paths = []

    # Try with hyphen/underscore variations
    if "-" in name:
        paths.append(f"static/{name.replace('-', '_')}.js")
    elif "_" in name:
        paths.append(f"static/{name.replace('_', '-')}.js")

    # Try in static/js directory
    paths.append(f"static/js/{name}.js")

    return paths


def _fallback_asset_path(name: str) -> str:
    """Get fallback path when manifest is not available.

    Args:
        name: Asset name.

    Returns:
        Fallback URL path.
    """
    if name == "styles":
        return "/static/css/app.css"

    if "/" in name:
        return f"/static/{name}.js"

    return f"/static/{name}.js"
