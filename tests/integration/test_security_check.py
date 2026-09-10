"""Integration tests for `feather security-check`.

Runs the command against temp directories with crafted ``.env`` files and,
for app mode, a minimal ``app.py``/``config.py`` pair.
"""

import json
import os
import secrets
import sys

import pytest
from click.testing import CliRunner

pytestmark = pytest.mark.integration


STRONG_KEY = secrets.token_hex(32)

ENV_VARS_TO_CLEAR = [
    "FLASK_ENV", "FLASK_CONFIG", "FLASK_DEBUG", "DEBUG", "SECRET_KEY",
    "SESSION_COOKIE_SECURE", "SESSION_COOKIE_HTTPONLY", "SESSION_COOKIE_SAMESITE",
    "REMEMBER_COOKIE_SECURE", "REMEMBER_COOKIE_HTTPONLY", "WTF_CSRF_ENABLED",
    "JOB_BACKEND", "JOB_SERIALIZER", "REDIS_URL", "CACHE_URL",
    "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "OAUTH_CALLBACK_URL",
    "TRUSTED_HOSTS", "FEATHER_SECURITY_HEADERS", "DATABASE_URL",
]


@pytest.fixture
def project(tmp_path, monkeypatch):
    """An empty project directory with a clean environment, cwd inside it."""
    for var in ENV_VARS_TO_CLEAR:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    for mod in ("app", "config"):
        monkeypatch.delitem(sys.modules, mod, raising=False)
    (tmp_path / ".gitignore").write_text("venv/\n.env\n")
    return tmp_path


def write_env(project, **values):
    lines = [f"{k}={v}" for k, v in values.items()]
    (project / ".env").write_text("\n".join(lines) + "\n")


def run(*args):
    import feather.cli  # noqa: F401 - ensures the module is in sys.modules

    security_check = sys.modules["feather.cli.security_check"].security_check
    return CliRunner().invoke(security_check, list(args), catch_exceptions=False)


def parse(result):
    """Return {check name: (status, message)} from plain output."""
    rows = {}
    for line in result.output.splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2 and parts[0] in {"PASS", "WARN", "FAIL", "SKIP"}:
            rows[parts[1]] = (parts[0], parts[2] if len(parts) > 2 else "")
    return rows


PRODUCTION_ENV = dict(FLASK_ENV="production", SECRET_KEY=STRONG_KEY)


