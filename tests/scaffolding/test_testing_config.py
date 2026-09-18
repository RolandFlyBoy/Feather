"""A scaffolded app's tests run against a database of their own.

The generated conftest used to build its app from app.py, whose config points
at DATABASE_URL: the developer's own database in development, and whatever the
environment says in CI. The suite creates and drops the schema around the run,
so `feather test` emptied the database the app was being built against.

Generated apps now carry a TestingConfig, and the conftest builds the app from
it. These tests pin down where that config sends the tests, and that a
generated suite really runs there.
"""

import importlib.util
import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.scaffolding


NO_DATABASE = {"database": "none"}

SQLITE_AUTH = {
    "database": "sqlite",
    "db_url": "sqlite:///app.db",
    "include_auth": True,
    "tenant_mode": "single",
    "admin_email": "admin@test.com",
}

POSTGRES = {"database": "postgresql", "db_url": "postgresql://localhost/shop"}


def load_config(project, **environment):
    """Import a generated config.py under a chosen environment.

    Its classes read os.environ in their bodies, which is the whole question
    here, so each case gets its own module object rather than a cached one.
    """
    saved = dict(os.environ)
    for key in ("DATABASE_URL", "TEST_DATABASE_URL"):
        os.environ.pop(key, None)
    os.environ.update(environment)
    name = f"scaffolded_config_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(name, project / "config.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        os.environ.clear()
        os.environ.update(saved)
    return module


# =============================================================================
# Where the test database comes from
# =============================================================================


class TestTestingConfig:
    def test_postgres_apps_get_a_test_database_of_their_own(self, scaffold_project):
        config = load_config(
            scaffold_project(POSTGRES), DATABASE_URL="postgresql://localhost/shop"
        )
        assert config.Config.DATABASE_URL == "postgresql://localhost/shop"
        assert config.TestingConfig.DATABASE_URL == "postgresql://localhost/shop_test"

    def test_sqlite_apps_run_in_memory(self, scaffold_project):
        config = load_config(scaffold_project(SQLITE_AUTH), DATABASE_URL="sqlite:///app.db")
        assert config.TestingConfig.DATABASE_URL == "sqlite:///:memory:"

    def test_apps_with_no_database_run_in_memory(self, scaffold_project):
        config = load_config(scaffold_project(NO_DATABASE))
        assert config.TestingConfig.DATABASE_URL == "sqlite:///:memory:"

    @pytest.mark.parametrize("app", [POSTGRES, SQLITE_AUTH, NO_DATABASE], ids=["postgres", "sqlite", "none"])
    def test_test_database_url_wins(self, scaffold_project, app):
        """CI hands the suite a throwaway database through the environment."""
        config = load_config(
            scaffold_project(app),
            DATABASE_URL="postgresql://localhost/shop",
            TEST_DATABASE_URL="postgresql://ci/throwaway",
        )
        assert config.TestingConfig.DATABASE_URL == "postgresql://ci/throwaway"

    @pytest.mark.parametrize("app", [POSTGRES, SQLITE_AUTH, NO_DATABASE], ids=["postgres", "sqlite", "none"])
    def test_testing_is_on_and_named_in_the_config_map(self, scaffold_project, app):
        config = load_config(scaffold_project(app))
        assert config.TestingConfig.TESTING is True
        assert config.config["testing"] is config.TestingConfig


# =============================================================================
# The generated conftest
# =============================================================================


class TestGeneratedConftest:
    @pytest.mark.parametrize("app", [SQLITE_AUTH, NO_DATABASE], ids=["database", "none"])
    def test_builds_the_app_from_the_testing_config(self, scaffold_project, app):
        conftest = (scaffold_project(app) / "tests/conftest.py").read_text()
        assert 'Feather("app", config_class="config.TestingConfig")' in conftest

    @pytest.mark.parametrize("app", [SQLITE_AUTH, NO_DATABASE], ids=["database", "none"])
    def test_does_not_import_the_app_module(self, scaffold_project, app):
        """Importing it would hand the tests the development configuration."""
        conftest = (scaffold_project(app) / "tests/conftest.py").read_text()
        assert "from app import" not in conftest

    def test_creates_and_drops_the_schema(self, scaffold_project):
        conftest = (scaffold_project(SQLITE_AUTH) / "tests/conftest.py").read_text()
        assert "db.create_all()" in conftest
        assert "db.drop_all()" in conftest

    def test_keeps_the_client_fixtures(self, scaffold_project):
        conftest = (scaffold_project(SQLITE_AUTH) / "tests/conftest.py").read_text()
        assert "def client(app)" in conftest
        assert "def csrf_client(app)" in conftest


# =============================================================================
# The generated suite, run
# =============================================================================


def test_a_generated_suite_runs_against_the_test_database(scaffold_project):
    """The proof: the test database is written to and the app's is not.

    TEST_DATABASE_URL points at a SQLite file, so a run that used it leaves
    that file behind. A run that used the app's own configuration would leave
    instance/app.db instead, which is the bug this replaced.
    """
    project = scaffold_project(SQLITE_AUTH)
    test_db = project / "tests.db"

    environment = dict(os.environ)
    environment.pop("DATABASE_URL", None)
    environment["TEST_DATABASE_URL"] = f"sqlite:///{test_db}"

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=str(project),
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert test_db.exists(), "the suite never touched the test database"
    assert not (project / "app.db").exists()
    assert not (project / "instance").exists()
