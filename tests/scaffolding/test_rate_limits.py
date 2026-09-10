"""Scaffolding tests for the generated app's Flask-Limiter wiring (0.9.9).

An app scaffolded with authentication gets a ``rate_limits.py`` that puts
Flask-Limiter on the OAuth login and callback routes and on the admin POST
routes, with Redis storage when a Redis URL is configured. Feather's own
``@rate_limit`` decorator stays a single-process tool.

Two mistakes cost real production time, and both are silent, so both are
covered behaviourally here rather than only in the source:

1. ``limiter.limit(rule)(view)`` returns a wrapper. Discarding it enforces
   nothing *and* drops the endpoint out of the default limit.
   ``test_discarding_the_wrapper_enforces_nothing`` re-runs the generated
   app with exactly that mutation and asserts the 429 disappears, so the
   positive test cannot pass for the wrong reason.
2. The default limit otherwise applies to static assets, and one page load
   fetches ten or more of them through Flask.
   ``test_static_assets_never_hit_the_limit`` asks for three times the
   default limit's worth of ``/feather-static/api.js`` and expects 200s.
"""

import json
import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.scaffolding


AUTH_APP = {
    "database": "sqlite",
    "db_url": "sqlite:///app.db",
    "include_auth": True,
    "tenant_mode": "single",
    "admin_email": "admin@test.com",
}

NO_AUTH_APP = {"database": "none"}


# =============================================================================
# Booting a generated app
# =============================================================================

#: Limits used by the behavioural probe. config.py reads every RATELIMIT_*
#: key from the environment, which is the point of keeping the numbers in
#: config.py rather than in the middle of rate_limits.py.
PROBE_ENV = {
    "RATELIMIT_LOGIN": "3 per minute",
    "RATELIMIT_DEFAULT": "4 per minute",
    "RATELIMIT_ADMIN": "5 per minute",
}

PROBE_SCRIPT = """
import importlib, json, os, sys

sys.path.insert(0, os.getcwd())

import rate_limits

if os.environ.get("SIMULATE_DISCARDED_WRAPPER") == "1":
    # The production trap, reproduced: build the wrapper, drop it on the
    # floor. No error, no log line, and no limit.
    def _discard(app, limiter, endpoint, rule):
        view = app.view_functions.get(endpoint)
        if view is None:
            return False
        limiter.limit(rule)(view)
        return True

    rate_limits._apply = _discard

from app import app

client = app.test_client()

# 3 per minute -> the 4th call is refused.
login = [client.get("/auth/google/login").status_code for _ in range(6)]
# Exempt: 12 calls against a default limit of 4 per minute.
static = [client.get("/feather-static/api.js").status_code for _ in range(12)]
# Not exempt: the default limit applies.
live = [client.get("/health/live").status_code for _ in range(6)]

admin = {}
module = importlib.import_module("routes.pages.admin")
for endpoint in ("admin.toggle_user_status", "admin.update_user_role"):
    registered = app.view_functions.get(endpoint)
    original = getattr(module, endpoint.split(".", 1)[1], None)
    admin[endpoint] = bool(registered is not None and original is not None
                           and registered is not original)

print("RESULT " + json.dumps({
    "login": login,
    "static": static,
    "live": live,
    "admin_rewrapped": admin,
    "limiter_installed": bool(app.extensions.get("limiter")),
}))
"""