class TestEnvFileMode:
    def test_clean_production_env_passes(self, project):
        write_env(project, **PRODUCTION_ENV)
        result = run()
        rows = parse(result)

        assert result.exit_code == 0, result.output
        assert "FAIL" not in {status for status, _ in rows.values()}
        assert rows["secret_key"][0] == "PASS"
        assert rows["environment"][0] == "PASS"
        assert rows["debug"][0] == "PASS"
        assert rows["session_cookie_secure"][0] == "PASS"
        assert rows["session_cookie_httponly"][0] == "PASS"
        assert rows["remember_cookie_secure"][0] == "PASS"
        assert rows["remember_cookie_httponly"][0] == "PASS"
        assert rows["cookie_samesite"][0] == "PASS"
        assert rows["csrf"][0] == "PASS"
        assert rows["security_headers"][0] == "PASS"
        assert rows["env_in_gitignore"][0] == "PASS"
        assert rows["dep_flask"][0] == "PASS"

    def test_default_secret_key_fails(self, project):
        write_env(project, FLASK_ENV="production", SECRET_KEY="dev-secret-key-change-in-production")
        result = run()
        rows = parse(result)

        assert result.exit_code == 1
        assert rows["secret_key"][0] == "FAIL"
        assert "secrets.token_hex" in result.output

    def test_short_secret_key_fails(self, project):
        write_env(project, FLASK_ENV="production", SECRET_KEY="tooshort")
        assert parse(run())["secret_key"][0] == "FAIL"

    def test_no_environment_set_fails(self, project):
        write_env(project, SECRET_KEY=STRONG_KEY)
        result = run()
        rows = parse(result)

        assert result.exit_code == 1
        assert rows["environment"][0] == "FAIL"
        assert "FLASK_ENV" in rows["environment"][1] or "FLASK_ENV" in result.output

    def test_flask_config_shortcut_counts_as_production(self, project):
        write_env(project, FLASK_CONFIG="prod", SECRET_KEY=STRONG_KEY)
        rows = parse(run())
        assert rows["environment"][0] == "PASS"
        assert rows["session_cookie_secure"][0] == "PASS"

    def test_debug_in_production_fails(self, project):
        write_env(project, **PRODUCTION_ENV, FLASK_DEBUG="1")
        result = run()
        assert result.exit_code == 1
        assert parse(result)["debug"][0] == "FAIL"

    def test_cookie_flags_off_in_production_fail(self, project):
        write_env(
            project, **PRODUCTION_ENV,
            SESSION_COOKIE_SECURE="false", REMEMBER_COOKIE_HTTPONLY="0",
            SESSION_COOKIE_SAMESITE="None",
        )
        rows = parse(run())
        assert rows["session_cookie_secure"][0] == "FAIL"
        assert rows["remember_cookie_httponly"][0] == "FAIL"
        assert rows["cookie_samesite"][0] == "WARN"

    def test_csrf_disabled_fails(self, project):
        write_env(project, **PRODUCTION_ENV, WTF_CSRF_ENABLED="false")
        assert parse(run())["csrf"][0] == "FAIL"

    def test_rq_with_pickle_warns(self, project):
        write_env(project, **PRODUCTION_ENV, JOB_BACKEND="rq", REDIS_URL="redis://localhost:6379/0")
        result = run()
        rows = parse(result)

        assert result.exit_code == 0  # WARN alone does not fail the run
        assert rows["job_serializer"][0] == "WARN"
        assert "JOB_SERIALIZER=json" in result.output
        assert rows["redis_url"][0] == "PASS"  # localhost without password is fine

    def test_rq_with_json_passes(self, project):
        write_env(project, **PRODUCTION_ENV, JOB_BACKEND="rq", JOB_SERIALIZER="json")
        assert parse(run())["job_serializer"][0] == "PASS"

    def test_remote_redis_without_password_warns(self, project):
        write_env(
            project, **PRODUCTION_ENV,
            REDIS_URL="redis://red-abc123:6379",
            CACHE_URL="redis://:s3cret@red-abc123:6379/1",
        )
        rows = parse(run())
        assert rows["redis_url"][0] == "WARN"
        assert rows["cache_url"][0] == "PASS"

    def test_google_auth_without_callback_warns(self, project):
        write_env(project, **PRODUCTION_ENV, GOOGLE_CLIENT_ID="x.apps.googleusercontent.com", GOOGLE_CLIENT_SECRET="y")
        rows = parse(run())
        assert rows["oauth_callback_url"][0] == "WARN"

        write_env(
            project, **PRODUCTION_ENV, GOOGLE_CLIENT_ID="x", GOOGLE_CLIENT_SECRET="y",
            OAUTH_CALLBACK_URL="https://app.example.com/auth/callback",
        )
        assert parse(run())["oauth_callback_url"][0] == "PASS"

    def test_trusted_hosts_missing_warns(self, project):
        write_env(project, **PRODUCTION_ENV)
        assert parse(run())["trusted_hosts"][0] == "WARN"

        write_env(project, **PRODUCTION_ENV, TRUSTED_HOSTS="app.example.com")
        assert parse(run())["trusted_hosts"][0] == "PASS"

    def test_security_headers_disabled_fails(self, project):
        write_env(project, **PRODUCTION_ENV, FEATHER_SECURITY_HEADERS="false")
        assert parse(run())["security_headers"][0] == "FAIL"

    def test_env_not_in_gitignore_fails(self, project):
        write_env(project, **PRODUCTION_ENV)
        (project / ".gitignore").write_text("venv/\n")
        result = run()
        assert result.exit_code == 1
        assert parse(result)["env_in_gitignore"][0] == "FAIL"

        (project / ".gitignore").unlink()
        assert parse(run())["env_in_gitignore"][0] == "FAIL"

    def test_production_checks_skipped_outside_production(self, project):
        write_env(project, FLASK_ENV="development", SECRET_KEY=STRONG_KEY, FLASK_DEBUG="1")
        result = run()
        rows = parse(result)
        assert result.exit_code == 0, result.output
        assert rows["debug"][0] == "SKIP"
        assert rows["session_cookie_secure"][0] == "SKIP"

    def test_production_flag_forces_production_rules(self, project):
        write_env(project, FLASK_ENV="development", SECRET_KEY=STRONG_KEY, FLASK_DEBUG="1")
        result = run("--production")
        assert result.exit_code == 1
        assert parse(result)["debug"][0] == "FAIL"

    def test_env_file_option(self, project):
        write_env(project, FLASK_ENV="production", SECRET_KEY="dev-secret-key-change-in-production")
        (project / "deploy.env").write_text(f"FLASK_ENV=production\nSECRET_KEY={STRONG_KEY}\n")

        assert parse(run())["secret_key"][0] == "FAIL"
        result = run("--env-file", "deploy.env")
        assert parse(result)["secret_key"][0] == "PASS"
        assert result.exit_code == 0, result.output

    def test_missing_env_file_option_errors(self, project):
        result = run("--env-file", "nope.env")
        assert result.exit_code != 0
        assert "nope.env" in result.output


