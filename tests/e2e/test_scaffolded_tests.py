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
