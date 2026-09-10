"""Scaffolding tests for the 0.9.6 generator fixes.

Covers, for each app type (simple / single-tenant / multi-tenant):

* every generated app gets ``static/js/vendor.js`` (base.html loads it and
  vite.config.js builds it, so a missing file broke the production build)
* generated apps boot and serve ``/`` and ``/health``, and ``/admin`` refuses
  anonymous callers instead of erroring
* multi-tenant admin log queries are scoped to the caller's tenant
* the config / .env hardening (remember cookie flags, CSRF lifetime, RQ
  serializer, debug flag vs. the thread job backend)
* the hx-confirm modal is resolved at event time, once, in app.js
"""

import json
import os
import py_compile
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.scaffolding


SIMPLE = {"database": "none"}

SINGLE_TENANT = {
    "database": "sqlite",
    "db_url": "sqlite:///app.db",
    "include_auth": True,
    "tenant_mode": "single",
    "admin_email": "admin@test.com",
}

MULTI_TENANT = {
    "database": "sqlite",
    "db_url": "sqlite:///app.db",
    "include_auth": True,
    "tenant_mode": "multi",
    "admin_email": "admin@test.com",
    "include_email": True,
}

APP_TYPES = [
    pytest.param(SIMPLE, id="simple"),
    pytest.param(SINGLE_TENANT, id="single-tenant"),
    pytest.param(MULTI_TENANT, id="multi-tenant"),
]


# =============================================================================
# Helpers
# =============================================================================

BOOT_SCRIPT = """
import json, os, sys

sys.path.insert(0, os.getcwd())

from app import app

app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False

# The app keeps the sqlite file its own config points at, inside the throwaway
# project directory; the engine is already bound, so overriding the URI here
# would have no effect.
if "sqlalchemy" in app.extensions:
    from feather.db import db

    with app.app_context():
        db.create_all()

client = app.test_client()
statuses = {path: client.get(path).status_code for path in ["/", "/health", "/admin/"]}
print("RESULT " + json.dumps(statuses))
"""


