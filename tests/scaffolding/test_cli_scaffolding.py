"""Tests for CLI scaffolding - verifies correct files are generated for each configuration."""

import py_compile
import pytest

pytestmark = pytest.mark.scaffolding


class TestMinimalApp:
    """Test scaffolding with no database (minimal app)."""

    def test_creates_core_files(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        assert (project / "app.py").exists()
        assert (project / "config.py").exists()
        assert (project / ".env").exists()
        assert (project / "CLAUDE.md").exists()

    def test_no_database_directories(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        assert not (project / "models").exists()
        assert not (project / "migrations").exists()

    def test_no_sqlalchemy_in_config(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        config = (project / "config.py").read_text()
        assert "SQLALCHEMY" not in config

    def test_no_sqlalchemy_in_requirements(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        reqs = (project / "requirements.txt").read_text()
        assert "Flask-SQLAlchemy" not in reqs

    def test_conftest_no_db_import(self, scaffold_project):
        project = scaffold_project({"database": "none"})
        conftest = (project / "tests/conftest.py").read_text()
        assert "from feather.db import db" not in conftest


class TestSQLiteNoAuth:
    """Test scaffolding with SQLite database, no auth."""

    def test_has_models_directory(self, scaffold_project):
        project = scaffold_project({"database": "sqlite", "db_url": "sqlite:///app.db"})
        assert (project / "models").is_dir()
        assert (project / "models/__init__.py").exists()

    def test_no_user_model(self, scaffold_project):
        project = scaffold_project({"database": "sqlite", "db_url": "sqlite:///app.db"})
        assert not (project / "models/user.py").exists()

    def test_has_migrations(self, scaffold_project):
        project = scaffold_project({"database": "sqlite", "db_url": "sqlite:///app.db"})
        assert (project / "migrations").is_dir()
        assert (project / "migrations/alembic.ini").exists()

    def test_sqlite_url_in_config(self, scaffold_project):
        project = scaffold_project({"database": "sqlite", "db_url": "sqlite:///app.db"})
        config = (project / "config.py").read_text()
        assert "sqlite:///app.db" in config

    def test_no_psycopg_in_requirements(self, scaffold_project):
        project = scaffold_project({"database": "sqlite", "db_url": "sqlite:///app.db"})
        reqs = (project / "requirements.txt").read_text()
        # psycopg2 not explicitly listed (comes from Feather)
        assert "psycopg2-binary" not in reqs
        # Core deps come from Feather framework
        assert "Feather framework" in reqs


class TestSQLiteWithAuth:
    """Test scaffolding with SQLite + auth (forced single-tenant)."""

    CONFIG = {
        "database": "sqlite",
        "db_url": "sqlite:///app.db",
        "include_auth": True,
        "tenant_mode": "single",
        "admin_email": "admin@test.com",
    }

    def test_user_model_exists(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "models/user.py").exists()

    def test_user_model_no_tenant_fields(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        user_model = (project / "models/user.py").read_text()
        assert "tenant_id" not in user_model
        assert "is_platform_admin" not in user_model

    def test_no_tenant_model(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert not (project / "models/tenant.py").exists()

    def test_seeds_file_exists(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "seeds.py").exists()

    def test_multi_tenant_false_in_config(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        config = (project / "config.py").read_text()
        assert "FEATHER_MULTI_TENANT = False" in config


class TestPostgreSQLNoAuth:
    """Test scaffolding with PostgreSQL database, no auth."""

    CONFIG = {
        "database": "postgresql",
        "db_url": "postgresql://localhost/testapp",
    }

    def test_has_models_directory(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "models").is_dir()
        assert (project / "models/__init__.py").exists()

    def test_no_user_model(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert not (project / "models/user.py").exists()

    def test_has_migrations(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "migrations").is_dir()
        assert (project / "migrations/alembic.ini").exists()

    def test_requirements_references_feather(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        reqs = (project / "requirements.txt").read_text()
        # psycopg2 comes from Feather framework, not listed explicitly
        assert "Feather framework" in reqs


class TestPostgreSQLSingleTenant:
    """Test scaffolding with PostgreSQL + auth (single-tenant)."""

    CONFIG = {
        "database": "postgresql",
        "db_url": "postgresql://localhost/testapp",
        "include_auth": True,
        "tenant_mode": "single",
        "admin_email": "admin@test.com",
    }

    def test_user_model_exists(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "models/user.py").exists()

    def test_user_model_no_tenant_fields(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        user_model = (project / "models/user.py").read_text()
        assert "tenant_id" not in user_model
        assert "is_platform_admin" not in user_model

    def test_no_tenant_model(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert not (project / "models/tenant.py").exists()

    def test_requirements_references_feather(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        reqs = (project / "requirements.txt").read_text()
        # psycopg2 comes from Feather framework, not listed explicitly
        assert "Feather framework" in reqs

    def test_multi_tenant_false_in_config(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        config = (project / "config.py").read_text()
        assert "FEATHER_MULTI_TENANT = False" in config

    def test_seeds_file_exists(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "seeds.py").exists()

    def test_seeds_no_platform_admin(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        seeds = (project / "seeds.py").read_text()
        assert "is_platform_admin" not in seeds


class TestPostgreSQLMultiTenant:
    """Test scaffolding with PostgreSQL + auth (multi-tenant)."""

    CONFIG = {
        "database": "postgresql",
        "db_url": "postgresql://localhost/testapp",
        "include_auth": True,
        "tenant_mode": "multi",
        "admin_email": "admin@test.com",
    }

    def test_user_model_has_tenant_fields(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        user_model = (project / "models/user.py").read_text()
        assert "tenant_id" in user_model
        assert "is_platform_admin" in user_model

    def test_tenant_model_exists(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "models/tenant.py").exists()

    def test_multi_tenant_true_in_config(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        config = (project / "config.py").read_text()
        assert "FEATHER_MULTI_TENANT = True" in config

    def test_log_has_tenant_id(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        log_model = (project / "models/log.py").read_text()
        assert "tenant_id" in log_model

    def test_seeds_has_platform_admin(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        seeds = (project / "seeds.py").read_text()
        assert "is_platform_admin" in seeds

    def test_seeds_tenant_creation_uses_valid_columns(self, scaffold_project):
        """Ensure Tenant() calls in seeds.py only use valid Tenant columns.

        Tenant model has: id, slug, domain, name, status, created_at, updated_at
        User model has: approved_at (but Tenant does NOT)
        """
        project = scaffold_project(self.CONFIG)
        seeds = (project / "seeds.py").read_text()

        # Check that _create_tenant_from_email doesn't use User columns on Tenant
        # approved_at is a User column, not a Tenant column
        assert "Tenant(" in seeds, "seeds.py should create Tenant objects"

        # Find Tenant creation blocks and check they don't use invalid columns
        import re
        tenant_blocks = re.findall(r"Tenant\([^)]+\)", seeds, re.DOTALL)
        for block in tenant_blocks:
            assert "approved_at" not in block, (
                f"Tenant() should not use 'approved_at' (User-only column): {block}"
            )


class TestGeneratedFileSyntax:
    """Test that all generated Python files are syntactically valid."""

    CONFIGS = [
        {"database": "none"},
        {"database": "sqlite", "db_url": "sqlite:///app.db"},
        {
            "database": "sqlite",
            "db_url": "sqlite:///app.db",
            "include_auth": True,
            "tenant_mode": "single",
            "admin_email": "a@b.com",
        },
        {
            "database": "postgresql",
            "db_url": "postgresql://localhost/test",
            "include_auth": True,
            "tenant_mode": "single",
            "admin_email": "a@b.com",
        },
        {
            "database": "postgresql",
            "db_url": "postgresql://localhost/test",
            "include_auth": True,
            "tenant_mode": "multi",
            "admin_email": "a@b.com",
        },
    ]

    def test_all_python_files_valid_syntax(self, scaffold_project):
        for i, config in enumerate(self.CONFIGS):
            project = scaffold_project(config)

            # Find all .py files
            for py_file in project.rglob("*.py"):
                try:
                    # This raises SyntaxError if file is invalid
                    py_compile.compile(str(py_file), doraise=True)
                except SyntaxError as e:
                    pytest.fail(
                        f"Syntax error in {py_file} (config {i}: {config}): {e}"
                    )


class TestAdminScaffoldingSingleTenant:
    """Test admin scaffolding for single-tenant apps."""

    CONFIG = {
        "database": "postgresql",
        "db_url": "postgresql://localhost/testapp",
        "include_auth": True,
        "tenant_mode": "single",
        "admin_email": "admin@test.com",
    }

    def test_admin_routes_exist(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "routes/pages/admin.py").exists()

    def test_admin_service_exists(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "services/admin_service.py").exists()

    def test_admin_base_template_exists(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "templates/pages/admin/base.html").exists()

    def test_admin_users_template_exists(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "templates/pages/admin/users.html").exists()

    def test_admin_user_detail_template_exists(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "templates/pages/admin/user_detail.html").exists()

    def test_admin_tools_template_exists(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "templates/pages/admin/tools.html").exists()

    def test_admin_analytics_template_exists(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "templates/pages/admin/analytics.html").exists()

    def test_admin_logs_template_exists(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "templates/pages/admin/logs.html").exists()

    def test_admin_partials_exist(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "templates/partials/admin/users_table.html").exists()
        assert (project / "templates/partials/admin/user_actions.html").exists()
        # email_result.html only exists when include_email=True
        assert (project / "templates/partials/admin/logs_table.html").exists()

    def test_no_tenant_templates(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert not (project / "templates/pages/admin/tenants.html").exists()
        assert not (project / "templates/pages/admin/tenant_detail.html").exists()
        assert not (project / "templates/partials/admin/tenants_table.html").exists()
        assert not (project / "templates/partials/admin/tenant_actions.html").exists()

    def test_admin_routes_no_tenant_routes(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        admin_routes = (project / "routes/pages/admin.py").read_text()
        assert "tenants_page" not in admin_routes
        assert "tenant_detail_page" not in admin_routes
        assert "@platform_admin_required" not in admin_routes

    def test_admin_service_no_tenant_methods(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        admin_service = (project / "services/admin_service.py").read_text()
        assert "get_all_tenants" not in admin_service
        assert "get_tenant_detail" not in admin_service
        assert "create_tenant" not in admin_service

    def test_admin_base_no_tenants_nav(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        admin_base = (project / "templates/pages/admin/base.html").read_text()
        assert "Tenants" not in admin_base

    def test_auth_tests_exist(self, scaffold_project):
        """Auth test file is scaffolded for auth-enabled apps."""
        project = scaffold_project(self.CONFIG)
        assert (project / "tests/test_auth.py").exists()
        auth_tests = (project / "tests/test_auth.py").read_text()
        assert "TestPublicAccess" in auth_tests
        assert "TestProtectedRoutes" in auth_tests

    def test_admin_tests_exist(self, scaffold_project):
        """Admin test file is scaffolded for auth-enabled apps."""
        project = scaffold_project(self.CONFIG)
        assert (project / "tests/test_admin.py").exists()
        admin_tests = (project / "tests/test_admin.py").read_text()
        assert "TestAdminAccess" in admin_tests
        assert "TestHealthEndpoints" in admin_tests

    def test_conftest_has_csrf_client(self, scaffold_project):
        """Scaffolded conftest includes CsrfTestClient."""
        project = scaffold_project(self.CONFIG)
        conftest = (project / "tests/conftest.py").read_text()
        assert "CsrfTestClient" in conftest
        assert "csrf_client" in conftest


class TestAdminScaffoldingMultiTenant:
    """Test admin scaffolding for multi-tenant apps."""

    CONFIG = {
        "database": "postgresql",
        "db_url": "postgresql://localhost/testapp",
        "include_auth": True,
        "tenant_mode": "multi",
        "admin_email": "admin@test.com",
    }

    def test_admin_routes_exist(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "routes/pages/admin.py").exists()

    def test_admin_service_exists(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "services/admin_service.py").exists()

    def test_admin_base_template_exists(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "templates/pages/admin/base.html").exists()

    def test_tenant_templates_exist(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "templates/pages/admin/tenants.html").exists()
        assert (project / "templates/pages/admin/tenant_detail.html").exists()

    def test_tenant_partials_exist(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        assert (project / "templates/partials/admin/tenants_table.html").exists()
        assert (project / "templates/partials/admin/tenant_actions.html").exists()

    def test_admin_routes_has_tenant_routes(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        admin_routes = (project / "routes/pages/admin.py").read_text()
        assert "tenants_page" in admin_routes
        assert "tenant_detail_page" in admin_routes
        assert "@platform_admin_required" in admin_routes

    def test_admin_service_has_tenant_methods(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        admin_service = (project / "services/admin_service.py").read_text()
        assert "get_all_tenants" in admin_service
        assert "get_tenant_detail" in admin_service
        assert "create_tenant" in admin_service

    def test_admin_base_has_tenants_nav(self, scaffold_project):
        project = scaffold_project(self.CONFIG)
        admin_base = (project / "templates/pages/admin/base.html").read_text()
        assert "Tenants" in admin_base


class TestNoAuthNoAdmin:
    """Test that admin files are NOT created when auth is disabled."""

    def test_no_admin_routes_without_auth(self, scaffold_project):
        project = scaffold_project({"database": "postgresql", "db_url": "postgresql://localhost/test"})
        assert not (project / "routes/pages/admin.py").exists()

    def test_no_admin_service_without_auth(self, scaffold_project):
        project = scaffold_project({"database": "postgresql", "db_url": "postgresql://localhost/test"})
        assert not (project / "services/admin_service.py").exists()

    def test_no_admin_templates_without_auth(self, scaffold_project):
        project = scaffold_project({"database": "postgresql", "db_url": "postgresql://localhost/test"})
        assert not (project / "templates/pages/admin").exists()
        assert not (project / "templates/partials/admin").exists()

    def test_no_auth_tests_without_auth(self, scaffold_project):
        """Auth test files are NOT created when auth is disabled."""
        project = scaffold_project({"database": "postgresql", "db_url": "postgresql://localhost/test"})
        assert not (project / "tests/test_auth.py").exists()
        assert not (project / "tests/test_admin.py").exists()


class TestEmailScaffolding:
    """Test email (Resend) scaffolding when include_email=True."""

    CONFIG_WITH_EMAIL = {
        "database": "postgresql",
        "db_url": "postgresql://localhost/testapp",
        "include_auth": True,
        "tenant_mode": "single",
        "admin_email": "admin@test.com",
        "include_email": True,
    }

    CONFIG_WITHOUT_EMAIL = {
        "database": "postgresql",
        "db_url": "postgresql://localhost/testapp",
        "include_auth": True,
        "tenant_mode": "single",
        "admin_email": "admin@test.com",
        "include_email": False,
    }

    def test_email_service_exists_when_enabled(self, scaffold_project):
        """Email service file created when include_email=True."""
        project = scaffold_project(self.CONFIG_WITH_EMAIL)
        assert (project / "services/email_service.py").exists()

    def test_email_service_not_exists_when_disabled(self, scaffold_project):
        """Email service file NOT created when include_email=False."""
        project = scaffold_project(self.CONFIG_WITHOUT_EMAIL)
        assert not (project / "services/email_service.py").exists()

    def test_email_result_partial_exists_when_enabled(self, scaffold_project):
        """Email result partial created when include_email=True."""
        project = scaffold_project(self.CONFIG_WITH_EMAIL)
        assert (project / "templates/partials/admin/email_result.html").exists()

    def test_email_result_partial_not_exists_when_disabled(self, scaffold_project):
        """Email result partial NOT created when include_email=False."""
        project = scaffold_project(self.CONFIG_WITHOUT_EMAIL)
        assert not (project / "templates/partials/admin/email_result.html").exists()

    def test_admin_routes_has_email_routes_when_enabled(self, scaffold_project):
        """Admin routes include email endpoints when include_email=True."""
        project = scaffold_project(self.CONFIG_WITH_EMAIL)
        admin_routes = (project / "routes/pages/admin.py").read_text()
        assert "send_email" in admin_routes
        assert "search_users_dropdown" in admin_routes

    def test_admin_routes_no_email_routes_when_disabled(self, scaffold_project):
        """Admin routes do NOT include email endpoints when include_email=False."""
        project = scaffold_project(self.CONFIG_WITHOUT_EMAIL)
        admin_routes = (project / "routes/pages/admin.py").read_text()
        assert "send_email" not in admin_routes
        assert "search_users_dropdown" not in admin_routes

    def test_env_has_resend_config_when_enabled(self, scaffold_project):
        """Env file includes Resend config when include_email=True."""
        project = scaffold_project(self.CONFIG_WITH_EMAIL)
        env_content = (project / ".env").read_text()
        assert "RESEND_API_KEY" in env_content
        assert "RESEND_FROM_EMAIL" in env_content

    def test_env_no_resend_config_when_disabled(self, scaffold_project):
        """Env file does NOT include Resend config when include_email=False."""
        project = scaffold_project(self.CONFIG_WITHOUT_EMAIL)
        env_content = (project / ".env").read_text()
        assert "RESEND_API_KEY" not in env_content
        assert "RESEND_FROM_EMAIL" not in env_content

    def test_config_has_resend_settings_when_enabled(self, scaffold_project):
        """Config file includes Resend settings when include_email=True."""
        project = scaffold_project(self.CONFIG_WITH_EMAIL)
        config_content = (project / "config.py").read_text()
        assert "RESEND_API_KEY" in config_content
        assert "RESEND_FROM_EMAIL" in config_content

    def test_config_no_resend_settings_when_disabled(self, scaffold_project):
        """Config file does NOT include Resend settings when include_email=False."""
        project = scaffold_project(self.CONFIG_WITHOUT_EMAIL)
        config_content = (project / "config.py").read_text()
        assert "RESEND_API_KEY" not in config_content
        assert "RESEND_FROM_EMAIL" not in config_content

    def test_services_init_exports_email_service_when_enabled(self, scaffold_project):
        """Services __init__.py exports EmailService when include_email=True."""
        project = scaffold_project(self.CONFIG_WITH_EMAIL)
        services_init = (project / "services/__init__.py").read_text()
        assert "EmailService" in services_init

    def test_services_init_no_email_service_when_disabled(self, scaffold_project):
        """Services __init__.py does NOT export EmailService when include_email=False."""
        project = scaffold_project(self.CONFIG_WITHOUT_EMAIL)
        services_init = (project / "services/__init__.py").read_text()
        assert "EmailService" not in services_init