class TestDependencyVersions:
    def test_outdated_dependency_fails(self, project, monkeypatch):
        import importlib.metadata as metadata

        real_version = metadata.version

        def fake_version(name):
            if name == "flask":
                return "3.0.0"
            if name == "weasyprint":
                raise metadata.PackageNotFoundError(name)
            return real_version(name)

        # feather.cli.security_check is the command object (the package
        # re-exports it), so reach the module through sys.modules.
        module = sys.modules["feather.cli.security_check"]
        monkeypatch.setattr(module, "installed_version", fake_version)
        write_env(project, **PRODUCTION_ENV)
        result = run()
        rows = parse(result)

        assert result.exit_code == 1
        assert rows["dep_flask"][0] == "FAIL"
        assert "3.1.3" in rows["dep_flask"][1]
        assert rows["dep_weasyprint"][0] == "SKIP"
        assert rows["dep_jinja2"][0] == "PASS"


class TestJsonOutput:
    def test_json_structure(self, project):
        write_env(project, **PRODUCTION_ENV, JOB_BACKEND="rq")
        result = run("--json")

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["mode"] == "env"
        assert data["environment"] == "production"
        assert set(data["summary"]) >= {"pass", "warn", "fail", "skip"}
        assert data["summary"]["warn"] >= 1

        by_name = {c["name"]: c for c in data["checks"]}
        assert by_name["secret_key"]["status"] == "PASS"
        assert by_name["job_serializer"]["status"] == "WARN"
        assert by_name["job_serializer"]["remedy"]
        for check in data["checks"]:
            assert set(check) >= {"name", "status", "message", "remedy"}

    def test_json_reports_failure(self, project):
        write_env(project, FLASK_ENV="production", SECRET_KEY="short")
        result = run("--json")
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["summary"]["fail"] >= 1


class TestAppMode:
    def test_loads_app_config_when_importable(self, project):
        """With app.py present the live app.config is the source of truth."""
        write_env(project, **PRODUCTION_ENV)
        (project / "config.py").write_text(
            "import os\n"
            "class ProductionConfig:\n"
            "    SECRET_KEY = os.environ.get('SECRET_KEY')\n"
            "    DEBUG = False\n"
            "    SESSION_COOKIE_SECURE = True\n"
            "    SESSION_COOKIE_HTTPONLY = True\n"
            "    SESSION_COOKIE_SAMESITE = 'Lax'\n"
            "    REMEMBER_COOKIE_SECURE = False\n"  # deliberately wrong, not in .env
            "    REMEMBER_COOKIE_HTTPONLY = True\n"
            "    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'\n"
            "    TRUSTED_HOSTS = ['app.example.com']\n"
            "config = {'production': ProductionConfig, 'default': ProductionConfig}\n"
        )
        (project / "app.py").write_text("from feather import Feather\napp = Feather(__name__)\n")

        result = run("--json")
        data = json.loads(result.output)
        by_name = {c["name"]: c for c in data["checks"]}

        assert data["mode"] == "app"
        assert by_name["secret_key"]["status"] == "PASS"
        assert by_name["remember_cookie_secure"]["status"] == "FAIL"
        assert by_name["trusted_hosts"]["status"] == "PASS"
        assert result.exit_code == 1

    def test_degrades_to_env_mode_when_app_import_fails(self, project):
        write_env(project, **PRODUCTION_ENV)
        (project / "app.py").write_text("raise RuntimeError('boom at import')\n")

        result = run("--json")
        data = json.loads(result.output)
        assert data["mode"] == "env"
        assert "boom at import" in data["notes"][0]
        assert {c["name"]: c for c in data["checks"]}["secret_key"]["status"] == "PASS"