def _run_in_project(project, script, timeout=180):
    """Run a python script inside a scaffolded project and return its stdout.

    Generated apps define modules named ``app``, ``config``, ``models`` and
    ``services``; importing several of them into the test process would collide,
    so each app boots in its own interpreter.
    """
    env = dict(os.environ)
    env["FLASK_ENV"] = "testing"
    env["PYTHONPATH"] = str(project)
    env.pop("DATABASE_URL", None)

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(project),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert result.returncode == 0, (
        f"script failed in {project}:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    payload = [line for line in result.stdout.splitlines() if line.startswith("RESULT ")]
    assert payload, f"no RESULT line:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    return json.loads(payload[-1][len("RESULT "):])


# =============================================================================
# Every app type
# =============================================================================


class TestAllAppTypes:
    """Checks that must hold for simple, single-tenant and multi-tenant apps."""

    @pytest.mark.parametrize("config", APP_TYPES)
    def test_vendor_js_written(self, scaffold_project, config):
        """vendor.js is a vite build input and base.html loads it - always emit it."""
        project = scaffold_project(config)

        vendor = project / "static/js/vendor.js"
        assert vendor.exists(), "static/js/vendor.js missing - vite build would fail"

        source = vendor.read_text()
        assert "htmx.org" in source
        assert "window.htmx" in source

        # base.html references it unconditionally and vite.config.js builds it
        assert "static/js/vendor.js" in (project / "templates/base.html").read_text()
        assert "static/js/vendor.js" in (project / "vite.config.js").read_text()

    @pytest.mark.parametrize("config", APP_TYPES)
    def test_python_files_compile(self, scaffold_project, config):
        project = scaffold_project(config)
        for py_file in project.rglob("*.py"):
            py_compile.compile(str(py_file), doraise=True)

    @pytest.mark.parametrize("config", APP_TYPES)
    def test_app_boots_and_serves_core_routes(self, scaffold_project, config):
        """The generated app imports, serves / and /health, and guards /admin."""
        project = scaffold_project(config)
        statuses = _run_in_project(project, BOOT_SCRIPT)

        assert statuses["/"] == 200
        assert statuses["/health"] == 200

        if config.get("include_auth"):
            # Anonymous callers are refused, never a 500
            assert statuses["/admin/"] in (301, 302, 401, 403), statuses
        else:
            # No admin panel without auth
            assert statuses["/admin/"] == 404, statuses


# =============================================================================
# Multi-tenant admin log isolation
# =============================================================================


LOG_ISOLATION_SCRIPT = """
import json, os, sys

sys.path.insert(0, os.getcwd())

from flask_login import login_user

from app import app
from feather.db import db
from models import Log, Tenant, User
from services.admin_service import AdminService

app.config["TESTING"] = True

with app.app_context():
    db.create_all()

    tenant_a = Tenant(slug="a", name="A", domain="a.example", status="active")
    tenant_b = Tenant(slug="b", name="B", domain="b.example", status="active")
    db.session.add_all([tenant_a, tenant_b])
    db.session.flush()

    tenant_admin = User(
        email="admin@a.example", username="admin_a", tenant_id=tenant_a.id,
        role="admin", active=True,
    )
    platform_admin = User(
        email="root@a.example", username="root_a", tenant_id=tenant_a.id,
        role="admin", is_platform_admin=True, active=True,
    )
    db.session.add_all([tenant_admin, platform_admin])
    db.session.flush()

    for tenant_id, message in [
        (tenant_a.id, "a-log"),
        (tenant_b.id, "b-log"),
        (None, "anonymous-log"),
    ]:
        db.session.add(Log(
            event_type="InternalError", level="ERROR", message=message,
            tenant_id=tenant_id, path="/boom", method="GET",
        ))
    db.session.commit()

    tenant_admin_id, platform_admin_id = tenant_admin.id, platform_admin.id
    out = {}

    for key, user_id in [("tenant_admin", tenant_admin_id), ("platform_admin", platform_admin_id)]:
        with app.test_request_context("/admin/logs"):
            login_user(db.session.get(User, user_id))
            service = AdminService()
            out[key] = {
                "logs": sorted(row.message for row in service.get_logs()["items"]),
                "stats_total": service.get_log_stats()["total"],
            }

print("RESULT " + json.dumps(out))
"""


class TestMultiTenantLogIsolation:
    """Multi-tenant admin log queries must be tenant-scoped."""

    def test_generated_source_filters_logs_by_tenant(self, scaffold_project):
        project = scaffold_project(MULTI_TENANT)
        source = (project / "services/admin_service.py").read_text()

        get_logs = source[source.index("def get_logs"):source.index("def get_log_stats")]
        get_log_stats = source[source.index("def get_log_stats"):]

        assert "Log.tenant_id == tenant_id" in get_logs, "get_logs does not scope by tenant"
        assert "self._get_tenant_id()" in get_logs

        assert "Log.tenant_id == tenant_id" in get_log_stats, (
            "get_log_stats does not scope by tenant"
        )
        assert "self._get_tenant_id()" in get_log_stats

    def test_single_tenant_has_no_log_tenant_filter(self, scaffold_project):
        """Single-tenant apps have no tenant_id on Log at all."""
        project = scaffold_project(SINGLE_TENANT)
        source = (project / "services/admin_service.py").read_text()
        assert "Log.tenant_id" not in source

    def test_tenant_admin_only_sees_own_tenant_logs(self, scaffold_project):
        """Behaviour check: boot the app and query logs as each kind of admin."""
        project = scaffold_project(MULTI_TENANT)
        result = _run_in_project(project, LOG_ISOLATION_SCRIPT)

        assert result["tenant_admin"]["logs"] == ["a-log"]
        assert result["tenant_admin"]["stats_total"] == 1

        # Platform admins see every tenant plus the NULL tenant_id rows that
        # unauthenticated 5xx errors produce
        assert result["platform_admin"]["logs"] == ["a-log", "anonymous-log", "b-log"]
        assert result["platform_admin"]["stats_total"] == 3

    def test_log_model_docstring_does_not_claim_automatic_scoping(self, scaffold_project):
        project = scaffold_project(MULTI_TENANT)
        docstring = (project / "models/log.py").read_text()
        assert "Logs are scoped by tenant_id so admins only see logs" not in docstring
        assert "NULL" in docstring


# =============================================================================
# Admin email tool
# =============================================================================


class TestAdminSendEmail:
    """The admin email tool is not an open relay."""

    def test_multi_tenant_recipient_must_be_a_tenant_user(self, scaffold_project):
        project = scaffold_project(MULTI_TENANT)
        routes = (project / "routes/pages/admin.py").read_text()
        service = (project / "services/admin_service.py").read_text()

        send_email = routes[routes.index("def send_email"):routes.index("def search_users_dropdown")]
        assert "find_user_by_email" in send_email
        assert "in your organization" in send_email
        assert "email_service.send(recipient.email" in send_email

        lookup = service[service.index("def find_user_by_email"):]
        assert "User.tenant_id == tenant_id" in lookup[:800]

    def test_single_tenant_recipient_must_be_a_user(self, scaffold_project):
        config = dict(SINGLE_TENANT, include_email=True)
        project = scaffold_project(config)
        routes = (project / "routes/pages/admin.py").read_text()

        send_email = routes[routes.index("def send_email"):routes.index("def search_users_dropdown")]
        assert "find_user_by_email" in send_email
        assert "Recipient must be an existing user." in send_email


# =============================================================================
# config.py / .env hardening
# =============================================================================


class TestGeneratedConfig:
    def test_remember_cookie_flags(self, scaffold_project):
        config = (scaffold_project(SINGLE_TENANT) / "config.py").read_text()

        assert "REMEMBER_COOKIE_HTTPONLY = True" in config
        assert 'REMEMBER_COOKIE_SAMESITE = "Lax"' in config

        development = config[config.index("class DevelopmentConfig"):config.index("class ProductionConfig")]
        production = config[config.index("class ProductionConfig"):]
        assert "REMEMBER_COOKIE_SECURE = False" in development
        assert "REMEMBER_COOKIE_SECURE = True" in production

    def test_session_protection_is_basic_in_development(self, scaffold_project):
        config = (scaffold_project(SINGLE_TENANT) / "config.py").read_text()
        development = config[config.index("class DevelopmentConfig"):config.index("class ProductionConfig")]
        assert 'SESSION_PROTECTION = "basic"' in development
        assert "SESSION_PROTECTION = None" not in config

    @pytest.mark.parametrize("config", APP_TYPES)
    def test_csrf_token_lifetime_bound_by_session(self, scaffold_project, config):
        generated = (scaffold_project(config) / "config.py").read_text()
        assert "WTF_CSRF_TIME_LIMIT = None" in generated

    def test_jobs_config_uses_json_serializer_and_guards_redis(self, scaffold_project):
        project = scaffold_project(dict(SINGLE_TENANT, include_jobs=True))
        config = (project / "config.py").read_text()

        assert 'JOB_SERIALIZER = os.environ.get("JOB_SERIALIZER", "json")' in config

        production = config[config.index("class ProductionConfig"):]
        assert "def check_job_backend" in production
        assert "ProductionConfig.check_job_backend()" in config
        assert "no password" in production

    def test_no_job_guard_without_jobs(self, scaffold_project):
        config = (scaffold_project(SIMPLE) / "config.py").read_text()
        assert "check_job_backend" not in config
        assert "urlparse" not in config


class TestGeneratedEnv:
    def test_debug_off_when_thread_jobs_are_the_default(self, scaffold_project):
        env = (scaffold_project(dict(SINGLE_TENANT, include_jobs=True)) / ".env").read_text()
        assert "FLASK_DEBUG=0" in env
        assert "FLASK_DEBUG=1\n" not in env
        assert "JOB_SERIALIZER=json" in env

    def test_debug_on_without_jobs(self, scaffold_project):
        env = (scaffold_project(SIMPLE) / ".env").read_text()
        assert "FLASK_DEBUG=1" in env
        assert "JOB_SERIALIZER" not in env


# =============================================================================
# Confirm modal wiring
# =============================================================================


class TestConfirmModal:
    def test_app_js_resolves_modal_inside_the_event_handler(self, scaffold_project):
        app_js = (scaffold_project(SINGLE_TENANT) / "static/js/app.js").read_text()

        handler = app_js[app_js.index('htmx:confirm'):]
        assert 'getElementById("confirm-modal")' in handler[:600], (
            "the modal must be looked up when the event fires, not at load time"
        )

        # No early return before the listener is registered
        before_handler = app_js[:app_js.index('htmx:confirm')]
        assert "if (!modal || !message) return;" not in before_handler

    def test_admin_js_does_not_register_a_second_confirm_handler(self, scaffold_project):
        admin_js = (scaffold_project(SINGLE_TENANT) / "static/js/admin.js").read_text()
        # A comment may mention the event; a second listener must not exist
        assert 'addEventListener("htmx:confirm"' not in admin_js
        assert "initConfirmModal" not in admin_js

    def test_admin_base_template_has_no_duplicate_modal(self, scaffold_project):
        template = (scaffold_project(SINGLE_TENANT) / "templates/pages/admin/base.html").read_text()
        assert 'id="confirm-modal"' not in template
        assert 'id="confirm-message"' not in template

        base = (scaffold_project(SINGLE_TENANT) / "templates/base.html").read_text()
        assert "{{ confirm_modal() }}" in base


# =============================================================================
# CLI surface
# =============================================================================


class TestCliOptions:
    def test_no_dead_template_option(self):
        from feather.cli.new import new

        option_names = {opt for param in new.params for opt in param.opts}
        assert "--template" not in option_names
        assert "--no-prompt" in option_names


# =============================================================================
# Frontend build (slow - needs npm)
# =============================================================================


@pytest.mark.skipif(shutil.which("npm") is None, reason="npm is not on PATH")
class TestViteBuild:
    """A scaffolded app's frontend actually builds.

    ``npm install`` rather than ``npm ci``: the scaffold ships package.json
    without a lockfile, which ``npm ci`` refuses. Only one app type is built -
    the install plus build takes on the order of a minute.
    """

    def test_simple_app_builds(self, scaffold_project):
        project = scaffold_project(SIMPLE)

        install = subprocess.run(
            ["npm", "install", "--no-audit", "--no-fund", "--prefer-offline"],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=900,
        )
        assert install.returncode == 0, f"npm install failed:\n{install.stderr}"

        build = subprocess.run(
            ["npx", "vite", "build"],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=900,
        )
        assert build.returncode == 0, f"vite build failed:\n{build.stdout}\n{build.stderr}"

        manifest = project / "static/dist/.vite/manifest.json"
        assert manifest.exists(), "vite build produced no manifest"

        entries = json.loads(manifest.read_text())
        assert any("vendor" in name for name in entries), (
            f"vendor entry missing from the build manifest: {sorted(entries)}"
        )
