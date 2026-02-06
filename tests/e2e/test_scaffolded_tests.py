"""E2E tests that verify scaffolded app tests actually run and pass.

This test scaffolds a complete app, installs dependencies, and runs pytest
to verify the generated tests work correctly.

Run with: pytest tests/e2e/test_scaffolded_tests.py -v
"""

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture
def feather_root():
    """Path to the Feather framework root."""
    return Path(__file__).parent.parent.parent


class TestScaffoldedTestsRun:
    """Verify scaffolded tests actually execute and pass."""

    @pytest.fixture
    def scaffolded_app(self, temp_project_dir, feather_root):
        """Scaffold an app with auth and set up its environment."""
        from feather.cli.new import _create_project_structure, _create_project_files

        project_path = temp_project_dir / "testapp"
        project_path.mkdir()

        # Scaffold with auth enabled (single-tenant for simplicity)
        _create_project_structure(project_path, database="sqlite", include_auth=True)
        _create_project_files(
            project_path=project_path,
            name="testapp",
            database="sqlite",
            include_auth=True,
            db_url="sqlite:///app.db",
            tenant_mode="single",
            admin_email="admin@test.com",
        )

        # Create venv and install dependencies
        venv_path = project_path / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            check=True,
            capture_output=True,
        )

        # Get pip path
        if sys.platform == "win32":
            pip = venv_path / "Scripts" / "pip"
            python = venv_path / "Scripts" / "python"
        else:
            pip = venv_path / "bin" / "pip"
            python = venv_path / "bin" / "python"

        # Install Feather framework (editable install from source)
        subprocess.run(
            [str(pip), "install", "-e", str(feather_root)],
            check=True,
            capture_output=True,
        )

        # Install pytest (in case not bundled)
        subprocess.run(
            [str(pip), "install", "pytest"],
            check=True,
            capture_output=True,
        )

        return {
            "path": project_path,
            "python": python,
            "pip": pip,
        }

    def test_scaffolded_tests_syntax_valid(self, scaffolded_app):
        """All scaffolded test files have valid Python syntax."""
        import py_compile

        project_path = scaffolded_app["path"]
        test_files = list((project_path / "tests").glob("*.py"))

        assert len(test_files) >= 3  # conftest, test_auth, test_admin

        for test_file in test_files:
            # This raises SyntaxError if invalid
            py_compile.compile(str(test_file), doraise=True)

    def test_scaffolded_tests_importable(self, scaffolded_app):
        """Scaffolded test files can be imported without errors."""
        python = scaffolded_app["python"]
        project_path = scaffolded_app["path"]

        # Try to import the test modules
        result = subprocess.run(
            [
                str(python),
                "-c",
                "import sys; sys.path.insert(0, '.'); "
                "from tests.conftest import *; "
                "print('conftest OK')",
            ],
            cwd=str(project_path),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "conftest OK" in result.stdout

    def test_scaffolded_auth_tests_pass(self, scaffolded_app):
        """Scaffolded auth tests run and pass."""
        python = scaffolded_app["python"]
        project_path = scaffolded_app["path"]

        result = subprocess.run(
            [
                str(python),
                "-m",
                "pytest",
                "tests/test_auth.py",
                "-v",
                "--tb=short",
            ],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Print output for debugging if failed
        if result.returncode != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.returncode == 0, f"Auth tests failed:\n{result.stdout}\n{result.stderr}"
        assert "passed" in result.stdout

    def test_scaffolded_admin_tests_pass(self, scaffolded_app):
        """Scaffolded admin tests run and pass."""
        python = scaffolded_app["python"]
        project_path = scaffolded_app["path"]

        result = subprocess.run(
            [
                str(python),
                "-m",
                "pytest",
                "tests/test_admin.py",
                "-v",
                "--tb=short",
            ],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.returncode == 0, f"Admin tests failed:\n{result.stdout}\n{result.stderr}"
        assert "passed" in result.stdout

    def test_all_scaffolded_tests_pass(self, scaffolded_app):
        """All scaffolded tests run and pass together."""
        python = scaffolded_app["python"]
        project_path = scaffolded_app["path"]

        result = subprocess.run(
            [
                str(python),
                "-m",
                "pytest",
                "tests/",
                "-v",
                "--tb=short",
            ],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.returncode == 0, f"Tests failed:\n{result.stdout}\n{result.stderr}"
        assert "passed" in result.stdout
        # Should have no failures
        assert "failed" not in result.stdout.lower() or "0 failed" in result.stdout.lower()


class TestMigrationsWork:
    """Verify migrations can be generated and applied on scaffolded apps."""

    @pytest.fixture
    def scaffolded_app_for_migration(self, temp_project_dir, feather_root):
        """Scaffold an app with auth for migration testing."""
        from feather.cli.new import _create_project_structure, _create_project_files

        project_path = temp_project_dir / "migrationtestapp"
        project_path.mkdir()

        # Scaffold with auth enabled (single-tenant for simplicity)
        _create_project_structure(project_path, database="sqlite", include_auth=True)
        _create_project_files(
            project_path=project_path,
            name="migrationtestapp",
            database="sqlite",
            include_auth=True,
            db_url="sqlite:///app.db",
            tenant_mode="single",
            admin_email="admin@test.com",
        )

        # Create venv and install dependencies
        venv_path = project_path / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            check=True,
            capture_output=True,
        )

        # Get pip/python paths
        if sys.platform == "win32":
            pip = venv_path / "Scripts" / "pip"
            python = venv_path / "Scripts" / "python"
            feather_cmd = venv_path / "Scripts" / "feather"
        else:
            pip = venv_path / "bin" / "pip"
            python = venv_path / "bin" / "python"
            feather_cmd = venv_path / "bin" / "feather"

        # Install Feather framework (editable install from source)
        subprocess.run(
            [str(pip), "install", "-e", str(feather_root)],
            check=True,
            capture_output=True,
        )

        return {
            "path": project_path,
            "python": python,
            "pip": pip,
            "feather": feather_cmd,
        }

    def test_migrations_apply_cleanly(self, scaffolded_app_for_migration):
        """Verify generated migrations can be applied to a fresh database.

        This test catches foreign key ordering issues where tables are created
        in the wrong order (e.g., accounts before users when accounts has FK to users).
        """
        project_path = scaffolded_app_for_migration["path"]
        feather_cmd = scaffolded_app_for_migration["feather"]

        # Generate migration
        result = subprocess.run(
            [str(feather_cmd), "db", "migrate", "-m", "initial"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            print("MIGRATE STDOUT:", result.stdout)
            print("MIGRATE STDERR:", result.stderr)

        assert result.returncode == 0, f"Migration generation failed:\n{result.stdout}\n{result.stderr}"

        # Apply migration
        result = subprocess.run(
            [str(feather_cmd), "db", "upgrade"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            print("UPGRADE STDOUT:", result.stdout)
            print("UPGRADE STDERR:", result.stderr)

        assert result.returncode == 0, f"Migration upgrade failed:\n{result.stdout}\n{result.stderr}"


class TestMultiTenantMigrationsWork:
    """Verify migrations work for multi-tenant apps with circular FK dependencies."""

    @pytest.fixture
    def scaffolded_multitenant_app(self, temp_project_dir, feather_root):
        """Scaffold a multi-tenant app for migration testing."""
        from feather.cli.new import _create_project_structure, _create_project_files

        project_path = temp_project_dir / "multitenanttestapp"
        project_path.mkdir()

        # Scaffold with auth enabled AND multi-tenant mode
        _create_project_structure(project_path, database="sqlite", include_auth=True)
        _create_project_files(
            project_path=project_path,
            name="multitenanttestapp",
            database="sqlite",
            include_auth=True,
            db_url="sqlite:///app.db",
            tenant_mode="multi",  # Multi-tenant triggers more complex FK relationships
            admin_email="admin@test.com",
        )

        # Create venv and install dependencies
        venv_path = project_path / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            check=True,
            capture_output=True,
        )

        # Get paths
        if sys.platform == "win32":
            pip = venv_path / "Scripts" / "pip"
            feather_cmd = venv_path / "Scripts" / "feather"
        else:
            pip = venv_path / "bin" / "pip"
            feather_cmd = venv_path / "bin" / "feather"

        # Install Feather framework (editable install from source)
        subprocess.run(
            [str(pip), "install", "-e", str(feather_root)],
            check=True,
            capture_output=True,
        )

        return {
            "path": project_path,
            "pip": pip,
            "feather": feather_cmd,
        }

    def test_multitenant_migrations_apply_cleanly(self, scaffolded_multitenant_app):
        """Verify multi-tenant migrations work with circular User<->Account FKs.

        Multi-tenant apps have:
        - User.subscription_owner_account_id -> accounts.id
        - Account.owner_user_id -> users.id

        Both FKs need use_alter=True to avoid circular dependency issues.
        """
        project_path = scaffolded_multitenant_app["path"]
        feather_cmd = scaffolded_multitenant_app["feather"]

        # Generate migration
        result = subprocess.run(
            [str(feather_cmd), "db", "migrate", "-m", "initial"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            print("MIGRATE STDOUT:", result.stdout)
            print("MIGRATE STDERR:", result.stderr)

        assert result.returncode == 0, f"Migration generation failed:\n{result.stdout}\n{result.stderr}"

        # Apply migration
        result = subprocess.run(
            [str(feather_cmd), "db", "upgrade"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            print("UPGRADE STDOUT:", result.stdout)
            print("UPGRADE STDERR:", result.stderr)

        assert result.returncode == 0, f"Multi-tenant migration upgrade failed:\n{result.stdout}\n{result.stderr}"


# =============================================================================
# Scaffolding Matrix: verify all meaningful CLI option combos produce runnable apps
# =============================================================================

# SQLite configs: scaffold + venv + install + run all generated tests
SQLITE_CONFIGS = [
    pytest.param(
        {
            "database": "none",
        },
        id="simple-no-db",
    ),
    pytest.param(
        {
            "database": "sqlite",
            "db_url": "sqlite:///app.db",
            "include_jobs": True,
        },
        id="simple-sqlite-jobs",
    ),
    pytest.param(
        {
            "database": "sqlite",
            "db_url": "sqlite:///app.db",
            "include_auth": True,
            "tenant_mode": "single",
            "admin_email": "admin@test.com",
        },
        id="single-manual-approve",
    ),
    pytest.param(
        {
            "database": "sqlite",
            "db_url": "sqlite:///app.db",
            "include_auth": True,
            "tenant_mode": "single",
            "admin_email": "admin@test.com",
            "auto_approve_users": True,
            "include_jobs": True,
            "include_cache": True,
            "include_storage": True,
            "storage_backend": "gcs",
            "include_email": True,
        },
        id="single-auto-approve-all-features",
    ),
    pytest.param(
        {
            "database": "sqlite",
            "db_url": "sqlite:///app.db",
            "include_auth": True,
            "tenant_mode": "single",
            "admin_email": "admin@test.com",
            "auto_approve_users": True,
            "user_fields": {"display_name": False, "profile_image_url": True},
        },
        id="single-auto-approve-no-displayname",
    ),
    pytest.param(
        {
            "database": "sqlite",
            "db_url": "sqlite:///app.db",
            "include_auth": True,
            "tenant_mode": "single",
            "admin_email": "admin@test.com",
            "user_fields": {"display_name": False, "profile_image_url": True},
        },
        id="single-manual-approve-no-displayname",
    ),
]

# PostgreSQL configs: scaffold + venv + install + syntax/import check only (no PG server)
POSTGRESQL_CONFIGS = [
    pytest.param(
        {
            "database": "postgresql",
            "db_url": "postgresql://localhost/testdb",
            "include_auth": True,
            "tenant_mode": "multi",
            "admin_email": "admin@test.com",
        },
        id="multi-tenant-defaults",
    ),
    pytest.param(
        {
            "database": "postgresql",
            "db_url": "postgresql://localhost/testdb",
            "include_auth": True,
            "tenant_mode": "multi",
            "admin_email": "admin@test.com",
            "auto_approve_users": True,
            "include_jobs": True,
            "include_cache": True,
            "include_storage": True,
            "storage_backend": "gcs",
            "include_email": True,
        },
        id="multi-tenant-all-features",
    ),
]


def _scaffold_and_install(config, project_path, feather_root):
    """Scaffold an app, create venv, and install dependencies.

    Shared helper for the matrix test classes.
    """
    from feather.cli.new import _create_project_structure, _create_project_files

    database = config.get("database", "none")
    include_auth = config.get("include_auth", False)

    _create_project_structure(project_path, database=database, include_auth=include_auth)
    _create_project_files(
        project_path=project_path,
        name=project_path.name,
        database=database,
        include_auth=include_auth,
        db_url=config.get("db_url"),
        tenant_mode=config.get("tenant_mode"),
        admin_email=config.get("admin_email"),
        auto_approve_users=config.get("auto_approve_users", False),
        include_cache=config.get("include_cache", False),
        include_jobs=config.get("include_jobs", False),
        include_storage=config.get("include_storage", False),
        storage_backend=config.get("storage_backend"),
        include_email=config.get("include_email", False),
        user_fields=config.get("user_fields"),
    )

    # Create venv and install dependencies
    venv_path = project_path / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_path)],
        check=True,
        capture_output=True,
    )

    if sys.platform == "win32":
        pip = venv_path / "Scripts" / "pip"
        python = venv_path / "Scripts" / "python"
    else:
        pip = venv_path / "bin" / "pip"
        python = venv_path / "bin" / "python"

    subprocess.run(
        [str(pip), "install", "-e", str(feather_root)],
        check=True,
        capture_output=True,
    )

    subprocess.run(
        [str(pip), "install", "pytest"],
        check=True,
        capture_output=True,
    )

    return {"path": project_path, "python": python, "pip": pip}


class TestScaffoldedAppMatrix:
    """Verify scaffolded apps with various CLI option combos produce runnable tests.

    Tests each meaningful axis: app type, database, auth, auto-approve,
    display_name, and optional features (jobs, cache, storage, email).
    """

    @pytest.fixture(params=SQLITE_CONFIGS)
    def scaffolded_app(self, request, temp_project_dir, feather_root):
        """Scaffold and install an app for each SQLite config."""
        config = request.param
        project_path = temp_project_dir / f"matrix_{request.param_index}"
        project_path.mkdir()
        return _scaffold_and_install(config, project_path, feather_root)

    def test_syntax_valid(self, scaffolded_app):
        """All generated Python files have valid syntax."""
        import py_compile

        project_path = scaffolded_app["path"]
        py_files = list(project_path.rglob("*.py"))
        # Exclude venv
        py_files = [f for f in py_files if "venv" not in f.parts]

        for py_file in py_files:
            py_compile.compile(str(py_file), doraise=True)

    def test_all_tests_pass(self, scaffolded_app):
        """All scaffolded tests run and pass."""
        python = scaffolded_app["python"]
        project_path = scaffolded_app["path"]

        # Some configs don't generate a tests/ dir (e.g. simple no-db)
        tests_dir = project_path / "tests"
        if not tests_dir.exists() or not list(tests_dir.glob("test_*.py")):
            pytest.skip("No test files generated for this config")

        result = subprocess.run(
            [str(python), "-m", "pytest", "tests/", "-v", "--tb=short"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.returncode == 0, f"Tests failed:\n{result.stdout}\n{result.stderr}"


class TestPostgreSQLScaffoldMatrix:
    """Verify PostgreSQL scaffolded apps have valid syntax and imports.

    Can't run migrations or full tests without a PG server,
    so we just verify the generated code is syntactically valid.
    """

    @pytest.fixture(params=POSTGRESQL_CONFIGS)
    def scaffolded_app(self, request, temp_project_dir, feather_root):
        """Scaffold and install an app for each PostgreSQL config."""
        config = request.param
        project_path = temp_project_dir / f"pg_matrix_{request.param_index}"
        project_path.mkdir()
        return _scaffold_and_install(config, project_path, feather_root)

    def test_syntax_valid(self, scaffolded_app):
        """All generated Python files have valid syntax."""
        import py_compile

        project_path = scaffolded_app["path"]
        py_files = list(project_path.rglob("*.py"))
        py_files = [f for f in py_files if "venv" not in f.parts]

        for py_file in py_files:
            py_compile.compile(str(py_file), doraise=True)

    def test_imports_work(self, scaffolded_app):
        """Scaffolded code can be imported without errors."""
        python = scaffolded_app["python"]
        project_path = scaffolded_app["path"]

        result = subprocess.run(
            [
                str(python),
                "-c",
                "import sys; sys.path.insert(0, '.'); "
                "from tests.conftest import *; "
                "print('conftest OK')",
            ],
            cwd=str(project_path),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "conftest OK" in result.stdout
