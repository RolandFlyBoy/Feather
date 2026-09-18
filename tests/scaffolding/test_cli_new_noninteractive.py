"""`feather new` driven entirely from flags, the way an orchestrator drives it.

The platform scaffolds an app on a server, with no terminal to answer prompts
on and no human to read "Next steps". These tests run the command end to end
for the two configurations that matter to it, a single-tenant PostgreSQL app
and a multi-tenant one, and check both the project on disk and the JSON.

The parts that need a network or a database (npm, pip, createdb, the first
migration) are replaced: they are not what these tests are about.
"""

import json
import sys

import pytest
from click.testing import CliRunner

from feather.cli.new import new

pytestmark = pytest.mark.scaffolding

# feather/cli/__init__.py binds the `new` *command* as an attribute of the
# feather.cli package, shadowing the submodule of the same name. Reach the
# real module through sys.modules instead.
new_module = sys.modules["feather.cli.new"]

SINGLE_TENANT = [
    "--app-type", "single-tenant",
    "--database", "postgresql",
    "--jobs",
    "--cache",
    "--storage",
    "--no-email",
    "--no-auto-approve-users",
    "--admin-email", "admin@example.com",
]

MULTI_TENANT = [
    "--app-type", "multi-tenant",
    "--no-jobs",
    "--no-cache",
    "--no-storage",
    "--no-email",
    "--no-auto-approve-users",
    "--admin-email", "platform@example.com",
]


@pytest.fixture
def scaffold(tmp_path, monkeypatch):
    """Run `feather new` in an empty directory, without touching the network."""
    monkeypatch.chdir(tmp_path)
    created = []

    def _created(db_name):
        created.append(db_name)
        return True

    monkeypatch.setattr(new_module, "_create_database", _created)
    monkeypatch.setattr(new_module, "_init_git", lambda path: None)
    monkeypatch.setattr(new_module, "_install_dependencies", lambda path: None)
    monkeypatch.setattr(new_module, "_setup_venv", lambda path: None)
    monkeypatch.setattr(new_module, "_create_initial_migration", lambda path: True)

    def _run(*args):
        result = CliRunner().invoke(new, ["shop", *args], catch_exceptions=False)
        assert result.exit_code == 0, result.output
        return result, tmp_path / "shop"

    _run.databases_created = created
    return _run


class TestSingleTenantPostgres:
    def test_the_project_is_built(self, scaffold):
        _, project = scaffold(*SINGLE_TENANT)
        assert (project / "app.py").exists()
        assert (project / "models/user.py").exists()
        assert (project / "seeds.py").exists()

    def test_the_database_is_created(self, scaffold):
        scaffold(*SINGLE_TENANT)
        assert scaffold.databases_created == ["shop"]

    def test_the_features_asked_for_are_in_the_project(self, scaffold):
        _, project = scaffold(*SINGLE_TENANT)
        env = (project / ".env").read_text()
        config = (project / "config.py").read_text()
        assert "REDIS_URL" in env
        assert "STORAGE_BACKEND" in config
        assert "RESEND_API_KEY" not in config
        assert not (project / "services/email_service.py").exists()

    def test_the_admin_email_reaches_seeds(self, scaffold):
        _, project = scaffold(*SINGLE_TENANT)
        assert "admin@example.com" in (project / "seeds.py").read_text()

    def test_it_is_single_tenant(self, scaffold):
        _, project = scaffold(*SINGLE_TENANT)
        assert "FEATHER_MULTI_TENANT = False" in (project / "config.py").read_text()

    def test_no_prompt_is_not_needed(self, scaffold):
        """The flags answer every question, so the command asks nothing."""
        result, _ = scaffold(*SINGLE_TENANT)
        assert "Select type" not in result.output
        assert "Project Configuration" not in result.output


class TestMultiTenant:
    def test_postgresql_without_asking(self, scaffold):
        _, project = scaffold(*MULTI_TENANT)
        assert "FEATHER_MULTI_TENANT = True" in (project / "config.py").read_text()
        assert (project / "models/tenant.py").exists()
        assert scaffold.databases_created == ["shop"]

    def test_the_database_name_can_be_chosen(self, scaffold):
        scaffold(*MULTI_TENANT, "--db-name", "shop_platform")
        assert scaffold.databases_created == ["shop_platform"]


class TestJsonOutput:
    def test_stdout_is_one_json_object(self, scaffold):
        result, project = scaffold(*SINGLE_TENANT, "--json")
        payload = json.loads(result.output)
        assert payload["path"] == str(project)
        assert payload["app_type"] == "single-tenant"
        assert payload["database"] == "postgresql"
        assert payload["database_url"] == "postgresql://localhost/shop"
        assert payload["jobs"] is True
        assert payload["cache"] is True
        assert payload["storage"] is True
        assert payload["email"] is False
        assert payload["admin_email"] == "admin@example.com"
        assert payload["migration_created"] is True

    def test_the_progress_narration_is_gone(self, scaffold):
        """A caller parses the whole of stdout, so nothing else may be on it."""
        result, _ = scaffold(*SINGLE_TENANT, "--json")
        assert "Creating new Feather project" not in result.output
        assert "Next steps" not in result.output

    def test_a_simple_app_reports_no_database(self, scaffold):
        result, _ = scaffold("--no-prompt", "--json")
        payload = json.loads(result.output)
        assert payload["database"] == "none"
        assert payload["database_url"] is None
        assert payload["migration_created"] is False

    def test_a_sqlite_app_reports_its_url(self, scaffold):
        """--json never prompts, so an open question takes its default."""
        result, _ = scaffold(
            "--app-type", "single-tenant",
            "--database", "sqlite",
            "--no-jobs", "--no-cache", "--no-storage", "--no-email",
            "--admin-email", "admin@example.com",
            "--json",
        )
        payload = json.loads(result.output)
        assert payload["database"] == "sqlite"
        assert payload["database_url"] == "sqlite:///app.db"


class TestHumanOutput:
    """Without --json the closing text is what it always was."""

    def test_next_steps_are_printed(self, scaffold):
        result, _ = scaffold(*SINGLE_TENANT)
        assert "Project created successfully!" in result.output
        assert "Next steps:" in result.output
        assert "python seeds.py" in result.output
        assert "Admin user will be created for: admin@example.com" in result.output

    def test_infrastructure_notes_follow_the_flags(self, scaffold):
        result, _ = scaffold(*SINGLE_TENANT)
        assert "Redis (for caching): redis-server" in result.output
        assert "Resend" not in result.output