def _probe(project, **extra_env):
    """Boot a generated app in its own interpreter and return the probe data.

    Generated apps define modules named ``app``, ``config`` and ``models``;
    importing them into the test process would collide with other apps, so
    each boot gets a fresh interpreter (the same approach as
    tests/scaffolding/test_app_types_096.py).
    """
    env = dict(os.environ)
    env["FLASK_ENV"] = "testing"
    env["PYTHONPATH"] = str(project)
    env.pop("DATABASE_URL", None)
    env.pop("REDIS_URL", None)
    env.pop("RATELIMIT_STORAGE_URI", None)
    env.update(PROBE_ENV)
    env.update(extra_env)

    result = subprocess.run(
        [sys.executable, "-c", PROBE_SCRIPT],
        cwd=str(project),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        f"probe failed in {project}:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    lines = [ln for ln in result.stdout.splitlines() if ln.startswith("RESULT ")]
    assert lines, f"no RESULT line:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    return json.loads(lines[-1][len("RESULT "):])


@pytest.fixture(scope="module")
def limiter_installed():
    """Skip the behavioural tests when the optional extra is absent."""
    return pytest.importorskip(
        "flask_limiter", reason="pip install 'feather-framework[ratelimit]'"
    )


# =============================================================================
# The generated files
# =============================================================================


class TestGeneratedFiles:
    """What an auth app gets on disk."""

    def test_rate_limits_module_is_written_and_compiles(self, scaffold_project):
        project = scaffold_project(AUTH_APP)
        source = (project / "rate_limits.py").read_text()
        compile(source, "rate_limits.py", "exec")

    def test_app_py_initialises_it_after_feather(self, scaffold_project):
        """The limiter replaces view functions, so it runs after discovery."""
        body = (scaffold_project(AUTH_APP) / "app.py").read_text()
        assert "from rate_limits import init_rate_limits" in body
        assert body.index("app = Feather(__name__)") < body.index("init_rate_limits(app)")

    def test_the_wrapper_is_assigned_back(self, scaffold_project):
        """Trap 1: limiter.limit(...)(view) must be re-registered, not dropped.

        A source-level guard for the behavioural test below, and for the
        reader: the assignment is the whole point of ``_apply``.
        """
        body = (scaffold_project(AUTH_APP) / "rate_limits.py").read_text()
        assert "app.view_functions[endpoint] = limiter.limit(rule)(view)" in body

    def test_static_endpoints_are_exempt(self, scaffold_project):
        """Trap 2: a page load's own assets must not spend the limit."""
        body = (scaffold_project(AUTH_APP) / "rate_limits.py").read_text()
        assert 'EXEMPT_ENDPOINTS = {"static", "feather_static"}' in body
        assert "limiter.request_filter(_exempt)" in body

    def test_storage_falls_back_to_memory_with_a_warning(self, scaffold_project):
        body = (scaffold_project(AUTH_APP) / "rate_limits.py").read_text()
        assert '"memory://"' in body
        assert "app.logger.warning" in body
        # The warning has to name the consequence, not just the fallback.
        assert "worker" in body

    def test_admin_post_routes_are_covered(self, scaffold_project):
        body = (scaffold_project(AUTH_APP) / "rate_limits.py").read_text()
        assert '_write_endpoints(app, "admin.")' in body

    def test_config_carries_the_tunable_limits(self, scaffold_project):
        config = (scaffold_project(AUTH_APP) / "config.py").read_text()
        for key in (
            "RATELIMIT_STORAGE_URI",
            "RATELIMIT_DEFAULT",
            "RATELIMIT_LOGIN",
            "RATELIMIT_ADMIN",
        ):
            assert key in config, key
        assert 'os.environ.get("REDIS_URL")' in config

    def test_env_files_carry_the_storage_key(self, scaffold_project):
        project = scaffold_project(AUTH_APP)
        assert "RATELIMIT_STORAGE_URI=" in (project / ".env").read_text()
        # .env.example is seeded from .env by the Docker layout.
        assert "RATELIMIT_STORAGE_URI=" in (project / ".env.example").read_text()

    def test_requirements_name_the_extra(self, scaffold_project):
        """Without the extra the app boots with no limits at all."""
        body = (scaffold_project(AUTH_APP) / "requirements.txt").read_text()
        spec = [ln for ln in body.splitlines() if ln.startswith("feather-framework")]
        assert spec, body
        assert "ratelimit" in spec[0]

    def test_guidance_explains_both_traps(self, scaffold_project):
        project = scaffold_project(AUTH_APP)
        guidance = (project / "AGENTS.md").read_text()
        assert guidance == (project / "CLAUDE.md").read_text()
        assert "Flask-Limiter" in guidance
        assert "app.view_functions[endpoint] = limiter.limit(rule)(view)" in guidance
        assert "per process" in guidance


class TestNoAuthApp:
    """An app with no login endpoint gets none of it."""

    def test_no_rate_limits_module(self, scaffold_project):
        assert not (scaffold_project(NO_AUTH_APP) / "rate_limits.py").exists()

    def test_app_py_is_untouched(self, scaffold_project):
        body = (scaffold_project(NO_AUTH_APP) / "app.py").read_text()
        assert "init_rate_limits" not in body

    def test_no_config_or_env_keys(self, scaffold_project):
        project = scaffold_project(NO_AUTH_APP)
        assert "RATELIMIT" not in (project / "config.py").read_text()
        assert "RATELIMIT" not in (project / ".env").read_text()

    def test_no_extra_in_requirements(self, scaffold_project):
        body = (scaffold_project(NO_AUTH_APP) / "requirements.txt").read_text()
        spec = [ln for ln in body.splitlines() if ln.startswith("feather-framework")]
        assert spec and "ratelimit" not in spec[0]

    def test_no_guidance_section(self, scaffold_project):
        assert "## Rate Limiting" not in (scaffold_project(NO_AUTH_APP) / "AGENTS.md").read_text()


# =============================================================================
# The behaviour, in a booted app
# =============================================================================


class TestEnforcement:
    """A generated app really refuses the N+1th request."""

    def test_login_is_limited(self, scaffold_project, limiter_installed):
        data = _probe(scaffold_project(AUTH_APP))
        assert data["limiter_installed"] is True
        login = data["login"]
        assert 429 not in login[:3], login
        assert login[3:] == [429, 429, 429], login

    def test_static_assets_never_hit_the_limit(self, scaffold_project, limiter_installed):
        """Trap 2, behaviourally: 12 asset requests against a 4/minute default."""
        data = _probe(scaffold_project(AUTH_APP))
        assert set(data["static"]) == {200}, data["static"]
        # ... while a non-exempt endpoint on the same default limit is cut off,
        # which is what makes the line above mean something.
        assert 429 in data["live"], data["live"]

    def test_admin_post_routes_are_re_registered(self, scaffold_project, limiter_installed):
        """The view Flask calls is the limiter's wrapper, not the original."""
        data = _probe(scaffold_project(AUTH_APP))
        assert data["admin_rewrapped"] == {
            "admin.toggle_user_status": True,
            "admin.update_user_role": True,
        }

    def test_discarding_the_wrapper_enforces_nothing(self, scaffold_project, limiter_installed):
        """Trap 1, behaviourally.

        Same app, same limits, with ``_apply`` mutated to drop what
        ``limiter.limit(...)`` returns - the exact production bug. Every
        login request succeeds: the endpoint loses its own limit *and* the
        default one. If the generated code ever regresses to that shape,
        ``test_login_is_limited`` fails; this test is what proves it would.
        """
        data = _probe(scaffold_project(AUTH_APP), SIMULATE_DISCARDED_WRAPPER="1")
        assert 429 not in data["login"], data["login"]
        assert data["admin_rewrapped"] == {
            "admin.toggle_user_status": False,
            "admin.update_user_role": False,
        }
